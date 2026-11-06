import hmac
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.auth import (
    SESSION_COOKIE,
    audit,
    clear_session_cookie,
    create_session,
    password_hash,
    require_admin,
    token_digest,
)
from app.config import get_settings
from app.db import SessionLocal
from app.face_provider import FaceNotFoundError, get_face_provider
from app.images import ALLOWED_IMAGE_TYPES, normalize_image_bytes
from app.matching import cosine_similarity, validated_embedding
from app.models import (
    AdminAuditEvent,
    AuthSession,
    BootstrapState,
    Celebrity,
    ConsentedUpload,
    FaceSample,
    InferenceEvent,
    Invitation,
    User,
    UserActivityEvent,
)
from app.narration import narrate_match
from app.observability import configure_logging, request_id_from_header, trace_context
from app.sensitive_storage import (
    decrypt_embedding,
    decrypt_image,
    encrypt_embedding,
    encrypt_image,
)

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("double_trouble.api")
limiter = Limiter(key_func=get_remote_address, default_limits=["120/hour"])


app = FastAPI(title="Double Trouble", docs_url=None, redoc_url=None, openapi_url=None)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.mount("/static", StaticFiles(directory=Path(__file__).parent.parent / "static"), name="static")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[host.strip() for host in settings.allowed_hosts.split(",") if host.strip()])
dummy_password_hash = password_hash.hash(secrets.token_urlsafe(32))
_last_retention_sweep = 0.0


def get_db():
    with SessionLocal() as session:
        yield session


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in required")
    auth_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(token)))
    now = datetime.now(UTC)
    if auth_session is None or auth_session.expires_at <= now:
        raise HTTPException(status_code=401, detail="Session expired")
    user = db.get(User, auth_session.user_id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="Account is inactive")
    return user


def current_admin(user: User = Depends(current_user)) -> User:
    return require_admin(user)


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class BootstrapBody(BaseModel):
    secret: str = Field(min_length=32, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=256)


class AcceptInviteBody(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=12, max_length=256)


class InviteBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: str = "user"


class RoleBody(BaseModel):
    role: str


def valid_email(value: str) -> str:
    email = value.strip().casefold()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    return email


def valid_candidate_name(value: str) -> str:
    name = " ".join(value.strip().split())
    if not 2 <= len(name) <= 40 or any(ord(character) < 32 for character in name):
        raise HTTPException(status_code=422, detail="Choose a Hot or Not display name between 2 and 40 characters")
    if "@" in name:
        raise HTTPException(status_code=422, detail="Use a nickname, not an email address, for Hot or Not")
    return name


def candidate_name_from_header(value: str) -> str:
    try:
        decoded = unquote(value, errors="strict")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="Hot or Not display name encoding is invalid") from exc
    return valid_candidate_name(decoded)


def write_inference(
    db: Session,
    user_id: str,
    request_id: str,
    started: float,
    status: str,
    reason: str | None = None,
    results: list | None = None,
    *,
    commit: bool = True,
) -> InferenceEvent:
    event = InferenceEvent(
        id=str(uuid4()), request_id=request_id, user_id=user_id, status=status,
        reason=reason, duration_ms=max(0, round((perf_counter() - started) * 1000)),
        model_version=settings.face_model_version, results=results or [],
    )
    db.add(event)
    if commit:
        db.commit()
    else:
        db.flush()
    return event


def activity(db: Session, user_id: str, action: str, details: dict | None = None) -> None:
    db.add(UserActivityEvent(id=str(uuid4()), user_id=user_id, action=action, details=details or {}))


def deactivate_hot_or_not_uploads(db: Session, upload_ids) -> None:
    db.execute(
        update(Celebrity)
        .where(Celebrity.consented_upload_id.in_(upload_ids))
        .values(
            consented_upload_id=None,
            is_hot_or_not_active=False,
            display_name="Withdrawn guest",
        )
    )


