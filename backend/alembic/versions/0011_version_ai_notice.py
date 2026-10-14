"""Version AI data notice acceptance so provider changes require renewed consent.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("ai_notice_version", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "ai_notice_version")
