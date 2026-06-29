"""Add test case reference library tables.

Revision ID: 0010_test_case_reference_library
Revises: 0009_rule_config_per_query_type
Create Date: 2026-06-25 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0010_test_case_reference_library"
down_revision: str | None = "0009_rule_config_per_query_type"
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


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(column["name"] == column_name for column in _inspector().get_columns(table_name))


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
    if not _table_exists("test_case_reference_categories"):
        op.create_table(
            "test_case_reference_categories",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("name_key", sa.String(length=80), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
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
            sa.PrimaryKeyConstraint("id"),
        )
    elif not _column_exists("test_case_reference_categories", "name_key"):
        op.add_column(
            "test_case_reference_categories",
            sa.Column("name_key", sa.String(length=80), nullable=False, server_default=""),
        )
        op.execute("UPDATE test_case_reference_categories SET name_key = trim(name)")
    _create_index_if_missing(
        "ix_test_case_reference_categories_project_id",
        "test_case_reference_categories",
        ["project_id"],
    )
    _create_index_if_missing(
        "uq_test_case_reference_categories_project_name_key",
        "test_case_reference_categories",
        ["project_id", "name_key"],
        unique=True,
    )

    if not _table_exists("test_case_reference_files"):
        op.create_table(
            "test_case_reference_files",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("stored_filename", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("suffix", sa.String(length=16), nullable=False, server_default=""),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("storage_path", sa.Text(), nullable=False, server_default=""),
            sa.Column("profile_json", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "is_recommended_primary",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("uploaded_by", sa.Integer(), nullable=True),
            sa.Column("deleted_by", sa.Integer(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.ForeignKeyConstraint(
                ["category_id"],
                ["test_case_reference_categories.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["deleted_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "ix_test_case_reference_files_project_id",
        "test_case_reference_files",
        ["project_id"],
    )
    _create_index_if_missing(
        "ix_test_case_reference_files_category_id",
        "test_case_reference_files",
        ["category_id"],
    )
    _create_index_if_missing(
        "ix_test_case_reference_files_project_category",
        "test_case_reference_files",
        ["project_id", "category_id"],
    )
    _create_index_if_missing(
        "ix_test_case_reference_files_project_filename",
        "test_case_reference_files",
        ["project_id", "original_filename"],
    )
    _create_index_if_missing(
        "ix_test_case_reference_files_project_recommended",
        "test_case_reference_files",
        ["project_id", "category_id", "is_recommended_primary"],
    )


def downgrade() -> None:
    _drop_table_if_exists("test_case_reference_files")
    _drop_table_if_exists("test_case_reference_categories")
