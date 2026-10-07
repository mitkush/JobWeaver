"""application tracker: one Application per User and Job, status history, hand-offs

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-06 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("follow_up_days", sa.Integer(), server_default="7", nullable=False)
    )
    op.create_table(
        "application_events",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        *_timestamps(),
    )
    op.create_index(
        "idx_application_events_user_app", "application_events", ["user_id", "application_id"]
    )
    op.create_table(
        "gmail_handoffs",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("gmail_draft_id", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["draft_id"], ["drafts.id"], ondelete="SET NULL"),
        *_timestamps(),
    )
    op.create_index("idx_gmail_handoffs_user_app", "gmail_handoffs", ["user_id", "application_id"])
    op.add_column(
        "applications", sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "applications", sa.Column("follow_up_after", sa.DateTime(timezone=True), nullable=True)
    )

    # Phase 4 kept one row per hand-off. Each (User, Job) keeps one row: the applied one
    # if any, else the newest; the others become hand-off records and are removed.
    op.execute(
        """
        CREATE TEMP TABLE app_survivors ON COMMIT DROP AS
        SELECT id, first_value(id) OVER (
            PARTITION BY user_id, job_id
            ORDER BY (applied_at IS NOT NULL) DESC, created_at DESC, id DESC
        ) AS survivor
        FROM applications
        """
    )
    op.execute(
        """
        INSERT INTO gmail_handoffs (id, user_id, application_id, kind, draft_id, version,
                                    recipient, gmail_draft_id, created_at, updated_at)
        SELECT gen_random_uuid(), a.user_id, s.survivor, 'application', a.draft_id, a.version,
               a.recipient, a.gmail_draft_id, a.created_at, a.updated_at
        FROM applications a JOIN app_survivors s ON s.id = a.id
        WHERE a.recipient IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE applications a SET
            applied_at = g.applied_at,
            status = CASE WHEN g.applied_at IS NOT NULL THEN 'applied' ELSE 'drafted' END,
            draft_id = g.latest_draft,
            status_changed_at = COALESCE(g.applied_at, g.first_created),
            follow_up_after = g.applied_at + interval '7 days'
        FROM (
            SELECT s.survivor,
                   min(x.applied_at) AS applied_at,
                   min(x.created_at) AS first_created,
                   (array_agg(x.draft_id ORDER BY x.created_at DESC))[1] AS latest_draft
            FROM applications x JOIN app_survivors s ON s.id = x.id
            GROUP BY s.survivor
        ) g
        WHERE a.id = g.survivor
        """
    )
    op.execute(
        """
        INSERT INTO application_events (id, user_id, application_id, status, created_at,
                                        updated_at)
        SELECT gen_random_uuid(), min(x.user_id::text)::uuid, s.survivor, 'drafted',
               min(x.created_at), min(x.created_at)
        FROM applications x JOIN app_survivors s ON s.id = x.id
        GROUP BY s.survivor
        UNION ALL
        SELECT gen_random_uuid(), a.user_id, a.id, 'applied', a.applied_at, a.applied_at
        FROM applications a JOIN app_survivors s ON s.id = a.id AND s.survivor = a.id
        WHERE a.applied_at IS NOT NULL
        """
    )
    op.execute(
        "DELETE FROM applications a USING app_survivors s WHERE s.id = a.id AND s.survivor <> a.id"
    )
    op.alter_column("applications", "status_changed_at", nullable=False)
    op.drop_column("applications", "gmail_draft_id")
    op.drop_column("applications", "version")
    op.drop_column("applications", "recipient")
    op.drop_index("idx_applications_user_job", table_name="applications")
    op.create_index("idx_applications_user_job", "applications", ["user_id", "job_id"], unique=True)


def downgrade() -> None:
    op.drop_index("idx_applications_user_job", table_name="applications")
    op.create_index("idx_applications_user_job", "applications", ["user_id", "job_id"])
    op.add_column("applications", sa.Column("recipient", sa.String(length=320), nullable=True))
    op.add_column(
        "applications", sa.Column("version", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("applications", sa.Column("gmail_draft_id", sa.String(length=255), nullable=True))
    # The newest application hand-off goes back on its row; statuses past Applied did not
    # exist before, so they read as Applied.
    op.execute(
        """
        UPDATE applications a SET recipient = h.recipient, version = COALESCE(h.version, 0),
               gmail_draft_id = h.gmail_draft_id
        FROM (
            SELECT DISTINCT ON (application_id) application_id, recipient, version,
                   gmail_draft_id
            FROM gmail_handoffs WHERE kind = 'application'
            ORDER BY application_id, created_at DESC
        ) h
        WHERE h.application_id = a.id
        """
    )
    op.execute(
        "UPDATE applications SET status = 'applied' "
        "WHERE status IN ('replied', 'interview', 'offer', 'rejected') AND applied_at IS NOT NULL"
    )
    op.execute(
        "UPDATE applications SET status = 'drafted' "
        "WHERE status IN ('replied', 'interview', 'offer', 'rejected')"
    )
    op.drop_column("applications", "follow_up_after")
    op.drop_column("applications", "status_changed_at")
    op.drop_index("idx_gmail_handoffs_user_app", table_name="gmail_handoffs")
    op.drop_table("gmail_handoffs")
    op.drop_index("idx_application_events_user_app", table_name="application_events")
    op.drop_table("application_events")
    op.drop_column("users", "follow_up_days")
