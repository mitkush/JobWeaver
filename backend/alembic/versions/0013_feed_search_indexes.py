"""Index existing literal Feed and preference substring searches.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

INDEXES = (
    ("idx_jobs_open_title_trgm", "jobs", "title", "expired_at IS NULL"),
    ("idx_jobs_open_company_trgm", "jobs", "company_name", "expired_at IS NULL"),
    ("idx_postings_description_trgm", "postings", "description", None),
    ("idx_postings_description_length", "postings", sa.text("length(description)"), None),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # Concurrent builds avoid blocking writes. A failed build can leave an invalid
    # index; recreate only these migration-owned indexes when retrying this revision.
    with op.get_context().autocommit_block():
        for name, table, column, predicate in INDEXES:
            op.drop_index(name, table_name=table, if_exists=True, postgresql_concurrently=True)
            options = {"postgresql_where": sa.text(predicate)} if predicate else {}
            if isinstance(column, str):
                options.update(postgresql_using="gin", postgresql_ops={column: "gin_trgm_ops"})
            op.create_index(
                name,
                table,
                [column],
                postgresql_concurrently=True,
                **options,
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, _, _ in reversed(INDEXES):
            op.drop_index(name, table_name=table, if_exists=True, postgresql_concurrently=True)
    # pg_trgm may be used by other database objects; retain the extension.
