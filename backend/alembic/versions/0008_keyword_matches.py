"""keyword matches: core keywords on Preferences, the match reason on Feed links

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-07 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "preferences",
        sa.Column(
            "core_keywords",
            postgresql.ARRAY(sa.String(length=100)),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "preferences",
        sa.Column("keyword_min_matches", sa.Integer(), server_default="2", nullable=False),
    )
    op.add_column(
        "preferences",
        sa.Column("search_keywords", sa.Boolean(), server_default="false", nullable=False),
    )
    # Every existing link came from a title match; the next Feed sync corrects any that
    # only stayed because of a Draft, an Application or a hide.
    op.add_column(
        "user_jobs",
        sa.Column("match_kind", sa.String(length=16), server_default="title", nullable=True),
    )
    op.alter_column("user_jobs", "match_kind", server_default=None)
    op.add_column(
        "user_jobs",
        sa.Column(
            "matched_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_jobs", "matched_keywords")
    op.drop_column("user_jobs", "match_kind")
    op.drop_column("preferences", "search_keywords")
    op.drop_column("preferences", "keyword_min_matches")
    op.drop_column("preferences", "core_keywords")
