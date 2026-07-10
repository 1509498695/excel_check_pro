"""runtime cleanup 的 Source Evidence 集成测试。"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.app.database import async_session_factory
from backend.app.models import (
    Project,
    SourceEvidenceRunRecord,
    TestCaseCoverageAuditRecord as GenerationCoverageAuditRecord,
    TestCaseGenerationCaseRecord as GenerationCaseRecord,
    TestCaseGenerationChunkRecord as GenerationChunkRecord,
    TestCaseGenerationRunRecord as GenerationRunRecord,
    TestCaseRequirementAtomRecord as RequirementAtomRecord,
    User,
)
from backend.app.services import runtime_cleanup
from backend.app.test_cases import source_evidence_storage


@pytest.fixture(autouse=True)
def _runtime_cleanup_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimpleNamespace:
    settings = SimpleNamespace(
        runtime_dir=tmp_path / "runtime",
        runtime_upload_dir=tmp_path / "runtime_uploads" / "local_excel",
        svn_cache_dir=tmp_path / "runtime" / "svn-cache",
        source_evidence_dir=tmp_path / "runtime" / "source-evidence",
        upload_retention_days=30,
        svn_cache_retention_days=30,
        execution_result_retention_days=90,
        log_retention_days=14,
    )
    monkeypatch.setattr(runtime_cleanup, "settings", settings)
    monkeypatch.setattr(
        source_evidence_storage,
        "settings",
        SimpleNamespace(source_evidence_dir=settings.source_evidence_dir),
    )
    return settings


async def _seed_runtime_source_evidence_run(
    *,
    project_id: int | None = None,
    expires_at: datetime.datetime,
    status: str = "ready",
) -> tuple[int, int]:
    async with async_session_factory() as session:
        if project_id is None:
            project = Project(name=f"runtime-cleanup-{uuid4().hex[:8]}", description="")
            session.add(project)
            await session.flush()
            project_id = project.id
        user = User(
            username=f"runtime-cleanup-user-{uuid4().hex[:8]}",
            hashed_password="x",
            is_super_admin=False,
            primary_project_id=project_id,
        )
        session.add(user)
        await session.flush()
        run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type="feishu",
            source_url="https://demo.feishu.cn/docx/doccn-runtime",
            source_token="doccn-runtime",
            source_identifier="doccn-runtime",
            source_title="runtime cleanup",
            status=status,
            created_by=user.id,
            expires_at=expires_at,
        )
        session.add(run)
        await session.commit()

    run_dir = source_evidence_storage.ensure_source_evidence_run_dir(
        project_id=project_id,
        run_id=run.id,
    )
    (run_dir / "source.md").write_text("runtime sensitive source", encoding="utf-8")
    return project_id, run.id


async def _seed_runtime_generation_run(
    *,
    project_id: int,
    source_evidence_run_id: int,
    expires_at: datetime.datetime,
) -> int:
    async with async_session_factory() as session:
        run = GenerationRunRecord(
            project_id=project_id,
            source_evidence_run_id=source_evidence_run_id,
            status="queued",
            planning_sheet_name="策划案",
            reference_ids_json="[]",
            total_chunks=1,
            completed_chunks=1,
            atom_count=1,
            case_count=1,
            stage_payload_json=json.dumps(
                {"safe_summary": "runtime cleanup", "raw_response": "must not leak"},
                ensure_ascii=False,
            ),
            expires_at=expires_at,
        )
        session.add(run)
        await session.flush()
        chunk = GenerationChunkRecord(
            run_id=run.id,
            project_id=project_id,
            chunk_index=0,
            status="completed",
        )
        session.add(chunk)
        await session.flush()
        session.add_all(
            [
                RequirementAtomRecord(
                    run_id=run.id,
                    project_id=project_id,
                    chunk_id=chunk.id,
                    atom_id="ATOM-RUNTIME-001",
                    requirement_text="runtime cleanup should not leak detail",
                ),
                GenerationCaseRecord(
                    run_id=run.id,
                    project_id=project_id,
                    case_id="TC-RUNTIME-001",
                    fields_json=json.dumps(
                        {"title": "runtime cleanup detail"},
                        ensure_ascii=False,
                    ),
                    atom_refs_json=json.dumps(["ATOM-RUNTIME-001"], ensure_ascii=False),
                ),
                GenerationCoverageAuditRecord(
                    run_id=run.id,
                    project_id=project_id,
                    status="completed",
                    total_atoms=1,
                    covered_atoms=1,
                ),
            ]
        )
        await session.commit()
        return run.id


async def _generation_run_detail_count(run_id: int) -> int:
    async with async_session_factory() as session:
        total = 0
        for model in (
            GenerationChunkRecord,
            RequirementAtomRecord,
            GenerationCaseRecord,
            GenerationCoverageAuditRecord,
        ):
            result = await session.execute(
                select(func.count(model.id)).where(model.run_id == run_id)
            )
            total += int(result.scalar_one() or 0)
        return total


@pytest.mark.anyio
async def test_runtime_cleanup_dry_run_collects_source_evidence_without_deleting(
    test_db,
) -> None:
    now = datetime.datetime(2026, 7, 8, 9, 0, tzinfo=datetime.UTC)
    project_id, run_id = await _seed_runtime_source_evidence_run(
        expires_at=now - datetime.timedelta(seconds=1)
    )

    async with async_session_factory() as session:
        report = await runtime_cleanup.collect_runtime_cleanup_candidates(session, now=now)

    assert report.dry_run is True
    assert report.source_evidence_runs.run_ids == [run_id]
    assert report.source_evidence_runs.cleaned_count == 0
    assert report.generation_runs.run_ids == []
    report_payload = report.to_dict()
    assert "source.md" not in str(report_payload)
    assert "source-evidence" not in str(report_payload)
    assert source_evidence_storage.resolve_source_evidence_path(
        project_id,
        run_id,
        "source.md",
    ).exists()


@pytest.mark.anyio
async def test_runtime_cleanup_execute_cleans_only_expired_source_evidence(
    test_db,
    _runtime_cleanup_settings: SimpleNamespace,
) -> None:
    now = datetime.datetime(2026, 7, 8, 9, 0, tzinfo=datetime.UTC)
    project_id, expired_run_id = await _seed_runtime_source_evidence_run(
        expires_at=now - datetime.timedelta(seconds=1)
    )
    _project_id, fresh_run_id = await _seed_runtime_source_evidence_run(
        project_id=project_id,
        expires_at=now + datetime.timedelta(days=1)
    )
    reference_file = (
        _runtime_cleanup_settings.runtime_dir
        / "test-case-references"
        / "1"
        / "case.xlsx"
    )
    reference_file.parent.mkdir(parents=True, exist_ok=True)
    reference_file.write_text("reference must stay", encoding="utf-8")
    upload_file = _runtime_cleanup_settings.runtime_upload_dir / "fresh.xlsx"
    upload_file.parent.mkdir(parents=True, exist_ok=True)
    upload_file.write_text("fresh upload", encoding="utf-8")
    global_svn_cache_file = (
        _runtime_cleanup_settings.svn_cache_dir
        / "samosvn"
        / "abc"
        / "QuestReward.xls"
    )
    global_svn_cache_file.parent.mkdir(parents=True, exist_ok=True)
    global_svn_cache_file.write_text("global svn cache", encoding="utf-8")

    async with async_session_factory() as session:
        report = await runtime_cleanup.cleanup_runtime(False, session, now=now)

    assert report.dry_run is False
    assert report.source_evidence_runs.run_ids == [expired_run_id]
    assert report.source_evidence_runs.cleaned_count == 1
    assert report.generation_runs.run_ids == []
    assert not source_evidence_storage.resolve_source_evidence_path(
        project_id,
        expired_run_id,
        "source.md",
    ).exists()
    assert source_evidence_storage.resolve_source_evidence_path(
        project_id,
        fresh_run_id,
        "source.md",
    ).exists()
    assert reference_file.read_text(encoding="utf-8") == "reference must stay"
    assert upload_file.read_text(encoding="utf-8") == "fresh upload"
    assert global_svn_cache_file.read_text(encoding="utf-8") == "global svn cache"

    async with async_session_factory() as session:
        expired_run = await session.get(SourceEvidenceRunRecord, expired_run_id)
        fresh_run = await session.get(SourceEvidenceRunRecord, fresh_run_id)
        assert expired_run is not None and expired_run.status == "cleaned"
        assert fresh_run is not None and fresh_run.status == "ready"


@pytest.mark.anyio
async def test_runtime_cleanup_report_serializes_source_evidence_summary(test_db) -> None:
    now = datetime.datetime(2026, 7, 8, 9, 0, tzinfo=datetime.UTC)
    _project_id, run_id = await _seed_runtime_source_evidence_run(
        expires_at=now - datetime.timedelta(seconds=1)
    )

    async with async_session_factory() as session:
        report = await runtime_cleanup.collect_runtime_cleanup_candidates(session, now=now)

    payload = report.to_dict()
    assert payload["source_evidence_runs"]["run_ids"] == [run_id]
    assert payload["source_evidence_runs"]["resource_count"] == 0
    assert payload["source_evidence_runs"]["observation_count"] == 0
    assert payload["generation_runs"]["run_ids"] == []
    assert payload["generation_runs"]["chunk_count"] == 0


@pytest.mark.anyio
async def test_runtime_cleanup_dry_run_collects_generation_runs_without_detail_leak(
    test_db,
) -> None:
    now = datetime.datetime(2026, 7, 8, 9, 0, tzinfo=datetime.UTC)
    project_id, source_run_id = await _seed_runtime_source_evidence_run(
        expires_at=now + datetime.timedelta(days=1)
    )
    run_id = await _seed_runtime_generation_run(
        project_id=project_id,
        source_evidence_run_id=source_run_id,
        expires_at=now - datetime.timedelta(seconds=1),
    )

    async with async_session_factory() as session:
        report = await runtime_cleanup.collect_runtime_cleanup_candidates(session, now=now)

    assert report.generation_runs.run_ids == [run_id]
    assert report.generation_runs.cleaned_count == 0
    assert report.generation_runs.chunk_count == 1
    assert report.generation_runs.atom_count == 1
    assert report.generation_runs.case_count == 1
    payload_text = json.dumps(report.to_dict(), ensure_ascii=False)
    assert "runtime cleanup detail" not in payload_text
    assert "must not leak" not in payload_text


@pytest.mark.anyio
async def test_runtime_cleanup_execute_cleans_generation_run_details_only(
    test_db,
) -> None:
    now = datetime.datetime(2026, 7, 8, 9, 0, tzinfo=datetime.UTC)
    project_id, source_run_id = await _seed_runtime_source_evidence_run(
        expires_at=now + datetime.timedelta(days=1)
    )
    source_file = source_evidence_storage.resolve_source_evidence_path(
        project_id,
        source_run_id,
        "source.md",
    )
    run_id = await _seed_runtime_generation_run(
        project_id=project_id,
        source_evidence_run_id=source_run_id,
        expires_at=now - datetime.timedelta(seconds=1),
    )

    async with async_session_factory() as session:
        report = await runtime_cleanup.cleanup_runtime(False, session, now=now)

    assert report.generation_runs.run_ids == [run_id]
    assert report.generation_runs.cleaned_count == 1
    assert report.source_evidence_runs.run_ids == []
    assert source_file.read_text(encoding="utf-8") == "runtime sensitive source"
    assert await _generation_run_detail_count(run_id) == 0

    async with async_session_factory() as session:
        run = await session.get(GenerationRunRecord, run_id)
        source_run = await session.get(SourceEvidenceRunRecord, source_run_id)
    assert run is not None
    assert run.status == "expired"
    assert run.cleaned_at is not None
    assert run.stage_payload_json == "{}"
    assert "runtime cleanup detail" not in run.minimal_audit_json
    assert source_run is not None and source_run.status == "ready"
