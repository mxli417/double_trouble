"""Preserve rating history when consented portraits are deleted.

Revision ID: 20261106_0006
Revises: 20261106_0005
"""

from alembic import op

revision = "20261106_0006"
down_revision = "20261106_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_celebrities_consented_upload_id",
        "celebrities",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_celebrities_consented_upload_id",
        "celebrities",
        "consented_uploads",
        ["consented_upload_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_celebrities_consented_upload_id",
        "celebrities",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_celebrities_consented_upload_id",
        "celebrities",
        "consented_uploads",
        ["consented_upload_id"],
        ["id"],
        ondelete="CASCADE",
    )
