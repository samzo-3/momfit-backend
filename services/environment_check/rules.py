"""YOLO 결과만으로 적용 가능한 보수적 2D 화면 규칙."""
# 판정 기준 - 탐지한 결과를 검사하여 PASS 등을 결정합니다.

from dataclasses import dataclass

from services.environment_check.detector import Detection
from services.environment_check.config import SETTINGS
from services.environment_check.profiles import EnvironmentProfile


@dataclass(frozen=True)
class RuleResult:
    status: str
    issue_codes: list[str]
    messages: list[str]


def area(box: tuple[float, float, float, float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def evaluate(
    detections: list[Detection], image_size: tuple[int, int], profile: EnvironmentProfile
) -> RuleResult:
    """탐지 결과만으로 가능한 화면상 환경 점검 결과를 만든다."""
    people = [item for item in detections if item.name == SETTINGS.person_label]
    objects = [item for item in detections if item.name != SETTINGS.person_label]
    if not people:
        return RuleResult("INCONCLUSIVE", ["PERSON_NOT_DETECTED"], ["사람을 찾지 못했어요. 전신이 보이도록 카메라를 다시 맞춰 주세요."])
    if len(people) > 1:
        return RuleResult("NEEDS_ADJUSTMENT", ["MULTIPLE_PEOPLE"], ["한 사람만 화면에 나오도록 조정해 주세요."])

    person = people[0]
    frame_area = image_size[0] * image_size[1]
    if not frame_area or area(person.bbox) / frame_area < SETTINGS.min_person_frame_ratio:
        return RuleResult("NEEDS_ADJUSTMENT", ["PERSON_TOO_SMALL"], ["사람이 너무 작게 보입니다. 카메라와의 거리를 조정해 주세요."])

    # 현 단계의 운동은 모두 맨몸운동이다. 주변 물체의 존재/미탐지만으로 실패시키지
    # 않으며, YOLO 2D bbox로 실제 공간 안전성도 확정하지 않는다.
    missing_required_objects = [
        name for name in profile.required_objects if not any(item.name == name for item in objects)
    ]
    if missing_required_objects:
        return RuleResult(
            "NEEDS_ADJUSTMENT",
            ["REQUIRED_OBJECT_NOT_DETECTED"],
            ["운동에 필요한 도구가 화면에서 확인되지 않아요. 도구와 카메라 구도를 확인해 주세요."],
        )

    return RuleResult("PASS", [], ["운동 대상자 1명이 확인되었습니다. 화면에서 확인 가능한 범위에 문제는 보이지 않아요."])
