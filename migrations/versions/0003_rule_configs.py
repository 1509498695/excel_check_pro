"""Add rule configuration storage and versions.

Revision ID: 0003_rule_configs
Revises: 0002_execution_run_tasks
Create Date: 2026-06-09 18:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003_rule_configs"
down_revision: str | None = "0002_execution_run_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return table_name in set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if not _table_exists(table_name):
        return
    if index_name in _index_names(table_name):
        return
    op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    if not _table_exists("rule_configs"):
        op.create_table(
            "rule_configs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("rule_family", sa.String(length=64), nullable=False),
            sa.Column("content_md", sa.Text(), nullable=False, server_default=""),
            sa.Column("parsed_config_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("draft_version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("published_version", sa.Integer(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("published_by", sa.Integer(), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "optimistic_lock_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
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
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["published_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists("rule_config_versions"):
        op.create_table(
            "rule_config_versions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("rule_family", sa.String(length=64), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("content_md", sa.Text(), nullable=False, server_default=""),
            sa.Column("parsed_config_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("action", sa.String(length=32), nullable=False),
            sa.Column("operator", sa.Integer(), nullable=True),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["operator"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    _create_index_if_missing(
        "uq_rule_configs_project_family",
        "rule_configs",
        ["project_id", "rule_family"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_rule_configs_project_id",
        "rule_configs",
        ["project_id"],
    )
    _create_index_if_missing(
        "ix_rule_configs_rule_family",
        "rule_configs",
        ["rule_family"],
    )
    _create_index_if_missing("ix_rule_configs_status", "rule_configs", ["status"])
    _create_index_if_missing(
        "uq_rule_config_versions_project_family_version",
        "rule_config_versions",
        ["project_id", "rule_family", "version"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_rule_config_versions_project_family",
        "rule_config_versions",
        ["project_id", "rule_family"],
    )
    _create_index_if_missing(
        "ix_rule_config_versions_created_at",
        "rule_config_versions",
        ["created_at"],
    )


def downgrade() -> None:
    for table_name in ("rule_config_versions", "rule_configs"):
        if _table_exists(table_name):
            op.drop_table(table_name)
