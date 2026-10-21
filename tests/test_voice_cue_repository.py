"""voice_cues Repository 조회 범위 테스트."""

import pytest

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
)
from sqlalchemy.orm import Session

from models.voice_cue import VoiceCue
from repositories.voice_cue_repository import list_active_by_scope


@pytest.fixture
def db():
    """테스트 전용 SQLite 메모리 DB.

    아직 exercises 및 exercise_steps ORM이 없으므로
    외래키가 없는 임시 voice_cues 테이블을 사용한다.
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()

    table = Table(
        "voice_cues",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("exercise_id", Integer, nullable=True),
        Column("exercise_step_id", Integer, nullable=True),
        Column("category", String(50), nullable=False),
        Column("event_code", String(50)),
        Column("audio_url", String(500), nullable=False),
        Column("is_active", Boolean, nullable=False),
        Column("message", String),
        Column("created_at", String),
        Column("modified_at", String),
    )

    metadata.create_all(engine)

    rows = [
        # TRACKING 공통 음성
        dict(
            id=1, category="TRACKING",
            exercise_id=None, exercise_step_id=None,
            event_code="USER_LOST", is_active=True,
        ),
        # EXERCISE 전체 공통
        dict(
            id=2, category="EXERCISE",
            exercise_id=None, exercise_step_id=None,
            event_code="START", is_active=True,
        ),
        # 운동 1 전용
        dict(
            id=3, category="EXERCISE",
            exercise_id=1, exercise_step_id=None,
            event_code="KNEE_TOO_BENT", is_active=True,
        ),
        # 운동 2 전용
        dict(
            id=4, category="EXERCISE",
            exercise_id=2, exercise_step_id=None,
            event_code="ARM_TOO_LOW", is_active=True,
        ),
        # STUDY 전체 공통
        dict(
            id=5, category="STUDY",
            exercise_id=None, exercise_step_id=None,
            event_code="STEP_START", is_active=True,
        ),
        # 운동 1 공통 STEP 안내
        dict(
            id=6, category="STUDY",
            exercise_id=1, exercise_step_id=None,
            event_code="STEP_COMPLETED", is_active=True,
        ),
        # 운동 1의 STEP 3 전용
        dict(
            id=7, category="STUDY",
            exercise_id=1, exercise_step_id=3,
            event_code="STEP_CORRECTION", is_active=True,
        ),
        # 운동 1의 STEP 4 전용
        dict(
            id=8, category="STUDY",
            exercise_id=1, exercise_step_id=4,
            event_code="STEP_CORRECTION", is_active=True,
        ),
        # 비활성화된 음성
        dict(
            id=9, category="EXERCISE",
            exercise_id=1, exercise_step_id=None,
            event_code="DISABLED", is_active=False,
        ),
    ]

    with engine.begin() as conn:
        conn.execute(
            insert(table),
            [
                {
                    **row,
                    "audio_url": f"/audio/test/{row['id']}.mp3",
                    "message": f"테스트 음성 {row['id']}",
                    "created_at": "2026-10-20 00:00:00",
                    "modified_at": "2026-10-20 00:00:00",
                }
                for row in rows
            ],
        )

    with Session(engine) as session:
        yield session

    engine.dispose()


def get_ids(cues: list[VoiceCue]) -> list[int]:
    return [cue.id for cue in cues]


def test_tracking_only(db):
    """추적 공통 음성만 조회."""
    result = list_active_by_scope(db, category="TRACKING")
    assert get_ids(result) == [1]


def test_exercise_one(db):
    """운동 1은 전체 공통 + 운동 1 전용만 조회."""
    result = list_active_by_scope(
        db, category="EXERCISE", exercise_id=1
    )
    assert get_ids(result) == [2, 3]


def test_exercise_two(db):
    """운동 2에는 운동 1의 음성이 포함되지 않는다."""
    result = list_active_by_scope(
        db, category="EXERCISE", exercise_id=2
    )
    assert get_ids(result) == [2, 4]


def test_study_step_three(db):
    """STEP 3은 전체 공통 + 운동 공통 + STEP 3만 조회."""
    result = list_active_by_scope(
        db, category="STUDY",
        exercise_id=1,
        exercise_step_id=3,
    )
    assert get_ids(result) == [5, 6, 7]


def test_study_step_four(db):
    """STEP 4는 STEP 3 음성을 가져오지 않는다."""
    result = list_active_by_scope(
        db, category="STUDY",
        exercise_id=1,
        exercise_step_id=4,
    )
    assert get_ids(result) == [5, 6, 8]


def test_inactive_excluded(db):
    """비활성 음성은 제외된다."""
    result = list_active_by_scope(
        db, category="EXERCISE", exercise_id=1
    )
    assert 9 not in get_ids(result)


def test_invalid_category(db):
    """알 수 없는 카테고리는 빈 목록 반환."""
    result = list_active_by_scope(db, category="UNKNOWN")
    assert result == []
