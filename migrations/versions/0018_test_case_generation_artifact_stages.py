"""Add quality audit and automatic artifact rendering stages.

Revision ID: 0018_test_case_generation_artifact_stages
Revises: 0017_test_case_generation_run_cleanup
Create Date: 2026-07-10 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0018_test_case_generation_artifact_stages"
down_revision: str | None = "0017_test_case_generation_run_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_OLD_STATUS_CHECK = (
    "status IN ("
    "'queued', 'reading', 'chunking', 'extracting_atoms', "
    "'merging_atoms', 'blueprinting', 'generating_cases', "
    "'auditing_coverage', 'supplementing', 'completed', "
    "'partial_completed', 'failed', 'cancelled', 'expired'"
    ")"
)
_NEW_STATUS_CHECK = (
    "status IN ("
    "'queued', 'reading', 'chunking', 'extracting_atoms', "
    "'merging_atoms', 'blueprinting', 'generating_cases', "
    "'auditing_coverage', 'supplementing', 'auditing_quality', "
    "'repairing_cases', 'rendering_artifacts', 'completed', "
    "'partial_completed', 'failed', 'cancelled', 'expired'"
    ")"
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("test_case_generation_runs"):
        return
    # 部分历史迁移测试只构造目标表，不构造其外键父表。SQLite batch
    # 重建会反射全部外键并因此失败；这类不完整 schema 不承载 Generation Run，
    # 只需让迁移链继续推进。真实应用库具备以下父表，仍会更新约束。
    required_parent_tables = {
        "projects",
        "source_evidence_runs",
        "users",
        "test_case_reference_files",
    }
    if op.get_bind().dialect.name == "sqlite" and any(
        not inspector.has_table(table_name) for table_name in required_parent_tables
    ):
        return
    with op.batch_alter_table(
        "test_case_generation_runs",
        recreate="always",
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_test_case_generation_runs_status",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_test_case_generation_runs_status",
            _NEW_STATUS_CHECK,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("test_case_generation_runs"):
        return
    required_parent_tables = {
        "projects",
        "source_evidence_runs",
        "users",
        "test_case_reference_files",
    }
    if op.get_bind().dialect.name == "sqlite" and any(
        not inspector.has_table(table_name) for table_name in required_parent_tables
    ):
        return
    with op.batch_alter_table(
        "test_case_generation_runs",
        recreate="always",
    ) as batch_op:
        batch_op.drop_constraint(
            "ck_test_case_generation_runs_status",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_test_case_generation_runs_status",
            _OLD_STATUS_CHECK,
        )
