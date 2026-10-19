"""email_verifications 테이블 접근."""

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from models.email_verification import EmailVerification


def add(db: Session, verification: EmailVerification) -> EmailVerification:
    """인증 코드 기록을 추가한다."""
    db.add(verification)
    db.flush()
    return verification


def consume_active(db: Session, email: str, purpose: str, now: datetime) -> None:
    """이메일·용도의 아직 유효한 코드를 모두 무효화한다. 새 코드를 발급할 때 쓴다."""
    db.execute(
        update(EmailVerification)
        .where(
            EmailVerification.email == email,
            EmailVerification.purpose == purpose,
            EmailVerification.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )


def get_latest_active_for_update(
    db: Session, email: str, purpose: str
) -> EmailVerification | None:
    """가장 최근에 발급된 유효 코드를 잠그고 조회한다. 시도 횟수가 동시에 갱신되는 것을 막는다."""
    return db.scalar(
        select(EmailVerification)
        .where(
            EmailVerification.email == email,
            EmailVerification.purpose == purpose,
            EmailVerification.consumed_at.is_(None),
        )
        .order_by(EmailVerification.created_at.desc(), EmailVerification.id.desc())
        .limit(1)
        .with_for_update()
    )


def get_latest_created_at(db: Session, email: str) -> datetime | None:
    """이메일로 마지막에 발송을 요청한 시각을 조회한다. (용도와 무관)"""
    return db.scalar(
        select(func.max(EmailVerification.created_at)).where(
            EmailVerification.email == email
        )
    )


def count_by_email_since(db: Session, email: str, since: datetime) -> int:
    """since 이후 해당 이메일로 발송을 요청한 횟수."""
    return db.scalar(
        select(func.count())
        .select_from(EmailVerification)
        .where(EmailVerification.email == email, EmailVerification.created_at >= since)
    ) or 0


def count_by_ip_since(db: Session, ip: str, since: datetime) -> int:
    """since 이후 해당 IP에서 발송을 요청한 횟수."""
    return db.scalar(
        select(func.count())
        .select_from(EmailVerification)
        .where(EmailVerification.ip == ip, EmailVerification.created_at >= since)
    ) or 0


def delete_by_email(db: Session, email: str) -> None:
    """이메일로 발급된 인증 코드 기록을 모두 삭제한다. 회원 탈퇴 때 쓴다."""
    db.execute(delete(EmailVerification).where(EmailVerification.email == email))
