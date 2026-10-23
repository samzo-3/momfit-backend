from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from api.sidekick_study import get_sidekick_exercise_config
from models.exercise import Exercise


def test_general_exercise_config_returns_side_kick_without_active_criteria(
    db_session: Session,
) -> None:
    db_session.add(
        Exercise(
            id=101,
            exercise_name="Side Kick",
            video_url="/side-kick.mp4",
        )
    )
    db_session.commit()

    config = get_sidekick_exercise_config(SimpleNamespace(id=1), db_session)

    assert config.exercise_id == 101
    assert config.exercise_name == "Side Kick"


def test_general_exercise_config_rejects_missing_side_kick(
    db_session: Session,
) -> None:
    with pytest.raises(HTTPException, match="SIDEKICK_EXERCISE_NOT_CONFIGURED"):
        get_sidekick_exercise_config(SimpleNamespace(id=1), db_session)
