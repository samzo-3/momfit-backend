"""user 쪽 모델이 timestamp mixin을 상속해 생성·수정 시각 컬럼을 갖는지 검증한다."""

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session, configure_mappers

from models import AuthIdentity, EmailVerification, RefreshToken, User
from models.timestamp_mixin import CreatedAtMixin, TimestampMixin


def test_모든_매퍼가_초기화된다() -> None:
    configure_mappers()


@pytest.mark.parametrize(
    ("model", "mixin"),
    [
        (User, TimestampMixin),
        (AuthIdentity, CreatedAtMixin),
        (RefreshToken, CreatedAtMixin),
        (EmailVerification, CreatedAtMixin),
    ],
)
def test_모델이_mixin을_상속한다(model: type, mixin: type) -> None:
    assert issubclass(model, mixin)


def test_수정_시각은_User만_가진다() -> None:
    assert "modified_at" in User.__table__.c
    for model in (AuthIdentity, RefreshToken, EmailVerification):
        assert "modified_at" not in model.__table__.c
        assert "created_at" in model.__table__.c


def test_이메일_인증_created_at_인덱스가_유지된다(db_session: Session) -> None:
    indexes = inspect(db_session.get_bind()).get_indexes("email_verifications")
    assert any(i["column_names"] == ["created_at"] for i in indexes)