async def read_limited_body(request: Request, limit: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > limit:
                raise HTTPException(status_code=413, detail="Request exceeds the upload limit")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(status_code=413, detail="Request exceeds the upload limit")
        body.extend(chunk)
    return bytes(body)


async def read_limited_image(request: Request) -> bytes:
    return await read_limited_body(request, settings.max_upload_bytes)


def embed_image(image_bytes: bytes) -> tuple[float, ...]:
    try:
        vector = get_face_provider().embed(image_bytes)
    except FaceNotFoundError as exc:
        raise HTTPException(status_code=422, detail="No clear face was detected in the image") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Licensed face model is not configured") from exc
    try:
        return validated_embedding(vector, settings.face_embedding_dim)
    except ValueError as exc:
        detail = "Configured face model has an unexpected embedding dimension" if str(exc) == "dimension" else "Face model returned an invalid embedding"
        status_code = 503 if str(exc) == "dimension" else 422
        raise HTTPException(status_code=status_code, detail=detail) from exc


@app.middleware("http")
async def security_headers(request: Request, call_next):
    global _last_retention_sweep
    sweep_time = perf_counter()
    if request.url.path.startswith("/api/") and sweep_time - _last_retention_sweep > 3600:
        _last_retention_sweep = sweep_time
        try:
            with SessionLocal() as cleanup_db:
                cutoff = datetime.now(UTC) - timedelta(days=settings.inference_retention_days)
                cleanup_db.execute(delete(InferenceEvent).where(InferenceEvent.created_at < cutoff))
                expired_uploads = select(ConsentedUpload.id).where(ConsentedUpload.expires_at < datetime.now(UTC))
                deactivate_hot_or_not_uploads(cleanup_db, expired_uploads)
                cleanup_db.execute(delete(ConsentedUpload).where(ConsentedUpload.expires_at < datetime.now(UTC)))
                audit_cutoff = datetime.now(UTC) - timedelta(days=365)
                cleanup_db.execute(delete(AdminAuditEvent).where(AdminAuditEvent.created_at < audit_cutoff))
                cleanup_db.execute(delete(UserActivityEvent).where(UserActivityEvent.created_at < audit_cutoff))
                cleanup_db.execute(delete(AuthSession).where(AuthSession.expires_at < datetime.now(UTC)))
                cleanup_db.execute(delete(Invitation).where(Invitation.expires_at < datetime.now(UTC)))
                cleanup_db.commit()
        except Exception:
            # Retention cleanup must not make user-facing requests fail.
            logger.warning("retention_cleanup_failed")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        fetch_site = request.headers.get("sec-fetch-site")
        if origin and urlsplit(origin).netloc.casefold() != request.headers.get("host", "").casefold():
            return JSONResponse(status_code=403, content={"detail": "Cross-origin writes are not accepted"})
        if fetch_site == "cross-site":
            return JSONResponse(status_code=403, content={"detail": "Cross-site writes are not accepted"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") or request.url.path in {"/accept", "/admin", "/setup-admin"} else "public, max-age=300"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    return response


@app.middleware("http")
async def request_observability(request: Request, call_next):
    started = perf_counter()
    request_id = request_id_from_header(request.headers.get("x-request-id"))
    trace_id, response_traceparent = trace_context(request.headers.get("traceparent"))
    log_context = {
        "deployment_environment": settings.deployment_environment,
        "experiment_variant": settings.experiment_variant,
        "http_method": request.method,
        "request_id": request_id,
        "trace_id": trace_id,
    }
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "request_failed",
            extra={
                **log_context,
                "http_path": getattr(request.scope.get("route"), "path", "unmatched"),
                "duration_ms": round((perf_counter() - started) * 1000),
                "error_type": type(exc).__name__,
                "http_status": 500,
            },
        )
        response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
    response.headers["X-Request-ID"] = request_id
    response.headers["traceparent"] = response_traceparent
    response.headers["X-Experiment-Variant"] = settings.experiment_variant
    logger.info(
        "request_complete",
        extra={
            **log_context,
            "http_path": getattr(request.scope.get("route"), "path", "unmatched"),
            "duration_ms": round((perf_counter() - started) * 1000),
            "http_status": response.status_code,
        },
    )
    return response


@app.post("/api/setup/first-admin")
@limiter.limit("5/minute")
def setup_first_admin(request: Request, body: BootstrapBody, response: Response, db: Session = Depends(get_db)):
    if not settings.bootstrap_secret:
        raise HTTPException(status_code=404, detail="Initial setup is disabled")
    if not hmac.compare_digest(body.secret, settings.bootstrap_secret):
        raise HTTPException(status_code=403, detail="Setup secret is incorrect")
    from sqlalchemy import text

    db.execute(text("SELECT pg_advisory_xact_lock(88445291)"))
    if db.get(BootstrapState, 1) or (db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.status == "active")) or 0):
        raise HTTPException(status_code=409, detail="Initial administrator setup is already complete")
    email = valid_email(body.email)
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account already exists for this email")
    user = User(id=str(uuid4()), email=email, role="admin", status="active", password_hash=password_hash.hash(body.password))
    db.add(user)
    db.flush()
    db.add(BootstrapState(id=1, completed_at=datetime.now(UTC)))
    audit(db, "admin.bootstrap", actor_id=user.id, subject_user_id=user.id)
    activity(db, user.id, "auth.bootstrap")
    create_session(db, user, response)
    db.commit()
    return {"id": user.id, "email": user.email, "role": user.role}


@app.post("/api/auth/login")
@limiter.limit("8/minute")
def login(request: Request, body: LoginBody, response: Response, db: Session = Depends(get_db)):
    email = valid_email(body.email)
    user = db.scalar(select(User).where(User.email == email))
    stored_hash = user.password_hash if user and user.password_hash else dummy_password_hash
    valid_password = password_hash.verify(body.password, stored_hash)
    if not user or user.status != "active" or not user.password_hash or not valid_password:
        audit(db, "auth.login_failed", details={"reason": "invalid_credentials"})
        db.commit()
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    user.last_login_at = datetime.now(UTC)
    create_session(db, user, response)
    activity(db, user.id, "auth.login")
    if user.role == "admin":
        audit(db, "auth.admin_login", actor_id=user.id)
    db.commit()
    return {"id": user.id, "email": user.email, "role": user.role}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        auth_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(token)))
        if auth_session:
            user = db.get(User, auth_session.user_id)
            if user and user.role == "admin":
                audit(db, "auth.admin_logout", actor_id=user.id)
            if user:
                activity(db, user.id, "auth.logout")
            db.delete(auth_session)
            db.commit()
    clear_session_cookie(response)
    return {"ok": True}


@app.get("/api/auth/me")
def who_am_i(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "role": user.role}


