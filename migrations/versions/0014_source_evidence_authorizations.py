"""Add Source Evidence Feishu authorization records.

Revision ID: 0014_source_evidence_authorizations
Revises: 0013_project_vision_visual_observations
Create Date: 2026-06-30 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0014_source_evidence_authorizations"
down_revision: str | None = "0013_project_vision_visual_observations"
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
    if not _table_exists("source_evidence_authorizations"):
        op.create_table(
            "source_evidence_authorizations",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("app_id", sa.String(length=64), nullable=False),
            sa.Column("doc_type", sa.String(length=32), nullable=False, server_default=""),
            sa.Column("permission", sa.String(length=16), nullable=False, server_default="edit"),
            sa.Column("source_token_hash", sa.String(length=64), nullable=False),
            sa.Column(
                "source_token_alias_hashes_json",
                sa.Text(),
                nullable=False,
                server_default="[]",
            ),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="authorization_sent",
            ),
            sa.Column("state_hash", sa.String(length=64), nullable=True),
            sa.Column("state_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("originating_run_id", sa.Integer(), nullable=True),
            sa.Column(
                "target_mode",
                sa.String(length=32),
                nullable=False,
                server_default="not_sent",
            ),
            sa.Column(
                "sent_targets_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "failed_targets_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "owner_candidates_truncated",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "authorized_by_open_id",
                sa.String(length=128),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "authorized_by_display_name_masked",
                sa.String(length=128),
                nullable=False,
                server_default="",
            ),
            sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "expires_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("invalidated_by", sa.Integer(), nullable=True),
            sa.Column("last_error_summary", sa.Text(), nullable=False, server_default=""),
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
            sa.ForeignKeyConstraint(["invalidated_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "uq_source_evidence_authorizations_project_app_source_perm",
        "source_evidence_authorizations",
        ["project_id", "app_id", "source_token_hash", "permission"],
        unique=True,
    )
    _create_index_if_missing(
        "uq_source_evidence_authorizations_state_hash",
        "source_evidence_authorizations",
        ["state_hash"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_source_evidence_authorizations_project_status_expires",
        "source_evidence_authorizations",
        ["project_id", "status", "expires_at"],
    )
    _create_index_if_missing(
        "ix_source_evidence_authorizations_project_originating_run",
        "source_evidence_authorizations",
        ["project_id", "originating_run_id"],
    )


def downgrade() -> None:
    _drop_table_if_exists("source_evidence_authorizations")
