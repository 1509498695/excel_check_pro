"""Initial database schema and legacy SQLite upgrade.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-03 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name: str) -> set[str]:
    if table_name not in _table_names():
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    if table_name not in _table_names():
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
    **dialect_options,
) -> None:
    if table_name not in _table_names():
        return
    if index_name in _index_names(table_name):
        return
    op.create_index(index_name, table_name, columns, unique=unique, **dialect_options)


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if table_name not in _table_names():
        return
    if column.name in _column_names(table_name):
        return
    op.add_column(table_name, column)


def _create_tables() -> None:
    existing_tables = _table_names()

    if "projects" not in existing_tables:
        op.create_table(
            "projects",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("username", sa.String(length=64), nullable=False),
            sa.Column("hashed_password", sa.String(length=256), nullable=False),
            sa.Column("is_super_admin", sa.Boolean(), nullable=False),
            sa.Column("primary_project_id", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["primary_project_id"],
                ["projects.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("username"),
        )

    if "feishu_bot_configs" not in existing_tables:
        op.create_table(
            "feishu_bot_configs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("app_id", sa.String(length=64), nullable=False),
            sa.Column("app_secret_cipher", sa.Text(), nullable=False),
            sa.Column("default_chat_id", sa.String(length=128), nullable=False),
            sa.Column("allowed_open_ids", sa.Text(), nullable=False),
            sa.Column("local_download_roots", sa.Text(), nullable=False),
            sa.Column("svn_download_roots", sa.Text(), nullable=False),
            sa.Column("allowed_download_suffixes", sa.Text(), nullable=False),
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

    if "feishu_sheet_authorizations" not in existing_tables:
        op.create_table(
            "feishu_sheet_authorizations",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("source_id", sa.String(length=128), nullable=False),
            sa.Column("spreadsheet_token", sa.String(length=128), nullable=False),
            sa.Column("sheet_url", sa.Text(), nullable=False),
            sa.Column("sheet_title", sa.String(length=255), nullable=False),
            sa.Column("authorized_by_open_id", sa.String(length=128), nullable=False),
            sa.Column("bot_open_id", sa.String(length=128), nullable=False),
            sa.Column("chat_id", sa.String(length=128), nullable=False),
            sa.Column("message_id", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=False),
            sa.Column("state_hash", sa.String(length=128), nullable=False),
            sa.Column("state_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.UniqueConstraint(
                "project_id",
                "source_id",
                name="uq_feishu_sheet_auth_project_source",
            ),
        )

    if "fixed_rules_configs" not in existing_tables:
        op.create_table(
            "fixed_rules_configs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("config_json", sa.Text(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if "ai_provider_credentials" not in existing_tables:
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

    if "ai_rule_drafts" not in existing_tables:
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

    if "execution_runs" not in existing_tables:
        op.create_table(
            "execution_runs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("scope_type", sa.String(length=32), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("total_results", sa.Integer(), nullable=False),
            sa.Column("execution_time_ms", sa.Integer(), nullable=False),
            sa.Column("total_rows_scanned", sa.Integer(), nullable=False),
            sa.Column("failed_sources_json", sa.Text(), nullable=False),
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

    if "user_project_roles" not in existing_tables:
        op.create_table(
            "user_project_roles",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column(
                "joined_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if "workbench_configs" not in existing_tables:
        op.create_table(
            "workbench_configs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("config_json", sa.Text(), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if "execution_result_items" not in existing_tables:
        op.create_table(
            "execution_result_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("sort_index", sa.Integer(), nullable=False),
            sa.Column("level", sa.String(length=32), nullable=False),
            sa.Column("rule_name", sa.String(length=255), nullable=False),
            sa.Column("location", sa.Text(), nullable=False),
            sa.Column("row_index", sa.Integer(), nullable=False),
            sa.Column("raw_value_json", sa.Text(), nullable=False),
            sa.Column("display_value_json", sa.Text(), nullable=False),
            sa.Column("extra_json", sa.Text(), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["execution_runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )


def _upgrade_legacy_columns() -> None:
    _add_column_if_missing(
        "users",
        sa.Column("primary_project_id", sa.Integer(), nullable=True),
    )
    _add_column_if_missing(
        "execution_result_items",
        sa.Column("display_value_json", sa.Text(), server_default="null", nullable=True),
    )
    _add_column_if_missing(
        "execution_result_items",
        sa.Column("extra_json", sa.Text(), server_default="{}", nullable=True),
    )
    _add_column_if_missing(
        "feishu_bot_configs",
        sa.Column("local_download_roots", sa.Text(), server_default="[]", nullable=True),
    )
    _add_column_if_missing(
        "feishu_bot_configs",
        sa.Column("svn_download_roots", sa.Text(), server_default="[]", nullable=True),
    )
    _add_column_if_missing(
        "feishu_bot_configs",
        sa.Column(
            "allowed_download_suffixes",
            sa.Text(),
            server_default='[".xls",".xlsx",".csv",".json",".xml",".txt"]',
            nullable=True,
        ),
    )


def _create_indexes() -> None:
    _create_index_if_missing(
        "ix_feishu_bot_configs_project_id",
        "feishu_bot_configs",
        ["project_id"],
        unique=True,
    )
    _create_index_if_missing(
        "uq_feishu_bot_configs_app_id",
        "feishu_bot_configs",
        ["app_id"],
        unique=True,
        sqlite_where=sa.text("app_id <> ''"),
    )
    _create_index_if_missing(
        "ix_feishu_sheet_auth_project_token",
        "feishu_sheet_authorizations",
        ["project_id", "spreadsheet_token"],
    )
    _create_index_if_missing(
        "ix_feishu_sheet_authorizations_spreadsheet_token",
        "feishu_sheet_authorizations",
        ["spreadsheet_token"],
    )
    _create_index_if_missing(
        "ix_feishu_sheet_authorizations_status",
        "feishu_sheet_authorizations",
        ["status"],
    )
    _create_index_if_missing(
        "ix_fixed_rules_configs_project_id",
        "fixed_rules_configs",
        ["project_id"],
    )
    _create_index_if_missing("ix_users_primary_project_id", "users", ["primary_project_id"])
    _create_index_if_missing(
        "ix_ai_provider_credentials_user_id",
        "ai_provider_credentials",
        ["user_id"],
        unique=True,
    )
    _create_index_if_missing("ix_ai_rule_drafts_project_id", "ai_rule_drafts", ["project_id"])
    _create_index_if_missing("ix_ai_rule_drafts_user_id", "ai_rule_drafts", ["user_id"])
    _create_index_if_missing("ix_ai_rule_drafts_created_at", "ai_rule_drafts", ["created_at"])
    _create_index_if_missing("ix_execution_runs_scope_type", "execution_runs", ["scope_type"])
    _create_index_if_missing("ix_execution_runs_project_id", "execution_runs", ["project_id"])
    _create_index_if_missing("ix_execution_runs_user_id", "execution_runs", ["user_id"])
    _create_index_if_missing(
        "ix_workbench_configs_project_id",
        "workbench_configs",
        ["project_id"],
    )
    _create_index_if_missing(
        "ix_workbench_configs_user_id",
        "workbench_configs",
        ["user_id"],
    )
    _create_index_if_missing(
        "ix_execution_result_items_run_id",
        "execution_result_items",
        ["run_id"],
    )
    _create_index_if_missing(
        "ix_execution_result_items_sort_index",
        "execution_result_items",
        ["sort_index"],
    )


def upgrade() -> None:
    _create_tables()
    _upgrade_legacy_columns()
    _create_indexes()


def downgrade() -> None:
    for table_name in (
        "execution_result_items",
        "workbench_configs",
        "user_project_roles",
        "execution_runs",
        "ai_rule_drafts",
        "ai_provider_credentials",
        "users",
        "fixed_rules_configs",
        "feishu_sheet_authorizations",
        "feishu_bot_configs",
        "projects",
    ):
        if table_name in _table_names():
            op.drop_table(table_name)
