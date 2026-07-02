"""Source Evidence Run 基础模型和审计 helper 契约测试。"""

from __future__ import annotations

import datetime
import json

import pytest

from backend.app.database import async_session_factory
from backend.app.models import (
    Project,
    SourceEvidenceResourceRecord,
    SourceEvidenceRunRecord,
    User,
)
from backend.app.test_cases.source_evidence import (
    SOURCE_EVIDENCE_RESOURCE_STATUSES,
    SOURCE_EVIDENCE_RUN_STATUSES,
    create_source_evidence_run,
    is_source_evidence_expired,
    list_project_source_evidence_resources,
    list_project_source_evidence_runs,
    scrub_source_evidence_sensitive_fields,
)


@pytest.mark.anyio
async def test_create_run_sets_project_actor_status_and_default_ttl(test_db) -> None:
    """创建 run 时写入项目、操作人、reading 状态，并以 created_at + 7 天过期。"""
    created_at = datetime.datetime(2026, 6, 29, 8, 0, tzinfo=datetime.UTC)
    async with async_session_factory() as session:
        project = Project(name="source-evidence-create", description="")
        user = User(
            username="source-evidence-creator",
            hashed_password="x",
            is_super_admin=False,
        )
        session.add_all([project, user])
        await session.flush()

        run = await create_source_evidence_run(
            session,
            project_id=project.id,
            created_by=user.id,
            source_type="feishu_doc",
            source_identifier="doccn-create",
            source_title="创建契约",
            now=created_at,
        )
        await session.commit()

        assert run.project_id == project.id
        assert run.created_by == user.id
        assert run.status == "reading"
        assert run.expires_at == created_at + datetime.timedelta(days=7)
        assert run.storage_path.endswith(f"/{project.id}/{run.id}") or run.storage_path.endswith(
            f"\\{project.id}\\{run.id}"
        )


@pytest.mark.anyio
async def test_run_and_resource_queries_are_project_isolated(test_db) -> None:
    """run/resource 查询必须按 project_id 过滤，不能跨项目串数据。"""
    async with async_session_factory() as session:
        project_a = Project(name="source-evidence-project-a", description="")
        project_b = Project(name="source-evidence-project-b", description="")
        user = User(
            username="source-evidence-isolation",
            hashed_password="x",
            is_super_admin=False,
        )
        session.add_all([project_a, project_b, user])
        await session.flush()

        run_a = await create_source_evidence_run(
            session,
            project_id=project_a.id,
            created_by=user.id,
            source_type="feishu_doc",
            source_identifier="doccn-a",
        )
        run_b = await create_source_evidence_run(
            session,
            project_id=project_b.id,
            created_by=user.id,
            source_type="feishu_doc",
            source_identifier="doccn-b",
        )
        resource_a = SourceEvidenceResourceRecord(
            run_id=run_a.id,
            project_id=project_a.id,
            ref="image-a",
            filename="a.png",
            status="downloaded",
        )
        resource_b = SourceEvidenceResourceRecord(
            run_id=run_b.id,
            project_id=project_b.id,
            ref="image-b",
            filename="b.png",
            status="downloaded",
        )
        session.add_all([resource_a, resource_b])
        await session.commit()

        runs = await list_project_source_evidence_runs(session, project_id=project_a.id)
        resources = await list_project_source_evidence_resources(
            session,
            project_id=project_a.id,
        )

        assert [record.id for record in runs] == [run_a.id]
        assert [record.id for record in resources] == [resource_a.id]


def test_status_enums_cover_required_states() -> None:
    """状态枚举先固定后台状态机边界，后续 API/清理任务只能在此基础上扩展。"""
    assert {
        "reading",
        "ready",
        "pending_permission",
        "vision_pending",
        "failed",
        "expired",
        "cleaned",
    }.issubset(SOURCE_EVIDENCE_RUN_STATUSES)
    assert {
        "pending",
        "downloaded",
        "download_failed",
        "pending_permission",
        "unobserved",
        "observed",
        "adopted",
        "rejected",
        "expired",
    }.issubset(SOURCE_EVIDENCE_RESOURCE_STATUSES)


