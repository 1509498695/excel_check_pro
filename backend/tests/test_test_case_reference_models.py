"""用例生成 V1 参考案例库持久化模型测试。"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app.database import async_session_factory
from backend.app.models import (
    Project,
    TestCaseReferenceCategoryRecord as ReferenceCategoryRecord,
    TestCaseReferenceFileRecord as ReferenceFileRecord,
    User,
)


@pytest.mark.anyio
async def test_reference_category_unique_by_project_and_trimmed_name_key(test_db) -> None:
    """分类在同一项目内按 trim 后名称唯一，不把分类当权限边界。"""
    async with async_session_factory() as session:
        project = Project(name="tc-ref-model", description="")
        other_project = Project(name="tc-ref-model-other", description="")
        session.add_all([project, other_project])
        await session.flush()

        session.add(
            ReferenceCategoryRecord(
                project_id=project.id,
                name="  冒烟  ",
            )
        )
        session.add(
            ReferenceCategoryRecord(
                project_id=other_project.id,
                name="冒烟",
            )
        )
        await session.commit()

        session.add(
            ReferenceCategoryRecord(
                project_id=project.id,
                name="冒烟",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.anyio
async def test_reference_file_supports_uncategorized_soft_delete_audit(test_db) -> None:
    """未分类用 nullable category_id 表示；软删除后保留审计元数据并清空可复用数据。"""
    deleted_at = datetime.datetime.now(datetime.UTC)
    async with async_session_factory() as session:
        project = Project(name="tc-ref-file-model", description="")
        user = User(username="tc-ref-file-user", hashed_password="x", is_super_admin=False)
        session.add_all([project, user])
        await session.flush()

        record = ReferenceFileRecord(
            project_id=project.id,
            category_id=None,
            original_filename="history.xlsx",
            stored_filename="stored.xlsx",
            suffix=".xlsx",
            size_bytes=128,
            storage_path="D:/runtime/test-case-references/1/stored.xlsx",
            profile_json='{"source_type":"excel"}',
            is_recommended_primary=True,
            uploaded_by=user.id,
        )
        session.add(record)
        await session.flush()

        record.storage_path = ""
        record.profile_json = ""
        record.is_recommended_primary = False
        record.deleted_by = user.id
        record.deleted_at = deleted_at
        await session.commit()
        await session.refresh(record)

        assert record.category_id is None
        assert record.original_filename == "history.xlsx"
        assert record.uploaded_by == user.id
        assert record.deleted_by == user.id
        assert record.deleted_at is not None
        assert record.storage_path == ""
        assert record.profile_json == ""
        assert record.is_recommended_primary is False


def test_reference_models_do_not_add_generation_history_or_profile_status() -> None:
    """本刀只建参考库表，不新增生成历史表和画像半成品状态字段。"""
    assert "test_case_generation_history" not in ReferenceFileRecord.metadata.tables
    assert "profile_status" not in ReferenceFileRecord.__table__.columns
    assert "profile_error" not in ReferenceFileRecord.__table__.columns
