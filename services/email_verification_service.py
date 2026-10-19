"""이메일 인증 코드 발송·검증 비즈니스 로직."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from core.clock import utc_now
from core.config import settings
from core.errors import AppError
from core.security import EMAIL_TOKEN_EXPIRE_SECONDS, create_email_verification_token
from models.email_verification import EmailVerification
from repositories import email_verification_repository, user_repository
from services.mailer import Mail

CODE_EXPIRE_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_INTERVAL_SECONDS = 60
MAX_SENDS_PER_EMAIL_PER_DAY = 5
MAX_SENDS_PER_IP_PER_DAY = 20

_SUBJECTS = {
    "signup": "[맘핏] 회원가입 이메일 인증 코드",
    "password_reset": "[맘핏] 비밀번호 재설정 인증 코드",
}


def _hash_code(email: str, purpose: str, code: str) -> str:
    # 6자리 코드는 해시만으로는 쉽게 복원되므로 서버 비밀 값을 섞는다. 실제 방어는 시도 횟수 제한이다.
    key = settings.require_jwt_secret().encode()
    return hmac.new(key, f"{email}:{purpose}:{code}".encode(), hashlib.sha256).hexdigest()


def _build_mail(email: str, purpose: str, code: str) -> Mail:
    return Mail(
        to=email,
        subject=_SUBJECTS[purpose],
        body=(
            f"인증 코드: {code}\n\n"
            f"{CODE_EXPIRE_MINUTES}분 안에 입력해 주세요.\n"
            "본인이 요청하지 않았다면 이 메일을 무시해 주세요."
        ),
    )


def _should_send(db: Session, email: str, purpose: str) -> bool:
    """실제로 메일을 보낼 대상인지 판단한다.

    가입은 이미 가입된 이메일이면, 비밀번호 재설정은 가입되지 않은 이메일이면 보내지 않는다.
    어느 쪽이든 호출자에게는 같은 응답을 주어 계정 존재 여부가 드러나지 않게 한다.
    """
    exists = user_repository.get_by_email(db, email) is not None
    return not exists if purpose == "signup" else exists


def _check_rate_limit(db: Session, email: str, ip: str | None, now: datetime) -> None:
    last_sent = email_verification_repository.get_latest_created_at(db, email)
    if last_sent is not None:
        wait = RESEND_INTERVAL_SECONDS - int((now - last_sent).total_seconds())
        if wait > 0:
            raise AppError(
                429,
                "RATE_LIMITED",
                f"{wait}초 후에 다시 요청해 주세요.",
                headers={"Retry-After": str(wait)},
            )

    since = now - timedelta(days=1)
    too_many_for_email = (
        email_verification_repository.count_by_email_since(db, email, since)
        >= MAX_SENDS_PER_EMAIL_PER_DAY
    )
    too_many_for_ip = ip is not None and (
        email_verification_repository.count_by_ip_since(db, ip, since)
        >= MAX_SENDS_PER_IP_PER_DAY
    )
    if too_many_for_email or too_many_for_ip:
        raise AppError(
            429, "RATE_LIMITED", "오늘 요청 가능한 횟수를 초과했습니다. 내일 다시 시도해 주세요."
        )


def send_code(
    db: Session,
    email: str,
    purpose: str,
    ip: str | None,
    now: datetime | None = None,
) -> Mail | None:
    """인증 코드를 만들어 저장하고, 보내야 할 메일을 반환한다. 보낼 필요가 없으면 None.

    발송 대상 여부와 상관없이 기록은 항상 남겨, 발송 제한이 계정 존재 여부에 따라 달라지지 않게 한다.
    메일 발송은 호출자가 응답 이후에 수행한다. (발송 지연으로 존재 여부가 드러나지 않게 하기 위해)
    """
    now = now or utc_now()
    _check_rate_limit(db, email, ip, now)

    code = f"{secrets.randbelow(10**6):06d}"
    email_verification_repository.consume_active(db, email, purpose, now)
    email_verification_repository.add(
        db,
        EmailVerification(
            email=email,
            purpose=purpose,
            code_hash=_hash_code(email, purpose, code),
            ip=ip,
            expires_at=now + timedelta(minutes=CODE_EXPIRE_MINUTES),
            created_at=now,
        ),
    )
    send = _should_send(db, email, purpose)
    db.commit()
    return _build_mail(email, purpose, code) if send else None


def verify_code(
    db: Session, email: str, purpose: str, code: str, now: datetime | None = None
) -> tuple[str, int]:
    """코드를 검증하고 (email_verification_token, expires_in)을 반환한다."""
    now = now or utc_now()
    invalid = AppError(400, "CODE_INVALID", "인증 코드가 올바르지 않습니다.")

    verification = email_verification_repository.get_latest_active_for_update(
        db, email, purpose
    )
    if verification is None:
        raise invalid
    if verification.expires_at <= now:
        raise AppError(400, "CODE_EXPIRED", "인증 코드가 만료되었습니다. 다시 요청해 주세요.")

    if not hmac.compare_digest(verification.code_hash, _hash_code(email, purpose, code)):
        verification.attempts += 1
        if verification.attempts >= MAX_ATTEMPTS:
            verification.consumed_at = now
        db.commit()
        raise invalid

    verification.consumed_at = now
    db.commit()
    return create_email_verification_token(email, purpose), EMAIL_TOKEN_EXPIRE_SECONDS