def test_ttl_expiration_uses_expires_at_only() -> None:
    """TTL 判断以 expires_at 为准，不依赖创建时间或状态名推断。"""
    expires_at = datetime.datetime(2026, 7, 6, 8, 0, tzinfo=datetime.UTC)
    assert not is_source_evidence_expired(
        expires_at,
        now=datetime.datetime(2026, 7, 6, 7, 59, 59, tzinfo=datetime.UTC),
    )
    assert is_source_evidence_expired(
        expires_at,
        now=datetime.datetime(2026, 7, 6, 8, 0, tzinfo=datetime.UTC),
    )


@pytest.mark.anyio
async def test_cleanup_helper_keeps_minimal_audit_and_scrubs_sensitive_fields(
    test_db,
) -> None:
    """清理 helper 只留下最小审计元数据，不保留原文、路径、观察详情或 prompt。"""
    cleaned_at = datetime.datetime(2026, 7, 7, 9, 30, tzinfo=datetime.UTC)
    async with async_session_factory() as session:
        project = Project(name="source-evidence-cleanup", description="")
        user = User(
            username="source-evidence-cleaner",
            hashed_password="x",
            is_super_admin=False,
        )
        session.add_all([project, user])
        await session.flush()

        run = SourceEvidenceRunRecord(
            project_id=project.id,
            source_type="feishu_doc",
            source_url="https://example.feishu.cn/docx/sensitive",
            source_token="docx-secret-token",
            source_identifier="docx-safe-identifier",
            source_title="需求文档",
            status="ready",
            storage_path="D:/runtime/source-evidence/1/2/raw.md",
            raw_manifest_json=json.dumps(
                {
                    "source_text": "不能保留的需求原文",
                    "prompt": "不能保留的 prompt",
                    "provider_response": "不能保留的模型响应",
                },
                ensure_ascii=False,
            ),
            created_by=user.id,
        )
        session.add(run)
        await session.flush()
        resource = SourceEvidenceResourceRecord(
            run_id=run.id,
            project_id=project.id,
            ref="image-1",
            filename="ui.png",
            file_token="file-secret-token",
            status="observed",
            local_path="D:/runtime/source-evidence/1/2/ui.png",
            observation_json=json.dumps(
                {"detail": "不能保留的观察详情", "prompt": "vision prompt"},
                ensure_ascii=False,
            ),
            visual_packet_path="D:/runtime/source-evidence/1/2/visual.json",
        )
        session.add(resource)
        await session.flush()

        summary = scrub_source_evidence_sensitive_fields(
            run,
            [resource],
            cleaned_by=user.id,
            cleaned_at=cleaned_at,
        )

        assert run.status == "cleaned"
        assert run.cleaned_by == user.id
        assert run.cleaned_at == cleaned_at
        assert run.source_url == ""
        assert run.source_token == ""
        assert run.storage_path == ""
        assert run.raw_manifest_json == "{}"
        assert resource.file_token == ""
        assert resource.local_path == ""
        assert resource.observation_json == ""
        assert resource.visual_packet_path == ""

        audit_json = json.dumps(summary, ensure_ascii=False)
        assert json.loads(run.minimal_audit_json) == summary
        assert summary["source_identifier"].startswith("sha256:")
        assert summary["source_identifier"] in audit_json
        assert "ui.png" in audit_json
        for forbidden in (
            "不能保留的需求原文",
            "不能保留的 prompt",
            "不能保留的模型响应",
            "不能保留的观察详情",
            "vision prompt",
            "D:/runtime/source-evidence",
            "docx-safe-identifier",
            "docx-secret-token",
            "file-secret-token",
        ):
            assert forbidden not in audit_json


def test_source_evidence_models_do_not_add_generation_history_or_payload_columns() -> None:
    """Source Evidence 不是生成历史表，模型层不保存蓝图、用例、prompt 或 provider response。"""
    assert "test_case_generation_history" not in SourceEvidenceRunRecord.metadata.tables
    assert "test_case_generation_history" not in SourceEvidenceResourceRecord.metadata.tables

    run_columns = set(SourceEvidenceRunRecord.__table__.columns.keys())
    resource_columns = set(SourceEvidenceResourceRecord.__table__.columns.keys())
    forbidden_columns = {
        "blueprint_json",
        "cases_json",
        "prompt",
        "prompt_json",
        "provider_response",
        "provider_response_json",
    }
    assert forbidden_columns.isdisjoint(run_columns)
    assert forbidden_columns.isdisjoint(resource_columns)
