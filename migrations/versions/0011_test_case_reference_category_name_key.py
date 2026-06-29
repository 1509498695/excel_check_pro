"""Repair test case reference category trimmed name key.

Revision ID: 0011_test_case_reference_category_name_key
Revises: 0010_test_case_reference_library
Create Date: 2026-06-25 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0011_test_case_reference_category_name_key"
down_revision: str | None = "0010_test_case_reference_library"
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


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(table_name))


def upgrade() -> None:
    table_name = "test_case_reference_categories"
    if not _table_exists(table_name):
        return

    if not _column_exists(table_name, "name_key"):
        op.add_column(
            table_name,
            sa.Column("name_key", sa.String(length=80), nullable=False, server_default=""),
        )
    op.execute("UPDATE test_case_reference_categories SET name_key = trim(name)")

    index_name = "uq_test_case_reference_categories_project_name_key"
    if not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, ["project_id", "name_key"], unique=True)


def downgrade() -> None:
    # No-op: 0010 already defines the desired column/index in this branch.
    return
