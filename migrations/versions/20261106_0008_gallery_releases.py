"""Track immutable gallery releases loaded into PostgreSQL.

Revision ID: 20261106_0008
Revises: 20261106_0007
"""

import sqlalchemy as sa
from alembic import op

revision = "20261106_0008"
down_revision = "20261106_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gallery_releases",
        sa.Column("digest", sa.String(length=64), primary_key=True),
        sa.Column("model_version", sa.String(length=120), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("identity_count", sa.Integer(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("gallery_releases")
