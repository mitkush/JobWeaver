"""Track fetch spend per credential without changing shared query checkpoints.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fetch_runs", sa.Column("credential_fingerprint", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("fetch_runs", "credential_fingerprint")
