"""Align created-at nullability with the ORM models.

Revision ID: 20261105_0004
Revises: 20261105_0003
"""

import sqlalchemy as sa
from alembic import op

revision = "20261105_0004"
down_revision = "20261105_0003"
branch_labels = None
depends_on = None

TABLES = (
    "admin_audit_events",
    "auth_sessions",
    "celebrities",
    "consented_uploads",
    "duels",
    "face_samples",
    "inference_events",
    "invitations",
    "rating_events",
    "user_activity_events",
    "users",
)


def upgrade() -> None:
    for table in TABLES:
        op.execute(sa.text(f'UPDATE "{table}" SET created_at=now() WHERE created_at IS NULL'))
        op.alter_column(table, "created_at", existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "created_at", existing_type=sa.DateTime(timezone=True), nullable=True)
