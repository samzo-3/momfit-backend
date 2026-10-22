"""STEP 기억 쓰기. 스텝 하나의 '오늘 메모'를 다시 써서 저장한다.

메모는 하루 중 스텝 하나에 하나이고, 여러 시도를 흐름으로 요약한다. 사용자에게 바로 보여 주지
않고, DAILY 리포트를 쓸 때 참고한다. 무엇을 기억할지는 코드가 정하고, 문장만 LLM이 쓴다.
"""

import json
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from models.agent.agent_step_feedback import AgentStepFeedback
from repositories.agent import agent_feedback_repository
from repositories.agent.team_activity_reader import (
    StepRecordRow,
    StepRow,
    build_team_activity_reader,
    kst_day_of,
)
from services.agent import config, output_check
from services.agent.llm import LlmClient, LlmError, Usage, build_llm_client
from services.agent.report_stats import group_step_attempts

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StepMemoryOutcome:
    """따라잡기 결과. 서비스 내부에서만 쓴다."""

    memos: dict[int, str]
    refreshed_step_ids: tuple[int, ...]
    # memos에 든 메모의 agent_step_feedback 번호 (스텝 번호 → 메모 번호). 저장하지 않으면 비어 있다.
    memo_ids: dict[int, int] = field(default_factory=dict)
    llm_calls: int = 0
    latency_ms: int = 0
    usage: Usage = Usage()
    failures: tuple[str, ...] = ()


def _memo_by_step(
    memos: list[AgentStepFeedback], step_records: list[StepRecordRow]
) -> dict[int, AgentStepFeedback]:
    """메모를 스텝에 붙인다.

    agent_step_feedback에는 exercise_step_id가 없어서 exercise_step_records_id로 맞춘다.
    같은 스텝·날짜에 메모가 여럿이면 가장 최근 행만 쓴다. (memos는 최신 순으로 들어온다)
    """
    step_of_record = {record.id: record.exercise_step_id for record in step_records}
    latest: dict[int, AgentStepFeedback] = {}
    for memo in memos:
        step_id = step_of_record.get(memo.exercise_step_records_id)
        if step_id is not None:
            latest.setdefault(step_id, memo)
    return latest


def _needs_refresh(
    memo: AgentStepFeedback | None, attempts: list[StepRecordRow]
) -> bool:
    """메모가 낡았는지 본다. 셋 중 하나면 갱신한다.

    1. 메모가 없다
    2. 메모의 exercise_step_records_id가 실제 마지막 시도 번호와 다르다
    3. 메모의 created_at이 그 스텝 오늘 시도들 중 가장 늦은 modified_at보다 이르다
       (같은 행에 점수와 판정이 나중에 채워지면 번호는 그대로인데 메모만 낡는다)
    """
    if memo is None:
        return True
    if memo.exercise_step_records_id != attempts[-1].id:
        return True
    latest_touch = max(
        (attempt.modified_at or attempt.created_at) for attempt in attempts
    )
    # 둘 다 팀 규칙대로 naive UTC라 그대로 비교한다.
    return memo.created_at < latest_touch


def _code_memo(step_name: str, attempts: list[StepRecordRow]) -> str:
    """판정 결과가 하나도 없을 때 코드가 쓰는 메모. LLM을 부르지 않는다.

    '통과'는 스텝 기록 status(PASS, 80점 이상)를 센 것이고, '자세 판정 결과 없음'은 step_report에
    CV 판정과 피드백 코드가 없다는 뜻이다. 둘은 출처가 달라 함께 적힐 수 있다.
    """
    scores = [a.step_score for a in attempts if a.step_score is not None]
    passed = sum(1 for a in attempts if a.status == config.STEP_STATUS_PASS)
    parts = [f"{len(attempts)}번 시도 중 {passed}번 통과"]
    if len(scores) >= 2:
        parts.append(f"{scores[0]:g}점에서 {scores[-1]:g}점")
    elif scores:
        parts.append(f"{scores[0]:g}점")
    else:
        parts.append("점수 없음")
    parts.append("자세 판정 결과 없음")
    return f"{step_name}: " + ", ".join(parts)


