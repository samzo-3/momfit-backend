"""오늘 기록 집계와 다음 집중 스텝 후보 고르기.

순수 함수만 둔다. DB, LLM, 파일을 읽지 않고 받은 값만으로 계산한다.
숫자와 판정은 모두 여기서 코드가 정한다. LLM은 문장만 쓴다.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date

from repositories.agent.team_activity_reader import (
    EVALUATION_STATUS_NOT_EVALUATED,
    EVALUATION_STATUSES,
    CorrectionCue,
    CriteriaVersionRow,
    ExerciseRecordRow,
    ExerciseRow,
    StepRecordRow,
    StepRow,
)
from services.agent import config
from services.user.pregnancy import calculate_pregnancy_week

KIND_EXERCISE = "exercise"
KIND_STEP = "step"


# --- 비교 가능 여부 ---------------------------------------------------------


@dataclass(frozen=True)
class ComparisonKey:
    """날짜가 다른 기록끼리 비교해도 되는지 판단할 때 쓰는 버전 묶음."""

    kind: str
    exercise_criteria_version_id: int | None = None
    measurement_profile_version: str | None = None
    criteria_version: str | None = None

    @classmethod
    def for_exercise(cls, exercise_criteria_version_id: int | None) -> "ComparisonKey":
        return cls(
            kind=KIND_EXERCISE,
            exercise_criteria_version_id=exercise_criteria_version_id,
        )

    @classmethod
    def for_step(
        cls, measurement_profile_version: str | None, criteria_version: str | None
    ) -> "ComparisonKey":
        return cls(
            kind=KIND_STEP,
            measurement_profile_version=measurement_profile_version,
            criteria_version=criteria_version,
        )


def is_comparable(a: ComparisonKey, b: ComparisonKey) -> bool:
    """두 기록을 두고 "나아졌다/줄었다"를 말해도 되는지 돌려준다.

    일반 운동은 운동 기준 버전이 같을 때만 비교할 수 있다.
    스텝은 관절 계산 공식 버전(measurement_profile_version)과 허용 범위 버전(criteria_version)이
    둘 다 있고 둘 다 같을 때만 비교할 수 있다. 계산 공식이 같아도 허용 범위가 바뀌면
    점수와 판정이 달라지기 때문이다.

    지금 리포트는 오늘 하루만 다루므로 쓰는 곳은 다음에 붙일 기억 꺼내기 도구다.
    """
    if a.kind != b.kind:
        return False
    if a.kind == KIND_EXERCISE:
        return (
            a.exercise_criteria_version_id is not None
            and a.exercise_criteria_version_id == b.exercise_criteria_version_id
        )
    versions = (
        a.measurement_profile_version,
        a.criteria_version,
        b.measurement_profile_version,
        b.criteria_version,
    )
    if any(version is None for version in versions):
        return False
    return (
        a.measurement_profile_version == b.measurement_profile_version
        and a.criteria_version == b.criteria_version
    )


# --- 집계 결과 --------------------------------------------------------------


@dataclass(frozen=True)
class SetProgress:
    """일반 운동 기록 하나의 완료 세트 / 목표 세트. 모르면 둘 다 또는 하나가 None이다."""

    completed_sets: int | None
    target_sets: int | None


@dataclass(frozen=True)
class ExerciseSummary:
    """일반 운동 하나의 오늘 요약.

    점수는 자세 점수가 아니라 '완료 세트 × 세트당 점수'다. (develop #9 기준:
    services/exercise_record_score.py) 그래서 기록마다 완료 세트 / 목표 세트를 함께 둔다.
    """

    exercise_id: int
    exercise_name: str
    target_reps: int | None
    record_count: int
    best_score: float | None
    first_score: float | None
    last_score: float | None
    # 기록 순서대로 하나씩
    sets: tuple[SetProgress, ...] = ()


@dataclass(frozen=True)
class StepSummary:
    """자세 배우기 스텝 하나의 오늘 요약."""

    exercise_step_id: int
    step_name: str
    attempt_count: int
    best_score: float | None
    last_score: float | None
    evaluation_counts: dict[str, int]
    feedback_code_counts: dict[str, int]
    # exercise_step_records.status가 PASS(80점 이상)인 시도 수. CV 판정(evaluation_counts)과는 따로 센다.
    pass_count: int = 0


@dataclass(frozen=True)
class FocusCandidate:
    """다음 집중 스텝 후보. LLM은 이 목록에서만 고를 수 있다."""

    exercise_step_id: int
    step_name: str
    step_description: str | None
    last_score: float | None
    # '무엇이 부족했나' (rules/feedback_codes.json의 상태 설명)
    issues: tuple[str, ...] = ()
    # '어떻게 고치나' (voice_cues.message). 다음 집중 스텝의 이유에만 쓴다.
    corrections: tuple[str, ...] = ()


@dataclass(frozen=True)
class CameraCheckStep:
    """측정 불가 시도만 있었던 스텝. 자세가 아니라 카메라 위치를 안내할 대상이다."""

    exercise_step_id: int
    step_name: str


@dataclass(frozen=True)
class ReportStats:
    """오늘 하루 숫자. 사실은 모두 이 안에 있고, LLM은 여기 있는 숫자만 쓴다."""

    exercise_count: int = 0
    record_count: int = 0
    completed_count: int = 0
    incomplete_count: int = 0
    total_minutes: int = 0
    exercises: tuple[ExerciseSummary, ...] = ()
    step_attempt_count: int = 0
    steps: tuple[StepSummary, ...] = ()
    pregnancy_week: int | None = None

    def has_records(self) -> bool:
        """오늘 기록이 있는지. 운동 기록과 스텝 기록이 둘 다 0일 때만 없다고 본다."""
        return self.record_count > 0 or self.step_attempt_count > 0


# --- 집계 -------------------------------------------------------------------


def _ordered_scores(attempts: list[StepRecordRow]) -> list[float]:
    return [a.step_score for a in attempts if a.step_score is not None]


def _sorted_attempts(attempts: list[StepRecordRow]) -> list[StepRecordRow]:
    return sorted(attempts, key=lambda item: (item.created_at, item.id))


def completed_sets_of(
    total_score: float | None, criteria: CriteriaVersionRow | None
) -> int | None:
    """일반 운동 점수를 완료 세트 수로 되돌린다. 되돌릴 수 없으면 None이다.

    팀은 완료 세트를 따로 저장하지 않고 total_score = min(100, 완료 세트 × 세트당 점수)만
    저장한다. (develop #9 기준: services/exercise_record_score.py) 100점 상한에 걸려 몇 세트인지
    하나로 정할 수 없거나, 세트당 점수로 나누어떨어지지 않으면 지어내지 않고 None으로 둔다.
    """
    if total_score is None or criteria is None or criteria.score_per_set <= 0:
        return None
    capped = criteria.target_sets * criteria.score_per_set > config.SCORE_MAX
    if capped and total_score >= config.SCORE_MAX:
        return None
    raw = total_score / criteria.score_per_set
    sets = round(raw)
    if abs(raw - sets) > 0.01 or not 0 <= sets <= criteria.target_sets:
        return None
    return sets


def group_step_attempts(
    step_records: list[StepRecordRow],
) -> dict[int, list[StepRecordRow]]:
    """스텝별 오늘 시도를 시도 순서대로 묶는다."""
    grouped: dict[int, list[StepRecordRow]] = {}
    for record in step_records:
        grouped.setdefault(record.exercise_step_id, []).append(record)
    return {
        step_id: _sorted_attempts(attempts) for step_id, attempts in grouped.items()
    }


def build_stats(
    *,
    records: list[ExerciseRecordRow],
    step_records: list[StepRecordRow],
    exercises: list[ExerciseRow],
    steps: list[StepRow],
    criteria: list[CriteriaVersionRow],
    due_date: date | None,
    today: date,
) -> ReportStats:
    """오늘 기록을 집계한다."""
    exercise_names = {row.id: row for row in exercises}
    step_rows = {row.id: row for row in steps}
    criteria_by_id = {row.id: row for row in criteria}

    by_exercise: dict[int, list[ExerciseRecordRow]] = {}
    for record in records:
        by_exercise.setdefault(record.exercise_id, []).append(record)

    exercise_summaries = []
    for exercise_id, items in sorted(by_exercise.items()):
        items = sorted(items, key=lambda item: (item.created_at, item.id))
        scores = [item.total_score for item in items if item.total_score is not None]
        row = exercise_names.get(exercise_id)
        sets = []
        for item in items:
            version = criteria_by_id.get(item.exercise_criteria_version_id)
            sets.append(
                SetProgress(
                    completed_sets=completed_sets_of(item.total_score, version),
                    target_sets=version.target_sets if version else None,
                )
            )
        exercise_summaries.append(
            ExerciseSummary(
                exercise_id=exercise_id,
                exercise_name=row.exercise_name if row else f"운동 {exercise_id}",
                target_reps=row.target_reps if row else None,
                record_count=len(items),
                best_score=max(scores) if scores else None,
                first_score=scores[0] if scores else None,
                last_score=scores[-1] if scores else None,
                sets=tuple(sets),
            )
        )

    # 완료 수는 status로만 센다. is_completed는 develop #9에서 status가 COMPLETED일 때만 참이라
    # 같은 뜻을 두 곳에서 읽지 않는다.
    completed_count = sum(
        1 for record in records if record.status == config.EXERCISE_STATUS_COMPLETED
    )
    total_seconds = 0.0
    for record in records:
        if record.started_at is None or record.ended_at is None:
            continue
        seconds = (record.ended_at - record.started_at).total_seconds()
        if seconds > 0:
            total_seconds += seconds

    step_summaries = []
    grouped = group_step_attempts(step_records)
    for step_id, attempts in grouped.items():
        scores = _ordered_scores(attempts)
        evaluation_counts = {status: 0 for status in EVALUATION_STATUSES}
        for attempt in attempts:
            # step_report가 없으면 판정 전으로 본다. (CV 명세의 측정 전 템플릿과 같은 상태)
            status = attempt.evaluation_status or EVALUATION_STATUS_NOT_EVALUATED
            if status not in evaluation_counts:
                evaluation_counts[status] = 0
            evaluation_counts[status] += 1
        code_counts = Counter(
            code for attempt in attempts for code in attempt.feedback_codes
        )
        row = step_rows.get(step_id)
        step_summaries.append(
            StepSummary(
                exercise_step_id=step_id,
                step_name=row.step_name if row else f"스텝 {step_id}",
                attempt_count=len(attempts),
                best_score=max(scores) if scores else None,
                last_score=scores[-1] if scores else None,
                evaluation_counts=evaluation_counts,
                feedback_code_counts=dict(code_counts),
                pass_count=sum(
                    1 for attempt in attempts if attempt.status == config.STEP_STATUS_PASS
                ),
            )
        )
    step_summaries.sort(
        key=lambda summary: (
            (
                step_rows[summary.exercise_step_id].step_order
                if summary.exercise_step_id in step_rows
                and step_rows[summary.exercise_step_id].step_order is not None
                else 10**6
            ),
            summary.exercise_step_id,
        )
    )

    return ReportStats(
        exercise_count=len(by_exercise),
        record_count=len(records),
        completed_count=completed_count,
        incomplete_count=len(records) - completed_count,
        total_minutes=int(total_seconds // 60),
        exercises=tuple(exercise_summaries),
        step_attempt_count=len(step_records),
        steps=tuple(step_summaries),
        pregnancy_week=calculate_pregnancy_week(due_date, today),
    )


def build_focus(
    *,
    step_records: list[StepRecordRow],
    steps: list[StepRow],
    issue_labels: dict[str, str],
    cues_by_step: dict[int, dict[str, CorrectionCue]],
) -> tuple[tuple[FocusCandidate, ...], tuple[CameraCheckStep, ...]]:
    """다음 집중 스텝 후보와 카메라 위치 확인 대상을 고른다.

    측정 불가였던 시도는 후보 계산에서 뺀다. 카메라가 몸을 못 잡아 점수가 낮은 것은
    자세 문제가 아니다. 그런 시도만 있는 스텝은 후보가 아니라 camera_check_steps로 넘긴다.
    점수가 있는 시도가 하나도 없으면 후보는 빈 목록이다. (오류가 아니라 정상이다)
    """
    step_rows = {row.id: row for row in steps}
    grouped = group_step_attempts(step_records)

    camera_checks: list[CameraCheckStep] = []
    ranked: list[tuple[float, int, int, FocusCandidate]] = []
    for step_id, attempts in grouped.items():
        row = step_rows.get(step_id)
        step_name = row.step_name if row else f"스텝 {step_id}"
        measurable = [a for a in attempts if not a.is_unavailable()]
        if not measurable:
            camera_checks.append(
                CameraCheckStep(exercise_step_id=step_id, step_name=step_name)
            )
            continue
        scores = _ordered_scores(measurable)
        if not scores:
            continue
        code_counts = Counter(
            code
            for attempt in measurable
            for code in attempt.feedback_codes
            if code in issue_labels
        )
        top_codes = [
            code
            for code, _ in code_counts.most_common(config.MAX_ISSUES_PER_CANDIDATE)
        ]
        cues = cues_by_step.get(step_id, {})
        candidate = FocusCandidate(
            exercise_step_id=step_id,
            step_name=step_name,
            step_description=row.step_description if row else None,
            last_score=scores[-1],
            issues=tuple(issue_labels[code] for code in top_codes),
            corrections=tuple(
                cues[code].message for code in top_codes if code in cues
            ),
        )
        # 점수가 같으면 스텝 순서로 정해 결과가 흔들리지 않게 한다.
        order = row.step_order if row and row.step_order is not None else 10**6
        ranked.append((scores[-1], order, step_id, candidate))

    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    candidates = tuple(item[3] for item in ranked[: config.MAX_FOCUS_CANDIDATES])
    camera_checks.sort(key=lambda item: item.exercise_step_id)
    return candidates, tuple(camera_checks)


def feedback_codes_in(step_records: list[StepRecordRow]) -> tuple[str, ...]:
    """오늘 나온 피드백 코드 목록. voice_cues를 찾을 때 쓴다."""
    seen: dict[str, None] = {}
    for record in step_records:
        for code in record.feedback_codes:
            seen.setdefault(code, None)
    return tuple(seen)
