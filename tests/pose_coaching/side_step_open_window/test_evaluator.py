import copy
import json
from pathlib import Path

import pytest

from services.pose_coaching.side_step_open_window.evaluator import (
    CriteriaValidationError,
    evaluate_step,
    validate_step_criteria_matches_parent,
)


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def parent_criteria():
    # 실제 제공받은 부모 기준 JSON을 fixture로 읽어, 코드에 기준값을 하드코딩하지 않는다.
    return json.loads((FIXTURES / "side_step_open_window_parent_evaluation_criteria_v0_3_0_draft.json").read_text(encoding="utf-8"))


@pytest.fixture
def step_criteria():
    # 부모 기준과 비교할 개별 스텝 JSON 5개를 각각 로드한다.
    return {index: json.loads((FIXTURES / f"0{index}_step_{name}.json").read_text(encoding="utf-8")) for index, name in {
        1: "ready", 2: "right_lift_peak", 3: "right_return", 4: "left_lift_peak", 5: "left_return"
    }.items()}


def evaluate(parent, step, metrics, **kwargs):
    # 대부분의 테스트는 부모 기준에 적힌 버전을 사용한다.
    return evaluate_step(parent, step, metrics, parent["measurement_profile_version"], parent["mapping_rule_version"], **kwargs)


def test_parent_and_individual_criteria_match(parent_criteria, step_criteria):
    # 부모 JSON의 순서/코드/타입 및 분리된 스텝 기준의 동일성을 함께 검증한다.
    assert [step["step_order"] for step in parent_criteria["steps"]] == [1, 2, 3, 4, 5]
    assert [step["step_code"] for step in parent_criteria["steps"]] == ["READY", "RIGHT_LIFT_PEAK", "RIGHT_RETURN", "LEFT_LIFT_PEAK", "LEFT_RETURN"]
    assert [step["criteria"]["type"] for step in parent_criteria["steps"]] == ["CALIBRATION", "RULES", "RULES", "RULES", "RULES"]
    assert all(validate_step_criteria_matches_parent(parent_criteria, index, step_criteria[index]) for index in range(1, 6))


@pytest.mark.parametrize(("step", "metrics", "status"), [
    ("RIGHT_LIFT_PEAK", {"right_ankle_offset_ratio": .223484, "wrist_distance_ratio": 1.984576}, "PASS"),
    ("RIGHT_LIFT_PEAK", {"right_ankle_offset_ratio": .223483, "wrist_distance_ratio": 1.984576}, "NON_PASS"),
    ("RIGHT_RETURN", {"right_ankle_offset_ratio": .317699}, "PASS"),
    ("RIGHT_RETURN", {"right_ankle_offset_ratio": .317700}, "NON_PASS"),
    ("LEFT_LIFT_PEAK", {"left_ankle_offset_ratio": .439825, "wrist_distance_ratio": 1.704028}, "PASS"),
    ("LEFT_LIFT_PEAK", {"left_ankle_offset_ratio": .439824, "wrist_distance_ratio": 1.704028}, "NON_PASS"),
])
def test_active_rules_and_boundaries(parent_criteria, step, metrics, status):
    # GTE/LTE의 정확한 기준값은 PASS이고, 아주 작은 차이도 NON_PASS인지 확인한다.
    assert evaluate(parent_criteria, step, metrics)["evaluation_status"] == status


def test_disabled_steps_are_not_evaluated(parent_criteria):
    # enabled=false는 규칙을 실행하거나 PASS 처리하지 않는다.
    assert evaluate(parent_criteria, "READY", {})["reason_code"] == "STEP_DISABLED"
    assert evaluate(parent_criteria, "LEFT_RETURN", {})["reason_code"] == "STEP_DISABLED"


def test_missing_and_invalid_metrics_are_not_evaluated(parent_criteria):
    # 누락값과 비정상 수치는 0으로 보정하지 않고 판정 불가로 끝낸다.
    assert evaluate(parent_criteria, 2, {"right_ankle_offset_ratio": .3})["reason_code"] == "MISSING_REQUIRED_METRIC"
    invalid = evaluate(parent_criteria, 2, {"right_ankle_offset_ratio": float("nan"), "wrist_distance_ratio": 2})
    assert invalid["reason_code"] == "INVALID_METRIC_VALUE"
    assert json.dumps(invalid)
    assert evaluate(parent_criteria, 2, {"right_ankle_offset_ratio": "0.3", "wrist_distance_ratio": 2})["reason_code"] == "INVALID_METRIC_VALUE"


