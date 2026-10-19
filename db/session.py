"""SQLAlchemy 엔진과 세션 팩토리."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """요청 단위 데이터베이스 세션을 제공한다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
