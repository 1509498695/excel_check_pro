"""Add V3 test case generation run records.

Revision ID: 0016_test_case_generation_runs
Revises: 0015_source_evidence_svn_roots
Create Date: 2026-07-02 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0016_test_case_generation_runs"
down_revision: str | None = "0015_source_evidence_svn_roots"
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
    if not _table_exists("test_case_generation_runs"):
        op.create_table(
            "test_case_generation_runs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("source_evidence_run_id", sa.Integer(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("cancelled_by", sa.Integer(), nullable=True),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="queued",
            ),
            sa.Column("planning_sheet_name", sa.String(length=255), nullable=False),
            sa.Column("reference_ids_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("primary_reference_id", sa.Integer(), nullable=True),
            sa.Column("primary_reference_sheet_name", sa.String(length=255), nullable=True),
            sa.Column("strict_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("completed_chunks", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_chunks", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("atom_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("case_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.CheckConstraint(
                "status IN ("
                "'queued', 'reading', 'chunking', 'extracting_atoms', "
                "'merging_atoms', 'blueprinting', 'generating_cases', "
                "'auditing_coverage', 'supplementing', 'completed', "
                "'partial_completed', 'failed', 'cancelled', 'expired'"
                ")",
                name="ck_test_case_generation_runs_status",
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["source_evidence_run_id"],
                ["source_evidence_runs.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["cancelled_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["primary_reference_id"],
                ["test_case_reference_files.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists("test_case_generation_chunks"):
        op.create_table(
            "test_case_generation_chunks",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("source_row_start", sa.Integer(), nullable=True),
            sa.Column("source_row_end", sa.Integer(), nullable=True),
            sa.Column("source_column_start", sa.Integer(), nullable=True),
            sa.Column("source_column_end", sa.Integer(), nullable=True),
            sa.Column("title_hint", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("structure_hints_json", sa.Text(), nullable=False, server_default="{}"),
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
            sa.ForeignKeyConstraint(
                ["run_id"],
                ["test_case_generation_runs.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists("test_case_requirement_atoms"):
        op.create_table(
            "test_case_requirement_atoms",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("chunk_id", sa.Integer(), nullable=True),
            sa.Column("atom_id", sa.String(length=64), nullable=False),
            sa.Column(
                "atom_type",
                sa.String(length=32),
                nullable=False,
                server_default="requirement",
            ),
            sa.Column("requirement_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("source_sheet_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("source_row_start", sa.Integer(), nullable=True),
            sa.Column("source_row_end", sa.Integer(), nullable=True),
            sa.Column("source_columns_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("cell_excerpt", sa.Text(), nullable=False, server_default=""),
            sa.Column("visual_evidence_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column(
                "coverage_status",
                sa.String(length=32),
                nullable=False,
                server_default="unmapped",
            ),
            sa.Column("merge_group_id", sa.String(length=64), nullable=False, server_default=""),
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
            sa.ForeignKeyConstraint(
                ["run_id"],
                ["test_case_generation_runs.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["chunk_id"],
                ["test_case_generation_chunks.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists("test_case_generation_cases"):
        op.create_table(
            "test_case_generation_cases",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("case_id", sa.String(length=64), nullable=False),
            sa.Column("fields_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("atom_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="official"),
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
            sa.ForeignKeyConstraint(
                ["run_id"],
                ["test_case_generation_runs.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if not _table_exists("test_case_coverage_audits"):
        op.create_table(
            "test_case_coverage_audits",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("total_atoms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("covered_atoms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("uncovered_atoms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("unfounded_case_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_chunk_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("uncovered_atom_ids_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("unfounded_candidates_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("supplement_summary_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("export_limitations_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
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
            sa.ForeignKeyConstraint(
                ["run_id"],
                ["test_case_generation_runs.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    _create_index_if_missing(
        "ix_test_case_generation_runs_project_id",
        "test_case_generation_runs",
        ["project_id"],
    )
    _create_index_if_missing(
        "ix_test_case_generation_runs_status",
        "test_case_generation_runs",
        ["status"],
    )
    _create_index_if_missing(
        "ix_test_case_generation_runs_project_status",
        "test_case_generation_runs",
        ["project_id", "status"],
    )
    _create_index_if_missing(
        "ix_test_case_generation_runs_project_expires",
        "test_case_generation_runs",
        ["project_id", "expires_at"],
    )
    _create_index_if_missing(
        "ix_test_case_generation_runs_source_evidence_run",
        "test_case_generation_runs",
        ["source_evidence_run_id"],
    )
    _create_index_if_missing(
        "uq_test_case_generation_chunks_run_chunk_index",
        "test_case_generation_chunks",
        ["run_id", "chunk_index"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_test_case_generation_chunks_run_id",
        "test_case_generation_chunks",
        ["run_id"],
    )
    _create_index_if_missing(
        "ix_test_case_generation_chunks_project_id",
        "test_case_generation_chunks",
        ["project_id"],
    )
    _create_index_if_missing(
        "ix_test_case_generation_chunks_project_status",
        "test_case_generation_chunks",
        ["project_id", "status"],
    )
    _create_index_if_missing(
        "uq_test_case_requirement_atoms_run_atom_id",
        "test_case_requirement_atoms",
        ["run_id", "atom_id"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_test_case_requirement_atoms_run_id",
        "test_case_requirement_atoms",
        ["run_id"],
    )
    _create_index_if_missing(
        "ix_test_case_requirement_atoms_project_id",
        "test_case_requirement_atoms",
        ["project_id"],
    )
    _create_index_if_missing(
        "ix_test_case_requirement_atoms_project_type",
        "test_case_requirement_atoms",
        ["project_id", "atom_type"],
    )
    _create_index_if_missing(
        "uq_test_case_generation_cases_run_case_id",
        "test_case_generation_cases",
        ["run_id", "case_id"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_test_case_generation_cases_run_id",
        "test_case_generation_cases",
        ["run_id"],
    )
    _create_index_if_missing(
        "ix_test_case_generation_cases_project_id",
        "test_case_generation_cases",
        ["project_id"],
    )
    _create_index_if_missing(
        "ix_test_case_generation_cases_project_status",
        "test_case_generation_cases",
        ["project_id", "status"],
    )
    _create_index_if_missing(
        "uq_test_case_coverage_audits_run_id",
        "test_case_coverage_audits",
        ["run_id"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_test_case_coverage_audits_project_id",
        "test_case_coverage_audits",
        ["project_id"],
    )
    _create_index_if_missing(
        "ix_test_case_coverage_audits_project_status",
        "test_case_coverage_audits",
        ["project_id", "status"],
    )


def downgrade() -> None:
    _drop_table_if_exists("test_case_coverage_audits")
    _drop_table_if_exists("test_case_generation_cases")
    _drop_table_if_exists("test_case_requirement_atoms")
    _drop_table_if_exists("test_case_generation_chunks")
    _drop_table_if_exists("test_case_generation_runs")