@app.post("/api/auth/accept-invite")
@limiter.limit("5/minute")
def accept_invite(request: Request, body: AcceptInviteBody, response: Response, db: Session = Depends(get_db)):
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == token_digest(body.token)).with_for_update())
    now = datetime.now(UTC)
    if not invitation or invitation.purpose not in {"activate", "reset"} or invitation.accepted_at or invitation.expires_at <= now:
        raise HTTPException(status_code=400, detail="This invitation is invalid or has expired")
    user = db.get(User, invitation.user_id)
    if not user or (invitation.purpose == "activate" and user.status != "invited") or (invitation.purpose == "reset" and user.status != "active"):
        raise HTTPException(status_code=400, detail="This invitation is no longer available")
    user.password_hash = password_hash.hash(body.password)
    user.status = "active"
    if invitation.purpose == "reset":
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    invitation.accepted_at = now
    audit(db, "account.invitation_accepted", subject_user_id=user.id)
    activity(db, user.id, "account.password_set" if invitation.purpose == "activate" else "account.password_reset")
    create_session(db, user, response)
    db.commit()
    return {"id": user.id, "email": user.email, "role": user.role}


@app.get("/api/admin/overview")
def admin_overview(request: Request, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    since = datetime.now(UTC) - timedelta(hours=24)
    day_total = db.scalar(select(func.count()).select_from(InferenceEvent).where(InferenceEvent.created_at >= since)) or 0
    day_failed = db.scalar(select(func.count()).select_from(InferenceEvent).where(InferenceEvent.created_at >= since, InferenceEvent.status != "ok")) or 0
    failed_logins = db.scalar(select(func.count()).select_from(AdminAuditEvent).where(AdminAuditEvent.action == "auth.login_failed", AdminAuditEvent.created_at >= since)) or 0
    active_users = db.scalar(select(func.count()).select_from(User).where(User.status == "active")) or 0
    top_users = db.execute(
        select(User.email, func.count(InferenceEvent.id).label("count"))
        .join(InferenceEvent, InferenceEvent.user_id == User.id)
        .where(InferenceEvent.created_at >= since)
        .group_by(User.email).order_by(func.count(InferenceEvent.id).desc()).limit(10)
    ).all()
    audit(db, "admin.overview.view", actor_id=admin.id)
    db.commit()
    return {"active_users": active_users, "inferences_24h": day_total, "failed_24h": day_failed, "failed_logins_24h": failed_logins,
            "failure_rate_24h": round(day_failed / day_total, 3) if day_total else 0,
            "top_users_24h": [{"email": row.email, "count": row.count, "flagged": row.count >= 50} for row in top_users]}


@app.get("/api/admin/users")
def admin_users(request: Request, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    users = db.scalars(select(User).order_by(User.created_at.desc()).limit(500)).all()
    audit(db, "admin.users.view", actor_id=admin.id)
    db.commit()
    return [{"id": u.id, "email": u.email, "role": u.role, "status": u.status,
             "created_at": u.created_at, "last_login_at": u.last_login_at} for u in users]


@app.post("/api/admin/invitations")
@limiter.limit("20/hour")
def create_invitation(request: Request, body: InviteBody, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    email = valid_email(body.email)
    if body.role not in {"user", "admin"}:
        raise HTTPException(status_code=422, detail="Role must be user or admin")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(hours=settings.invite_hours)
    user = User(id=str(uuid4()), email=email, role=body.role, status="invited", created_by=admin.id)
    db.add(user)
    db.flush()
    db.add(Invitation(id=str(uuid4()), user_id=user.id, token_hash=token_digest(token), expires_at=expires))
    audit(db, "admin.invitation.create", actor_id=admin.id, subject_user_id=user.id, details={"role": body.role})
    db.commit()
    return {"email": email, "role": body.role, "expires_at": expires, "invite_url": str(request.base_url).rstrip("/") + "/accept#token=" + token}


def issue_link(request: Request, db: Session, admin: User, user: User, purpose: str) -> dict:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(hours=settings.invite_hours)
    db.execute(delete(Invitation).where(Invitation.user_id == user.id, Invitation.accepted_at.is_(None)))
    db.add(Invitation(id=str(uuid4()), user_id=user.id, token_hash=token_digest(token), purpose=purpose, expires_at=expires))
    audit(db, f"admin.account.{purpose}_link", actor_id=admin.id, subject_user_id=user.id)
    db.commit()
    return {"email": user.email, "expires_at": expires, "invite_url": str(request.base_url).rstrip("/") + "/accept#token=" + token}


@app.post("/api/admin/users/{user_id}/password-reset")
@limiter.limit("20/hour")
def password_reset_link(request: Request, user_id: str, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    user = db.get(User, user_id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=404, detail="Active account not found")
    return issue_link(request, db, admin, user, "reset")


@app.post("/api/admin/users/{user_id}/invitation")
@limiter.limit("20/hour")
def reissue_invitation(request: Request, user_id: str, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    user = db.get(User, user_id)
    if user is None or user.status != "invited":
        raise HTTPException(status_code=404, detail="Pending invitation not found")
    return issue_link(request, db, admin, user, "activate")


@app.patch("/api/admin/users/{user_id}/status")
def set_user_status(request: Request, user_id: str, status: str, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    if status not in {"active", "disabled"}:
        raise HTTPException(status_code=422, detail="Status must be active or disabled")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if status == "active" and user.password_hash is None:
        raise HTTPException(status_code=409, detail="This invitation has not been accepted; issue a new invitation instead")
    if status == "disabled" and user.password_hash is None:
        raise HTTPException(status_code=409, detail="A pending invitation cannot be disabled; let it expire or resend it")
    if user.id == admin.id and status == "disabled":
        raise HTTPException(status_code=409, detail="You cannot disable your own admin account")
    if user.role == "admin" and user.status == "active" and status == "disabled":
        admins = db.scalars(select(User).where(User.role == "admin", User.status == "active").order_by(User.id).with_for_update()).all()
        if len(admins) <= 1:
            raise HTTPException(status_code=409, detail="The last active admin cannot be disabled")
    user.status = status
    if status == "disabled":
        db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    audit(db, "admin.account.status", actor_id=admin.id, subject_user_id=user.id, details={"status": status})
    db.commit()
    return {"id": user.id, "status": user.status}


@app.patch("/api/admin/users/{user_id}/role")
def set_user_role(request: Request, user_id: str, body: RoleBody, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    if body.role not in {"user", "admin"}:
        raise HTTPException(status_code=422, detail="Role must be user or admin")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if user.id == admin.id and body.role != "admin":
        raise HTTPException(status_code=409, detail="You cannot remove your own admin role")
    if user.role == "admin" and user.status == "active" and body.role != "admin":
        admins = db.scalars(select(User).where(User.role == "admin", User.status == "active").order_by(User.id).with_for_update()).all()
        if len(admins) <= 1:
            raise HTTPException(status_code=409, detail="The last active admin cannot be demoted")
    old_role = user.role
    user.role = body.role
    audit(db, "admin.account.role", actor_id=admin.id, subject_user_id=user.id, details={"from": old_role, "to": body.role})
    db.commit()
    return {"id": user.id, "role": user.role}


@app.get("/api/admin/inferences")
def admin_inferences(request: Request, limit: int = 100, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    if not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 200")
    events = db.execute(
        select(InferenceEvent, User.email).outerjoin(User, InferenceEvent.user_id == User.id)
        .order_by(InferenceEvent.created_at.desc()).limit(limit)
    ).all()
    audit(db, "admin.inferences.view", actor_id=admin.id, details={"limit": limit})
    db.commit()
    return [{"id": event.id, "request_id": event.request_id, "user_email": email,
             "status": event.status, "reason": event.reason, "duration_ms": event.duration_ms,
             "model_version": event.model_version, "results": event.results, "created_at": event.created_at}
            for event, email in events]


@app.get("/api/admin/consented-uploads")
def admin_consented_uploads(
    request: Request, limit: int = 100, db: Session = Depends(get_db), admin: User = Depends(current_admin)
):
    if not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 200")
    rows = db.execute(
        select(ConsentedUpload, User.email).outerjoin(User, ConsentedUpload.user_id == User.id)
        .order_by(ConsentedUpload.created_at.desc()).limit(limit)
    ).all()
    audit(db, "admin.consented_uploads.view", actor_id=admin.id, details={"limit": limit})
    db.commit()
    return [{
        "id": upload.id,
        "user_email": email,
        "model_version": upload.model_version,
        "embedding_dimensions": upload.embedding_dimensions,
        "consent_text_version": upload.consent_text_version,
        "consented_at": upload.consented_at,
        "hot_or_not_consent_version": upload.hot_or_not_consent_version,
        "hot_or_not_consented_at": upload.hot_or_not_consented_at,
        "expires_at": upload.expires_at,
    } for upload, email in rows]


@app.get("/api/admin/consented-uploads/{upload_id}/image")
def admin_consented_upload_image(
    request: Request, upload_id: str, db: Session = Depends(get_db), admin: User = Depends(current_admin)
):
    upload = db.get(ConsentedUpload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Stored upload not found")
    try:
        image = decrypt_image(upload.encrypted_image)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Stored upload cannot be decrypted") from exc
    audit(db, "admin.consented_upload.image_view", actor_id=admin.id, subject_user_id=upload.user_id,
          details={"upload_id": upload.id})
    db.commit()
    return Response(content=image, media_type=upload.image_media_type, headers={"Cache-Control": "no-store"})


@app.get("/api/admin/consented-uploads/{upload_id}/embedding")
def admin_consented_upload_embedding(
    request: Request, upload_id: str, db: Session = Depends(get_db), admin: User = Depends(current_admin)
):
    upload = db.get(ConsentedUpload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Stored upload not found")
    try:
        embedding = decrypt_embedding(upload.encrypted_embedding)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Stored embedding cannot be decrypted") from exc
    audit(db, "admin.consented_upload.embedding_view", actor_id=admin.id, subject_user_id=upload.user_id,
          details={"upload_id": upload.id})
    db.commit()
    return JSONResponse(
        content={"model_version": upload.model_version, "embedding": embedding},
        headers={"Cache-Control": "no-store"},
    )


@app.delete("/api/admin/consented-uploads/{upload_id}")
def admin_delete_consented_upload(
    request: Request, upload_id: str, db: Session = Depends(get_db), admin: User = Depends(current_admin)
):
    upload = db.get(ConsentedUpload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Stored upload not found")
    subject_user_id = upload.user_id
    deactivate_hot_or_not_uploads(db, [upload.id])
    db.delete(upload)
    audit(db, "admin.consented_upload.delete", actor_id=admin.id, subject_user_id=subject_user_id,
          details={"upload_id": upload_id})
    db.commit()
    return {"deleted": True}


@app.delete("/api/me/consented-uploads")
def delete_my_consented_uploads(
    request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    upload_ids = select(ConsentedUpload.id).where(ConsentedUpload.user_id == user.id)
    deactivate_hot_or_not_uploads(db, upload_ids)
    deleted = db.execute(delete(ConsentedUpload).where(ConsentedUpload.user_id == user.id)).rowcount
    activity(db, user.id, "consent.uploads.withdrawn", {"deleted": deleted})
    db.commit()
    return {"deleted": deleted}


@app.get("/api/admin/audit")
def admin_audit(request: Request, limit: int = 100, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    if not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 200")
    audit(db, "admin.audit.view", actor_id=admin.id, details={"limit": limit})
    db.commit()
    events = db.execute(
        select(AdminAuditEvent, User.email).outerjoin(User, AdminAuditEvent.actor_id == User.id)
        .order_by(AdminAuditEvent.created_at.desc()).limit(limit)
    ).all()
    return [{"id": event.id, "actor_email": email, "action": event.action,
             "subject_user_id": event.subject_user_id, "details": event.details, "created_at": event.created_at}
            for event, email in events]


@app.get("/api/admin/activity")
def admin_activity(request: Request, limit: int = 100, db: Session = Depends(get_db), admin: User = Depends(current_admin)):
    if not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 200")
    audit(db, "admin.activity.view", actor_id=admin.id, details={"limit": limit})
    db.commit()
    events = db.execute(
        select(UserActivityEvent, User.email).outerjoin(User, UserActivityEvent.user_id == User.id)
        .order_by(UserActivityEvent.created_at.desc()).limit(limit)
    ).all()
    return [{"id": event.id, "user_email": email, "action": event.action,
             "details": event.details, "created_at": event.created_at} for event, email in events]


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    from sqlalchemy import text

    db.execute(text("SELECT 1"))
    hot_or_not_candidates = db.scalar(
        select(func.count()).select_from(Celebrity).where(
            Celebrity.is_hot_or_not_active.is_(True),
            or_(Celebrity.candidate_type != "user", Celebrity.consented_upload_id.is_not(None)),
        )
    ) or 0
    return {
        "status": "ok",
        "matching_enabled": settings.matching_enabled,
        "gallery_loaded": bool(db.scalar(select(func.count()).select_from(FaceSample))),
        "hot_or_not_ready": hot_or_not_candidates >= 2,
        "environment": settings.deployment_environment,
        "experiment_variant": settings.experiment_variant,
    }


@app.get("/api/ready")
def ready(db: Session = Depends(get_db)):
    from sqlalchemy import text

    db.execute(text("SELECT 1"))
    gallery_samples = db.scalar(select(func.count()).select_from(FaceSample)) or 0
    hot_or_not_candidates = db.scalar(
        select(func.count()).select_from(Celebrity).where(
            Celebrity.is_hot_or_not_active.is_(True),
            or_(Celebrity.candidate_type != "user", Celebrity.consented_upload_id.is_not(None)),
        )
    ) or 0
    failures = []
    if settings.gallery_required and gallery_samples == 0:
        failures.append("gallery_not_loaded")
    if settings.gallery_required and hot_or_not_candidates < 2:
        failures.append("hot_or_not_not_ready")
    if settings.matching_enabled:
        try:
            provider = get_face_provider()
            if getattr(provider, "embedding_dim", settings.face_embedding_dim) != settings.face_embedding_dim:
                failures.append("face_model_dimension_mismatch")
        except RuntimeError:
            failures.append("face_model_unavailable")
    content = {
        "status": "ready" if not failures else "not_ready",
        "matching_enabled": settings.matching_enabled,
        "gallery_loaded": gallery_samples > 0,
        "hot_or_not_ready": hot_or_not_candidates >= 2,
        "environment": settings.deployment_environment,
    }
    if failures:
        content["failures"] = failures
        return JSONResponse(status_code=503, content=content)
    return content


@app.get("/api/features")
def features(user: User = Depends(current_user)):
    return {
        "retention_available": settings.retention_available,
        "hot_or_not_available": settings.retention_available,
        "retained_upload_days": settings.retained_upload_days,
        "narration_available": settings.narration_available,
    }


@app.get("/api/rankings")
@limiter.limit("30/minute")
def rankings(request: Request, limit: int = 20, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    current_upload_ids = select(ConsentedUpload.id).where(
        ConsentedUpload.hot_or_not_consented_at.is_not(None),
        ConsentedUpload.expires_at > datetime.now(UTC),
    )
    ranked_candidates = (
        select(
            Celebrity.id.label("id"),
            Celebrity.display_name.label("name"),
            Celebrity.candidate_type.label("candidate_type"),
            Celebrity.owner_user_id.label("owner_user_id"),
            Celebrity.elo.label("elo"),
            Celebrity.vote_count.label("votes"),
            func.rank().over(order_by=Celebrity.elo.desc()).label("rank"),
        )
        .where(
            Celebrity.is_hot_or_not_active.is_(True),
            or_(
                Celebrity.candidate_type != "user",
                Celebrity.consented_upload_id.in_(current_upload_ids),
            ),
        )
        .subquery()
    )
    rows = db.execute(
        select(ranked_candidates)
        .order_by(ranked_candidates.c.rank, ranked_candidates.c.name)
        .limit(limit)
    ).mappings().all()
    own_candidate = db.execute(
        select(ranked_candidates).where(ranked_candidates.c.owner_user_id == user.id)
    ).mappings().first()
    human_candidates = db.execute(
        select(ranked_candidates)
        .where(ranked_candidates.c.candidate_type == "user")
        .order_by(ranked_candidates.c.rank, ranked_candidates.c.name)
    ).mappings().all()

    def public_candidate(row, *, include_owner: bool = False) -> dict:
        candidate = {
            "id": row["id"],
            "name": row["name"],
            "candidate_type": row["candidate_type"],
            "rank": int(row["rank"]),
            "image_url": f"/api/hot-or-not/candidates/{row['id']}/image",
            "elo": round(row["elo"]),
            "votes": row["votes"],
        }
        if include_owner:
            candidate["is_owner"] = row["owner_user_id"] == user.id
        return candidate

    return {
        "rankings": [public_candidate(row, include_owner=True) for row in rows],
        "my_candidate": None if own_candidate is None else public_candidate(own_candidate),
        "human_players": [
            public_candidate(row, include_owner=True)
            for row in human_candidates
        ],
    }


@app.get("/api/hot-or-not/candidates/{candidate_id}/image")
@limiter.limit("120/minute")
def hot_or_not_candidate_image(
    candidate_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    candidate = db.get(Celebrity, candidate_id)
    if candidate is None or not candidate.is_hot_or_not_active:
        raise HTTPException(status_code=404, detail="Hot or Not portrait not found")
    if candidate.candidate_type == "user":
        upload = db.get(ConsentedUpload, candidate.consented_upload_id)
        if (
            upload is None
            or upload.hot_or_not_consented_at is None
            or upload.expires_at <= datetime.now(UTC)
        ):
            raise HTTPException(status_code=404, detail="Hot or Not portrait is no longer available")
        try:
            image = decrypt_image(upload.encrypted_image)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="Hot or Not portrait cannot be decrypted") from exc
        return Response(content=image, media_type=upload.image_media_type, headers={"Cache-Control": "no-store"})
    if candidate.portrait_image is None or candidate.portrait_media_type is None:
        raise HTTPException(status_code=404, detail="Gallery portrait not available")
    return Response(
        content=candidate.portrait_image,
        media_type=candidate.portrait_media_type,
        headers={"Cache-Control": "private, no-store"},
    )


@app.post("/api/match")
@limiter.limit("8/minute")
async def match(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    started = perf_counter()
    request_id = str(uuid4())
    status, reason, audit_results = "error", "internal_error", []
    try:
        retention_consent = request.headers.get("x-retention-consent", "false").casefold() == "true"
        hot_or_not_consent = request.headers.get("x-hot-or-not-consent", "false").casefold() == "true"
        narration_consent = request.headers.get("x-narration-consent", "false").casefold() == "true"
        if hot_or_not_consent and not retention_consent:
            status, reason = "rejected", "hot_or_not_requires_retention"
            raise HTTPException(status_code=422, detail="Hot or Not participation requires encrypted photo retention consent")
        if retention_consent and not settings.retention_available:
            status, reason = "blocked", "retention_unavailable"
            raise HTTPException(status_code=503, detail="Consented upload storage is not configured")
        hot_or_not_name = (
            candidate_name_from_header(request.headers.get("x-hot-or-not-name", ""))
            if hot_or_not_consent
            else None
        )
        now = datetime.now(UTC)
        recent = db.scalar(select(func.count()).select_from(InferenceEvent).where(InferenceEvent.user_id == user.id, InferenceEvent.created_at >= now - timedelta(minutes=1))) or 0
        daily = db.scalar(select(func.count()).select_from(InferenceEvent).where(InferenceEvent.user_id == user.id, InferenceEvent.created_at >= now - timedelta(days=1))) or 0
        if recent >= 8 or daily >= settings.inference_daily_limit:
            status, reason = "blocked", "account_rate_limit"
            raise HTTPException(status_code=429, detail="Inference limit reached. Please try again later.")
        if not settings.matching_enabled:
            status, reason = "blocked", "matching_disabled"
            raise HTTPException(status_code=503, detail="Lookalike matching is not enabled yet")
        if not db.scalar(select(func.count()).select_from(FaceSample)):
            status, reason = "blocked", "gallery_not_loaded"
            raise HTTPException(status_code=503, detail="The reference gallery is not loaded")
        if request.headers.get("content-type", "").split(";", maxsplit=1)[0] not in ALLOWED_IMAGE_TYPES:
            status, reason = "rejected", "unsupported_type"
            raise HTTPException(status_code=415, detail="Upload a JPEG, PNG, WebP, HEIC, or HEIF image")

        body = await read_limited_image(request)
        if len(body) > settings.max_upload_bytes:
            status, reason = "rejected", "upload_too_large"
            raise HTTPException(status_code=413, detail="Image exceeds the upload limit")
        try:
            normalized_image = normalize_image_bytes(body, settings.max_image_pixels, settings.image_max_side)
            vector = embed_image(normalized_image)
        except HTTPException as exc:
            if exc.status_code in {413, 415}:
                status, reason = "rejected", "invalid_image"
            elif exc.status_code == 503:
                status, reason = "error", "model_unavailable"
            else:
                status, reason = ("rejected", "face_not_found") if exc.detail == "No clear face was detected in the image" else ("error", "invalid_model_output")
            raise
        # Query vectors remain request-local unless the authenticated user explicitly opted in.
        from sqlalchemy import text

        result = db.execute(
            text("""WITH identity_distances AS (
                     SELECT c.id, c.display_name, c.wikipedia_url,
                            (c.portrait_image IS NOT NULL AND c.is_hot_or_not_active) AS has_portrait,
                            MIN(fs.embedding <=> CAST(:embedding AS vector)) AS distance
                     FROM face_samples AS fs
                     JOIN celebrities AS c ON c.id = fs.celebrity_id
                     GROUP BY c.id, c.display_name, c.wikipedia_url, c.portrait_image, c.is_hot_or_not_active
                 )
                 SELECT id, display_name, wikipedia_url, has_portrait, 1 - distance AS similarity
                 FROM identity_distances
                 ORDER BY distance
                 LIMIT 5"""),
            {"embedding": str(list(vector))},
        ).mappings().all()
        if not result:
            status, reason = "blocked", "gallery_not_loaded"
            raise HTTPException(status_code=503, detail="The reference gallery is not loaded")
        matches = [
            {
                "id": row["id"],
                "name": row["display_name"],
                "wikipedia_url": row["wikipedia_url"],
                "similarity": round(float(row["similarity"]), 3),
                "image_url": f"/api/hot-or-not/candidates/{row['id']}/image" if row["has_portrait"] else None,
            }
            for row in result
        ]
        audit_results = [{"celebrity_id": row["id"], "name": row["display_name"], "similarity": round(float(row["similarity"]), 3)} for row in result]
        status, reason = "ok", None
        event = write_inference(db, user.id, request_id, started, status, results=audit_results, commit=False)
        if retention_consent:
            retained_image = normalize_image_bytes(
                normalized_image, settings.max_image_pixels, settings.retained_image_max_side, quality=82
            )
            retained_upload = ConsentedUpload(
                id=str(uuid4()), inference_event_id=event.id, user_id=user.id,
                encrypted_image=encrypt_image(retained_image), image_media_type="image/jpeg",
                original_media_type=request.headers.get("content-type", "").split(";", maxsplit=1)[0],
                encrypted_embedding=encrypt_embedding(list(vector)), embedding_dimensions=len(vector),
                model_version=settings.face_model_version,
                encryption_key_version=settings.data_encryption_key_version,
                consent_text_version=settings.consent_text_version, consented_at=now,
                hot_or_not_consent_version=settings.consent_text_version if hot_or_not_consent else None,
                hot_or_not_consented_at=now if hot_or_not_consent else None,
                expires_at=now + timedelta(days=settings.retained_upload_days),
            )
            db.add(retained_upload)
            db.flush()
            if hot_or_not_consent:
                candidate = db.scalar(select(Celebrity).where(Celebrity.owner_user_id == user.id))
                if candidate is None:
                    candidate = Celebrity(
                        id=str(uuid4()),
                        display_name=hot_or_not_name,
                        candidate_type="user",
                        owner_user_id=user.id,
                        consented_upload_id=retained_upload.id,
                        is_hot_or_not_active=True,
                    )
                    db.add(candidate)
                else:
                    candidate.display_name = hot_or_not_name
                    candidate.candidate_type = "user"
                    candidate.consented_upload_id = retained_upload.id
                    candidate.is_hot_or_not_active = True
                    candidate.last_hot_or_not_shown_at = None
                activity(
                    db,
                    user.id,
                    "hot_or_not.consent.granted",
                    {"candidate_id": candidate.id, "days": settings.retained_upload_days},
                )
            activity(db, user.id, "consent.upload.retained", {"days": settings.retained_upload_days})
        db.commit()
        narration = await narrate_match(matches) if narration_consent else None
        return {"matches": matches, "narration": narration}
    except HTTPException:
        write_inference(db, user.id, request_id, started, status, reason, audit_results)
        raise
    except Exception:
        db.rollback()
        write_inference(db, user.id, request_id, started, status, reason, audit_results)
        raise


@app.post("/api/self-similarity")
@limiter.limit("4/minute")
async def self_similarity(request: Request, user: User = Depends(current_user)):
    if not settings.matching_enabled:
        raise HTTPException(status_code=503, detail="Lookalike matching is not enabled yet")
    if request.headers.get("content-type", "").split(";", maxsplit=1)[0] != "application/octet-stream":
        raise HTTPException(status_code=415, detail="Self-check requires two encoded images")
    if request.headers.get("x-first-image-type") not in ALLOWED_IMAGE_TYPES or request.headers.get("x-second-image-type") not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Upload JPEG, PNG, WebP, HEIC, or HEIF images")
    try:
        second_offset = int(request.headers.get("x-second-image-offset", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Second image offset is invalid") from exc
    body = await read_limited_body(request, settings.max_upload_bytes * 2)
    if not 0 < second_offset < len(body):
        raise HTTPException(status_code=400, detail="Two images are required")
    first_image, second_image = body[:second_offset], body[second_offset:]
    if len(first_image) > settings.max_upload_bytes or len(second_image) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Image exceeds the upload limit")
    normalized_first = normalize_image_bytes(first_image, settings.max_image_pixels, settings.image_max_side)
    normalized_second = normalize_image_bytes(second_image, settings.max_image_pixels, settings.image_max_side)
    first_vector = embed_image(normalized_first)
    second_vector = embed_image(normalized_second)
    try:
        similarity = cosine_similarity(first_vector, second_vector)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Face model returned an invalid embedding") from exc
    # Images and both query embeddings fall out of scope with this request and are never persisted or logged.
    return {
        "similarity": round(similarity, 3),
        "threshold": settings.self_similarity_threshold,
        "passed": similarity >= settings.self_similarity_threshold,
    }


@app.get("/api/duel")
@limiter.limit("30/minute")
def duel(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    gallery_candidates = db.scalars(
        select(Celebrity)
        .where(
            Celebrity.is_hot_or_not_active.is_(True),
            Celebrity.candidate_type != "user",
            Celebrity.portrait_image.is_not(None),
        )
        .order_by(func.random())
        .limit(250)
    ).all()
    queued_user = db.scalar(
        select(Celebrity)
        .join(ConsentedUpload, Celebrity.consented_upload_id == ConsentedUpload.id)
        .where(
            Celebrity.is_hot_or_not_active.is_(True),
            Celebrity.candidate_type == "user",
            Celebrity.owner_user_id != user.id,
            ConsentedUpload.hot_or_not_consented_at.is_not(None),
            ConsentedUpload.expires_at > datetime.now(UTC),
        )
        .order_by(
            Celebrity.last_hot_or_not_shown_at.asc().nullsfirst(),
            ConsentedUpload.hot_or_not_consented_at.desc(),
        )
        .limit(1)
    )
    if queued_user is not None and gallery_candidates:
        left = queued_user
        nearby_gallery = sorted(gallery_candidates, key=lambda item: abs(item.elo - left.elo))
        right = nearby_gallery[uuid4().int % min(5, len(nearby_gallery))]
    elif len(gallery_candidates) >= 2:
        left = gallery_candidates[uuid4().int % len(gallery_candidates)]
        right_candidates = [item for item in gallery_candidates if item.id != left.id]
        right_candidates.sort(key=lambda item: abs(item.elo - left.elo))
        right = right_candidates[uuid4().int % min(5, len(right_candidates))]
    else:
        raise HTTPException(status_code=503, detail="Hot or Not needs at least two consented or cleared portraits")
    # Fresh or least-recently shown user profiles lead the queue and face a nearby gallery rating.
    if left.candidate_type == "user":
        left.last_hot_or_not_shown_at = datetime.now(UTC)
    from app.models import Duel

    duel_id = str(uuid4())
    db.add(Duel(id=duel_id, left_id=left.id, right_id=right.id))
    activity(
        db,
        user.id,
        "hot_or_not.loaded",
        {"duel_id": duel_id, "candidate_ids": [left.id, right.id]},
    )
    db.commit()
    return {
        "id": duel_id,
        "left": {
            "id": left.id,
            "name": left.display_name,
            "candidate_type": left.candidate_type,
            "image_url": f"/api/hot-or-not/candidates/{left.id}/image",
        },
        "right": {
            "id": right.id,
            "name": right.display_name,
            "candidate_type": right.candidate_type,
            "image_url": f"/api/hot-or-not/candidates/{right.id}/image",
        },
    }


@app.post("/api/duel/{duel_id}/vote")
@limiter.limit("30/minute")
def vote(duel_id: str, request: Request, winner_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from app.elo import update_pair
    from app.models import Duel, RatingEvent

    try:
        current_duel = db.scalar(select(Duel).where(Duel.id == duel_id).with_for_update())
        if current_duel is None:
            raise HTTPException(status_code=404, detail="Duel not found")
        if current_duel.winner_id is not None:
            raise HTTPException(status_code=409, detail="This duel has already been voted on")
        if winner_id not in {current_duel.left_id, current_duel.right_id}:
            raise HTTPException(status_code=422, detail="Winner must be one of the duel candidates")
        loser_id = current_duel.right_id if winner_id == current_duel.left_id else current_duel.left_id
        people = db.scalars(select(Celebrity).where(Celebrity.id.in_([winner_id, loser_id])).order_by(Celebrity.id).with_for_update()).all()
        by_id = {person.id: person for person in people}
        winner, loser = by_id[winner_id], by_id[loser_id]
        new_winner, new_loser = update_pair(winner.elo, loser.elo)
        winner_delta, loser_delta = new_winner - winner.elo, new_loser - loser.elo
        winner.elo, loser.elo = new_winner, new_loser
        winner.vote_count += 1
        loser.vote_count += 1
        current_duel.winner_id = winner_id
        db.add(RatingEvent(id=str(uuid4()), duel_id=duel_id, winner_id=winner_id, loser_id=loser_id, winner_delta=winner_delta, loser_delta=loser_delta))
        activity(
            db,
            user.id,
            "hot_or_not.vote",
            {"duel_id": duel_id, "winner_id": winner_id, "loser_id": loser_id},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"ok": True, "winner_elo": round(new_winner), "loser_elo": round(new_loser)}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(Path(__file__).parent.parent / "static" / "index.html")


@app.get("/accept", include_in_schema=False)
def accept_page():
    return FileResponse(Path(__file__).parent.parent / "static" / "accept.html")


@app.get("/setup-admin", include_in_schema=False)
def setup_admin_page():
    return FileResponse(Path(__file__).parent.parent / "static" / "setup-admin.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(Path(__file__).parent.parent / "static" / "admin.html")
