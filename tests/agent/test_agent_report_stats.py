"""오늘 기록 집계와 다음 집중 스텝 후보 검사. DB와 LLM을 쓰지 않는 순수 함수 검사다."""

from datetime import date, datetime, timedelta

from repositories.agent.team_activity_reader import (
    ExerciseRecordRow,
    ExerciseRow,
    StepRecordRow,
    StepRow,
)
from services.agent.report_stats import (
    ComparisonKey,
    build_focus,
    build_stats,
    is_comparable,
)

TODAY = date(2026, 10, 19)
BASE = datetime(2026, 10, 19, 1, 0)
PROFILE = "side_step_front_2d_v1"
LABELS = {
    "ARMS_NOT_OPEN_ENOUGH": "양팔 벌림 부족",
    "LEFT_STEP_TOO_SHORT": "왼쪽 스텝 이동량 부족",
    "TRACKING_UNAVAILABLE": "관절 인식 불가",
}


def _record(
    rid: int,
    *,
    score: float | None = 70.0,
    status: str = "완료",
    minutes: int | None = 10,
    version: int | None = 1,
) -> ExerciseRecordRow:
    started = BASE + timedelta(minutes=rid)
    return ExerciseRecordRow(
        id=rid,
        exercise_id=1,
        exercise_criteria_version_id=version,
        total_score=score,
        status=status,
        started_at=started if minutes is not None else None,
        ended_at=started + timedelta(minutes=minutes) if minutes is not None else None,
        created_at=started,
    )


def _attempt(
    rid: int,
    step_id: int,
    *,
    score: float | None = 60.0,
    status: str | None = "FAIL",
    codes: tuple[str, ...] = (),
    tracking: str | None = "VALID",
    criteria_version: str | None = "0.1.0",
) -> StepRecordRow:
    moment = BASE + timedelta(minutes=rid)
    return StepRecordRow(
        id=rid,
        exercise_id=1,
        exercise_step_id=step_id,
        status="완료",
        step_score=score,
        created_at=moment,
        modified_at=moment,
        evaluation_status=status,
        feedback_codes=codes,
        tracking_status=tracking,
        measurement_profile_version=PROFILE,
        criteria_version=criteria_version,
    )


def _step_row(step_id: int, order: int, name: str) -> StepRow:
    return StepRow(
        id=step_id,
        exercise_id=1,
        step_order=order,
        step_name=name,
        step_description=f"{name} 설명",
    )


STEPS = [_step_row(11, 1, "준비 자세"), _step_row(12, 2, "오른쪽 스텝"), _step_row(13, 3, "왼쪽 스텝")]
EXERCISES = [ExerciseRow(id=1, exercise_name="사이드 스텝", target_reps=10)]


def _stats(records=(), attempts=(), due_date=date(2026, 12, 1)):
    return build_stats(
        records=list(records),
        step_records=list(attempts),
        exercises=EXERCISES,
        steps=STEPS,
        due_date=due_date,
        today=TODAY,
    )


def _focus(attempts, cues_by_step=None):
    return build_focus(
        step_records=list(attempts),
        steps=STEPS,
        issue_labels=LABELS,
        cues_by_step=cues_by_step or {},
    )


def test_기록이_없으면_기록_없음으로_본다() -> None:
    stats = _stats()

    assert stats.has_records() is False
    assert stats.record_count == 0
    assert stats.step_attempt_count == 0
    assert stats.exercises == ()
    assert stats.steps == ()


def test_스텝_기록만_있고_운동_기록이_0건이면_기록_있음으로_본다() -> None:
    # 스텝 기록에는 운동 기록과 이어지는 컬럼이 없어서, 자세 배우기만 한 날은 운동 기록이 0일 수 있다.
    stats = _stats(attempts=[_attempt(1, 12)])

    assert stats.has_records() is True
    assert stats.record_count == 0
    assert stats.step_attempt_count == 1


def test_시간이_빈_기록은_운동_시간에서_빠진다() -> None:
    stats = _stats(records=[_record(1, minutes=20), _record(2, minutes=None)])

    assert stats.record_count == 2
    assert stats.total_minutes == 20


def test_완료_수는_status로만_센다() -> None:
    # is_completed는 '이 기록을 끝까지 했다'인지 '이 운동을 수료했다'인지 알 수 없어 읽지 않는다.
    stats = _stats(records=[_record(1, status="완료"), _record(2, status="진행중")])

    assert stats.completed_count == 1
    assert stats.incomplete_count == 1
    assert not hasattr(_record(1), "is_completed")


def test_운동별로_최고_처음_마지막_점수를_모은다() -> None:
    stats = _stats(
        records=[_record(1, score=60.0), _record(2, score=80.0), _record(3, score=70.0)]
    )

    summary = stats.exercises[0]
    assert (summary.best_score, summary.first_score, summary.last_score) == (80.0, 60.0, 70.0)
    assert summary.record_count == 3


