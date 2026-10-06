"""jobs, correspondence and feed

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-06 04:53:15.596603
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _merge_companies() -> None:
    """Company keys now drop words like "India" or "Software" ("Razorpay Software Pvt Ltd"
    and "Razorpay" are one Company), so existing rows are re-keyed and merged."""
    from app.adapters.normalize import normalize_company

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, name, normalized_name FROM companies ORDER BY created_at, id")
    ).all()
    survivors: dict[str, object] = {}
    renames: list[tuple[object, str]] = []
    for company_id, name, old_key in rows:
        key = (normalize_company(name) or old_key)[:255]
        if key not in survivors:
            survivors[key] = company_id
            if key != old_key:
                renames.append((company_id, key))
            continue
        params = {"old": company_id, "new": survivors[key]}
        bind.execute(
            sa.text("UPDATE postings SET company_id = :new WHERE company_id = :old"), params
        )
        bind.execute(
            sa.text("UPDATE ats_boards SET company_id = :new WHERE company_id = :old"), params
        )
        bind.execute(sa.text("DELETE FROM companies WHERE id = :old"), params)
    for company_id, key in renames:
        bind.execute(
            sa.text("UPDATE companies SET normalized_name = :key WHERE id = :id"),
            {"key": key, "id": company_id},
        )


def upgrade() -> None:
    # Neon and the pgvector image both ship the extension; it needs superuser to create.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    _merge_companies()
    op.create_table(
        "jobs",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("primary_posting_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=False),
        sa.Column("locations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("work_mode", sa.String(length=16), nullable=True),
        sa.Column("apply_url", sa.String(length=2048), nullable=True),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sources", postgresql.ARRAY(sa.String(length=64)), nullable=False),
        sa.Column("required_skills", postgresql.ARRAY(sa.String(length=100)), nullable=True),
        sa.Column("skills_extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_jobs_open_posted", "jobs", ["expired_at", "posted_at"], unique=False)
    op.create_table(
        "user_jobs",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_user_jobs_job", "user_jobs", ["job_id"], unique=False)
    op.create_index(
        "idx_user_jobs_user_hidden", "user_jobs", ["user_id", "hidden_at"], unique=False
    )
    op.create_index("idx_user_jobs_user_job", "user_jobs", ["user_id", "job_id"], unique=True)
    op.create_table(
        "match_pairs",
        sa.Column("posting_a_id", sa.Uuid(), nullable=False),
        sa.Column("posting_b_id", sa.Uuid(), nullable=False),
        sa.Column("band", sa.Enum("exact", "high", "medium", name="match_band"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("auto", "open", "confirmed", "rejected", name="pair_status"),
            nullable=False,
        ),
        sa.Column("signals", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["posting_a_id"], ["postings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["posting_b_id"], ["postings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_match_pairs_b", "match_pairs", ["posting_b_id"], unique=False)
    op.create_index(
        "idx_match_pairs_pair", "match_pairs", ["posting_a_id", "posting_b_id"], unique=True
    )
    op.create_index("idx_match_pairs_status", "match_pairs", ["status"], unique=False)
    op.create_table(
        "rejected_pairs",
        sa.Column("posting_a_id", sa.Uuid(), nullable=False),
        sa.Column("posting_b_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(["posting_a_id"], ["postings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["posting_b_id"], ["postings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_rejected_pairs_b", "rejected_pairs", ["posting_b_id"], unique=False)
    op.create_index(
        "idx_rejected_pairs_pair", "rejected_pairs", ["posting_a_id", "posting_b_id"], unique=True
    )
    op.add_column("postings", sa.Column("job_id", sa.Uuid(), nullable=True))
    op.add_column(
        "postings",
        sa.Column("match_state", sa.String(length=24), nullable=False, server_default="pending"),
    )
    op.alter_column("postings", "match_state", server_default=None)
    op.execute("ALTER TABLE postings ADD COLUMN embedding vector(768)")
    op.add_column("postings", sa.Column("embedding_model", sa.String(length=64), nullable=True))
    op.create_index("idx_postings_job", "postings", ["job_id"], unique=False)
    op.create_index("idx_postings_match_state", "postings", ["match_state"], unique=False)
    op.create_foreign_key(
        "fk_postings_job_id", "postings", "jobs", ["job_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_postings_job_id", "postings", type_="foreignkey")
    op.drop_index("idx_postings_match_state", table_name="postings")
    op.drop_index("idx_postings_job", table_name="postings")
    op.drop_column("postings", "embedding_model")
    op.drop_column("postings", "embedding")
    op.drop_column("postings", "match_state")
    op.drop_column("postings", "job_id")
    op.drop_index("idx_rejected_pairs_pair", table_name="rejected_pairs")
    op.drop_index("idx_rejected_pairs_b", table_name="rejected_pairs")
    op.drop_table("rejected_pairs")
    op.drop_index("idx_match_pairs_status", table_name="match_pairs")
    op.drop_index("idx_match_pairs_pair", table_name="match_pairs")
    op.drop_index("idx_match_pairs_b", table_name="match_pairs")
    op.drop_table("match_pairs")
    op.drop_index("idx_user_jobs_user_job", table_name="user_jobs")
    op.drop_index("idx_user_jobs_user_hidden", table_name="user_jobs")
    op.drop_index("idx_user_jobs_job", table_name="user_jobs")
    op.drop_table("user_jobs")
    op.drop_index("idx_jobs_open_posted", table_name="jobs")
    op.drop_table("jobs")
    op.execute("DROP TYPE IF EXISTS match_band")
    op.execute("DROP TYPE IF EXISTS pair_status")
