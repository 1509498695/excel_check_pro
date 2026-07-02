"""Add source evidence run tables.

Revision ID: 0012_source_evidence_runs
Revises: 0011_test_case_reference_category_name_key
Create Date: 2026-06-29 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0012_source_evidence_runs"
down_revision: str | None = "0011_test_case_reference_category_name_key"
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
    if not _table_exists("source_evidence_runs"):
        op.create_table(
            "source_evidence_runs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("source_type", sa.String(length=32), nullable=False, server_default=""),
            sa.Column("source_url", sa.Text(), nullable=False, server_default=""),
            sa.Column("source_token", sa.Text(), nullable=False, server_default=""),
            sa.Column("source_identifier", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("source_title", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="reading"),
            sa.Column("storage_path", sa.Text(), nullable=False, server_default=""),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("cleaned_by", sa.Integer(), nullable=True),
            sa.Column("error_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("raw_manifest_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("minimal_audit_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("cleaned_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.ForeignKeyConstraint(["cleaned_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    _create_index_if_missing(
        "ix_source_evidence_runs_project_id",
        "source_evidence_runs",
        ["project_id"],
    )
    _create_index_if_missing(
        "ix_source_evidence_runs_status",
        "source_evidence_runs",
        ["status"],
    )
    _create_index_if_missing(
        "ix_source_evidence_runs_project_status",
        "source_evidence_runs",
        ["project_id", "status"],
    )
    _create_index_if_missing(
        "ix_source_evidence_runs_project_expires",
        "source_evidence_runs",
        ["project_id", "expires_at"],
    )

    if not _table_exists("source_evidence_resources"):
        op.create_table(
            "source_evidence_resources",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("ref", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("resource_type", sa.String(length=32), nullable=False, server_default=""),
            sa.Column("position", sa.Text(), nullable=False, server_default=""),
            sa.Column("filename", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("file_token", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column(
                "download_status",
                sa.String(length=32),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("local_path", sa.Text(), nullable=False, server_default=""),
            sa.Column("mime_type", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("observation_json", sa.Text(), nullable=False, server_default=""),
            sa.Column("visual_packet_path", sa.Text(), nullable=False, server_default=""),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("cleaned_at", sa.DateTime(timezone=True), nullable=True),
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
                ["source_evidence_runs.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    _create_index_if_missing(
        "ix_source_evidence_resources_run_id",
        "source_evidence_resources",
        ["run_id"],
    )
    _create_index_if_missing(
        "ix_source_evidence_resources_project_id",
        "source_evidence_resources",
        ["project_id"],
    )
    _create_index_if_missing(
        "ix_source_evidence_resources_status",
        "source_evidence_resources",
        ["status"],
    )
    _create_index_if_missing(
        "ix_source_evidence_resources_project_status",
        "source_evidence_resources",
        ["project_id", "status"],
    )
    _create_index_if_missing(
        "ix_source_evidence_resources_run_ref",
        "source_evidence_resources",
        ["run_id", "ref"],
    )


def downgrade() -> None:
    _drop_table_if_exists("source_evidence_resources")
    _drop_table_if_exists("source_evidence_runs")
