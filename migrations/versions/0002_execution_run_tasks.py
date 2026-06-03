"""Add execution run task status fields.

Revision ID: 0002_execution_run_tasks
Revises: 0001_initial_schema
Create Date: 2026-06-03 12:40:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0002_execution_run_tasks"
down_revision: str | None = "0001_initial_schema"
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
    if column.name in _column_names(table_name):
        return
    op.add_column(table_name, column)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if index_name in _index_names(table_name):
        return
    op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    if not _table_exists("execution_runs"):
        return

    _add_column_if_missing(
        "execution_runs",
        sa.Column(
            "execution_mode",
            sa.String(length=16),
            server_default="sync",
            nullable=False,
        ),
    )
    _add_column_if_missing(
        "execution_runs",
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="success",
            nullable=False,
        ),
    )
    _add_column_if_missing(
        "execution_runs",
        sa.Column("error_message", sa.Text(), server_default="", nullable=False),
    )
    _add_column_if_missing(
        "execution_runs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        "execution_runs",
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    _create_index_if_missing(
        "ix_execution_runs_execution_mode",
        "execution_runs",
        ["execution_mode"],
    )
    _create_index_if_missing("ix_execution_runs_status", "execution_runs", ["status"])


def downgrade() -> None:
    if not _table_exists("execution_runs"):
        return

    for index_name in ("ix_execution_runs_status", "ix_execution_runs_execution_mode"):
        if index_name in _index_names("execution_runs"):
            op.drop_index(index_name, table_name="execution_runs")

    with op.batch_alter_table("execution_runs") as batch_op:
        for column_name in (
            "finished_at",
            "started_at",
            "error_message",
            "status",
            "execution_mode",
        ):
            if column_name in _column_names("execution_runs"):
                batch_op.drop_column(column_name)
