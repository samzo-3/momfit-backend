"""Side Kick 운동 기록 서비스 통합 테스트 (DB 변경 롤백)."""

from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from db.session import engine
from models.exercise_record import ExerciseRecord
from services.exercise_record_service import (
    create_record,
    get_record,
    pause_record,
    resume_record,
    complete_record,
)

USER_ID = 2
EXERCISE_ID = 1


def record_count(db):
    return db.scalar(
        select(func.count())
        .select_from(ExerciseRecord)
        .where(ExerciseRecord.exercise_id == EXERCISE_ID)
    )


with engine.connect() as conn:
    outer_tx = conn.begin()
    test_id = None

    try:
        # 서비스 내부 commit은 SAVEPOINT에만 적용
        with Session(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ) as db:

            before = record_count(db)
            assert before == 3, f"기존 운동 기록 수 불일치: {before}"

            # 1. 운동 시작
            record = create_record(db, USER_ID, EXERCISE_ID)
            test_id = record.id

            assert record.status == "IN_PROGRESS"
            assert record.exercise_criteria_version_id == 2
            assert record.completed_sets == 0
            print("CREATE_OK:", test_id)

            # 2. 3세트 수행 후 일시정지
            record = pause_record(db, USER_ID, test_id, 3)

            assert record.status == "PAUSED"
            assert record.completed_sets == 3
            assert record.total_score == Decimal("30.00")
            print("PAUSE_OK: 3세트 / 30점")

            # 3. 운동 재개
            record = resume_record(db, USER_ID, test_id)

            assert record.status == "IN_PROGRESS"
            assert record.completed_sets == 3
            print("RESUME_OK")

            # 4. 총 7세트 수행 후 완료
            record = complete_record(db, USER_ID, test_id, 7)

            assert record.status == "COMPLETED"
            assert record.is_completed is True
            assert record.completed_sets == 7
            assert record.total_score == Decimal("70.00")
            assert record.ended_at is not None
            print("COMPLETE_OK: 7세트 / 70점")

            # 5. 완료 기록 조회
            record = get_record(db, USER_ID, test_id)
            assert record.status == "COMPLETED"
            print("GET_RECORD_OK")

        print("SERVICE_INTEGRATION_OK")

    finally:
        # 성공/실패 여부와 관계없이 테스트 데이터 롤백
        if outer_tx.is_active:
            outer_tx.rollback()
        print("TEST_TRANSACTION_ROLLED_BACK")

# 실제 저장 데이터가 변하지 않았는지 확인
with Session(engine) as db:
    after = record_count(db)
    assert after == 3, f"기존 기록 수 변경됨: {after}"

    if test_id is not None:
        assert db.get(ExerciseRecord, test_id) is None

    print("EXISTING_RECORDS_PRESERVED:", after)

print("SIDEKICK_SERVICE_TEST_PASSED")
