"""Extend project Feishu bot config with bindings and credentials.

Revision ID: 0005_feishu_bot_config_extension
Revises: 0004_project_query_roots
Create Date: 2026-06-09 21:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005_feishu_bot_config_extension"
down_revision: str | None = "0004_project_query_roots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return table_name in set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _table_exists(table_name):
        return
    if column.name in _column_names(table_name):
        return
    op.add_column(table_name, column)


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


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if not _table_exists(table_name):
        return
    if index_name not in _index_names(table_name):
        return
    op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    _add_column_if_missing(
        "feishu_bot_configs",
        sa.Column("auto_match_threshold", sa.Float(), nullable=False, server_default="0.9"),
    )
    _add_column_if_missing(
        "feishu_bot_configs",
        sa.Column("candidate_threshold", sa.Float(), nullable=False, server_default="0.6"),
    )
    _add_column_if_missing(
        "feishu_bot_configs",
        sa.Column("max_candidates", sa.Integer(), nullable=False, server_default="10"),
    )

    _drop_index_if_exists("uq_feishu_bot_configs_app_id", "feishu_bot_configs")
    _create_index_if_missing(
        "ix_feishu_bot_configs_app_id",
        "feishu_bot_configs",
        ["app_id"],
    )

    if not _table_exists("feishu_bot_bound_chats"):
        op.create_table(
            "feishu_bot_bound_chats",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("chat_id", sa.String(length=128), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "ix_feishu_bot_bound_chats_project_id",
        "feishu_bot_bound_chats",
        ["project_id"],
    )
    _create_index_if_missing(
        "uq_feishu_bot_bound_chats_chat_id",
        "feishu_bot_bound_chats",
        ["chat_id"],
        unique=True,
    )

    if not _table_exists("project_svn_credentials"):
        op.create_table(
            "project_svn_credentials",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("password_cipher", sa.Text(), nullable=False, server_default=""),
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
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "ix_project_svn_credentials_project_id",
        "project_svn_credentials",
        ["project_id"],
        unique=True,
    )

    if not _table_exists("project_ai_credentials"):
        op.create_table(
            "project_ai_credentials",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("provider_preset", sa.String(length=64), nullable=False),
            sa.Column("base_url", sa.Text(), nullable=False, server_default=""),
            sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("encrypted_api_key", sa.Text(), nullable=False, server_default=""),
            sa.Column("extra_headers_json", sa.Text(), nullable=False, server_default="{}"),
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
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "ix_project_ai_credentials_project_id",
        "project_ai_credentials",
        ["project_id"],
        unique=True,
    )


def downgrade() -> None:
    if _table_exists("project_ai_credentials"):
        op.drop_table("project_ai_credentials")
    if _table_exists("project_svn_credentials"):
        op.drop_table("project_svn_credentials")
    if _table_exists("feishu_bot_bound_chats"):
        op.drop_table("feishu_bot_bound_chats")
    _drop_index_if_exists("ix_feishu_bot_configs_app_id", "feishu_bot_configs")
    _create_index_if_missing(
        "uq_feishu_bot_configs_app_id",
        "feishu_bot_configs",
        ["app_id"],
        unique=True,
    )
