import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException, Response
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AdminAuditEvent, AuthSession, User

password_hash = PasswordHash.recommended()
SESSION_COOKIE = "lookalike_session"


def token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def audit(db: Session, action: str, actor_id: str | None = None, subject_user_id: str | None = None, details: dict | None = None) -> None:
    db.add(AdminAuditEvent(
        id=str(uuid4()), actor_id=actor_id, action=action,
        subject_user_id=subject_user_id, details=details or {},
    ))


def create_session(db: Session, user: User, response: Response) -> None:
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    db.add(AuthSession(
        id=str(uuid4()), user_id=user.id, token_hash=token_digest(token),
        expires_at=now + timedelta(hours=settings.session_hours),
    ))
    response.set_cookie(
        SESSION_COOKIE, token, max_age=settings.session_hours * 3600,
        httponly=True, secure=settings.session_cookie_secure, samesite="strict", path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=get_settings().session_cookie_secure, samesite="strict")


def require_admin(user: User) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
