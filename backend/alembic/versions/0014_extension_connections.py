"""Application Extension grants and credentials (ADR-0017).

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _common() -> list[sa.Column]:
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
        sa.Column("extension_id", sa.String(32), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "extension_grants",
        *_common(),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("challenge", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_extension_grants_user", "extension_grants", ["user_id"])
    op.create_table(
        "extension_credentials",
        *_common(),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_extension_credentials_user", "extension_credentials", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_extension_credentials_user", "extension_credentials")
    op.drop_table("extension_credentials")
    op.drop_index("idx_extension_grants_user", "extension_grants")
    op.drop_table("extension_grants")
