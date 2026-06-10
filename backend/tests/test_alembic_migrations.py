"""Alembic 数据库迁移契约测试。"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa

from backend.app import models as _models  # noqa: F401
from backend.app.database import Base
from backend.app.db_migrations import run_database_migrations, to_sync_database_url


def _async_sqlite_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


def _inspect_database(path: Path) -> sa.Inspector:
    engine = sa.create_engine(f"sqlite:///{path.as_posix()}")
    try:
        return sa.inspect(engine)
    finally:
        engine.dispose()


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _sqlite_master_sql(path: Path, object_name: str) -> str:
    engine = sa.create_engine(f"sqlite:///{path.as_posix()}")
    try:
        with engine.connect() as conn:
            return (
                conn.execute(
                    sa.text("SELECT sql FROM sqlite_master WHERE name = :name"),
                    {"name": object_name},
                ).scalar_one()
                or ""
            )
    finally:
        engine.dispose()


def _alembic_version(path: Path) -> str:
    engine = sa.create_engine(f"sqlite:///{path.as_posix()}")
    try:
        with engine.connect() as conn:
            return conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()


def test_migrate_empty_sqlite_database_creates_current_schema(tmp_path: Path) -> None:
    """空 SQLite 库执行 Alembic 后应包含当前 ORM 表和版本表。"""
    db_path = tmp_path / "nested" / "fresh.db"

    run_database_migrations(_async_sqlite_url(db_path))

    assert db_path.is_file()
    inspector = _inspect_database(db_path)
    tables = set(inspector.get_table_names())
    assert set(Base.metadata.tables).issubset(tables)
    assert "alembic_version" in tables
    assert "ai_rule_drafts" not in tables
    assert "ai_provider_credentials" not in tables

    assert to_sync_database_url(_async_sqlite_url(db_path)).startswith("sqlite:///")
    execution_run_columns = _column_names(inspector, "execution_runs")
    assert {
        "execution_mode",
        "status",
        "error_message",
        "started_at",
        "finished_at",
    }.issubset(execution_run_columns)
    assert "ix_execution_runs_execution_mode" in _index_names(inspector, "execution_runs")
    assert "ix_execution_runs_status" in _index_names(inspector, "execution_runs")
    assert {
        "project_id",
        "rule_family",
        "content_md",
        "parsed_config_json",
        "status",
        "draft_version",
        "published_version",
        "created_by",
        "updated_by",
        "published_by",
        "published_at",
        "optimistic_lock_version",
    }.issubset(_column_names(inspector, "rule_configs"))
    assert {
        "project_id",
        "rule_family",
        "version",
        "content_md",
        "parsed_config_json",
        "status",
        "action",
        "operator",
        "description",
        "created_at",
    }.issubset(_column_names(inspector, "rule_config_versions"))
    assert "uq_rule_configs_project_family" in _index_names(inspector, "rule_configs")
    assert "uq_rule_config_versions_project_family_version" in _index_names(
        inspector,
        "rule_config_versions",
    )
    assert {
        "project_id",
        "alias",
        "display_name",
        "svn_root_url",
        "status",
        "created_at",
        "updated_at",
    }.issubset(_column_names(inspector, "project_query_roots"))
    assert "uq_project_query_roots_project_alias" in _index_names(
        inspector,
        "project_query_roots",
    )
    assert "ix_project_query_roots_project_status" in _index_names(
        inspector,
        "project_query_roots",
    )
    assert {
        "auto_match_threshold",
        "candidate_threshold",
        "max_candidates",
    }.issubset(_column_names(inspector, "feishu_bot_configs"))
    assert "ix_feishu_bot_configs_app_id" in _index_names(
        inspector,
        "feishu_bot_configs",
    )
    assert "uq_feishu_bot_configs_app_id" not in _index_names(
        inspector,
        "feishu_bot_configs",
    )
    assert {
        "project_id",
        "chat_id",
        "created_at",
    }.issubset(_column_names(inspector, "feishu_bot_bound_chats"))
    assert "uq_feishu_bot_bound_chats_chat_id" in _index_names(
        inspector,
        "feishu_bot_bound_chats",
    )
    assert "ix_feishu_bot_bound_chats_project_id" in _index_names(
        inspector,
        "feishu_bot_bound_chats",
    )
    assert {
        "project_id",
        "username",
        "password_cipher",
        "created_at",
        "updated_at",
    }.issubset(_column_names(inspector, "project_svn_credentials"))
    assert "ix_project_svn_credentials_project_id" in _index_names(
        inspector,
        "project_svn_credentials",
    )
    assert {
        "project_id",
        "provider_preset",
        "base_url",
        "model",
        "encrypted_api_key",
        "extra_headers_json",
        "enabled",
        "auto_match_threshold",
        "candidate_threshold",
        "max_candidates",
        "last_test_status",
        "last_test_at",
        "last_test_error_summary",
        "updated_by",
        "created_at",
        "updated_at",
    }.issubset(_column_names(inspector, "project_ai_credentials"))
    assert "ix_project_ai_credentials_project_id" in _index_names(
        inspector,
        "project_ai_credentials",
    )
    assert _alembic_version(db_path) == "0008_drop_ai_provider_credentials"


def test_migrate_legacy_sqlite_database_adds_missing_columns_and_indexes(
    tmp_path: Path,
) -> None:
    """旧库缺少历史手工 ALTER 字段时，应由正式 migration 补齐。"""
    db_path = tmp_path / "legacy.db"
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        metadata = sa.MetaData()
        sa.Table(
            "projects",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(128), nullable=False, unique=True),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        sa.Table(
            "users",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(64), nullable=False, unique=True),
            sa.Column("hashed_password", sa.String(256), nullable=False),
            sa.Column("is_super_admin", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        sa.Table(
            "execution_runs",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("scope_type", sa.String(32), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("total_results", sa.Integer(), nullable=False),
            sa.Column("execution_time_ms", sa.Integer(), nullable=False),
            sa.Column("total_rows_scanned", sa.Integer(), nullable=False),
            sa.Column("failed_sources_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        sa.Table(
            "execution_result_items",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("sort_index", sa.Integer(), nullable=False),
            sa.Column("level", sa.String(32), nullable=False),
            sa.Column("rule_name", sa.String(255), nullable=False),
            sa.Column("location", sa.Text(), nullable=False),
            sa.Column("row_index", sa.Integer(), nullable=False),
            sa.Column("raw_value_json", sa.Text(), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
        )
        sa.Table(
            "feishu_bot_configs",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("app_id", sa.String(64), nullable=False),
            sa.Column("app_secret_cipher", sa.Text(), nullable=False),
            sa.Column("default_chat_id", sa.String(128), nullable=False),
            sa.Column("allowed_open_ids", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO execution_runs "
                    "(id, scope_type, project_id, user_id, total_results, "
                    "execution_time_ms, total_rows_scanned, failed_sources_json, created_at) "
                    "VALUES "
                    "(1, 'workbench', 1, 1, 0, 0, 0, '[]', CURRENT_TIMESTAMP)"
                )
            )
    finally:
        engine.dispose()

    run_database_migrations(_async_sqlite_url(db_path))

    inspector = _inspect_database(db_path)
    assert {
        "primary_project_id",
    }.issubset(_column_names(inspector, "users"))
    assert {
        "display_value_json",
        "extra_json",
    }.issubset(_column_names(inspector, "execution_result_items"))
    assert {
        "local_download_roots",
        "svn_download_roots",
        "allowed_download_suffixes",
        "auto_match_threshold",
        "candidate_threshold",
        "max_candidates",
    }.issubset(_column_names(inspector, "feishu_bot_configs"))
    assert "ix_users_primary_project_id" in _index_names(inspector, "users")
    assert "ix_execution_result_items_run_id" in _index_names(
        inspector,
        "execution_result_items",
    )
    assert "ix_feishu_bot_configs_app_id" in _index_names(
        inspector,
        "feishu_bot_configs",
    )
    assert "uq_feishu_bot_configs_app_id" not in _index_names(
        inspector,
        "feishu_bot_configs",
    )
    assert "feishu_bot_bound_chats" in set(inspector.get_table_names())
    assert "project_svn_credentials" in set(inspector.get_table_names())
    assert "project_ai_credentials" in set(inspector.get_table_names())
    assert "ai_provider_credentials" not in set(inspector.get_table_names())
    assert {
        "enabled",
        "auto_match_threshold",
        "candidate_threshold",
        "max_candidates",
        "last_test_status",
        "last_test_at",
        "last_test_error_summary",
        "updated_by",
    }.issubset(_column_names(inspector, "project_ai_credentials"))
    assert {
        "execution_mode",
        "status",
        "error_message",
        "started_at",
        "finished_at",
    }.issubset(_column_names(inspector, "execution_runs"))
    assert "ix_execution_runs_execution_mode" in _index_names(inspector, "execution_runs")
    assert "ix_execution_runs_status" in _index_names(inspector, "execution_runs")

    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT execution_mode, status, error_message "
                    "FROM execution_runs WHERE id = 1"
                )
            ).one()
    finally:
        engine.dispose()
    assert row == ("sync", "success", "")


def test_migration_can_run_twice_without_duplicate_columns(tmp_path: Path) -> None:
    """迁移重复执行应保持幂等，不重复添加历史字段。"""
    db_path = tmp_path / "idempotent.db"
    db_url = _async_sqlite_url(db_path)

    run_database_migrations(db_url)
    run_database_migrations(db_url)

    inspector = _inspect_database(db_path)
    assert "extra_json" in _column_names(inspector, "execution_result_items")
    assert "status" in _column_names(inspector, "execution_runs")
    assert "project_query_roots" in set(inspector.get_table_names())
    assert "feishu_bot_bound_chats" in set(inspector.get_table_names())
    assert _alembic_version(db_path) == "0008_drop_ai_provider_credentials"
