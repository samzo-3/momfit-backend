"""Side Step & Open the Window의 순수 기준(JSON) 기반 평가 엔진.

MediaPipe 관절 추출·집계·좌우 매핑은 프론트엔드 책임이다. 이 모듈은 전달된
정규화 수치와 기준 JSON만 비교하므로 HTTP, DB, YOLO에 의존하지 않는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any


class CriteriaValidationError(ValueError):
    """기준 JSON이 손상되었거나 지원하지 않는 형식일 때 발생한다."""


def validate_step_criteria_matches_parent(parent_criteria: Mapping[str, Any], step_identifier: str | int, step_criteria: Mapping[str, Any]) -> bool:
    """지정한 부모 스텝의 criteria와 별도 스텝 JSON이 같은지 검증한다."""
    steps = _validate_parent_criteria(parent_criteria)
    return _find_step(steps, step_identifier)["criteria"] == dict(step_criteria)


def evaluate_step(parent_criteria: Mapping[str, Any], step_identifier: str | int, observed_metrics: Mapping[str, Any], measurement_profile_version: str, mapping_rule_version: str, measurement_valid: bool = True, step_criteria: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """한 스텝을 평가해 JSON 직렬화 가능한 step_report용 dict를 반환한다."""
    # 부모 전체를 먼저 검사해 선택하지 않은 다른 스텝의 손상도 PASS를 만들지 못하게 한다.
    steps = _validate_parent_criteria(parent_criteria)
    step = _find_step(steps, step_identifier)
    criteria = step["criteria"]
    if step_criteria is not None and criteria != step_criteria:
        raise CriteriaValidationError("STEP_CRITERIA_MISMATCH")

    required_names = _required_metric_names(criteria)
    valid_metrics, ignored_names, invalid_names = _metric_context(observed_metrics, required_names)
    report = _report_base(step["step_code"], valid_metrics, measurement_profile_version, mapping_rule_version, ignored_names, invalid_names)
    # 다른 프론트 매핑 결과는 올바른 PASS로 간주할 수 없다.
    if measurement_profile_version != parent_criteria["measurement_profile_version"]:
        return _not_evaluated(report, "MEASUREMENT_PROFILE_VERSION_MISMATCH")
    if mapping_rule_version != parent_criteria["mapping_rule_version"]:
        return _not_evaluated(report, "MAPPING_RULE_VERSION_MISMATCH")
    if not isinstance(measurement_valid, bool) or not measurement_valid:
        return _not_evaluated(report, "MEASUREMENT_INVALID")
    # 비정상 값은 추가 메트릭이어도 조용히 버리고 PASS 처리하지 않는다.
    if invalid_names:
        return _not_evaluated(report, "INVALID_METRIC_VALUE")
    if not criteria["enabled"]:
        return _not_evaluated(report, "STEP_DISABLED")
    if criteria["type"] == "CALIBRATION":
        # USER_READY 보정식은 아직 미확정이므로 임의 계산을 만들지 않는다.
        return _not_evaluated(report, "CALIBRATION_NOT_IMPLEMENTED")

    results: list[dict[str, Any]] = []
    for rule in criteria["rules"]:
        metric = rule["metric"]
        if metric not in valid_metrics:
            return _not_evaluated(report, "MISSING_REQUIRED_METRIC", results)
        observed = valid_metrics[metric]
        threshold = rule["value"]
        # GTE/LTE의 경계값 자체는 통과한다.
        passed = observed >= threshold if rule["operator"] == "GTE" else observed <= threshold
        results.append({"metric": metric, "operator": rule["operator"], "threshold": threshold, "reference_value": rule["reference_value"], "observed_value": observed, "status": "PASS" if passed else "NON_PASS", "deviation_from_threshold": observed - threshold})
    report["rule_results"] = results
    # 현재 JSON의 logic=ALL: 모든 규칙을 통과해야 스텝도 통과한다.
    report["evaluation_status"] = "PASS" if all(item["status"] == "PASS" for item in results) else "NON_PASS"
    report["reason_code"] = "ALL_RULES_PASSED" if report["evaluation_status"] == "PASS" else "RULE_NOT_MET"
    return report


def _validate_parent_criteria(parent_criteria: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """부모 JSON 전체 구조와 모든 스텝 기준을 실행 전에 검사한다."""
    if not isinstance(parent_criteria, Mapping):
        raise CriteriaValidationError("INVALID_PARENT_CRITERIA")
    _required_string(parent_criteria, "measurement_profile_version")
    _required_string(parent_criteria, "mapping_rule_version")
    study = parent_criteria.get("study")
    if not isinstance(study, Mapping) or not _is_positive_int(study.get("start_step_order")) or not isinstance(study.get("final_pass_rule"), str):
        raise CriteriaValidationError("INVALID_STUDY")
    steps = parent_criteria.get("steps")
    if not isinstance(steps, list) or not steps:
        raise CriteriaValidationError("INVALID_PARENT_STEPS")
    orders: set[int] = set()
    codes: set[str] = set()
    for step in steps:
        if not isinstance(step, Mapping) or not _is_positive_int(step.get("step_order")):
            raise CriteriaValidationError("INVALID_STEP_DEFINITION")
        code = step.get("step_code")
        if not isinstance(code, str) or not code or code in codes or step["step_order"] in orders:
            raise CriteriaValidationError("DUPLICATE_OR_INVALID_STEP_IDENTIFIER")
        if not isinstance(step.get("step_criteria_version"), str) or not step["step_criteria_version"]:
            raise CriteriaValidationError("INVALID_STEP_CRITERIA_VERSION")
        criteria = step.get("criteria")
        if not isinstance(criteria, Mapping):
            raise CriteriaValidationError("INVALID_STEP_CRITERIA")
        _validate_criteria(criteria)
        orders.add(step["step_order"])
        codes.add(code)
    if orders != set(range(1, len(steps) + 1)):
        raise CriteriaValidationError("MISSING_STEP_ORDER")
    return steps


def _validate_criteria(criteria: Mapping[str, Any]) -> None:
    """RULES/CALIBRATION 별 필수 필드와 값의 유효성을 검사한다."""
    if not isinstance(criteria.get("enabled"), bool):
        raise CriteriaValidationError("INVALID_ENABLED")
    if criteria.get("type") == "CALIBRATION":
        _required_string(criteria, "baseline")
        values = criteria.get("reference_values")
        if not isinstance(values, Mapping) or not values or any(not isinstance(key, str) or not _is_number(value) for key, value in values.items()):
            raise CriteriaValidationError("INVALID_CALIBRATION_REFERENCE_VALUES")
        return
    if criteria.get("type") != "RULES":
        raise CriteriaValidationError("UNSUPPORTED_CRITERIA_TYPE")
    _required_string(criteria, "side")
    if criteria.get("logic") != "ALL":
        raise CriteriaValidationError("UNSUPPORTED_RULE_LOGIC")
    if criteria.get("on_missing_metric") != "NOT_EVALUATED":
        raise CriteriaValidationError("UNSUPPORTED_MISSING_METRIC_POLICY")
    rules = criteria.get("rules")
    if not isinstance(rules, list) or not rules:
        raise CriteriaValidationError("INVALID_RULES")
    names: set[str] = set()
    for rule in rules:
        metric = _validated_rule(rule)
        if metric in names:
            raise CriteriaValidationError("DUPLICATE_RULE_METRIC")
        names.add(metric)


def _find_step(steps: list[Mapping[str, Any]], step_identifier: str | int) -> Mapping[str, Any]:
    """코드 또는 순서로 대상 스텝을 정확히 하나 찾는다."""
    matches = [step for step in steps if step_identifier in (step["step_code"], step["step_order"])]
    if len(matches) != 1:
        raise CriteriaValidationError("STEP_NOT_FOUND")
    return matches[0]


def _validated_rule(rule: Any) -> str:
    if not isinstance(rule, Mapping):
        raise CriteriaValidationError("INVALID_RULE")
    metric = _required_string(rule, "metric")
    if rule.get("operator") not in {"GTE", "LTE"}:
        raise CriteriaValidationError("UNSUPPORTED_OPERATOR")
    if not _is_number(rule.get("value")) or not _is_number(rule.get("reference_value")):
        raise CriteriaValidationError("INVALID_RULE_VALUE")
    return metric


def _required_metric_names(criteria: Mapping[str, Any]) -> set[str]:
    return set() if criteria["type"] != "RULES" else {rule["metric"] for rule in criteria["rules"]}


def _metric_context(observed_metrics: Any, required_names: set[str]) -> tuple[dict[str, float | int], list[str], list[str]]:
    """입력 메트릭을 필수값/무시할 정상값/오류값으로 안전하게 분류한다."""
    if not isinstance(observed_metrics, Mapping):
        return {}, [], ["<observed_metrics>"]
    valid: dict[str, float | int] = {}
    ignored: list[str] = []
    invalid: list[str] = []
    for name, value in observed_metrics.items():
        safe_name = name if isinstance(name, str) else "<non_string_metric_name>"
        if not isinstance(name, str) or not _is_number(value):
            invalid.append(safe_name)
        elif name in required_names:
            valid[name] = value
        else:
            ignored.append(name)
    return valid, sorted(ignored), sorted(set(invalid))


def _required_string(document: Mapping[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise CriteriaValidationError(f"INVALID_{key.upper()}")
    return value


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _report_base(step_code: str, observed_metrics: dict[str, float | int], profile: str, mapping: str, ignored_names: list[str], invalid_names: list[str]) -> dict[str, Any]:
    """모든 경로에서 JSON 직렬화 가능한 공통 결과 골격을 만든다."""
    return {"step_code": step_code, "evaluation_status": "NOT_EVALUATED", "reason_code": None, "rule_results": [], "observed_metrics": observed_metrics, "ignored_metric_names": ignored_names, "invalid_metric_names": invalid_names, "measurement_profile_version": profile, "mapping_rule_version": mapping, "step_score": None}


def _not_evaluated(report: dict[str, Any], reason_code: str, results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    report["reason_code"] = reason_code
    if results:
        report["rule_results"] = results
    return report
