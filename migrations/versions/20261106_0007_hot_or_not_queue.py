"""Add fair Hot or Not user-profile queue state.

Revision ID: 20261106_0007
Revises: 20261106_0006
"""

import sqlalchemy as sa
from alembic import op

revision = "20261106_0007"
down_revision = "20261106_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "celebrities",
        sa.Column("last_hot_or_not_shown_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_celebrities_last_hot_or_not_shown_at",
        "celebrities",
        ["last_hot_or_not_shown_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_celebrities_last_hot_or_not_shown_at", table_name="celebrities")
    op.drop_column("celebrities", "last_hot_or_not_shown_at")