def _llm_payload(
    step_id: int, step_name: str, attempts: list[StepRecordRow], labels: dict[str, str]
) -> dict:
    """LLM에 보내는 스텝 하나. 관절 수치는 애초에 읽지 않아 보낼 것이 없다."""
    return {
        "exercise_step_id": step_id,
        "step_name": step_name,
        "attempts": [
            {
                "order": order,
                "score": attempt.step_score,
                "evaluation_status": attempt.evaluation_status,
                "tracking_status": attempt.tracking_status,
                "issues": [
                    labels[code] for code in attempt.feedback_codes if code in labels
                ],
            }
            for order, attempt in enumerate(attempts, start=1)
        ],
    }


def refresh_step_memories(
    db: Session,
    *,
    user_id: int,
    step_records: list[StepRecordRow],
    steps: list[StepRow],
    memos: list[AgentStepFeedback],
    llm: LlmClient,
    deadline: float | None = None,
    save: bool = True,
) -> StepMemoryOutcome:
    """오늘 연습한 스텝들의 메모를 최신으로 맞춘다. 이미 최신이면 아무것도 하지 않는다.

    연결을 인자로 받는다. 리포트 요청 안에서 돌기 때문에 요청의 연결을 그대로 써도 된다.
    commit은 부르는 쪽에서 한다. save가 False면(가짜 기록) 메모를 만들어 돌려주기만 하고 저장하지 않는다.
    """
    grouped = group_step_attempts(step_records)
    if not grouped:
        return StepMemoryOutcome(memos={}, refreshed_step_ids=())

    step_names = {row.id: row.step_name for row in steps}
    labels = config.feedback_labels()
    existing = _memo_by_step(memos, step_records)

    current: dict[int, str] = {}
    memo_ids: dict[int, int] = {}
    stale: list[int] = []
    for step_id, attempts in grouped.items():
        if _needs_refresh(existing.get(step_id), attempts):
            stale.append(step_id)
        else:
            current[step_id] = existing[step_id].step_summary or ""
            memo_ids[step_id] = existing[step_id].id

    written: list[int] = []
    llm_steps: list[int] = []
    for step_id in stale:
        attempts = grouped[step_id]
        step_name = step_names.get(step_id, f"스텝 {step_id}")
        if any(attempt.has_evaluation() for attempt in attempts):
            llm_steps.append(step_id)
            continue
        memo = _code_memo(step_name, attempts)
        if save:
            memo_ids[step_id] = agent_feedback_repository.save_step_memo(
                db, user_id, attempts[-1].id, memo
            ).id
        current[step_id] = memo
        written.append(step_id)

    llm_calls = 0
    latency_ms = 0
    usage = Usage()
    failures: list[str] = []
    if llm_steps:
        timeout = config.llm_timeout_seconds()
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failures.append("제한 시간이 남지 않아 STEP 메모를 건너뜀")
                return StepMemoryOutcome(
                    memos=current,
                    refreshed_step_ids=tuple(written),
                    memo_ids=memo_ids,
                    failures=tuple(failures),
                )
            timeout = min(timeout, remaining)

        prompt = config.load_prompt("step_memory_system")
        payload = {
            "steps": [
                _llm_payload(
                    step_id,
                    step_names.get(step_id, f"스텝 {step_id}"),
                    grouped[step_id],
                    labels,
                )
                for step_id in llm_steps
            ]
        }
        # 갱신이 필요한 스텝은 한 번의 호출로 묶어 처리한다.
        started = time.monotonic()
        try:
            text, usage = llm.generate(
                prompt.text, json.dumps(payload, ensure_ascii=False), timeout
            )
            llm_calls = 1
        except LlmError as error:
            latency_ms = int((time.monotonic() - started) * 1000)
            logger.warning(
                "STEP 메모 LLM 호출 실패: user_id=%s, steps=%s, 이유=%s",
                user_id,
                llm_steps,
                error,
            )
            return StepMemoryOutcome(
                memos=current,
                refreshed_step_ids=tuple(written),
                memo_ids=memo_ids,
                llm_calls=1,
                latency_ms=latency_ms,
                failures=(str(error),),
            )
        latency_ms = int((time.monotonic() - started) * 1000)

        checked, memo_failures = output_check.check_step_memos(text, tuple(llm_steps))
        failures.extend(memo_failures)
        for step_id, memo in checked.items():
            if save:
                memo_ids[step_id] = agent_feedback_repository.save_step_memo(
                    db, user_id, grouped[step_id][-1].id, memo
                ).id
            current[step_id] = memo
            written.append(step_id)
        if memo_failures:
            # 통과한 것만 저장한다. 실패한 스텝은 다음 따라잡기 때 다시 시도한다.
            logger.warning(
                "STEP 메모 검사 실패: user_id=%s, 사유=%s", user_id, memo_failures
            )

    return StepMemoryOutcome(
        memos=current,
        refreshed_step_ids=tuple(written),
        memo_ids=memo_ids,
        llm_calls=llm_calls,
        latency_ms=latency_ms,
        usage=usage,
        failures=tuple(failures),
    )


