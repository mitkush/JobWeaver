"""Application profile and Saved Answers for the Application Extension (ADR-0017), and
the version of the access list each extension connection was approved for.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
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
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "application_profiles",
        *_base(),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fact_hashes", postgresql.JSONB(), nullable=False),
    )
    op.create_index(
        "idx_application_profiles_user", "application_profiles", ["user_id"], unique=True
    )
    op.create_table(
        "saved_answers",
        *_base(),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("question_key", sa.String(255), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("country", sa.String(2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("period", sa.String(8)),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE")),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("sensitive", sa.Boolean(), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="SET NULL")),
    )
    op.create_index("idx_saved_answers_user_key", "saved_answers", ["user_id", "question_key"])
    # Existing connections were approved for name and email only: version 1.
    for table in ("extension_grants", "extension_credentials"):
        op.add_column(
            table, sa.Column("scopes_version", sa.Integer(), nullable=False, server_default="1")
        )


def downgrade() -> None:
    for table in ("extension_grants", "extension_credentials"):
        op.drop_column(table, "scopes_version")
    op.drop_index("idx_saved_answers_user_key", "saved_answers")
    op.drop_table("saved_answers")
    op.drop_index("idx_application_profiles_user", "application_profiles")
    op.drop_table("application_profiles")
