"""Add project vision AI credentials and visual observation indexes.

Revision ID: 0013_project_vision_visual_observations
Revises: 0012_source_evidence_runs
Create Date: 2026-06-29 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0013_project_vision_visual_observations"
down_revision: str | None = "0012_source_evidence_runs"
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
    if not _table_exists("project_vision_ai_credentials"):
        op.create_table(
            "project_vision_ai_credentials",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("provider_preset", sa.String(length=64), nullable=False),
            sa.Column("base_url", sa.Text(), nullable=False, server_default=""),
            sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("encrypted_api_key", sa.Text(), nullable=False, server_default=""),
            sa.Column("extra_headers_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("last_test_status", sa.String(length=32), nullable=False, server_default=""),
            sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_test_error_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("updated_by", sa.Integer(), nullable=True),
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
            sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "ix_project_vision_ai_credentials_project_id",
        "project_vision_ai_credentials",
        ["project_id"],
        unique=True,
    )

    if not _table_exists("source_evidence_visual_observations"):
        op.create_table(
            "source_evidence_visual_observations",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("resource_id", sa.Integer(), nullable=True),
            sa.Column("ref", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("position", sa.Text(), nullable=False, server_default=""),
            sa.Column("filename", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="observed"),
            sa.Column("observation_path", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("adopted_by", sa.Integer(), nullable=True),
            sa.Column("revoked_by", sa.Integer(), nullable=True),
            sa.Column("adopted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.ForeignKeyConstraint(
                ["resource_id"],
                ["source_evidence_resources.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["adopted_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["revoked_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "ix_source_evidence_visual_observations_run_id",
        "source_evidence_visual_observations",
        ["run_id"],
    )
    _create_index_if_missing(
        "ix_source_evidence_visual_observations_project_id",
        "source_evidence_visual_observations",
        ["project_id"],
    )
    _create_index_if_missing(
        "ix_source_evidence_visual_observations_status",
        "source_evidence_visual_observations",
        ["status"],
    )
    _create_index_if_missing(
        "ix_source_evidence_visual_observations_project_status",
        "source_evidence_visual_observations",
        ["project_id", "status"],
    )
    _create_index_if_missing(
        "uq_source_evidence_visual_observations_run_ref",
        "source_evidence_visual_observations",
        ["run_id", "ref"],
        unique=True,
    )


def downgrade() -> None:
    _drop_table_if_exists("source_evidence_visual_observations")
    _drop_table_if_exists("project_vision_ai_credentials")