def test_versions_measurement_and_calibration_are_not_silently_scored(parent_criteria):
    # 프론트 매핑 계약이 달라졌거나 보정식이 미확정이면 점수를 추측하지 않는다.
    result = evaluate_step(parent_criteria, 2, {}, "wrong", parent_criteria["mapping_rule_version"])
    assert result["reason_code"] == "MEASUREMENT_PROFILE_VERSION_MISMATCH"
    result = evaluate_step(parent_criteria, 2, {}, parent_criteria["measurement_profile_version"], "wrong")
    assert result["reason_code"] == "MAPPING_RULE_VERSION_MISMATCH"
    modified = copy.deepcopy(parent_criteria)
    modified["steps"][0]["criteria"]["enabled"] = True
    assert evaluate(modified, 1, {})["reason_code"] == "CALIBRATION_NOT_IMPLEMENTED"


def test_invalid_criteria_and_mismatched_step_json_fail_safely(parent_criteria, step_criteria):
    # 서버 기준 데이터 자체가 잘못된 경우에는 안전하게 예외로 중단한다.
    malformed = copy.deepcopy(parent_criteria)
    malformed["steps"][1]["criteria"]["rules"][0]["value"] = float("inf")
    with pytest.raises(CriteriaValidationError):
        evaluate(malformed, 2, {"right_ankle_offset_ratio": 1, "wrist_distance_ratio": 2})
    mismatch = copy.deepcopy(step_criteria[2]); mismatch["enabled"] = False
    with pytest.raises(CriteriaValidationError):
        evaluate_step(parent_criteria, 2, {}, parent_criteria["measurement_profile_version"], parent_criteria["mapping_rule_version"], step_criteria=mismatch)


def test_other_step_criteria_cannot_be_linked(parent_criteria, step_criteria):
    # STEP 4 기준이 부모 어딘가에 있어도 STEP 2 기준으로는 사용할 수 없다.
    assert not validate_step_criteria_matches_parent(parent_criteria, 2, step_criteria[4])


@pytest.mark.parametrize(("mutator", "error"), [
    (lambda parent: parent["steps"][1].update(step_code="READY"), "DUPLICATE_OR_INVALID_STEP_IDENTIFIER"),
    (lambda parent: parent["steps"][1].update(step_order=1), "DUPLICATE_OR_INVALID_STEP_IDENTIFIER"),
    (lambda parent: parent["steps"][1]["criteria"]["rules"][0].update(operator="EQ"), "UNSUPPORTED_OPERATOR"),
    (lambda parent: parent["steps"][1]["criteria"].update(logic="ANY"), "UNSUPPORTED_RULE_LOGIC"),
])
def test_invalid_parent_structure_never_evaluates(parent_criteria, mutator, error):
    malformed = copy.deepcopy(parent_criteria)
    mutator(malformed)
    with pytest.raises(CriteriaValidationError, match=error):
        evaluate(malformed, 2, {"right_ankle_offset_ratio": 1, "wrist_distance_ratio": 2})


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), "1.0"])
def test_invalid_metric_is_reported_and_is_json_safe(parent_criteria, bad_value):
    result = evaluate(parent_criteria, 2, {"right_ankle_offset_ratio": .3, "wrist_distance_ratio": 2, "tracking_quality": bad_value})
    assert result["evaluation_status"] == "NOT_EVALUATED"
    assert result["reason_code"] == "INVALID_METRIC_VALUE"
    assert result["invalid_metric_names"] == ["tracking_quality"]
    assert json.dumps(result)


def test_valid_extra_metric_is_ignored_and_recorded(parent_criteria):
    result = evaluate(parent_criteria, 2, {"right_ankle_offset_ratio": .3, "wrist_distance_ratio": 2, "tracking_quality": .95})
    assert result["evaluation_status"] == "PASS"
    assert result["observed_metrics"] == {"right_ankle_offset_ratio": .3, "wrist_distance_ratio": 2}
    assert result["ignored_metric_names"] == ["tracking_quality"]
