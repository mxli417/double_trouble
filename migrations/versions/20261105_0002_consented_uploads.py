"""Add explicitly consented encrypted uploads and embeddings.

Revision ID: 20261105_0002
Revises: 20261101_0001
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "20261105_0002"
down_revision = "20261101_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consented_uploads",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "inference_event_id",
            sa.String(length=36),
            sa.ForeignKey("inference_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("encrypted_image", sa.LargeBinary(), nullable=False),
        sa.Column("image_media_type", sa.String(length=40), nullable=False),
        sa.Column("original_media_type", sa.String(length=40), nullable=False),
        sa.Column("embedding", Vector(128), nullable=False),
        sa.Column("model_version", sa.String(length=120), nullable=False),
        sa.Column("encryption_key_version", sa.String(length=40), nullable=False),
        sa.Column("consent_text_version", sa.String(length=40), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_consented_uploads_inference_event_id", "consented_uploads", ["inference_event_id"], unique=True)
    op.create_index("ix_consented_uploads_user_id", "consented_uploads", ["user_id"])
    op.create_index("ix_consented_uploads_expires_at", "consented_uploads", ["expires_at"])


def downgrade() -> None:
    op.drop_table("consented_uploads")
