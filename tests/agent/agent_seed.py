"""services/agent/fixtures의 가짜 기록을 팀 모델(develop #15)로 테스트 DB에 넣는다.

DB 모드 테스트가 fixture 모드와 같은 행을 쓰게 해서 두 모드의 결과를 맞춰 볼 수 있게 한다.
"""

import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from models.exercise import Exercise
from models.exercise_criteria_version import ExerciseCriteriaVersion
from models.exercise_record import ExerciseRecord
from models.exercise_step import ExerciseStep
from models.exercise_step_record import ExerciseStepRecord
from models.voice_cue import VoiceCue
from services.agent import config

DECIMAL_FIELDS = {"total_score", "step_score"}
STEP_RESULT_STATUSES = {"PASS", "NON_PASS", "NOT_EVALUATED"}


def _load(name: str) -> dict:
    return json.loads((config.FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _values(row: dict, user_id: int | None = None) -> dict:
    """fixture 한 줄을 팀 모델에 넣을 값으로 바꾼다."""
    values = {}
    for key, value in row.items():
        if key.endswith("_at") and value is not None:
            value = datetime.fromisoformat(value)
        elif key in DECIMAL_FIELDS and value is not None:
            value = Decimal(str(value))
        values[key] = value
    if user_id is not None:
        values["user_id"] = user_id
    return values


def _criteria_version_id(exercise_id: int, catalog: dict, rows: dict) -> int:
    """시나리오에 쓰인 기준 버전을 우선 사용하고, 없으면 단일 ACTIVE 버전을 사용한다."""
    record_ids = {
        item["exercise_criteria_version_id"]
        for item in rows["exercise_records"]
        if item["exercise_id"] == exercise_id
        and item.get("exercise_criteria_version_id") is not None
    }
    if len(record_ids) == 1:
        return next(iter(record_ids))

    active_ids = {
        item["id"]
        for item in catalog["exercise_criteria_versions"]
        if item["exercise_id"] == exercise_id
        and item.get("status", "ACTIVE") == "ACTIVE"
    }
    if len(active_ids) == 1:
        return next(iter(active_ids))

    raise ValueError(
        f"운동 {exercise_id}의 평가 기준 버전을 하나로 결정할 수 없습니다. "
        "scenario의 exercise_step_records에 exercise_criteria_version_id를 명시하세요."
    )


def seed_scenario(db: Session, user_id: int, scenario: str) -> None:
    """fixture 행을 팀 모델로 넣는다. 사용자 번호만 테스트 사용자로 바꾼다."""
    catalog = _load("catalog.json")
    rows = _load(f"scenario_{scenario}.json")
    for model, items in (
        (Exercise, catalog["exercises"]),
        (ExerciseCriteriaVersion, catalog["exercise_criteria_versions"]),
        (ExerciseStep, catalog["exercise_steps"]),
        (VoiceCue, catalog["voice_cues"]),
    ):
        db.add_all(model(**_values(item)) for item in items)
        db.flush()

    db.add_all(ExerciseRecord(**_values(item, user_id)) for item in rows["exercise_records"])

    step_records = []
    for item in rows["exercise_step_records"]:
        values = _values(item, user_id)

        # 구형 fixture의 status는 판정 결과였으므로 신규 스텝 결과 필드로 옮긴다.
        if values.get("status") in STEP_RESULT_STATUSES:
            values.setdefault("step_result_status", values["status"])
            values["status"] = "completed"

        if values.get("exercise_criteria_version_id") is None:
            values["exercise_criteria_version_id"] = _criteria_version_id(
                values["exercise_id"], catalog, rows
            )

        step_records.append(ExerciseStepRecord(**values))

    db.add_all(step_records)
    db.commit()
