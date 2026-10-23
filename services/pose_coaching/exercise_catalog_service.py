"""DB PK/FK 기반 운동·STEP·기준 조회 서비스."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import AppError
from models.exercise import Exercise
from models.exercise_criteria_version import (
    CRITERIA_STATUS_ACTIVE,
    ExerciseCriteriaVersion,
)
from models.exercise_step import ExerciseStep
from models.exercise_step_criteria_version import ExerciseStepCriteriaVersion
from schemas.exercise_catalog import (
    ExerciseCriteriaResponse,
    ExerciseCriteriaStepResponse,
)


def get_exercise(db: Session, exercise_id: int) -> Exercise:
    exercise = db.get(Exercise, exercise_id)
    if exercise is None:
        raise AppError(404, "EXERCISE_NOT_FOUND", "운동을 찾을 수 없습니다.")
    return exercise


def get_step(db: Session, step_id: int) -> ExerciseStep:
    step = db.get(ExerciseStep, step_id)
    if step is None:
        raise AppError(404, "EXERCISE_STEP_NOT_FOUND", "운동 STEP을 찾을 수 없습니다.")
    return step


def list_steps(db: Session, exercise_id: int) -> list[ExerciseStep]:
    get_exercise(db, exercise_id)
    return db.scalars(
        select(ExerciseStep)
        .where(ExerciseStep.exercise_id == exercise_id)
        .order_by(ExerciseStep.step_order, ExerciseStep.id)
    ).all()


def get_active_criteria(db: Session, exercise_id: int) -> ExerciseCriteriaResponse:
    get_exercise(db, exercise_id)
    versions = db.scalars(
        select(ExerciseCriteriaVersion).where(
            ExerciseCriteriaVersion.exercise_id == exercise_id,
            ExerciseCriteriaVersion.status == CRITERIA_STATUS_ACTIVE,
        )
    ).all()
    if not versions:
        raise AppError(404, "ACTIVE_EXERCISE_CRITERIA_NOT_FOUND", "활성 평가 기준이 없습니다.")
    if len(versions) != 1:
        raise AppError(409, "MULTIPLE_ACTIVE_EXERCISE_CRITERIA", "활성 평가 기준이 둘 이상입니다.")
    return _criteria_response(db, versions[0])


def get_criteria_version(
    db: Session, exercise_id: int, version_id: int
) -> ExerciseCriteriaResponse:
    get_exercise(db, exercise_id)
    version = db.scalar(
        select(ExerciseCriteriaVersion).where(
            ExerciseCriteriaVersion.id == version_id,
            ExerciseCriteriaVersion.exercise_id == exercise_id,
        )
    )
    if version is None:
        raise AppError(404, "EXERCISE_CRITERIA_VERSION_NOT_FOUND", "평가 기준 버전을 찾을 수 없습니다.")
    return _criteria_response(db, version)


def _criteria_response(
    db: Session, version: ExerciseCriteriaVersion
) -> ExerciseCriteriaResponse:
    steps = list_steps(db, version.exercise_id)
    children = db.scalars(
        select(ExerciseStepCriteriaVersion).where(
            ExerciseStepCriteriaVersion.exercise_criteria_version_id == version.id
        )
    ).all()
    _validate_criteria_graph(version, steps, children)
    by_step_id = {child.exercise_step_id: child for child in children}
    return ExerciseCriteriaResponse(
        id=version.id,
        exercise_id=version.exercise_id,
        criteria_version=version.criteria_version,
        schema_version=version.schema_version,
        status=version.status,
        evaluation_criteria=version.evaluation_criteria,
        steps=[
            ExerciseCriteriaStepResponse(
                id=by_step_id[step.id].id,
                exercise_step_id=step.id,
                step_order=step.step_order,
                step_name=step.step_name,
                step_criteria_version=by_step_id[step.id].step_criteria_version,
                evaluation_criteria=by_step_id[step.id].evaluation_criteria,
            )
            for step in steps
        ],
    )


def _validate_criteria_graph(
    version: ExerciseCriteriaVersion,
    steps: list[ExerciseStep],
    children: list[ExerciseStepCriteriaVersion],
) -> None:
    """부모 JSON, 실제 STEP, 자식 기준 간의 손상된 매핑을 API로 노출하지 않는다."""
    parent_steps = version.evaluation_criteria.get("steps") if isinstance(version.evaluation_criteria, dict) else None
    if not isinstance(parent_steps, list):
        raise AppError(409, "INVALID_PARENT_EVALUATION_CRITERIA", "부모 평가 기준 형식이 올바르지 않습니다.")
    parent_by_order = {
        item.get("step_order"): item
        for item in parent_steps
        if isinstance(item, dict) and isinstance(item.get("step_order"), int)
    }
    if len(parent_by_order) != len(parent_steps) or set(parent_by_order) != {step.step_order for step in steps}:
        raise AppError(409, "PARENT_STEP_MAPPING_MISMATCH", "부모 기준과 STEP 순서가 일치하지 않습니다.")
    children_by_step = {child.exercise_step_id: child for child in children}
    if len(children_by_step) != len(children) or set(children_by_step) != {step.id for step in steps}:
        raise AppError(409, "STEP_CRITERIA_MAPPING_MISMATCH", "STEP별 평가 기준 매핑이 일치하지 않습니다.")
    for step in steps:
        parent = parent_by_order[step.step_order]
        child = children_by_step[step.id]
        if parent.get("criteria") != child.evaluation_criteria:
            raise AppError(409, "STEP_CRITERIA_VALUE_MISMATCH", "부모와 STEP 평가 기준 값이 일치하지 않습니다.")
        if parent.get("step_criteria_version") != child.step_criteria_version:
            raise AppError(409, "STEP_CRITERIA_VERSION_MISMATCH", "부모와 STEP 기준 버전이 일치하지 않습니다.")
