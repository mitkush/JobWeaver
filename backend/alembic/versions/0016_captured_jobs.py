"""Durable captured Jobs and private Page Descriptions.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_jobs", sa.Column("captured_at", sa.DateTime(timezone=True)))
    op.add_column("user_jobs", sa.Column("page_description", postgresql.JSONB()))


def downgrade() -> None:
    op.drop_column("user_jobs", "page_description")
    op.drop_column("user_jobs", "captured_at")
