"""Add gallery portraits and consented Hot or Not candidates.

Revision ID: 20261106_0005
Revises: 20261105_0004
"""

import sqlalchemy as sa
from alembic import op

revision = "20261106_0005"
down_revision = "20261105_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "celebrities",
        sa.Column("candidate_type", sa.String(length=20), nullable=False, server_default="gallery"),
    )
    op.add_column("celebrities", sa.Column("owner_user_id", sa.String(length=36)))
    op.add_column("celebrities", sa.Column("consented_upload_id", sa.String(length=36)))
    op.add_column("celebrities", sa.Column("portrait_image", sa.LargeBinary()))
    op.add_column("celebrities", sa.Column("portrait_media_type", sa.String(length=40)))
    op.add_column(
        "celebrities",
        sa.Column("is_hot_or_not_active", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_foreign_key(
        "fk_celebrities_owner_user_id",
        "celebrities",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_celebrities_consented_upload_id",
        "celebrities",
        "consented_uploads",
        ["consented_upload_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_celebrities_owner_user_id", "celebrities", ["owner_user_id"], unique=True)
    op.create_index(
        "ix_celebrities_consented_upload_id",
        "celebrities",
        ["consented_upload_id"],
        unique=True,
    )
    op.create_index(
        "ix_celebrities_hot_or_not_active",
        "celebrities",
        ["is_hot_or_not_active"],
    )
    op.add_column(
        "consented_uploads",
        sa.Column("hot_or_not_consent_version", sa.String(length=40)),
    )
    op.add_column(
        "consented_uploads",
        sa.Column("hot_or_not_consented_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_column("consented_uploads", "hot_or_not_consented_at")
    op.drop_column("consented_uploads", "hot_or_not_consent_version")
    op.drop_index("ix_celebrities_hot_or_not_active", table_name="celebrities")
    op.drop_index("ix_celebrities_consented_upload_id", table_name="celebrities")
    op.drop_index("ix_celebrities_owner_user_id", table_name="celebrities")
    op.drop_constraint("fk_celebrities_consented_upload_id", "celebrities", type_="foreignkey")
    op.drop_constraint("fk_celebrities_owner_user_id", "celebrities", type_="foreignkey")
    op.drop_column("celebrities", "is_hot_or_not_active")
    op.drop_column("celebrities", "portrait_media_type")
    op.drop_column("celebrities", "portrait_image")
    op.drop_column("celebrities", "consented_upload_id")
    op.drop_column("celebrities", "owner_user_id")
    op.drop_column("celebrities", "candidate_type")
