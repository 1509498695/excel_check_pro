"""Drop personal AI provider credentials.

Revision ID: 0008_drop_ai_provider_credentials
Revises: 0007_drop_ai_rule_drafts
Create Date: 2026-06-10 11:45:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0008_drop_ai_provider_credentials"
down_revision: str | None = "0007_drop_ai_rule_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("ai_provider_credentials"):
        return
    if _index_exists("ai_provider_credentials", "ix_ai_provider_credentials_user_id"):
        op.drop_index("ix_ai_provider_credentials_user_id", table_name="ai_provider_credentials")
    op.drop_table("ai_provider_credentials")


def downgrade() -> None:
    if _table_exists("ai_provider_credentials"):
        return

    op.create_table(
        "ai_provider_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider_preset", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("extra_headers_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_provider_credentials_user_id",
        "ai_provider_credentials",
        ["user_id"],
        unique=True,
    )
