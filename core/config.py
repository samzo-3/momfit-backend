"""환경변수 기반 애플리케이션 설정."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """실행 환경에서 읽는 설정 값."""

    database_url: str


def get_settings() -> Settings:
    """환경변수를 읽어 애플리케이션 설정을 만든다."""
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "mysql+pymysql://momfit:momfit@localhost:3306/momfit",
        )
    )


settings = get_settings()
