"""Alembic 数据库迁移契约测试。"""

from __future__ import annotations

from pathlib import Path

from alembic import command
import sqlalchemy as sa

from backend.app import models as _models  # noqa: F401
from backend.app.database import Base
from backend.app.db_migrations import (
    make_alembic_config,
    run_database_migrations,
    to_sync_database_url,
)


CURRENT_ALEMBIC_HEAD = "0018_test_case_generation_artifact_stages"
V3_BASE_ALEMBIC_HEAD = "0016_test_case_generation_runs"
PRE_V3_ALEMBIC_HEAD = "0015_source_evidence_svn_roots"
GENERATION_RUN_TABLES = {
    "test_case_generation_runs",
    "test_case_generation_chunks",
    "test_case_requirement_atoms",
    "test_case_generation_cases",
    "test_case_coverage_audits",
}
FORBIDDEN_GENERATION_RUN_COLUMNS = {
    "raw_prompt",
    "raw_response",
    "prompt",
    "provider_response",
}


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


def _assert_generation_run_schema(inspector: sa.Inspector) -> None:
    tables = set(inspector.get_table_names())
    assert GENERATION_RUN_TABLES.issubset(tables)

    run_columns = _column_names(inspector, "test_case_generation_runs")
    assert {
        "project_id",
        "source_evidence_run_id",
        "created_by",
        "cancelled_by",
        "status",
        "planning_sheet_name",
        "reference_ids_json",
        "primary_reference_id",
        "primary_reference_sheet_name",
        "strict_mode",
        "total_chunks",
        "completed_chunks",
        "failed_chunks",
        "atom_count",
        "case_count",
        "warning_count",
        "error_summary",
        "warnings_json",
        "summary_json",
        "stage_payload_json",
        "minimal_audit_json",
        "expires_at",
        "completed_at",
        "cancelled_at",
        "expired_at",
        "cleaned_at",
        "created_at",
        "updated_at",
    }.issubset(run_columns)
    assert FORBIDDEN_GENERATION_RUN_COLUMNS.isdisjoint(run_columns)
    run_indexes = _index_names(inspector, "test_case_generation_runs")
    assert "ix_test_case_generation_runs_project_status" in run_indexes
    assert "ix_test_case_generation_runs_project_expires" in run_indexes
    assert "ix_test_case_generation_runs_source_evidence_run" in run_indexes

    chunk_columns = _column_names(inspector, "test_case_generation_chunks")
    assert {
        "run_id",
        "project_id",
        "chunk_index",
        "status",
        "retry_count",
        "error_summary",
        "structure_hints_json",
        "created_at",
        "updated_at",
    }.issubset(chunk_columns)
    assert FORBIDDEN_GENERATION_RUN_COLUMNS.isdisjoint(chunk_columns)
    chunk_indexes = _index_names(inspector, "test_case_generation_chunks")
    assert "uq_test_case_generation_chunks_run_chunk_index" in chunk_indexes
    assert "ix_test_case_generation_chunks_project_status" in chunk_indexes

    atom_columns = _column_names(inspector, "test_case_requirement_atoms")
    assert {
        "run_id",
        "project_id",
        "chunk_id",
        "atom_id",
        "atom_type",
        "requirement_text",
        "source_sheet_name",
        "source_row_start",
        "source_row_end",
        "source_columns_json",
        "visual_evidence_refs_json",
        "confidence",
        "coverage_status",
        "merge_group_id",
        "created_at",
        "updated_at",
    }.issubset(atom_columns)
    assert FORBIDDEN_GENERATION_RUN_COLUMNS.isdisjoint(atom_columns)
    atom_indexes = _index_names(inspector, "test_case_requirement_atoms")
    assert "uq_test_case_requirement_atoms_run_atom_id" in atom_indexes
    assert "ix_test_case_requirement_atoms_project_type" in atom_indexes

    case_columns = _column_names(inspector, "test_case_generation_cases")
    assert {
        "run_id",
        "project_id",
        "case_id",
        "fields_json",
        "atom_refs_json",
        "status",
        "created_at",
        "updated_at",
    }.issubset(case_columns)
    assert FORBIDDEN_GENERATION_RUN_COLUMNS.isdisjoint(case_columns)
    case_indexes = _index_names(inspector, "test_case_generation_cases")
    assert "uq_test_case_generation_cases_run_case_id" in case_indexes
    assert "ix_test_case_generation_cases_project_id" in case_indexes

    audit_columns = _column_names(inspector, "test_case_coverage_audits")
    assert {
        "run_id",
        "project_id",
        "status",
        "total_atoms",
        "covered_atoms",
        "uncovered_atoms",
        "unfounded_case_count",
        "failed_chunk_count",
        "uncovered_atom_ids_json",
        "unfounded_candidates_json",
        "supplement_summary_json",
        "export_limitations_json",
        "warnings_json",
        "created_at",
        "updated_at",
    }.issubset(audit_columns)
    assert FORBIDDEN_GENERATION_RUN_COLUMNS.isdisjoint(audit_columns)
    audit_indexes = _index_names(inspector, "test_case_coverage_audits")
    assert "uq_test_case_coverage_audits_run_id" in audit_indexes
    assert "ix_test_case_coverage_audits_project_id" in audit_indexes


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
    assert "test_case_generation_history" not in tables

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
        "query_type",
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
        "rule_config_id",
        "project_id",
        "rule_family",
        "query_type",
        "version",
        "content_md",
        "parsed_config_json",
        "status",
        "action",
        "operator",
        "description",
        "created_at",
    }.issubset(_column_names(inspector, "rule_config_versions"))
    assert "uq_rule_configs_project_family_query_type" in _index_names(
        inspector,
        "rule_configs",
    )
    assert "uq_rule_config_versions_rule_config_version" in _index_names(
        inspector,
        "rule_config_versions",
    )
    assert "ix_rule_config_versions_rule_config_id" in _index_names(
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
        "project_id",
        "alias",
        "display_name",
        "svn_root_url",
        "status",
        "created_at",
        "updated_at",
    }.issubset(_column_names(inspector, "project_source_evidence_svn_roots"))
    assert "uq_project_source_evidence_svn_roots_project_alias" in _index_names(
        inspector,
        "project_source_evidence_svn_roots",
    )
    assert "ix_project_source_evidence_svn_roots_project_status" in _index_names(
        inspector,
        "project_source_evidence_svn_roots",
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
    assert {
        "project_id",
        "provider_preset",
        "base_url",
        "model",
        "encrypted_api_key",
        "extra_headers_json",
        "enabled",
        "last_test_status",
        "last_test_at",
        "last_test_error_summary",
        "updated_by",
        "created_at",
        "updated_at",
    }.issubset(_column_names(inspector, "project_vision_ai_credentials"))
    assert "ix_project_vision_ai_credentials_project_id" in _index_names(
        inspector,
        "project_vision_ai_credentials",
    )
    assert {
        "project_id",
        "name",
        "name_key",
        "created_by",
        "created_at",
        "updated_at",
    }.issubset(_column_names(inspector, "test_case_reference_categories"))
    assert "uq_test_case_reference_categories_project_name_key" in _index_names(
        inspector,
        "test_case_reference_categories",
    )
    assert {
        "project_id",
        "category_id",
        "original_filename",
        "stored_filename",
        "suffix",
        "size_bytes",
        "storage_path",
        "profile_json",
        "is_recommended_primary",
        "uploaded_by",
        "deleted_by",
        "deleted_at",
        "created_at",
        "updated_at",
    }.issubset(_column_names(inspector, "test_case_reference_files"))
    assert "profile_status" not in _column_names(inspector, "test_case_reference_files")
    assert "profile_error" not in _column_names(inspector, "test_case_reference_files")
    assert "ix_test_case_reference_files_project_category" in _index_names(
        inspector,
        "test_case_reference_files",
    )
    assert "ix_test_case_reference_files_project_recommended" in _index_names(
        inspector,
        "test_case_reference_files",
    )
    assert {
        "project_id",
        "source_type",
        "source_url",
        "source_token",
        "source_identifier",
        "source_title",
        "status",
        "storage_path",
        "expires_at",
        "created_by",
        "cleaned_by",
        "error_summary",
        "raw_manifest_json",
        "minimal_audit_json",
        "created_at",
        "updated_at",
        "cleaned_at",
    }.issubset(_column_names(inspector, "source_evidence_runs"))
    assert "ix_source_evidence_runs_project_status" in _index_names(
        inspector,
        "source_evidence_runs",
    )
    assert "ix_source_evidence_runs_project_expires" in _index_names(
        inspector,
        "source_evidence_runs",
    )
    assert {
        "run_id",
        "project_id",
        "ref",
        "resource_type",
        "position",
        "filename",
        "file_token",
        "status",
        "download_status",
        "local_path",
        "mime_type",
        "observation_json",
        "visual_packet_path",
        "metadata_json",
        "created_at",
        "updated_at",
        "cleaned_at",
    }.issubset(_column_names(inspector, "source_evidence_resources"))
    assert "ix_source_evidence_resources_project_status" in _index_names(
        inspector,
        "source_evidence_resources",
    )
    assert "ix_source_evidence_resources_run_ref" in _index_names(
        inspector,
        "source_evidence_resources",
    )
    assert {
        "run_id",
        "project_id",
        "resource_id",
        "ref",
        "position",
        "filename",
        "status",
        "observation_path",
        "created_by",
        "adopted_by",
        "revoked_by",
        "adopted_at",
        "revoked_at",
        "cleaned_at",
        "created_at",
        "updated_at",
    }.issubset(_column_names(inspector, "source_evidence_visual_observations"))
    assert "ix_source_evidence_visual_observations_project_status" in _index_names(
        inspector,
        "source_evidence_visual_observations",
    )
    assert "uq_source_evidence_visual_observations_run_ref" in _index_names(
        inspector,
        "source_evidence_visual_observations",
    )
    assert {
        "project_id",
        "app_id",
        "doc_type",
        "permission",
        "source_token_hash",
        "source_token_alias_hashes_json",
        "status",
        "state_hash",
        "state_expires_at",
        "originating_run_id",
        "target_mode",
        "sent_targets_count",
        "failed_targets_count",
        "owner_candidates_truncated",
        "authorized_by_open_id",
        "authorized_by_display_name_masked",
        "authorized_at",
        "expires_at",
        "invalidated_at",
        "invalidated_by",
        "last_error_summary",
        "created_at",
        "updated_at",
    }.issubset(_column_names(inspector, "source_evidence_authorizations"))
    authorization_indexes = _index_names(inspector, "source_evidence_authorizations")
    assert "uq_source_evidence_authorizations_project_app_source_perm" in authorization_indexes
    assert "uq_source_evidence_authorizations_state_hash" in authorization_indexes
    assert "ix_source_evidence_authorizations_project_status_expires" in authorization_indexes
    assert "ix_source_evidence_authorizations_project_originating_run" in authorization_indexes
    assert {
        "blueprint_json",
        "cases_json",
        "prompt",
        "provider_response",
    }.isdisjoint(_column_names(inspector, "source_evidence_runs"))
    assert {
        "blueprint_json",
        "cases_json",
        "prompt",
        "provider_response",
    }.isdisjoint(_column_names(inspector, "source_evidence_resources"))
    assert {
        "prompt",
        "provider_response",
        "local_path",
        "file_token",
    }.isdisjoint(_column_names(inspector, "source_evidence_visual_observations"))
    _assert_generation_run_schema(inspector)
    assert _alembic_version(db_path) == CURRENT_ALEMBIC_HEAD


def test_downgrade_from_v3_removes_generation_run_tables(tmp_path: Path) -> None:
    """从 V3 迁移降级回 0015 时应删除 Generation Run 新表。"""
    db_path = tmp_path / "downgrade-v3.db"
    db_url = _async_sqlite_url(db_path)

    run_database_migrations(db_url)
    command.downgrade(make_alembic_config(db_url), PRE_V3_ALEMBIC_HEAD)

    inspector = _inspect_database(db_path)
    assert GENERATION_RUN_TABLES.isdisjoint(set(inspector.get_table_names()))
    assert _alembic_version(db_path) == PRE_V3_ALEMBIC_HEAD


def test_generation_run_cleanup_migration_adds_and_downgrades_columns(
    tmp_path: Path,
) -> None:
    """0017 只为 Generation Run 主表增加 TTL 清理审计列，可降级移除。"""
    db_path = tmp_path / "generation-run-cleanup.db"
    db_url = _async_sqlite_url(db_path)
    cleanup_columns = {
        "completed_at",
        "cleaned_at",
        "stage_payload_json",
        "minimal_audit_json",
    }

    config = make_alembic_config(db_url)
    command.upgrade(config, V3_BASE_ALEMBIC_HEAD)
    inspector = _inspect_database(db_path)
    assert GENERATION_RUN_TABLES.issubset(set(inspector.get_table_names()))
    assert cleanup_columns.isdisjoint(
        _column_names(inspector, "test_case_generation_runs")
    )

    command.upgrade(config, CURRENT_ALEMBIC_HEAD)
    inspector = _inspect_database(db_path)
    assert cleanup_columns.issubset(
        _column_names(inspector, "test_case_generation_runs")
    )
    assert FORBIDDEN_GENERATION_RUN_COLUMNS.isdisjoint(
        _column_names(inspector, "test_case_generation_runs")
    )

    command.downgrade(config, V3_BASE_ALEMBIC_HEAD)
    inspector = _inspect_database(db_path)
    assert cleanup_columns.isdisjoint(
        _column_names(inspector, "test_case_generation_runs")
    )
    assert _alembic_version(db_path) == V3_BASE_ALEMBIC_HEAD


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
    assert "test_case_reference_categories" in set(inspector.get_table_names())
    assert "test_case_reference_files" in set(inspector.get_table_names())
    assert "source_evidence_runs" in set(inspector.get_table_names())
    assert "source_evidence_resources" in set(inspector.get_table_names())
    assert "project_source_evidence_svn_roots" in set(inspector.get_table_names())
    assert GENERATION_RUN_TABLES.issubset(set(inspector.get_table_names()))
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
    assert "name_key" in _column_names(inspector, "test_case_reference_categories")
    assert "uq_test_case_reference_categories_project_name_key" in _index_names(
        inspector,
        "test_case_reference_categories",
    )

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


def test_migrate_old_reference_library_revision_adds_category_name_key(
    tmp_path: Path,
) -> None:
    """已执行旧 0010 的库也要补齐 trim 后唯一键，避免执行顺序漂移。"""
    db_path = tmp_path / "old-reference-library.db"
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        metadata = sa.MetaData()
        sa.Table(
            "alembic_version",
            metadata,
            sa.Column("version_num", sa.String(32), primary_key=True),
        )
        sa.Table(
            "test_case_reference_categories",
            metadata,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO alembic_version (version_num) "
                    "VALUES ('0010_test_case_reference_library')"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO test_case_reference_categories "
                    "(id, project_id, name, created_by, created_at, updated_at) "
                    "VALUES (1, 1, '  冒烟  ', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
    finally:
        engine.dispose()

    run_database_migrations(_async_sqlite_url(db_path))

    inspector = _inspect_database(db_path)
    assert "name_key" in _column_names(inspector, "test_case_reference_categories")
    assert "uq_test_case_reference_categories_project_name_key" in _index_names(
        inspector,
        "test_case_reference_categories",
    )

    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with engine.connect() as conn:
            name_key = conn.execute(
                sa.text("SELECT name_key FROM test_case_reference_categories WHERE id = 1")
            ).scalar_one()
    finally:
        engine.dispose()

    assert name_key == "冒烟"
    assert "source_evidence_runs" in set(inspector.get_table_names())
    assert "source_evidence_resources" in set(inspector.get_table_names())
    assert "source_evidence_authorizations" in set(inspector.get_table_names())
    assert "project_source_evidence_svn_roots" in set(inspector.get_table_names())
    assert GENERATION_RUN_TABLES.issubset(set(inspector.get_table_names()))
    assert _alembic_version(db_path) == CURRENT_ALEMBIC_HEAD


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
    assert "test_case_reference_categories" in set(inspector.get_table_names())
    assert "source_evidence_runs" in set(inspector.get_table_names())
    assert "source_evidence_resources" in set(inspector.get_table_names())
    assert "source_evidence_authorizations" in set(inspector.get_table_names())
    assert "project_source_evidence_svn_roots" in set(inspector.get_table_names())
    assert GENERATION_RUN_TABLES.issubset(set(inspector.get_table_names()))
    assert "name_key" in _column_names(inspector, "test_case_reference_categories")
    assert _alembic_version(db_path) == CURRENT_ALEMBIC_HEAD
