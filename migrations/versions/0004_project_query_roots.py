"""Add project query roots for config lookup validation.

Revision ID: 0004_project_query_roots
Revises: 0003_rule_configs
Create Date: 2026-06-09 19:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004_project_query_roots"
down_revision: str | None = "0003_rule_configs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    return table_name in set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


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


def upgrade() -> None:
    if not _table_exists("project_query_roots"):
        op.create_table(
            "project_query_roots",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("alias", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("svn_root_url", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="enabled"),
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
        "uq_project_query_roots_project_alias",
        "project_query_roots",
        ["project_id", "alias"],
        unique=True,
    )
    _create_index_if_missing(
        "ix_project_query_roots_project_status",
        "project_query_roots",
        ["project_id", "status"],
    )
    _create_index_if_missing(
        "ix_project_query_roots_status",
        "project_query_roots",
        ["status"],
    )


def downgrade() -> None:
    if _table_exists("project_query_roots"):
        op.drop_table("project_query_roots")
