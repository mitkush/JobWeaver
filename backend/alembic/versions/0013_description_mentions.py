"""Add nullable description mention caches without reading or backfilling text.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("postings", sa.Column("description_mentions", postgresql.ARRAY(sa.Text())))
    op.add_column("postings", sa.Column("description_usable", sa.Boolean()))
    op.add_column("postings", sa.Column("description_mentions_version", sa.String(64)))


def downgrade() -> None:
    op.drop_column("postings", "description_mentions_version")
    op.drop_column("postings", "description_usable")
    op.drop_column("postings", "description_mentions")
