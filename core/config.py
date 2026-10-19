"""환경변수 기반 애플리케이션 설정."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """실행 환경에서 읽는 설정 값."""

    database_url: str
    # 비밀 값이므로 기본값을 두지 않는다. 토큰을 발급하는 시점에 require_jwt_secret()로 확인한다.
    jwt_secret: str
    jwt_algorithm: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    # refresh 토큰 쿠키의 Secure 속성. HTTPS가 아닌 환경에서만 false로 둔다.
    cookie_secure: bool
    # "smtp"(운영) 또는 "console"(개발: 인증 코드를 로그로만 출력). 기본값은 운영 기준인 smtp다.
    mail_backend: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    mail_from: str

    def require_jwt_secret(self) -> str:
        """JWT 서명 키를 반환하고, 설정되지 않았으면 예외를 발생시킨다."""
        if not self.jwt_secret:
            raise RuntimeError("JWT_SECRET 환경변수가 설정되지 않았습니다.")
        return self.jwt_secret


def get_settings() -> Settings:
    """환경변수를 읽어 애플리케이션 설정을 만든다."""
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "mysql+pymysql://momfit:momfit@localhost:3306/momfit",
        ),
        jwt_secret=os.getenv("JWT_SECRET", ""),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
        access_token_expire_minutes=int(
            os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
        ),
        refresh_token_expire_days=int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "14")),
        cookie_secure=os.getenv("COOKIE_SECURE", "true").lower() == "true",
        mail_backend=os.getenv("MAIL_BACKEND") or "smtp",
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT") or "587"),
        smtp_username=os.getenv("SMTP_USERNAME", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        mail_from=os.getenv("MAIL_FROM", ""),
    )


settings = get_settings()
