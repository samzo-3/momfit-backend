"""최신 ERD의 운동 ORM 핵심 제약을 DB 마이그레이션 없이 검증한다."""

from sqlalchemy import UniqueConstraint, inspect

from models.exercise_criteria_version import ExerciseCriteriaVersion
from models.exercise_record import ExerciseRecord
from models.exercise_step import ExerciseStep
from models.exercise_step_criteria_version import ExerciseStepCriteriaVersion
from models.exercise_step_record import ExerciseStepRecord


def test_exercise_step_important_is_required_boolean_without_default():
    column = ExerciseStep.__table__.c.important
    assert column.type.python_type is bool
    assert column.nullable is False
    assert column.default is None
    assert column.server_default is None


def test_step_record_session_id_is_required_uuid_sized_string_without_unique_constraint():
    column = ExerciseStepRecord.__table__.c.step_session_id
    assert column.type.length == 36
    assert column.nullable is False
    assert not any(column.name in constraint.columns for constraint in ExerciseStepRecord.__table__.constraints if getattr(constraint, "unique", False))


def test_criteria_version_has_active_database_default():
    default = ExerciseCriteriaVersion.__table__.c.status.server_default
    assert default is not None
    assert "ACTIVE" in str(default.arg)


def test_criteria_foreign_keys_and_step_criteria_composite_unique_are_preserved():
    step_record_fks = {foreign_key.target_fullname for foreign_key in ExerciseStepRecord.__table__.foreign_keys}
    assert "exercise_criteria_versions.id" in step_record_fks
    constraints = inspect(ExerciseStepCriteriaVersion).local_table.constraints
    assert any({column.name for column in constraint.columns} == {"exercise_step_id", "exercise_criteria_version_id"} for constraint in constraints if isinstance(constraint, UniqueConstraint))
    assert "step_criteria_version" in ExerciseStepCriteriaVersion.__table__.c


def test_exercise_record_completion_fields_and_step_status_fields_stay_separate():
    # 최신 ERD의 완료 집계 필드와 실행 상태/평가 결과 상태를 혼동하지 않는다.
    assert ExerciseRecord.__table__.c.completed_sets.nullable is False
    assert ExerciseRecord.__table__.c.is_completed.nullable is False
    assert "status" in ExerciseStepRecord.__table__.c
    assert "step_result_status" in ExerciseStepRecord.__table__.c
