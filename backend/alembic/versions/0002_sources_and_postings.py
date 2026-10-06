"""sources and postings

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-05 12:53:05.282206
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_table(
        "query_watermarks",
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("query_key", sa.String(length=300), nullable=False),
        sa.Column("last_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_watermarks_source_query", "query_watermarks", ["source", "query_key"], unique=True
    )
    op.create_table(
        "sources",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "state", sa.Enum("healthy", "degraded", "disabled", name="source_state"), nullable=False
        ),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("degraded_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manual_runs_today", sa.Integer(), nullable=False),
        sa.Column("manual_runs_date", sa.String(length=10), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "ats_boards",
        sa.Column("ats", sa.String(length=32), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("discovered_from", sa.String(length=16), nullable=False),
        sa.Column("added_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_nonempty_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["added_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_ats_boards_ats_slug", "ats_boards", ["ats", "slug"], unique=True)
    op.create_table(
        "fetch_runs",
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum("running", "succeeded", "failed", "skipped", name="run_status"),
            nullable=False,
        ),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("query_key", sa.String(length=300), nullable=True),
        sa.Column("board_id", sa.Uuid(), nullable=True),
        sa.Column("window_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("postings_found", sa.Integer(), nullable=False),
        sa.Column("postings_new", sa.Integer(), nullable=False),
        sa.Column("postings_closed", sa.Integer(), nullable=False),
        sa.Column("credits_used", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["board_id"], ["ats_boards.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_fetch_runs_source_created", "fetch_runs", ["source", "created_at"], unique=False
    )
    op.create_table(
        "postings",
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_job_id", sa.String(length=255), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("ats_board_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("locations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("work_mode", sa.String(length=16), nullable=True),
        sa.Column("apply_url", sa.String(length=2048), nullable=True),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_reason", sa.String(length=32), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["ats_board_id"], ["ats_boards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_postings_board_open", "postings", ["ats_board_id", "closed_at"], unique=False
    )
    op.create_index(
        "idx_postings_company_open", "postings", ["company_id", "closed_at"], unique=False
    )
    op.create_index("idx_postings_source_job", "postings", ["source", "source_job_id"], unique=True)


def downgrade() -> None:
    op.drop_index("idx_postings_source_job", table_name="postings")
    op.drop_index("idx_postings_company_open", table_name="postings")
    op.drop_index("idx_postings_board_open", table_name="postings")
    op.drop_table("postings")
    op.drop_index("idx_fetch_runs_source_created", table_name="fetch_runs")
    op.drop_table("fetch_runs")
    op.drop_index("idx_ats_boards_ats_slug", table_name="ats_boards")
    op.drop_table("ats_boards")
    op.drop_table("sources")
    op.drop_index("idx_watermarks_source_query", table_name="query_watermarks")
    op.drop_table("query_watermarks")
    op.drop_table("companies")
    for enum_name in ("run_status", "source_state"):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
