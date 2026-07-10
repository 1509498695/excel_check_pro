"""Generation Run 服务层 TTL 与清理骨架测试。"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from backend.app.database import async_session_factory
from backend.app.models import (
    SourceEvidenceRunRecord,
    TestCaseCoverageAuditRecord as GenerationCoverageAuditRecord,
    TestCaseGenerationCaseRecord as GenerationCaseRecord,
    TestCaseGenerationChunkRecord as GenerationChunkRecord,
    TestCaseGenerationRunRecord as GenerationRunRecord,
    TestCaseRequirementAtomRecord as RequirementAtomRecord,
)
from backend.app.test_cases import (
    generation_artifact_storage,
    generation_runs,
    source_evidence_cleanup,
    source_evidence_storage,
)
from backend.app.test_cases.generation_runs import (
    GenerationRunError,
    build_generation_run_export_placeholder,
    cancel_generation_run,
    cleanup_expired_generation_runs,
    create_generation_run,
    get_project_generation_run,
    update_generation_run_stage,
)
from backend.app.test_cases.schemas import (
    TestCaseGenerationRunCreateRequest as GenerationRunCreateRequest,
)


@pytest.fixture(autouse=True)
def _source_evidence_storage_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimpleNamespace:
    settings = SimpleNamespace(source_evidence_dir=tmp_path / "source-evidence")
    monkeypatch.setattr(source_evidence_storage, "settings", settings)
    monkeypatch.setattr(
        generation_artifact_storage,
        "settings",
        SimpleNamespace(runtime_dir=tmp_path / "runtime"),
    )
    monkeypatch.setattr(generation_runs, "source_evidence_storage", source_evidence_storage, raising=False)
    return settings


async def _seed_source_evidence_run(
    project_id: int,
    *,
    expires_at: datetime.datetime | None = None,
    status: str = "ready",
    created_by: int | None = None,
) -> int:
    async with async_session_factory() as session:
        run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type="feishu",
            source_url="https://demo.feishu.cn/docx/doccn-generation-run",
            source_token="doccn-generation-run",
            source_identifier=f"doccn-generation-run-{uuid4().hex[:8]}",
            source_title="Generation Run 测试策划案",
            status=status,
            created_by=created_by,
            expires_at=expires_at
            or datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(run)
        await session.commit()
        return run.id


async def _seed_generation_run_with_details(
    project_id: int,
    *,
    source_evidence_run_id: int | None = None,
    status: str = "queued",
    expires_at: datetime.datetime | None = None,
    created_by: int | None = None,
) -> int:
    if source_evidence_run_id is None:
        source_evidence_run_id = await _seed_source_evidence_run(project_id)

    async with async_session_factory() as session:
        run = GenerationRunRecord(
            project_id=project_id,
            source_evidence_run_id=source_evidence_run_id,
            created_by=created_by,
            status=status,
            planning_sheet_name="策划案",
            reference_ids_json="[]",
            strict_mode=True,
            total_chunks=1,
            completed_chunks=1,
            atom_count=1,
            case_count=1,
            warning_count=1,
            stage_payload_json=json.dumps(
                {"stage": "generating_cases", "safe": "summary"},
                ensure_ascii=False,
            ),
            expires_at=expires_at
            or datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(run)
        await session.flush()
        chunk = GenerationChunkRecord(
            run_id=run.id,
            project_id=project_id,
            chunk_index=0,
            source_row_start=1,
            source_row_end=5,
            title_hint="活动入口",
            status="completed",
            structure_hints_json=json.dumps({"sheet": "策划案"}, ensure_ascii=False),
        )
        session.add(chunk)
        await session.flush()
        session.add_all(
            [
                RequirementAtomRecord(
                    run_id=run.id,
                    project_id=project_id,
                    chunk_id=chunk.id,
                    atom_id="ATOM-001",
                    atom_type="requirement",
                    requirement_text="活动入口按配置开放",
                    source_sheet_name="策划案",
                    source_row_start=1,
                    source_row_end=1,
                    source_columns_json=json.dumps(["A", "B"], ensure_ascii=False),
                    confidence=0.9,
                    coverage_status="covered",
                ),
                GenerationCaseRecord(
                    run_id=run.id,
                    project_id=project_id,
                    case_id="TC-001",
                    fields_json=json.dumps({"title": "活动入口正常展示"}, ensure_ascii=False),
                    atom_refs_json=json.dumps(["ATOM-001"], ensure_ascii=False),
                    status="official",
                ),
                GenerationCoverageAuditRecord(
                    run_id=run.id,
                    project_id=project_id,
                    status="completed",
                    total_atoms=1,
                    covered_atoms=1,
                    uncovered_atoms=0,
                    supplement_summary_json=json.dumps({"summary": "已覆盖"}, ensure_ascii=False),
                ),
            ]
        )
        await session.commit()
        return run.id


async def _detail_counts(run_id: int) -> dict[str, int]:
    async with async_session_factory() as session:
        counts: dict[str, int] = {}
        for name, model in (
            ("chunks", GenerationChunkRecord),
            ("atoms", RequirementAtomRecord),
            ("cases", GenerationCaseRecord),
            ("audits", GenerationCoverageAuditRecord),
        ):
            result = await session.execute(
                select(func.count(model.id)).where(model.run_id == run_id)
            )
            counts[name] = int(result.scalar_one() or 0)
        return counts


@pytest.mark.anyio
async def test_create_generation_run_uses_default_ttl_and_empty_stage_payload(
    test_db,
    test_project_id: int,
) -> None:
    """创建 run 使用默认 7 天 TTL，并返回空的 sanitized stage payload。"""
    source_run_id = await _seed_source_evidence_run(test_project_id)
    request = GenerationRunCreateRequest(
        source_evidence_run_id=source_run_id,
        planning_sheet_name="策划案",
        reference_ids=[],
        strict_mode=True,
    )

    async with async_session_factory() as session:
        response = await create_generation_run(
            session,
            project_id=test_project_id,
            created_by=None,
            payload=request,
        )
        await session.commit()

    expires_at = datetime.datetime.fromisoformat(response.expires_at or "")
    ttl_days = expires_at - datetime.datetime.now(datetime.UTC)
    assert response.status == "queued"
    assert response.stage_payload == {}
    assert response.cleaned_at is None
    assert response.completed_at is None
    assert datetime.timedelta(days=6, hours=23) < ttl_days < datetime.timedelta(days=7, minutes=1)


@pytest.mark.anyio
async def test_api_get_expired_generation_run_marks_expired_and_cleans_details(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """API 读取过期 run 时执行懒清理，只返回 run 摘要。"""
    now = datetime.datetime.now(datetime.UTC)
    run_id = await _seed_generation_run_with_details(
        test_project_id,
        expires_at=now - datetime.timedelta(seconds=1),
    )

    response = await auth_client.get(f"/api/v1/test-cases/generation-runs/{run_id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "expired"
    assert data["expired_at"] is not None
    assert data["cleaned_at"] is not None
    assert data["stage_payload"] == {}

    assert await _detail_counts(run_id) == {
        "chunks": 0,
        "atoms": 0,
        "cases": 0,
        "audits": 0,
    }
    async with async_session_factory() as session:
        run = await session.get(GenerationRunRecord, run_id)
        assert run is not None
        audit = json.loads(run.minimal_audit_json)
    assert audit["run_id"] == run_id
    assert audit["project_id"] == test_project_id
    assert audit["status_before_expired"] == "queued"
    assert audit["counts"]["chunk_count"] == 1
    assert audit["counts"]["atom_detail_count"] == 1
    assert audit["counts"]["case_detail_count"] == 1
    assert audit["counts"]["audit_count"] == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("get", "atoms"),
        ("get", "cases"),
        ("post", "export"),
    ],
)
async def test_expired_generation_run_rejects_result_detail_endpoints(
    auth_client: AsyncClient,
    test_project_id: int,
    method: str,
    suffix: str,
) -> None:
    """expired run 不返回 atoms/cases/export 详情。"""
    run_id = await _seed_generation_run_with_details(
        test_project_id,
        expires_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1),
    )

    response = await getattr(auth_client, method)(
        f"/api/v1/test-cases/generation-runs/{run_id}/{suffix}"
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Generation Run 已过期，详情已清理。"


@pytest.mark.anyio
async def test_completed_run_renders_lists_previews_and_retries_artifact_bundle(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """旧 completed run 首次导出补渲染，之后只读取并确定性重试五个文件。"""
    run_id = await _seed_generation_run_with_details(
        test_project_id,
        status="completed",
    )

    export_response = await auth_client.post(
        f"/api/v1/test-cases/generation-runs/{run_id}/export"
    )
    assert export_response.status_code == 200
    assert export_response.content[:2] == b"PK"

    listing_response = await auth_client.get(
        f"/api/v1/test-cases/generation-runs/{run_id}/artifacts"
    )
    assert listing_response.status_code == 200
    items = listing_response.json()["data"]["items"]
    assert [item["key"] for item in items] == [
        "workbook",
        "blueprint",
        "stats",
        "coverage_audit",
        "quality_audit",
    ]
    assert all(item["status"] == "ready" for item in items)
    assert all(item["size_bytes"] > 0 for item in items)
    assert all(len(item["sha256"]) == 64 for item in items)

    preview_response = await auth_client.get(
        f"/api/v1/test-cases/generation-runs/{run_id}/artifacts/blueprint?inline=true"
    )
    assert preview_response.status_code == 200
    assert "策划案：用例蓝图" in preview_response.text

    retry_response = await auth_client.post(
        f"/api/v1/test-cases/generation-runs/{run_id}/artifacts/retry"
    )
    assert retry_response.status_code == 200
    assert retry_response.json()["data"]["total"] == 5

    second_listing = await auth_client.get(
        f"/api/v1/test-cases/generation-runs/{run_id}/artifacts"
    )
    assert [item["sha256"] for item in second_listing.json()["data"]["items"]] == [
        item["sha256"] for item in retry_response.json()["data"]["items"]
    ]


@pytest.mark.anyio
async def test_cleanup_expired_generation_runs_deletes_details_and_keeps_minimal_audit(
    test_db,
    test_project_id: int,
) -> None:
    """批量清理删除 detail rows 和 stage payload，但保留主表最小审计。"""
    run_id = await _seed_generation_run_with_details(
        test_project_id,
        expires_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1),
    )

    async with async_session_factory() as session:
        summary = await cleanup_expired_generation_runs(session)
        await session.commit()

    assert summary.run_ids == [run_id]
    assert summary.cleaned_count == 1
    assert summary.chunk_count == 1
    assert summary.atom_count == 1
    assert summary.case_count == 1
    assert summary.audit_count == 1
    assert await _detail_counts(run_id) == {
        "chunks": 0,
        "atoms": 0,
        "cases": 0,
        "audits": 0,
    }

    async with async_session_factory() as session:
        run = await session.get(GenerationRunRecord, run_id)
        assert run is not None
        assert run.status == "expired"
        assert run.stage_payload_json == "{}"
        assert run.cleaned_at is not None
        audit = json.loads(run.minimal_audit_json)
    assert audit["source_evidence_run_id"] == run.source_evidence_run_id
    assert audit["planning_sheet_name"] == "策划案"
    assert audit["status"] == "expired"
    assert audit["created_at"] is not None


@pytest.mark.anyio
async def test_cancelled_run_keeps_details_until_ttl_but_cannot_complete_or_export(
    test_db,
    test_project_id: int,
) -> None:
    """cancelled run 在 TTL 前保留 detail，但不能继续推进或导出。"""
    run_id = await _seed_generation_run_with_details(test_project_id, status="reading")

    async with async_session_factory() as session:
        cancelled = await cancel_generation_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
            cancelled_by=None,
        )
        await session.commit()

    assert cancelled.status == "cancelled"
    assert await _detail_counts(run_id) == {
        "chunks": 1,
        "atoms": 1,
        "cases": 1,
        "audits": 1,
    }

    async with async_session_factory() as session:
        with pytest.raises(GenerationRunError) as update_error:
            await update_generation_run_stage(
                session,
                project_id=test_project_id,
                run_id=run_id,
                status="completed",
            )
        with pytest.raises(GenerationRunError) as export_error:
            await build_generation_run_export_placeholder(
                session,
                project_id=test_project_id,
                run_id=run_id,
            )

    assert update_error.value.status_code == 409
    assert export_error.value.status_code == 409
    assert export_error.value.message == "当前 Generation Run 状态不可导出。"


@pytest.mark.anyio
async def test_failed_run_keeps_sanitized_error_summary_without_raw_response(
    test_db,
    test_project_id: int,
) -> None:
    """failed run 只保留脱敏错误摘要，不保存 prompt/raw/provider response。"""
    run_id = await _seed_generation_run_with_details(test_project_id, status="generating_cases")

    async with async_session_factory() as session:
        response = await update_generation_run_stage(
            session,
            project_id=test_project_id,
            run_id=run_id,
            status="failed",
            error_summary=(
                "生成失败 provider_response raw_response prompt "
                "tenant_access_token=secret-value D:/secret/source.xlsx "
                "https://secret.example.com/token"
            ),
            stage_payload={
                "safe_summary": "生成失败",
                "raw_response": "secret raw response body",
                "provider_response": {"token": "secret-token"},
                "prompt": "raw prompt body",
            },
        )
        await session.commit()

    assert response.status == "failed"
    async with async_session_factory() as session:
        run = await session.get(GenerationRunRecord, run_id)
        assert run is not None
        persisted_text = f"{run.error_summary}\n{run.stage_payload_json}"

    assert "生成失败" in persisted_text
    for forbidden in (
        "secret-value",
        "secret-token",
        "secret.example.com",
        "D:/secret",
        "provider_response",
        "raw_response",
        "raw prompt",
        "prompt",
    ):
        assert forbidden not in persisted_text


@pytest.mark.anyio
async def test_cleanup_does_not_touch_source_evidence_files_or_cleanup_audit(
    test_db,
    test_project_id: int,
) -> None:
    """Generation Run 清理只处理自身 DB detail，不删除 Source Evidence 文件或 audit。"""
    audit_source_run_id = await _seed_source_evidence_run(test_project_id)
    source_run_id = await _seed_source_evidence_run(test_project_id)
    source_file_dir = source_evidence_storage.ensure_source_evidence_run_dir(
        project_id=test_project_id,
        run_id=source_run_id,
    )
    source_file = source_file_dir / "source.md"
    source_file.write_text("source evidence must stay", encoding="utf-8")
    run_id = await _seed_generation_run_with_details(
        test_project_id,
        source_evidence_run_id=source_run_id,
        expires_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1),
    )

    async with async_session_factory() as session:
        await source_evidence_cleanup.cleanup_source_evidence_run(
            session,
            project_id=test_project_id,
            run_id=audit_source_run_id,
            cleaned_by=None,
        )
        _items_before, total_before = await source_evidence_cleanup.list_source_evidence_cleanup_audits(
            session,
            project_id=test_project_id,
        )
        summary = await cleanup_expired_generation_runs(session)
        _items_after, total_after = await source_evidence_cleanup.list_source_evidence_cleanup_audits(
            session,
            project_id=test_project_id,
        )
        await session.commit()

    assert summary.run_ids == [run_id]
    assert total_after == total_before == 1
    assert source_file.read_text(encoding="utf-8") == "source evidence must stay"
    async with async_session_factory() as session:
        source_run = await session.get(SourceEvidenceRunRecord, source_run_id)
        generation_run = await get_project_generation_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
    assert source_run is not None and source_run.status == "ready"
    assert generation_run.status == "expired"
