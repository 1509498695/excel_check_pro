"""Drop AI rule draft history.

Revision ID: 0007_drop_ai_rule_drafts
Revises: 0006_project_ai_config_enhancement
Create Date: 2026-06-10 10:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0007_drop_ai_rule_drafts"
down_revision: str | None = "0006_project_ai_config_enhancement"
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
    if not _table_exists("ai_rule_drafts"):
        return

    for index_name in (
        "ix_ai_rule_drafts_project_id",
        "ix_ai_rule_drafts_user_id",
        "ix_ai_rule_drafts_created_at",
    ):
        if _index_exists("ai_rule_drafts", index_name):
            op.drop_index(index_name, table_name="ai_rule_drafts")
    op.drop_table("ai_rule_drafts")


def downgrade() -> None:
    if _table_exists("ai_rule_drafts"):
        return

    op.create_table(
        "ai_rule_drafts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("rule_type", sa.String(length=64), nullable=True),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_rule_drafts_project_id", "ai_rule_drafts", ["project_id"])
    op.create_index("ix_ai_rule_drafts_user_id", "ai_rule_drafts", ["user_id"])
    op.create_index("ix_ai_rule_drafts_created_at", "ai_rule_drafts", ["created_at"])
