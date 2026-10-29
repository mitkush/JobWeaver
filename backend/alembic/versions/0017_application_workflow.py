"""Immutable job context, active packages and background proposals.

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "drafts", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.add_column(
        "draft_versions", sa.Column("job_context", pg.JSONB(), nullable=False, server_default="{}")
    )
    op.execute(
        "UPDATE draft_versions v SET job_context=d.job_snapshot FROM drafts d WHERE v.draft_id=d.id"
    )
    op.execute("""WITH ranked AS (
        SELECT d.id, row_number() OVER (PARTITION BY d.user_id,d.job_id ORDER BY
          CASE WHEN a.draft_id=d.id THEN 0 ELSE 1 END, d.created_at DESC,d.id DESC) AS n
        FROM drafts d LEFT JOIN applications a ON a.user_id=d.user_id AND a.job_id=d.job_id
    ) UPDATE drafts SET active=false FROM ranked WHERE drafts.id=ranked.id AND ranked.n>1""")
    op.create_index(
        "uq_drafts_active_user_job",
        "drafts",
        ["user_id", "job_id"],
        unique=True,
        postgresql_where=sa.text("active"),
    )
    op.add_column("applications", sa.Column("draft_version", sa.Integer()))
    op.add_column("users", sa.Column("writing_style", sa.Text(), nullable=False, server_default=""))
    op.create_table(
        "draft_proposals",
        sa.Column("id", pg.UUID(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "user_id", pg.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "draft_id", pg.UUID(), sa.ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("part", sa.String(24), nullable=False),
        sa.Column("section", sa.String(40)),
        sa.Column("instruction", sa.Text(), nullable=False, server_default=""),
        sa.Column("state", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("progress", sa.String(255), nullable=False, server_default="Queued"),
        sa.Column("error", sa.Text()),
        sa.Column("content", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("facts", pg.JSONB(), nullable=False, server_default="[]"),
        sa.Column("job_context", pg.JSONB(), nullable=False, server_default="{}"),
        sa.Column("warnings", pg.JSONB(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_draft_proposals_draft_id", "draft_proposals", ["draft_id"])


def downgrade():
    op.drop_table("draft_proposals")
    op.drop_column("users", "writing_style")
    op.drop_column("applications", "draft_version")
    op.drop_column("draft_versions", "job_context")
    op.drop_index("uq_drafts_active_user_job", "drafts")
    op.drop_column("drafts", "active")
