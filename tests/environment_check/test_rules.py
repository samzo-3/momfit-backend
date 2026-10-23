from services.environment_check.detector import Detection
from services.environment_check.profiles import DEFAULT_PROFILE
from services.environment_check.rules import evaluate


def d(name, bbox):
    return Detection(name=name, confidence=0.9, bbox=bbox)


def test_person_zero_is_inconclusive():
    assert evaluate([], (1000, 800), DEFAULT_PROFILE).issue_codes == ["PERSON_NOT_DETECTED"]


def test_multiple_people_needs_adjustment():
    assert evaluate([d("person", (100, 100, 400, 700)), d("person", (500, 100, 800, 700))], (1000, 800), DEFAULT_PROFILE).issue_codes == ["MULTIPLE_PEOPLE"]


def test_default_passes_with_one_person_and_no_surrounding_object():
    assert evaluate([d("person", (300, 100, 600, 700))], (1000, 800), DEFAULT_PROFILE).status == "PASS"


def test_surrounding_object_does_not_block_bodyweight_exercise():
    assert evaluate([d("person", (300, 100, 600, 700)), d("chair", (350, 300, 550, 650))], (1000, 800), DEFAULT_PROFILE).status == "PASS"


def test_bbox_coordinates_are_not_mirrored():
    assert d("chair", (12, 30, 112, 330)).bbox == (12, 30, 112, 330)
