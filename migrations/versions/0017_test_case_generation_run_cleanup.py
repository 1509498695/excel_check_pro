"""Add cleanup metadata to V3 generation runs.

Revision ID: 0017_test_case_generation_run_cleanup
Revises: 0016_test_case_generation_runs
Create Date: 2026-07-03 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0017_test_case_generation_run_cleanup"
down_revision: str | None = "0016_test_case_generation_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _table_exists(table_name):
        return
    if _column_exists(table_name, column.name):
        return
    op.add_column(table_name, column)


def upgrade() -> None:
    table_name = "test_case_generation_runs"
    _add_column_if_missing(
        table_name,
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        table_name,
        sa.Column("cleaned_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        table_name,
        sa.Column(
            "stage_payload_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
    )
    _add_column_if_missing(
        table_name,
        sa.Column(
            "minimal_audit_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    table_name = "test_case_generation_runs"
    if not _table_exists(table_name):
        return
    removable_columns = [
        "minimal_audit_json",
        "stage_payload_json",
        "cleaned_at",
        "completed_at",
    ]
    existing_columns = [
        column_name
        for column_name in removable_columns
        if _column_exists(table_name, column_name)
    ]
    if not existing_columns:
        return
    with op.batch_alter_table(table_name) as batch_op:
        for column_name in existing_columns:
            batch_op.drop_column(column_name)
