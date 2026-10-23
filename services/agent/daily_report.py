"""오늘의 운동 리포트 (DAILY 기억 꺼내기).

사실(날짜별 횟수와 점수)은 항상 팀 테이블에서 코드가 계산한다. STEP 메모는 빠지거나 늦을 수
있는 요약본이라, 에이전트가 무엇을 봤고 뭐라고 했는지만 덧붙인다.

처리 순서는 build_daily_report 안의 번호 주석과 같다.
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from core.clock import today_kst, utc_now
from models.agent.agent_daily_feedback import TODAY_SUMMARY_MAX_LENGTH
from models.user import User
from repositories.agent import agent_feedback_repository
from repositories.agent.team_activity_reader import (
    ExerciseRecordRow,
    StepRecordRow,
    TeamActivityReader,
    report_date_of,
)
from services.agent import config, output_check, report_stats
from services.agent.llm import LlmClient, LlmError, LlmRateLimitedError, LlmTimeoutError
from services.agent.output_check import (
    REASON_LLM_ERROR,
    REASON_NO_CONSENT,
    REASON_NO_RECORDS,
    REASON_OUTPUT_CHECK,
    REASON_PAST_DAY,
    REASON_RATE_LIMIT,
    REASON_TIMEOUT,
    NextFocus,
)
from services.agent.report_stats import ReportStats
from services.agent.step_memory import refresh_step_memories

logger = logging.getLogger(__name__)

EMPTY_SUMMARY = "오늘은 아직 운동 기록이 없어요. 기록이 생기면 리포트를 만들어 드릴게요."
PAST_EMPTY_SUMMARY = "이날은 운동 기록이 없어요."
# 저장하는 today_summary에서 한마디 뒤에 붙는 다음 집중 스텝 줄의 모양
FOCUS_LINE = "\n다음 집중 스텝: "
FOCUS_REASON_SEPARATOR = " — "


@dataclass(frozen=True)
class DailyReportResult:
    """서비스 내부 결과. API 라우터는 이 중 응답 필드만 내보낸다.

    fallback_reason, llm_calls, saved, 토큰 수는 응답에 넣지 않는다.
    (scripts/agent/run_scenarios.py와 로그가 쓴다)
    """

    date: date
    stats: ReportStats
    safety_notice: str
    summary: str
    next_focus: NextFocus | None = None
    prompt_version: str | None = None
    provider: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    fallback_reason: str | None = None
    llm_calls: int = 0
    saved: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None


def _count_sentence(stats: ReportStats, when: str) -> str:
    """stats 숫자만으로 쓰는 기록 문장. when은 '오늘' 또는 '이날'이다."""
    parts = []
    if stats.record_count:
        parts.append(f"운동 {stats.record_count}회")
    if stats.step_attempt_count:
        parts.append(f"자세 배우기 {stats.step_attempt_count}번")
    text = f"{when} {', '.join(parts)} 하신 기록이 있어요." if parts else f"{when} 기록이 있어요."
    if stats.total_minutes:
        text += f" 운동 시간은 모두 {stats.total_minutes}분이에요."
    return text


def _fallback_summary(stats: ReportStats) -> str:
    """stats 숫자만으로 코드가 쓰는 대체 문장. 원인도 판정도 말하지 않는다."""
    return _count_sentence(stats, "오늘") + " 자세한 안내는 잠시 후 다시 확인해 주세요."


def _past_summary(stats: ReportStats) -> str:
    """지난 날짜에 쓸 수 있는 리포트가 없을 때의 문장. 다시 만들지 않으니 '잠시 후'라고 하지 않는다."""
    return _count_sentence(stats, "이날")


def _stats_for_llm(stats: ReportStats) -> dict:
    """LLM에 보내는 숫자. 닉네임·이메일과 사용자·기록·운동 번호는 넣지 않는다."""
    return {
        "exercise_count": stats.exercise_count,
        "record_count": stats.record_count,
        "completed_count": stats.completed_count,
        "incomplete_count": stats.incomplete_count,
        "total_minutes": stats.total_minutes,
        "step_attempt_count": stats.step_attempt_count,
        "exercises": [
            {
                "exercise_name": item.exercise_name,
                "record_count": item.record_count,
                "best_score": item.best_score,
                "first_score": item.first_score,
                "last_score": item.last_score,
                "sets": [
                    {
                        "completed_sets": progress.completed_sets,
                        "target_sets": progress.target_sets,
                    }
                    for progress in item.sets
                ],
            }
            for item in stats.exercises
        ],
        "steps": [
            {
                "step_name": item.step_name,
                "attempt_count": item.attempt_count,
                "best_score": item.best_score,
                "last_score": item.last_score,
                "pass_count": item.pass_count,
                "evaluation_counts": item.evaluation_counts,
            }
            for item in stats.steps
        ],
    }


def _daily_payload(
    *,
    stats: ReportStats,
    candidates: tuple[report_stats.FocusCandidate, ...],
    camera_checks: tuple[report_stats.CameraCheckStep, ...],
    step_memos: dict[int, str],
    feedback_code_counts: dict[str, int],
) -> dict:
    """DAILY 호출 입력.

    exercise_step_id는 LLM이 후보 중 하나를 고를 수 있어야 해서 보내는 유일한 번호다.
    사용자·기록·운동 번호와 닉네임·이메일은 보내지 않는다. 임신 주차는 보내도 된다.
    관절 수치(measured_metrics, metric_results)는 읽지도 않으므로 보낼 것이 없다.
    """
    return {
        "pregnancy_week": stats.pregnancy_week,
        "stats": _stats_for_llm(stats),
        "focus_candidates": [
            {
                "exercise_step_id": item.exercise_step_id,
                "step_name": item.step_name,
                "step_description": item.step_description,
                "last_score": item.last_score,
                "issues": list(item.issues),
                "corrections": list(item.corrections),
            }
            for item in candidates
        ],
        "camera_check_steps": [
            {"exercise_step_id": item.exercise_step_id, "step_name": item.step_name}
            for item in camera_checks
        ],
        "step_memos": [
            {"exercise_step_id": step_id, "memo": memo}
            for step_id, memo in sorted(step_memos.items())
        ],
        "feedback_codes": feedback_code_counts,
        # 날짜가 다른 기록과 비교해도 되는지는 코드가 정한다. 오늘 하루만 다루는 지금은 비교하지 않는다.
        "comparable": None,
        # TODO: get_recent_days 도구 붙일 자리 (기억 꺼내기)
    }


def _today_summary_row(
    summary: str, next_focus: NextFocus | None, step_name: str | None
) -> str:
    """저장할 today_summary. 화면에 보여 준 한마디와 다음 집중 스텝 한 줄을 합친다."""
    if next_focus is None:
        return summary
    name = step_name or f"스텝 {next_focus.step_id}"
    return f"{summary}{FOCUS_LINE}{name}{FOCUS_REASON_SEPARATOR}{next_focus.reason}"


def _split_saved_row(text: str, stats: ReportStats) -> tuple[str, NextFocus | None]:
    """저장한 today_summary를 한마디와 다음 집중 스텝으로 되돌린다. _today_summary_row의 반대다.

    저장할 때 스텝 번호 대신 이름을 적었으므로, 그날 스텝 중 이름이 같은 것의 번호를 찾는다.
    못 찾으면 한마디만 돌려준다.
    """
    summary, found, focus_line = text.rpartition(FOCUS_LINE)
    if not found:
        return text, None
    name, _, reason = focus_line.partition(FOCUS_REASON_SEPARATOR)
    step_ids = {step.step_name: step.exercise_step_id for step in stats.steps}
    if name not in step_ids or not reason:
        return summary, None
    return summary, NextFocus(step_id=step_ids[name], reason=reason)


def _last_touch(
    records: list[ExerciseRecordRow], step_records: list[StepRecordRow]
) -> datetime:
    """그날 기록이 마지막으로 바뀐 시각. 기록이 하나 이상 있을 때만 부른다."""
    return max(
        row.modified_at or row.created_at for row in [*records, *step_records]
    )


def _saved_report(
    db: Session,
    user_id: int,
    day: date,
    stats: ReportStats,
    notice: str,
    last_touch: datetime,
) -> DailyReportResult | None:
    """그날 마지막으로 저장한 리포트를 그대로 쓸 수 있으면 돌려준다. 쓸 수 없으면 None이다.

    그대로 쓰려면 둘 다 맞아야 한다.
    1. 그날 기록이 마지막으로 바뀐 뒤에 숫자를 셌다 (아니면 한마디와 다시 센 숫자가 어긋난다)
    2. 대체 문장이 아니다 (대체 문장은 '잠시 후 다시 확인해 주세요'라고 했다. 오늘은 다시 만들어야
       그 말이 맞고, 다시 만들지 않는 지난 날짜에서는 그 말을 지킬 수 없다)
    """
    row = agent_feedback_repository.latest_daily_report(
        db, user_id, report_date_of(day)
    )
    if (
        row is None
        or not row.today_summary
        or row.created_at is None
        # 리포트 시각은 숫자를 센 시각이다. 둘 다 팀 규칙대로 naive UTC라 그대로 비교한다.
        or row.created_at < last_touch
        or row.today_summary == _fallback_summary(stats)
    ):
        return None
    summary, next_focus = _split_saved_row(row.today_summary, stats)
    return DailyReportResult(
        date=day,
        stats=stats,
        safety_notice=notice,
        summary=summary,
        next_focus=next_focus,
    )


def build_daily_report(
    db: Session,
    user: User,
    day: date,
    reader: TeamActivityReader,
    llm: LlmClient,
    today: date | None = None,
) -> DailyReportResult:
    """하루 리포트를 만든다. 실패해도 예외를 내지 않고 대체 문장으로 돌려준다.

    LLM은 오늘 리포트에만, 그것도 그날 마지막 리포트 뒤에 기록이 바뀌었을 때만 부른다.
    지난 날짜는 다시 만들지 않고 그날 만든 리포트를 그대로 돌려준다.
    가짜 기록(reader.real_records가 False)이면 에이전트 테이블을 읽지도 쓰지도 않는다.
    저장한 리포트가 없으니 날짜와 상관없이 그날을 오늘로 보고 매번 새로 만든다.
    """
    deadline = time.monotonic() + config.report_timeout_seconds()
    save = reader.real_records
    past = save and day < (today or today_kst())
    notice = config.safety_notice()
    report_date = report_date_of(day)

    # 1. 오늘 기록 집계
    #    저장하는 리포트의 시각은 숫자를 세기 직전 시각이다. LLM을 기다리는 사이 바뀐 기록은
    #    이 시각보다 늦게 바뀌므로, 다음 요청에서 그 리포트가 낡았다고 알 수 있다.
    read_at = utc_now()
    records = reader.list_exercise_records(user.id, day)
    step_records = reader.list_step_records(user.id, day)
    steps = reader.get_steps(sorted({r.exercise_step_id for r in step_records}))
    exercises = reader.get_exercises(sorted({r.exercise_id for r in records}))
    stats = report_stats.build_stats(
        records=records,
        step_records=step_records,
        exercises=exercises,
        steps=steps,
        due_date=user.due_date,
        today=day,
    )

    # 2. 기록이 0건이면 LLM 없이 stats와 빈 안내 문구를 돌려주고 저장하지 않는다.
    #    (스텝 기록에는 운동 기록과 이어지는 컬럼이 없어서, 자세 배우기만 한 날은 운동 기록이 0일 수 있다)
    if not stats.has_records():
        return DailyReportResult(
            date=day,
            stats=stats,
            safety_notice=notice,
            summary=PAST_EMPTY_SUMMARY if past else EMPTY_SUMMARY,
            fallback_reason=REASON_NO_RECORDS,
        )

    # 3. 그날 저장한 리포트가 아직 맞으면 LLM 없이 그대로 돌려주고 새로 저장하지 않는다.
    #    지난 날짜는 다시 만들지 않으니, 쓸 수 없으면 숫자만으로 쓴 문장을 돌려준다.
    if save:
        saved = _saved_report(
            db, user.id, day, stats, notice, _last_touch(records, step_records)
        )
        if saved is not None:
            return saved
        if past:
            return DailyReportResult(
                date=day,
                stats=stats,
                safety_notice=notice,
                summary=_past_summary(stats),
                fallback_reason=REASON_PAST_DAY,
            )

    labels = config.feedback_labels()
    grouped = report_stats.group_step_attempts(step_records)
    cues_by_step: dict[int, dict] = {}
    for step_id, attempts in grouped.items():
        codes = sorted({code for a in attempts for code in a.feedback_codes})
        if codes:
            cues_by_step[step_id] = reader.get_correction_cues(
                codes, step_id, attempts[0].exercise_id
            )
    candidates, camera_checks = report_stats.build_focus(
        step_records=step_records,
        steps=steps,
        issue_labels=labels,
        cues_by_step=cues_by_step,
    )
    candidate_ids = tuple(item.exercise_step_id for item in candidates)
    step_names = {item.exercise_step_id: item.step_name for item in candidates}

    # 4. 민감 건강정보 동의가 없으면 LLM 없이 대체 문장을 쓴다.
    #    (가입·온보딩에서 필수 동의라 보통은 걸리지 않는 방어 장치다)
    if user.health_data_agreed_at is None:
        summary = _fallback_summary(stats)
        logger.info(
            "건강정보 동의가 없어 대체 문장을 썼습니다. user_id=%s, 이유=%s",
            user.id,
            REASON_NO_CONSENT,
        )
        if save:
            agent_feedback_repository.save_daily_report(
                db, user.id, report_date, summary, created_at=read_at
            )
            db.commit()
        return DailyReportResult(
            date=day,
            stats=stats,
            safety_notice=notice,
            summary=summary,
            fallback_reason=REASON_NO_CONSENT,
            saved=save,
        )

    # 5. STEP 따라잡기: 메모가 낡은 스텝만 다시 쓴다. 이미 최신이면 LLM을 부르지 않는다.
    outcome = refresh_step_memories(
        db,
        user_id=user.id,
        step_records=step_records,
        steps=steps,
        memos=(
            agent_feedback_repository.list_step_memos(
                db, user.id, [record.id for record in step_records]
            )
            if save
            else []
        ),
        llm=llm,
        deadline=deadline,
        save=save,
    )
    llm_calls = outcome.llm_calls
    latency_ms = outcome.latency_ms
    input_tokens = outcome.usage.input_tokens
    output_tokens = outcome.usage.output_tokens
    prompt_version = (
        config.load_prompt("step_memory_system").version if outcome.llm_calls else None
    )

    # 6. DAILY 기억 꺼내기
    feedback_code_counts: dict[str, int] = {}
    for summary_row in stats.steps:
        for code, count in summary_row.feedback_code_counts.items():
            feedback_code_counts[code] = feedback_code_counts.get(code, 0) + count
    daily_prompt = config.load_prompt("daily_system")
    payload = _daily_payload(
        stats=stats,
        candidates=candidates,
        camera_checks=camera_checks,
        step_memos=outcome.memos,
        feedback_code_counts=feedback_code_counts,
    )

    summary: str | None = None
    next_focus: NextFocus | None = None
    reason: str | None = None
    detail: str | None = None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        reason = REASON_TIMEOUT
        detail = "리포트 제한 시간이 지나 DAILY 호출을 건너뜀"
    else:
        prompt_version = daily_prompt.version
        started = time.monotonic()
        try:
            text, usage = llm.generate(
                daily_prompt.text,
                json.dumps(payload, ensure_ascii=False),
                min(config.llm_timeout_seconds(), remaining),
            )
            llm_calls += 1
            latency_ms += int((time.monotonic() - started) * 1000)
            input_tokens = (input_tokens or 0) + (usage.input_tokens or 0)
            output_tokens = (output_tokens or 0) + (usage.output_tokens or 0)
        except LlmError as error:
            llm_calls += 1
            latency_ms += int((time.monotonic() - started) * 1000)
            if isinstance(error, LlmTimeoutError):
                reason = REASON_TIMEOUT
            elif isinstance(error, LlmRateLimitedError):
                reason = REASON_RATE_LIMIT
            else:
                reason = REASON_LLM_ERROR
            detail = str(error)
        else:
            # 7. 출력 검사
            checked = output_check.check_daily(text, candidate_ids)
            if isinstance(checked, output_check.CheckFailure):
                reason = REASON_OUTPUT_CHECK
                detail = checked.detail
            else:
                focus = checked.next_focus
                row = _today_summary_row(
                    checked.summary,
                    focus,
                    step_names.get(focus.step_id) if focus else None,
                )
                if len(row) > TODAY_SUMMARY_MAX_LENGTH:
                    # 저장 칸(팀 최종 ERD의 today_summary VARCHAR(255))에 들어가지 않으면 대체 문장을 쓴다.
                    # 저장하지 않는 가짜 기록 모드에서도 똑같이 걸러서, 두 모드가 같은 문장을 보여 준다.
                    reason = REASON_OUTPUT_CHECK
                    detail = f"저장할 문장이 {TODAY_SUMMARY_MAX_LENGTH}자를 넘음 ({len(row)}자)"
                else:
                    summary = checked.summary
                    next_focus = focus

    if summary is None:
        summary = _fallback_summary(stats)
        next_focus = None
        # 대체한 이유는 로그로만 남긴다. API 응답에는 넣지 않는다.
        logger.warning(
            "대체 문장을 썼습니다. user_id=%s, date=%s, 이유=%s, 자세히=%s",
            user.id,
            day,
            reason,
            detail,
        )

    # 8. 화면에 보여 준 한마디와 다음 집중 스텝 한 줄을 합쳐 agent_daily_feedback에 저장한다.
    #    LLM이 쓴 한마디면 참고한 스텝 메모를 daily_feedback_sources에 잇는다.
    #    대체 문장은 숫자만으로 썼으니 잇지 않는다.
    if save:
        focus_step_name = step_names.get(next_focus.step_id) if next_focus else None
        agent_feedback_repository.save_daily_report(
            db,
            user.id,
            report_date,
            _today_summary_row(summary, next_focus, focus_step_name),
            created_at=read_at,
            step_feedback_ids=outcome.memo_ids.values() if reason is None else (),
        )
        db.commit()

    return DailyReportResult(
        date=day,
        stats=stats,
        safety_notice=notice,
        summary=summary,
        next_focus=next_focus,
        prompt_version=prompt_version,
        provider=llm.name if llm_calls else None,
        model=llm.model if llm_calls else None,
        latency_ms=latency_ms if llm_calls else None,
        fallback_reason=reason,
        llm_calls=llm_calls,
        saved=save,
        input_tokens=input_tokens if llm_calls else None,
        output_tokens=output_tokens if llm_calls else None,
    )
