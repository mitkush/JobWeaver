"""Persist asynchronous provider collections before polling.

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("query_key", sa.String(300), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("credential_fingerprint", sa.String(64), nullable=False),
        sa.Column("window_since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("credits_recorded", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_index(
        "idx_pending_collection_source_query",
        "pending_collections",
        ["source", "query_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("pending_collections")
