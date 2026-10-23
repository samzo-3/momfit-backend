"""개발용 MomFit DB 테이블 생성."""

from db.base import Base
from db.session import engine

# 모든 ORM 모델 등록
import models  # noqa: F401


def create_tables():
    url = engine.url

    # Windows 로컬 개발 DB만 허용
    if not (
        url.host in {"localhost", "127.0.0.1"}
        and url.port == 3307
        and url.database == "momfit-db"
    ):
        raise RuntimeError(
            "로컬 MomFit DB가 아닙니다."
        )

    tables = list(Base.metadata.tables.keys())

    if not tables:
        raise RuntimeError("등록된 테이블이 없습니다.")

    print("DB HOST:", url.host)
    print("DB PORT:", url.port)
    print("DB NAME:", url.database)

    print("\n등록된 테이블:")
    for table in tables:
        print("-", table)

    # 테이블이 없으면 생성, 있으면 유지
    Base.metadata.create_all(bind=engine)

    print("\n테이블 생성 완료!")


if __name__ == "__main__":
    create_tables()