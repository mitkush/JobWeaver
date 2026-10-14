"""Cache parsed experience hints on shared Jobs.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("experience_requirement", sa.String(100), nullable=True))
    op.execute(
        """
        WITH hints AS (
            SELECT j.id, regexp_match(
                p.description,
                '(\\d+(?:\\.\\d+)?)\\s*(?:\\+\\s*)?(?:[-–]\\s*(\\d+(?:\\.\\d+)?)\\s*)?'
                'years?\\s*(?:of\\s+)?(?:(?:relevant|professional|industry)\\s+)?experience',
                'i'
            ) AS parts
            FROM jobs j
            JOIN postings p ON p.id = j.primary_posting_id
        )
        UPDATE jobs j
        SET experience_requirement = CASE
            WHEN hints.parts[2] IS NOT NULL THEN
                hints.parts[1] || '–' || hints.parts[2] || ' years'
            ELSE hints.parts[1] || '+ years'
        END
        FROM hints
        WHERE hints.id = j.id AND hints.parts IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("jobs", "experience_requirement")
