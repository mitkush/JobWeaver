"""Cache parsed experience hints on shared Jobs.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa

from alembic import op
from app.tailoring.job_experience import experience_requirement

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("postings", sa.Column("experience_requirement", sa.String(100), nullable=True))
    op.add_column("jobs", sa.Column("experience_requirement", sa.String(100), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, description FROM postings"))
    update_posting = sa.text(
        "UPDATE postings SET experience_requirement = :hint WHERE id = :posting_id"
    )
    while batch := rows.fetchmany(500):
        bind.execute(
            update_posting,
            [
                {"posting_id": posting_id, "hint": experience_requirement(description)}
                for posting_id, description in batch
            ],
        )
    bind.execute(
        sa.text(
            "UPDATE jobs SET experience_requirement = postings.experience_requirement "
            "FROM postings WHERE jobs.primary_posting_id = postings.id"
        )
    )


def downgrade() -> None:
    op.drop_column("jobs", "experience_requirement")
    op.drop_column("postings", "experience_requirement")
