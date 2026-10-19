"""SQLAlchemy ORM 모델의 공통 Base."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """모든 ORM 모델이 상속하는 Base."""