def test_판정_상태와_피드백_코드를_집계한다() -> None:
    stats = _stats(
        attempts=[
            _attempt(1, 12, codes=("ARMS_NOT_OPEN_ENOUGH",), status="FAIL"),
            _attempt(2, 12, codes=("ARMS_NOT_OPEN_ENOUGH",), status="FAIL"),
            _attempt(3, 12, codes=(), status="PASS"),
            _attempt(4, 12, codes=(), status=None),
        ]
    )

    step = stats.steps[0]
    assert step.attempt_count == 4
    assert step.evaluation_counts == {
        "PASS": 1,
        "FAIL": 2,
        "UNAVAILABLE": 0,
        # step_report가 없으면 판정 전으로 본다.
        "NOT_EVALUATED": 1,
    }
    assert step.feedback_code_counts == {"ARMS_NOT_OPEN_ENOUGH": 2}


def test_due_date가_없으면_임신_주차는_비어_있다() -> None:
    assert _stats(records=[_record(1)], due_date=None).pregnancy_week is None


def test_마지막_점수가_낮은_스텝을_최대_두_개_고른다() -> None:
    attempts = [
        _attempt(1, 11, score=90.0, status="PASS"),
        _attempt(2, 12, score=50.0, codes=("ARMS_NOT_OPEN_ENOUGH",)),
        _attempt(3, 13, score=70.0, codes=("LEFT_STEP_TOO_SHORT",)),
    ]

    candidates, camera_checks = _focus(attempts)

    assert [item.exercise_step_id for item in candidates] == [12, 13]
    assert camera_checks == ()


def test_점수가_같은_후보는_스텝_순서로_정한다() -> None:
    attempts = [
        _attempt(1, 13, score=60.0, codes=("LEFT_STEP_TOO_SHORT",)),
        _attempt(2, 12, score=60.0, codes=("ARMS_NOT_OPEN_ENOUGH",)),
        _attempt(3, 11, score=60.0, status="PASS"),
    ]

    candidates, _ = _focus(attempts)

    assert [item.exercise_step_id for item in candidates] == [11, 12]


def test_측정_불가_시도만_있는_스텝은_후보가_아니라_카메라_확인_대상이다() -> None:
    attempts = [
        _attempt(
            1,
            13,
            score=10.0,
            status="UNAVAILABLE",
            codes=("TRACKING_UNAVAILABLE",),
            tracking="UNAVAILABLE",
        ),
        _attempt(2, 12, score=80.0, codes=("ARMS_NOT_OPEN_ENOUGH",)),
    ]

    candidates, camera_checks = _focus(attempts)

    assert [item.exercise_step_id for item in candidates] == [12]
    assert [item.exercise_step_id for item in camera_checks] == [13]


def test_점수가_전부_없으면_후보는_빈_목록이다() -> None:
    attempts = [
        _attempt(1, 12, score=None, status="NOT_EVALUATED"),
        _attempt(2, 13, score=None, status="NOT_EVALUATED"),
    ]

    candidates, camera_checks = _focus(attempts)

    assert candidates == ()
    assert camera_checks == ()


def test_후보에는_상태_설명과_교정_방법이_함께_붙는다() -> None:
    from repositories.agent.team_activity_reader import CorrectionCue

    attempts = [_attempt(1, 12, score=50.0, codes=("ARMS_NOT_OPEN_ENOUGH",))]
    cues = {
        12: {
            "ARMS_NOT_OPEN_ENOUGH": CorrectionCue(
                event_code="ARMS_NOT_OPEN_ENOUGH", message="팔을 더 벌려 주세요."
            )
        }
    }

    candidates, _ = _focus(attempts, cues)

    assert candidates[0].issues == ("양팔 벌림 부족",)
    assert candidates[0].corrections == ("팔을 더 벌려 주세요.",)


def test_비교_가능_여부는_운동_기준_버전이_같을_때만_참이다() -> None:
    assert is_comparable(ComparisonKey.for_exercise(1), ComparisonKey.for_exercise(1)) is True
    assert is_comparable(ComparisonKey.for_exercise(1), ComparisonKey.for_exercise(2)) is False
    assert (
        is_comparable(ComparisonKey.for_exercise(None), ComparisonKey.for_exercise(None))
        is False
    )


def test_스텝은_두_버전이_모두_있고_같을_때만_비교할_수_있다() -> None:
    both = ComparisonKey.for_step(PROFILE, "0.1.0")

    assert is_comparable(both, ComparisonKey.for_step(PROFILE, "0.1.0")) is True
    # 허용 범위 버전이 없으면 비교하지 않는다. (지금 CV 명세의 사용자 JSON에는 이 값이 없다)
    assert is_comparable(
        ComparisonKey.for_step(PROFILE, None), ComparisonKey.for_step(PROFILE, None)
    ) is False
    # 계산 공식이 같아도 허용 범위가 바뀌면 점수와 판정이 달라진다.
    assert is_comparable(both, ComparisonKey.for_step(PROFILE, "0.2.0")) is False
    assert is_comparable(both, ComparisonKey.for_step("other_v2", "0.1.0")) is False


def test_운동_기준과_스텝_기준은_서로_비교하지_않는다() -> None:
    assert (
        is_comparable(ComparisonKey.for_exercise(1), ComparisonKey.for_step(PROFILE, "0.1.0"))
        is False
    )
