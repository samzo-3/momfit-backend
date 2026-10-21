"""Side Kick HTTP API 통합 테스트. 테스트 DB 변경은 롤백한다."""

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_onboarded_user
from api.exercise_records import router
from db.session import engine, get_db
from models.exercise_record import ExerciseRecord
from models.user import User

USER_ID = 2
EXERCISE_ID = 1

app = FastAPI()
app.include_router(router)


def count_records(db):
    return db.scalar(
        select(func.count())
        .select_from(ExerciseRecord)
        .where(ExerciseRecord.exercise_id == EXERCISE_ID)
    )


with engine.connect() as conn:
    outer_tx = conn.begin()

    try:
        # 서비스 내부 commit은 SAVEPOINT로 격리한다.
        with Session(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ) as db:
            before = count_records(db)
            assert before == 3, f"기존 기록 수 불일치: {before}"

            user = db.get(User, USER_ID)
            assert user is not None, "테스트 사용자 ID 2가 없습니다."

            def override_db():
                yield db

            def override_user():
                return user

            app.dependency_overrides[get_db] = override_db
            app.dependency_overrides[get_onboarded_user] = override_user

            with TestClient(app) as client:
                # 1. 운동 시작
                response = client.post(
                    "/api/exercise-records",
                    json={"exercise_id": EXERCISE_ID},
                )
                assert response.status_code == 201, (
                    response.status_code, response.text
                )
                data = response.json()
                record_id = data["id"]
                assert data["exercise_criteria_version_id"] == 2
                assert data["completed_sets"] == 0
                assert data["status"] == "in_progress"
                print("HTTP_CREATE_OK: 201")

                # 2. 일시정지
                response = client.patch(
                    f"/api/exercise-records/{record_id}/pause",
                    json={"completed_sets": 3},
                )
                assert response.status_code == 200, response.text
                data = response.json()
                assert data["status"] == "paused"
                assert data["completed_sets"] == 3
                assert Decimal(str(data["total_score"])) == Decimal("30.00")
                print("HTTP_PAUSE_OK: 200")

                # 3. 재개
                response = client.patch(
                    f"/api/exercise-records/{record_id}/resume",
                )
                assert response.status_code == 200, response.text
                assert response.json()["status"] == "in_progress"
                print("HTTP_RESUME_OK: 200")

                # 4. 완료
                response = client.patch(
                    f"/api/exercise-records/{record_id}/complete",
                    json={"completed_sets": 7},
                )
                assert response.status_code == 200, response.text
                data = response.json()
                assert data["status"] == "completed"
                assert data["is_completed"] is True
                assert data["completed_sets"] == 7
                assert Decimal(str(data["total_score"])) == Decimal("70.00")
                assert data["ended_at"] is not None
                print("HTTP_COMPLETE_OK: 200")

                # 5. 완료 기록 조회
                response = client.get(
                    f"/api/exercise-records/{record_id}"
                )
                assert response.status_code == 200, response.text
                assert response.json()["status"] == "completed"
                print("HTTP_GET_OK: 200")

                # 6. 이미 완료한 운동 중복 완료 방지
                response = client.patch(
                    f"/api/exercise-records/{record_id}/complete",
                    json={"completed_sets": 8},
                )
                assert response.status_code == 409, response.text
                print("HTTP_DUPLICATE_COMPLETE_BLOCKED: 409")

                # 7. 잘못된 세트 수 요청 검증
                response = client.post(
                    "/api/exercise-records",
                    json={"exercise_id": 0},
                )
                assert response.status_code == 422, response.text
                print("HTTP_VALIDATION_OK: 422")

            print("HTTP_INTEGRATION_OK")

    finally:
        app.dependency_overrides.clear()
        if outer_tx.is_active:
            outer_tx.rollback()
        print("TEST_TRANSACTION_ROLLED_BACK")

with Session(engine) as db:
    after = count_records(db)
    assert after == 3, f"기존 기록 수 변경됨: {after}"
    print("EXISTING_RECORDS_PRESERVED:", after)

print("SIDEKICK_HTTP_TEST_PASSED")
