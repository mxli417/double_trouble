from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Celebrity(Base):
    __tablename__ = "celebrities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    wikipedia_url: Mapped[str | None] = mapped_column(Text)
    elo: Mapped[float] = mapped_column(Float, nullable=False, default=1500)
    vote_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FaceSample(Base):
    __tablename__ = "face_samples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    celebrity_id: Mapped[str] = mapped_column(ForeignKey("celebrities.id", ondelete="CASCADE"), nullable=False, index=True)
    source_dataset: Mapped[str] = mapped_column(String(120), nullable=False)
    source_image_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_license: Mapped[str | None] = mapped_column(String(200))
    embedding: Mapped[list[float]] = mapped_column(Vector(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Duel(Base):
    __tablename__ = "duels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    left_id: Mapped[str] = mapped_column(ForeignKey("celebrities.id", ondelete="CASCADE"), nullable=False)
    right_id: Mapped[str] = mapped_column(ForeignKey("celebrities.id", ondelete="CASCADE"), nullable=False)
    winner_id: Mapped[str | None] = mapped_column(ForeignKey("celebrities.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RatingEvent(Base):
    __tablename__ = "rating_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    duel_id: Mapped[str] = mapped_column(ForeignKey("duels.id", ondelete="CASCADE"), unique=True, nullable=False)
    winner_id: Mapped[str] = mapped_column(ForeignKey("celebrities.id", ondelete="CASCADE"), nullable=False)
    loser_id: Mapped[str] = mapped_column(ForeignKey("celebrities.id", ondelete="CASCADE"), nullable=False)
    winner_delta: Mapped[float] = mapped_column(Float, nullable=False)
    loser_delta: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="invited")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False, default="activate")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InferenceEvent(Base):
    __tablename__ = "inference_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(60))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(String(120), nullable=False)
    results: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class ConsentedUpload(Base):
    __tablename__ = "consented_uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    inference_event_id: Mapped[str] = mapped_column(
        ForeignKey("inference_events.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    encrypted_image: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    image_media_type: Mapped[str] = mapped_column(String(40), nullable=False, default="image/jpeg")
    original_media_type: Mapped[str] = mapped_column(String(40), nullable=False)
    encrypted_embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(String(120), nullable=False)
    encryption_key_version: Mapped[str] = mapped_column(String(40), nullable=False)
    consent_text_version: Mapped[str] = mapped_column(String(40), nullable=False)
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminAuditEvent(Base):
    __tablename__ = "admin_audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    subject_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class UserActivityEvent(Base):
    __tablename__ = "user_activity_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class BootstrapState(Base):
    __tablename__ = "bootstrap_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
