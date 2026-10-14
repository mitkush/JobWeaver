"""Disable noisy Google Jobs discovery providers without deleting history.

Revision ID: 0010
Revises: 0009
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE sources SET enabled = false WHERE name IN ('jsearch', 'serpapi')")


def downgrade() -> None:
    # Preserve the admin's enabled/disabled choices. Re-enable through Sources if wanted.
    pass
