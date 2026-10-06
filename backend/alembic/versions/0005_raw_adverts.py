"""raw adverts: free-text adverts waiting for AI extraction (Hacker News)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-06 10:43:20.629299
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "raw_adverts",
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("ref", sa.String(length=255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("postings", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_raw_adverts_pending", "raw_adverts", ["extracted_at", "attempts"], unique=False
    )
    op.create_index("idx_raw_adverts_source_ref", "raw_adverts", ["source", "ref"], unique=True)


def downgrade() -> None:
    op.drop_index("idx_raw_adverts_source_ref", table_name="raw_adverts")
    op.drop_index("idx_raw_adverts_pending", table_name="raw_adverts")
    op.drop_table("raw_adverts")
