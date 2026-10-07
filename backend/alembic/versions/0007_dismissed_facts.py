"""dismissed facts: Fact text a re-parse must not add back (FR-A2 AC3)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-07 05:55:48.366733
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dismissed_facts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("text_key", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_dismissed_facts_user_text", "dismissed_facts", ["user_id", "text_key"], unique=True
    )


def downgrade() -> None:
    op.drop_index("idx_dismissed_facts_user_text", table_name="dismissed_facts")
    op.drop_table("dismissed_facts")
