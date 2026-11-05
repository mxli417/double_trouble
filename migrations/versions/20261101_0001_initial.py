"""Initial gallery and Elo tables.

Revision ID: 20261101_0001
Revises:
Create Date: 2026-11-01
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "20261101_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "celebrities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("wikipedia_url", sa.Text()),
        sa.Column("elo", sa.Float(), nullable=False, server_default="1500"),
        sa.Column("vote_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "face_samples",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("celebrity_id", sa.String(length=36), sa.ForeignKey("celebrities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_dataset", sa.String(length=120), nullable=False),
        sa.Column("source_image_id", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("source_license", sa.String(length=200)),
        sa.Column("embedding", Vector(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_face_samples_celebrity_id", "face_samples", ["celebrity_id"])
    op.create_table(
        "duels",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("left_id", sa.String(length=36), sa.ForeignKey("celebrities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("right_id", sa.String(length=36), sa.ForeignKey("celebrities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("winner_id", sa.String(length=36), sa.ForeignKey("celebrities.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "rating_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("duel_id", sa.String(length=36), sa.ForeignKey("duels.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("winner_id", sa.String(length=36), sa.ForeignKey("celebrities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("loser_id", sa.String(length=36), sa.ForeignKey("celebrities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("winner_delta", sa.Float(), nullable=False),
        sa.Column("loser_delta", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512)),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="user"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="invited"),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=True)
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "invitations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False, server_default="activate"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_invitations_user_id", "invitations", ["user_id"])
    op.create_index("ix_invitations_token_hash", "invitations", ["token_hash"], unique=True)
    op.create_index("ix_invitations_expires_at", "invitations", ["expires_at"])
    op.create_table(
        "inference_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=60)),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=120), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_inference_events_request_id", "inference_events", ["request_id"])
    op.create_index("ix_inference_events_user_id", "inference_events", ["user_id"])
    op.create_index("ix_inference_events_created_at", "inference_events", ["created_at"])
    op.create_table(
        "admin_audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("actor_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("subject_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_admin_audit_events_actor_id", "admin_audit_events", ["actor_id"])
    op.create_index("ix_admin_audit_events_action", "admin_audit_events", ["action"])
    op.create_index("ix_admin_audit_events_subject_user_id", "admin_audit_events", ["subject_user_id"])
    op.create_index("ix_admin_audit_events_created_at", "admin_audit_events", ["created_at"])
    op.create_table(
        "user_activity_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_user_activity_events_user_id", "user_activity_events", ["user_id"])
    op.create_index("ix_user_activity_events_action", "user_activity_events", ["action"])
    op.create_index("ix_user_activity_events_created_at", "user_activity_events", ["created_at"])
    op.create_table(
        "bootstrap_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("bootstrap_state")
    op.drop_table("user_activity_events")
    op.drop_table("admin_audit_events")
    op.drop_table("inference_events")
    op.drop_table("invitations")
    op.drop_table("auth_sessions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_table("rating_events")
    op.drop_table("duels")
    op.drop_index("ix_face_samples_celebrity_id", table_name="face_samples")
    op.drop_table("face_samples")
    op.drop_table("celebrities")
