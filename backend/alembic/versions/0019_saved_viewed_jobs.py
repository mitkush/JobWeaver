"""Saved and Viewed marks on a User's link to a Job.

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_jobs", sa.Column("saved_at", sa.DateTime(timezone=True)))
    op.add_column("user_jobs", sa.Column("viewed_at", sa.DateTime(timezone=True)))
    op.create_index("idx_user_jobs_user_saved", "user_jobs", ["user_id", "saved_at"])


def downgrade() -> None:
    op.drop_index("idx_user_jobs_user_saved", table_name="user_jobs")
    op.drop_column("user_jobs", "viewed_at")
    op.drop_column("user_jobs", "saved_at")
