"""Enhance project AI credential configuration.

Revision ID: 0006_project_ai_config_enhancement
Revises: 0005_feishu_bot_config_extension
Create Date: 2026-06-09 22:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0006_project_ai_config_enhancement"
down_revision: str | None = "0005_feishu_bot_config_extension"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return table_name in set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _table_exists(table_name):
        return
    if column.name in _column_names(table_name):
        return
    op.add_column(table_name, column)


def upgrade() -> None:
    _add_column_if_missing(
        "project_ai_credentials",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    _add_column_if_missing(
        "project_ai_credentials",
        sa.Column("auto_match_threshold", sa.Float(), nullable=False, server_default="0.9"),
    )
    _add_column_if_missing(
        "project_ai_credentials",
        sa.Column("candidate_threshold", sa.Float(), nullable=False, server_default="0.6"),
    )
    _add_column_if_missing(
        "project_ai_credentials",
        sa.Column("max_candidates", sa.Integer(), nullable=False, server_default="10"),
    )
    _add_column_if_missing(
        "project_ai_credentials",
        sa.Column("last_test_status", sa.String(length=32), nullable=False, server_default=""),
    )
    _add_column_if_missing(
        "project_ai_credentials",
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        "project_ai_credentials",
        sa.Column("last_test_error_summary", sa.Text(), nullable=False, server_default=""),
    )
    _add_column_if_missing(
        "project_ai_credentials",
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )

    if _table_exists("feishu_bot_configs") and _table_exists("project_ai_credentials"):
        op.execute(
            sa.text(
                """
                UPDATE project_ai_credentials
                SET
                  auto_match_threshold = COALESCE((
                    SELECT feishu_bot_configs.auto_match_threshold
                    FROM feishu_bot_configs
                    WHERE feishu_bot_configs.project_id = project_ai_credentials.project_id
                  ), auto_match_threshold),
                  candidate_threshold = COALESCE((
                    SELECT feishu_bot_configs.candidate_threshold
                    FROM feishu_bot_configs
                    WHERE feishu_bot_configs.project_id = project_ai_credentials.project_id
                  ), candidate_threshold),
                  max_candidates = COALESCE((
                    SELECT feishu_bot_configs.max_candidates
                    FROM feishu_bot_configs
                    WHERE feishu_bot_configs.project_id = project_ai_credentials.project_id
                  ), max_candidates)
                """
            )
        )


def downgrade() -> None:
    # SQLite drop-column support depends on the runtime version; keep downgrade conservative.
    return
