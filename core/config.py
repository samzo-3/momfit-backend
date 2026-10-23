"""환경변수 기반 애플리케이션 설정."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 프로젝트 루트의 .env 읽기
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

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
    # 카카오 로그인. 비어 있으면 카카오 로그인은 동작하지 않는다. (비밀 값이라 기본값 없음)
    kakao_client_id: str
    kakao_client_secret: str
    # 카카오 콘솔에 등록한 Redirect URI와 정확히 같아야 한다. 프록시를 거치는 프론트 주소 기준이다.
    kakao_redirect_uri: str
    # 회원 탈퇴 시 카카오 연결 해제(unlink)에 쓰는 서비스 앱 어드민 키
    kakao_admin_key: str
    # 카카오 로그인 후 돌아갈 프론트 주소. 비워 두면 같은 도메인(프록시)의 상대 경로로 보낸다.
    frontend_url: str
    # 탈퇴 후 데이터를 그대로 두는 유예 기간(일). 이 기간 안에는 로그인해서 복구할 수 있다.
    account_grace_days: int
    # 유예 기간이 지난 계정을 삭제하는 주기(시간). 0이면 앱 안의 주기 작업을 끈다.
    account_purge_interval_hours: int

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
        kakao_client_id=os.getenv("KAKAO_CLIENT_ID", ""),
        kakao_client_secret=os.getenv("KAKAO_CLIENT_SECRET", ""),
        kakao_redirect_uri=os.getenv("KAKAO_REDIRECT_URI", ""),
        kakao_admin_key=os.getenv("KAKAO_ADMIN_KEY", ""),
        frontend_url=os.getenv("FRONTEND_URL", "").rstrip("/"),
        account_grace_days=int(os.getenv("ACCOUNT_GRACE_DAYS") or "30"),
        account_purge_interval_hours=int(
            os.getenv("ACCOUNT_PURGE_INTERVAL_HOURS") or "6"
        ),
    )


settings = get_settings()
