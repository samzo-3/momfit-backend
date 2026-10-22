"""관리자 회원관리 API (목록, 상세, 강제 탈퇴, 복구)와 조회·조치 이력."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.clock import utc_now
from core.config import settings
from models.admin_audit_log import AdminAuditLog
from models.daily_visit import DailyVisit
from models.exercise import Exercise
from models.exercise_criteria_version import ExerciseCriteriaVersion
from models.exercise_record import ExerciseRecord
from models.refresh_token import RefreshToken
from models.user import ROLE_ADMIN, STATUS_ACTIVE, STATUS_WITHDRAWN, User
from services.auth import account_service
from tests.conftest import FakeKakaoClient
from tests.helpers import kakao_login, signup_payload

MEMBERS = "/api/admin/members"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signup(client: TestClient, n: int, **overrides) -> tuple[str, int]:
    response = client.post(
        "/api/auth/signup",
        json=signup_payload(
            login_id=f"member{n:02d}",
            email=f"m{n}@example.com",
            nickname=overrides.pop("nickname", f"회원{n:02d}"),
            **overrides,
        ),
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    return token, client.get("/api/users/me", headers=_bearer(token)).json()["id"]


def _admin(client: TestClient, db: Session) -> dict[str, str]:
    token, user_id = _signup(client, 99, nickname="운영자")
    db.get(User, user_id).role = ROLE_ADMIN
    db.commit()
    return _bearer(token)


def _record(db: Session, user_id: int, days_ago: int, *, completed=True) -> None:
    if db.get(Exercise, 1) is None:
        db.add(Exercise(id=1, exercise_name="Side Kick", video_url="https://example.com/v"))
        db.flush()
        db.add(
            ExerciseCriteriaVersion(
                id=1, exercise_id=1, evaluation_criteria={}, criteria_version="v1",
                schema_version=1,
            )
        )
        db.flush()
    db.add(
        ExerciseRecord(
            id=db.query(ExerciseRecord).count() + 1,
            user_id=user_id,
            exercise_id=1,
            exercise_criteria_version_id=1,
            status="completed" if completed else "in_progress",
            is_completed=completed,
            total_score=90 if completed else None,
            started_at=utc_now() - timedelta(days=days_ago),
        )
    )
    db.commit()


def _history(db: Session, user_id: int) -> list[str]:
    return [
        log.action
        for log in db.query(AdminAuditLog)
        .filter_by(target_user_id=user_id)
        .order_by(AdminAuditLog.id)
    ]


# ---------- 접근 제어 ----------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", MEMBERS),
        ("GET", f"{MEMBERS}/1"),
        ("POST", f"{MEMBERS}/1/withdraw"),
        ("POST", f"{MEMBERS}/1/restore"),
    ],
)
def test_일반_사용자는_회원관리_API가_403이다(
    client: TestClient, method: str, path: str
) -> None:
    token, _ = _signup(client, 1)

    response = client.request(method, path, headers=_bearer(token))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# ---------- 목록 ----------


def test_목록은_일반_회원만_가입_최신순으로_보여_준다(
    client: TestClient, db_session: Session
) -> None:
    _, first = _signup(client, 1)
    _, second = _signup(client, 2)
    admin = _admin(client, db_session)
    db_session.get(User, first).created_at = datetime(2026, 1, 1)
    db_session.get(User, second).created_at = datetime(2026, 2, 1)
    db_session.commit()

    body = client.get(MEMBERS, headers=admin).json()

    assert [m["nickname"] for m in body["items"]] == ["회원02", "회원01"]
    assert body["total"] == 2  # 관리자 제외
    assert body["page"] == 1


def test_목록_행에_필요한_정보가_담긴다(client: TestClient, db_session: Session) -> None:
    _, user_id = _signup(client, 1)
    admin = _admin(client, db_session)
    _record(db_session, user_id, 1)
    _record(db_session, user_id, 2)
    _record(db_session, user_id, 3, completed=False)
    db_session.query(DailyVisit).filter_by(user_id=user_id).delete()
    db_session.add(DailyVisit(visit_date=date(2026, 3, 5), user_id=user_id))
    db_session.add(DailyVisit(visit_date=date(2026, 3, 9), user_id=user_id))
    db_session.commit()

    item = client.get(MEMBERS, headers=admin).json()["items"][0]

    assert item["email"] == "m1@example.com"
    assert item["login_id"] == "member01"
    assert item["provider"] == "local"
    assert item["status"] == "active"
    assert item["last_visit_date"] == "2026-03-09"
    assert item["completed_exercises"] == 2
    assert item["withdrawn_at"] is None
    assert item["purge_at"] is None


def test_카카오_회원은_provider가_kakao다(client: TestClient, db_session: Session) -> None:
    admin = _admin(client, db_session)
    kakao_login(client)

    items = client.get(MEMBERS, headers=admin).json()["items"]

    assert [i["provider"] for i in items] == ["kakao"]
    assert items[0]["login_id"] is None


@pytest.mark.parametrize("query", ["회원01", "M1@example", "member01", "원01"])
def test_닉네임_이메일_아이디로_검색한다(
    client: TestClient, db_session: Session, query: str
) -> None:
    _signup(client, 1)
    _signup(client, 2)
    admin = _admin(client, db_session)

    body = client.get(MEMBERS, params={"q": query}, headers=admin).json()

    assert [m["nickname"] for m in body["items"]] == ["회원01"]


def test_검색어의_와일드카드는_글자_그대로_찾는다(
    client: TestClient, db_session: Session
) -> None:
    _signup(client, 1, nickname="100%맘")
    _signup(client, 2, nickname="평범한맘")
    admin = _admin(client, db_session)

    percent = client.get(MEMBERS, params={"q": "%"}, headers=admin).json()
    underscore = client.get(MEMBERS, params={"q": "_"}, headers=admin).json()

    assert [m["nickname"] for m in percent["items"]] == ["100%맘"]
    assert underscore["items"] == []


def test_상태로_거른다(client: TestClient, db_session: Session) -> None:
    _, leaving = _signup(client, 1)
    _signup(client, 2)
    admin = _admin(client, db_session)
    user = db_session.get(User, leaving)
    user.status = STATUS_WITHDRAWN
    user.withdrawn_at = utc_now()
    db_session.commit()

    withdrawn = client.get(MEMBERS, params={"status": "withdrawn"}, headers=admin).json()
    active = client.get(MEMBERS, params={"status": "active"}, headers=admin).json()

    assert [m["nickname"] for m in withdrawn["items"]] == ["회원01"]
    assert withdrawn["items"][0]["purge_at"] is not None
    assert [m["nickname"] for m in active["items"]] == ["회원02"]


def test_페이지로_나누어_보여_준다(client: TestClient, db_session: Session) -> None:
    for n in range(1, 6):
        _, user_id = _signup(client, n)
        db_session.get(User, user_id).created_at = datetime(2026, 1, n)
    admin = _admin(client, db_session)
    db_session.commit()

    page2 = client.get(MEMBERS, params={"size": 2, "page": 2}, headers=admin).json()
    last = client.get(MEMBERS, params={"size": 2, "page": 3}, headers=admin).json()

    assert page2["total"] == 5
    assert [m["nickname"] for m in page2["items"]] == ["회원03", "회원02"]
    assert [m["nickname"] for m in last["items"]] == ["회원01"]


def test_잘못된_페이지_값은_422다(client: TestClient, db_session: Session) -> None:
    admin = _admin(client, db_session)

    assert client.get(MEMBERS, params={"size": 500}, headers=admin).status_code == 422
    assert client.get(MEMBERS, params={"page": 0}, headers=admin).status_code == 422
    assert client.get(MEMBERS, params={"status": "x"}, headers=admin).status_code == 422


def test_목록과_상세에_비밀번호_정보가_없다(client: TestClient, db_session: Session) -> None:
    _, user_id = _signup(client, 1)
    admin = _admin(client, db_session)

    listing = client.get(MEMBERS, headers=admin).text
    detail = client.get(f"{MEMBERS}/{user_id}", headers=admin).text

    for text in (listing, detail):
        assert "password" not in text
        assert "hash" not in text


# ---------- 상세 ----------


def test_상세에_프로필과_최근_운동_기록이_담긴다(
    client: TestClient, db_session: Session
) -> None:
    _, user_id = _signup(client, 1)
    admin = _admin(client, db_session)
    for days_ago in range(12):
        _record(db_session, user_id, days_ago)

    body = client.get(f"{MEMBERS}/{user_id}", headers=admin).json()

    assert body["nickname"] == "회원01"
    assert body["onboarding_completed"] is True
    assert body["exercise_level"] == "low"
    assert body["due_date"] is not None
    assert body["completed_exercises"] == 12
    assert body["visit_days_last_30"] == 1  # 가입할 때 기록된 오늘
    assert len(body["recent_records"]) == 10
    assert body["recent_records"][0]["exercise_name"] == "Side Kick"
    assert body["recent_records"][0]["total_score"] == 90.0


def test_상세를_조회하면_이력이_남고_상세에_보인다(
    client: TestClient, db_session: Session
) -> None:
    _, user_id = _signup(client, 1)
    admin = _admin(client, db_session)

    client.get(f"{MEMBERS}/{user_id}", headers=admin)
    body = client.get(f"{MEMBERS}/{user_id}", headers=admin).json()

    assert _history(db_session, user_id) == ["view_member", "view_member"]
    assert [h["action"] for h in body["history"]] == ["view_member", "view_member"]
    assert body["history"][0]["admin_nickname"] == "운영자"


def test_목록_조회는_이력을_남기지_않는다(client: TestClient, db_session: Session) -> None:
    _, user_id = _signup(client, 1)
    admin = _admin(client, db_session)

    client.get(MEMBERS, headers=admin)

    assert _history(db_session, user_id) == []


def test_없는_회원이나_관리자_계정은_404다(client: TestClient, db_session: Session) -> None:
    token, admin_id = _signup(client, 98, nickname="다른운영자")
    db_session.get(User, admin_id).role = ROLE_ADMIN
    db_session.commit()
    admin = _bearer(token)

    for path in (f"{MEMBERS}/9999", f"{MEMBERS}/{admin_id}"):
        response = client.get(path, headers=admin)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "MEMBER_NOT_FOUND"
    assert client.post(f"{MEMBERS}/{admin_id}/withdraw", headers=admin).status_code == 404
    assert db_session.get(User, admin_id).status == STATUS_ACTIVE


# ---------- 강제 탈퇴 ----------


def test_강제_탈퇴하면_유예_상태가_되고_로그인이_해제된다(
    client: TestClient, db_session: Session
) -> None:
    member_token, user_id = _signup(client, 1)
    admin = _admin(client, db_session)

    response = client.post(f"{MEMBERS}/{user_id}/withdraw", headers=admin)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "withdrawn"
    assert body["purge_at"] is not None
    assert [h["action"] for h in body["history"]] == ["withdraw_member"]
    user = db_session.get(User, user_id)
    assert user.status == STATUS_WITHDRAWN
    assert user.withdrawn_at is not None
    assert (
        db_session.query(RefreshToken)
        .filter_by(user_id=user_id, revoked_at=None)
        .count()
        == 0
    )
    # 이미 발급된 access 토큰으로도 더는 들어올 수 없다.
    assert client.get("/api/users/me", headers=_bearer(member_token)).status_code == 401


def test_이미_탈퇴한_회원은_다시_탈퇴시킬_수_없다(
    client: TestClient, db_session: Session
) -> None:
    _, user_id = _signup(client, 1)
    admin = _admin(client, db_session)
    client.post(f"{MEMBERS}/{user_id}/withdraw", headers=admin)

    response = client.post(f"{MEMBERS}/{user_id}/withdraw", headers=admin)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MEMBER_ALREADY_WITHDRAWN"
    assert _history(db_session, user_id) == ["withdraw_member"]  # 실패는 이력에 남기지 않는다


def test_카카오_회원을_강제_탈퇴하면_카카오_연결을_끊는다(
    client: TestClient, db_session: Session, kakao: FakeKakaoClient
) -> None:
    admin = _admin(client, db_session)
    kakao_login(client)
    user_id = (
        db_session.query(User).filter(User.email.is_(None), User.role == "user").one().id
    )

    client.post(f"{MEMBERS}/{user_id}/withdraw", headers=admin)

    assert kakao.unlinked == ["12345"]


# ---------- 복구 ----------


def test_복구하면_다시_로그인할_수_있다(client: TestClient, db_session: Session) -> None:
    _, user_id = _signup(client, 1)
    admin = _admin(client, db_session)
    client.post(f"{MEMBERS}/{user_id}/withdraw", headers=admin)

    response = client.post(f"{MEMBERS}/{user_id}/restore", headers=admin)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "active"
    assert body["withdrawn_at"] is None
    assert [h["action"] for h in body["history"]] == ["restore_member", "withdraw_member"]
    login = client.post(
        "/api/auth/login", json={"login_id": "member01", "password": "password1"}
    )
    assert login.status_code == 200


def test_이용_중인_회원은_복구할_수_없다(client: TestClient, db_session: Session) -> None:
    _, user_id = _signup(client, 1)
    admin = _admin(client, db_session)

    response = client.post(f"{MEMBERS}/{user_id}/restore", headers=admin)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MEMBER_NOT_RESTORABLE"
    assert _history(db_session, user_id) == []


def test_유예_기간이_지난_회원은_복구할_수_없다(
    client: TestClient, db_session: Session
) -> None:
    _, user_id = _signup(client, 1)
    admin = _admin(client, db_session)
    user = db_session.get(User, user_id)
    user.status = STATUS_WITHDRAWN
    user.withdrawn_at = utc_now() - timedelta(days=settings.account_grace_days + 1)
    db_session.commit()

    response = client.post(f"{MEMBERS}/{user_id}/restore", headers=admin)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MEMBER_NOT_RESTORABLE"


# ---------- 이력 보존 ----------


def test_회원이_완전히_삭제돼도_이력은_남는다(
    client: TestClient, db_session: Session
) -> None:
    _, user_id = _signup(client, 1)
    admin = _admin(client, db_session)
    client.post(f"{MEMBERS}/{user_id}/withdraw", headers=admin)

    account_service.purge_expired(db_session, now=utc_now() + timedelta(days=3650))

    assert db_session.get(User, user_id) is None
    log = db_session.query(AdminAuditLog).filter_by(target_user_id=user_id).one()
    assert (log.action, log.target_nickname, log.admin_nickname) == (
        "withdraw_member",
        "회원01",
        "운영자",
    )
