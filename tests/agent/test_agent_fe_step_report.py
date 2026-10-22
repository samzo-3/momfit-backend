"""FE 자세 배우기 화면이 실제로 보내는 step_report를 에이전트가 읽는지 검사한다.

FE 모양은 momfit-frontend develop #13의 src/features/pose/api/saveSideKickStep.ts를 그대로 옮겼다.
DB와 LLM을 쓰지 않는다.
"""

from datetime import date

from repositories.agent.team_activity_reader import StepRow, _build_step_record
from services.agent import config
from services.agent.output_check import find_banned_term, find_health_term
from services.agent.report_stats import build_focus, build_stats

# FE 채점 코드(side-kick-study-score.ts)가 eventCode로 낼 수 있는 코드 전부.
# 복귀 코드 5개는 STEP 3·5가 준비 자세 기준으로 채점되어 지금은 나오지 않는다.
SIDE_KICK_CODES = (
    "READY_POSITION_ADJUST",
    "LEFT_LEG_HEIGHT_ADJUST",
    "RIGHT_LEG_HEIGHT_ADJUST",
    "LEFT_LEG_POSITION_ADJUST",
    "RIGHT_LEG_POSITION_ADJUST",
    "LEFT_KNEE_POSITION_ADJUST",
    "RIGHT_KNEE_POSITION_ADJUST",
    "POSTURE_ADJUST",
    "LEFT_LEG_RETURN_ADJUST",
    "RIGHT_LEG_RETURN_ADJUST",
    "TORSO_RETURN_ADJUST",
    "ELBOW_RETURN_ADJUST",
    "RETURN_POSTURE_ADJUST",
)
STEPS = [
    StepRow(id=12, exercise_id=1, step_order=2, step_name="왼쪽 다리 들기", step_description=None),
]


def _fe_row(rid: int, status: str, score: float | None, codes: list[str]) -> dict:
    """saveSideKickStep.ts가 보내는 본문을 저장된 행 모양으로 만든다."""
    return {
        "id": rid,
        "exercise_id": 1,
        "exercise_step_id": 12,
        "status": status,
        "step_score": score,
        "step_report": {
            "schema_version": 1,
            "measurement_profile_version": "side_step_front_2d_v1",
            "tracking_info": {
                "camera_view": "FRONT",
                "coordinate_system": "IMAGE_NORMALIZED_2D",
                "tracking_status": "NOT_EVALUATED" if status == "NOT_EVALUATED" else "TRACKING_OK",
            },
            "evaluation_result": {
                "status": status,
                "feedback_count": len(codes),
                "feedback_codes": codes,
            },
        },
        "created_at": f"2026-10-19T01:{rid:02d}:00",
        "modified_at": None,
    }


def test_FE의_NON_PASS와_TRACKING_OK를_CV_명세_값으로_읽는다() -> None:
    record = _build_step_record(_fe_row(1, "NON_PASS", 55.0, ["LEFT_LEG_HEIGHT_ADJUST"]))

    assert record.evaluation_status == "FAIL"
    assert record.tracking_status == "VALID"
    assert record.has_evaluation()
    assert not record.is_unavailable()


def test_FE가_음성_안내마다_쌓은_코드는_시도_하나에서_한_번만_남긴다() -> None:
    codes = ["LEFT_LEG_HEIGHT_ADJUST", "LEFT_LEG_POSITION_ADJUST", "LEFT_LEG_HEIGHT_ADJUST"]

    record = _build_step_record(_fe_row(1, "NON_PASS", 60.0, codes))

    assert record.feedback_codes == ("LEFT_LEG_HEIGHT_ADJUST", "LEFT_LEG_POSITION_ADJUST")


def test_점수_없는_FE_기록은_측정_불가로_단정하지_않는다() -> None:
    # FE는 점수가 한 번이라도 매겨진 스텝만 저장한다. 점수가 없는 이유를 알 수 없으니
    # 카메라 위치 안내 대상으로 보지 않고 판정 없음으로 둔다.
    record = _build_step_record(_fe_row(1, "NOT_EVALUATED", None, []))

    assert record.evaluation_status == "NOT_EVALUATED"
    assert record.tracking_status == "NOT_EVALUATED"
    assert not record.has_evaluation()
    assert not record.is_unavailable()


def test_CV_명세_값은_그대로_읽는다() -> None:
    row = _fe_row(1, "NOT_EVALUATED", None, ["TRACKING_UNAVAILABLE"])
    row["step_report"]["evaluation_result"]["status"] = "UNAVAILABLE"
    row["step_report"]["tracking_info"]["tracking_status"] = "UNAVAILABLE"

    record = _build_step_record(row)

    assert record.evaluation_status == "UNAVAILABLE"
    assert record.tracking_status == "UNAVAILABLE"
    assert record.is_unavailable()


def test_판정_값이_문자열이_아니어도_예외를_내지_않는다() -> None:
    row = _fe_row(1, "NON_PASS", 55.0, [])
    row["step_report"]["evaluation_result"]["status"] = ["NON_PASS"]
    row["step_report"]["tracking_info"]["tracking_status"] = None

    record = _build_step_record(row)

    assert record.evaluation_status == ["NON_PASS"]
    assert record.tracking_status is None


def test_FE_채점_코드마다_상태_설명이_있다() -> None:
    labels = config.feedback_labels()

    assert [code for code in SIDE_KICK_CODES if code not in labels] == []


def test_상태_설명에는_금지어와_건강_단어가_없다() -> None:
    # 상태 설명은 LLM 입력으로 가고 한마디에 인용된다. 금지어가 있으면 출력 검사에서 버려진다.
    for code, label in config.feedback_labels().items():
        assert find_banned_term(label) is None, code
        assert find_health_term(label) is None, code


def test_FE_기록으로_다음_집중_스텝_후보에_상태_설명이_붙는다() -> None:
    records = [
        _build_step_record(_fe_row(1, "NON_PASS", 52.0, ["LEFT_LEG_HEIGHT_ADJUST"] * 2)),
        _build_step_record(
            _fe_row(2, "NON_PASS", 60.0, ["LEFT_LEG_HEIGHT_ADJUST", "LEFT_LEG_POSITION_ADJUST"])
        ),
        _build_step_record(_fe_row(3, "PASS", 86.0, [])),
    ]

    stats = build_stats(
        records=[], step_records=records, exercises=[], steps=STEPS, due_date=None, today=date(2026, 10, 19)
    )
    candidates, camera_checks = build_focus(
        step_records=records, steps=STEPS, issue_labels=config.feedback_labels(), cues_by_step={}
    )

    (step,) = stats.steps
    assert step.evaluation_counts == {"PASS": 1, "FAIL": 2, "UNAVAILABLE": 0, "NOT_EVALUATED": 0}
    assert step.feedback_code_counts == {"LEFT_LEG_HEIGHT_ADJUST": 2, "LEFT_LEG_POSITION_ADJUST": 1}
    assert candidates[0].issues == ("왼쪽 다리 들어 올림 부족", "왼쪽 다리 옆으로 벌림 부족")
    assert camera_checks == ()
