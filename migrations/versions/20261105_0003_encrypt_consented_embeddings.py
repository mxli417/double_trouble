"""Encrypt consented query embeddings at application level.

Revision ID: 20261105_0003
Revises: 20261105_0002
"""

import json
import os

import sqlalchemy as sa
from alembic import op
from cryptography.fernet import Fernet
from pgvector.sqlalchemy import Vector

revision = "20261105_0003"
down_revision = "20261105_0002"
branch_labels = None
depends_on = None


def _values(value: object) -> list[float]:
    if isinstance(value, str):
        value = json.loads(value)
    return [float(item) for item in value]  # type: ignore[arg-type]


def upgrade() -> None:
    op.add_column("consented_uploads", sa.Column("encrypted_embedding", sa.LargeBinary(), nullable=True))
    op.add_column("consented_uploads", sa.Column("embedding_dimensions", sa.Integer(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, embedding FROM consented_uploads")).all()
    if rows:
        key = os.environ.get("DATA_ENCRYPTION_KEY")
        if not key:
            raise RuntimeError("DATA_ENCRYPTION_KEY is required to migrate consented embeddings")
        cipher = Fernet(key.encode("ascii"))
        for upload_id, embedding in rows:
            values = _values(embedding)
            encrypted = cipher.encrypt(
                json.dumps(values, separators=(",", ":"), allow_nan=False).encode("utf-8")
            )
            connection.execute(
                sa.text(
                    "UPDATE consented_uploads SET encrypted_embedding=:encrypted, "
                    "embedding_dimensions=:dimensions WHERE id=:upload_id"
                ),
                {"encrypted": encrypted, "dimensions": len(values), "upload_id": upload_id},
            )

    op.alter_column("consented_uploads", "encrypted_embedding", nullable=False)
    op.alter_column("consented_uploads", "embedding_dimensions", nullable=False)
    op.drop_column("consented_uploads", "embedding")


def downgrade() -> None:
    op.add_column("consented_uploads", sa.Column("embedding", Vector(128), nullable=True))
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, encrypted_embedding FROM consented_uploads")
    ).all()
    if rows:
        key = os.environ.get("DATA_ENCRYPTION_KEY")
        if not key:
            raise RuntimeError("DATA_ENCRYPTION_KEY is required to downgrade consented embeddings")
        cipher = Fernet(key.encode("ascii"))
        for upload_id, encrypted in rows:
            values = json.loads(cipher.decrypt(encrypted))
            connection.execute(
                sa.text("UPDATE consented_uploads SET embedding=CAST(:embedding AS vector) WHERE id=:upload_id"),
                {"embedding": json.dumps(values), "upload_id": upload_id},
            )
    op.alter_column("consented_uploads", "embedding", nullable=False)
    op.drop_column("consented_uploads", "embedding_dimensions")
    op.drop_column("consented_uploads", "encrypted_embedding")
