"""Store config lookup rules per query type.

Revision ID: 0009_rule_config_per_query_type
Revises: 0008_drop_ai_provider_credentials
Create Date: 2026-06-10 18:20:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0009_rule_config_per_query_type"
down_revision: str | None = "0008_drop_ai_provider_credentials"
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


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if not _table_exists(table_name):
        return
    if _index_exists(table_name, index_name):
        return
    op.create_index(index_name, table_name, columns, unique=unique)


def _drop_table_if_exists(table_name: str) -> None:
    if _table_exists(table_name):
        op.drop_table(table_name)


def upgrade() -> None:
    # Old records intentionally are not migrated: this phase changes the identity
    # from one document per project/family to one rule per query type.
    _drop_table_if_exists("rule_config_versions")
    _drop_table_if_exists("rule_configs")

    op.create_table(
        "rule_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("rule_family", sa.String(length=64), nullable=False),
        sa.Column("query_type", sa.String(length=100), nullable=False),
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
    _create_index_if_missing(
        "uq_rule_configs_project_family_query_type",
        "rule_configs",
        ["project_id", "rule_family", "query_type"],
        unique=True,
    )
    _create_index_if_missing("ix_rule_configs_project_id", "rule_configs", ["project_id"])
    _create_index_if_missing("ix_rule_configs_rule_family", "rule_configs", ["rule_family"])
    _create_index_if_missing("ix_rule_configs_status", "rule_configs", ["status"])

    op.create_table(
        "rule_config_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_config_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("rule_family", sa.String(length=64), nullable=False),
        sa.Column("query_type", sa.String(length=100), nullable=False),
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
        sa.ForeignKeyConstraint(["rule_config_id"], ["rule_configs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operator"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index_if_missing(
        "uq_rule_config_versions_rule_config_version",
        "rule_config_versions",
        ["rule_config_id", "version"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_rule_config_versions_rule_config_id",
        "rule_config_versions",
        ["rule_config_id"],
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
    _drop_table_if_exists("rule_config_versions")
    _drop_table_if_exists("rule_configs")

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
        sa.Column("optimistic_lock_version", sa.Integer(), nullable=False, server_default="0"),
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
    _create_index_if_missing(
        "uq_rule_configs_project_family",
        "rule_configs",
        ["project_id", "rule_family"],
        unique=True,
    )
    _create_index_if_missing("ix_rule_configs_project_id", "rule_configs", ["project_id"])
    _create_index_if_missing("ix_rule_configs_rule_family", "rule_configs", ["rule_family"])
    _create_index_if_missing("ix_rule_configs_status", "rule_configs", ["status"])

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
