"""services/agent/fixtures의 가짜 기록을 팀 모델(develop #9)로 테스트 DB에 넣는다.

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

DECIMAL_FIELDS = {"total_score", "step_score", "score_per_set"}


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
    db.add_all(
        ExerciseStepRecord(**_values(item, user_id)) for item in rows["exercise_step_records"]
    )
    db.commit()