def update_step_memory(step_record_id: int) -> None:
    """스텝 기록 하나가 저장된 뒤 부르는 함수. 그 스텝의 오늘 메모를 다시 쓴다.

    BE 사용 예시 — 스텝 기록을 저장한 직후에 번호만 넘긴다::

        from fastapi import BackgroundTasks
        from services.agent.step_memory import update_step_memory

        @router.post("/api/exercises/step-records", status_code=201)
        def create_step_record(
            body: StepRecordRequest,
            background_tasks: BackgroundTasks,
            user: User = Depends(get_onboarded_user),
            db: Session = Depends(get_db),
        ) -> StepRecordResponse:
            record = step_record_repository.add(db, ...)
            db.commit()
            background_tasks.add_task(update_step_memory, record.id)
            return to_step_record_response(record)

    객체 대신 번호만 받는 이유는, 새 연결로 다시 읽어야 그사이 채워진 점수와 판정까지 최신으로
    읽기 때문이다. DB 연결도 인자로 받지 않고 여기서 새로 연다. 이 함수는 BackgroundTasks로
    응답을 보낸 뒤에 도는데, 그때는 요청에 딸린 연결(Depends(get_db))이 이미 닫혀 있을 수 있다.

    이 함수가 예외를 내도 BE의 저장이 실패해서는 안 되므로 안에서 잡고 로그만 남긴다.
    조용히 실패하면 리포트의 따라잡기가 메워 주므로, 로그에 스텝 기록 번호를 꼭 남긴다.
    """
    try:
        from db.session import SessionLocal

        with SessionLocal() as db:
            reader = build_team_activity_reader(db)
            if not reader.real_records:
                # 가짜 기록 모드에서는 에이전트 테이블을 쓰지 않는다. 실제 스텝 기록 번호가 들어와도 넘어간다.
                logger.info(
                    "가짜 기록 모드라 스텝 메모를 쓰지 않았습니다. step_record_id=%s",
                    step_record_id,
                )
                return
            owner = reader.get_step_record(step_record_id)
            if owner is None:
                logger.warning(
                    "스텝 기록을 찾지 못해 메모를 쓰지 않았습니다. step_record_id=%s",
                    step_record_id,
                )
                return
            day = kst_day_of(owner.created_at)
            same_step = [
                record
                for record in reader.list_step_records(owner.user_id, day)
                if record.exercise_step_id == owner.exercise_step_id
            ]
            if not same_step:
                logger.warning(
                    "그날 스텝 시도를 찾지 못해 메모를 쓰지 않았습니다. step_record_id=%s",
                    step_record_id,
                )
                return
            refresh_step_memories(
                db,
                user_id=owner.user_id,
                step_records=same_step,
                steps=reader.get_steps([owner.exercise_step_id]),
                memos=agent_feedback_repository.list_step_memos(
                    db, owner.user_id, [record.id for record in same_step]
                ),
                llm=build_llm_client(),
            )
            db.commit()
    except Exception:
        logger.exception(
            "스텝 메모를 쓰지 못했습니다. step_record_id=%s", step_record_id
        )
