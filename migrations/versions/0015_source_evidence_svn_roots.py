"""Add Source Evidence SVN root records.

Revision ID: 0015_source_evidence_svn_roots
Revises: 0014_source_evidence_authorizations
Create Date: 2026-07-01 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0015_source_evidence_svn_roots"
down_revision: str | None = "0014_source_evidence_authorizations"
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
    if not _table_exists("project_source_evidence_svn_roots"):
        op.create_table(
            "project_source_evidence_svn_roots",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("alias", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("svn_root_url", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="enabled",
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
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "uq_project_source_evidence_svn_roots_project_alias",
        "project_source_evidence_svn_roots",
        ["project_id", "alias"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_project_source_evidence_svn_roots_project_status",
        "project_source_evidence_svn_roots",
        ["project_id", "status"],
    )
    _create_index_if_missing(
        "ix_project_source_evidence_svn_roots_status",
        "project_source_evidence_svn_roots",
        ["status"],
    )


def downgrade() -> None:
    _drop_table_if_exists("project_source_evidence_svn_roots")
