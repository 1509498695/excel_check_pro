"""V3 Generation Run orchestrator integration tests."""

from __future__ import annotations

import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import func, select

from backend.app.database import async_session_factory
from backend.app.models import (
    ProjectAiCredentialRecord,
    SourceEvidenceRunRecord,
    TestCaseCoverageAuditRecord as CoverageAuditRecord,
    TestCaseGenerationCaseRecord as GenerationCaseRecord,
    TestCaseGenerationChunkRecord as GenerationChunkRecord,
    TestCaseGenerationRunRecord as GenerationRunRecord,
    TestCaseRequirementAtomRecord as RequirementAtomRecord,
)
from backend.app.security.crypto import encrypt_secret
from backend.app.test_cases import source_evidence_storage
from backend.app.test_cases.generation_runs import (
    create_generation_run,
    retry_failed_generation_chunks,
)
from backend.app.test_cases.schemas import (
    TestCaseGenerationRunCreateRequest as GenerationRunCreateRequest,
)


@pytest.fixture(autouse=True)
def _source_evidence_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        source_evidence_storage,
        "settings",
        SimpleNamespace(source_evidence_dir=tmp_path / "source-evidence"),
    )


async def _seed_project_ai(project_id: int, *, api_key: str = "sk-orchestrator-secret") -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectAiCredentialRecord(
                project_id=project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret(api_key),
                extra_headers_json='{"X-Test":"orchestrator"}',
                enabled=True,
            )
        )
        await session.commit()


async def _seed_source_evidence_run(
    project_id: int,
    *,
    expires_at: datetime.datetime | None = None,
    status: str = "ready",
) -> int:
    async with async_session_factory() as session:
        run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type="local_file",
            source_url="https://demo.invalid/orchestrator.xlsx",
            source_token="source-token-must-not-leak",
            source_identifier="orchestrator-source",
            source_title="orchestrator.xlsx",
            status=status,
            expires_at=expires_at
            or datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(run)
        await session.flush()
        source_evidence_storage.ensure_source_evidence_subdirs(
            project_id=project_id,
            run_id=run.id,
        )
        source_evidence_storage.write_source_evidence_json(
            project_id,
            run.id,
            "raw/parsed_source.json",
            {
                "source_type": "local_file",
                "title": "orchestrator.xlsx",
                "doc_type": "xlsx",
                "token": "source-token-must-not-leak",
                "url": "",
                "markdown": "# Source: orchestrator.xlsx",
                "source_units": [
                    {
                        "unit_id": "sheet-a",
                        "kind": "sheet",
                        "title": "需求A",
                        "cells": [
                            {"coord": "A1", "row": 1, "col": 1, "text": "模块"},
                            {"coord": "B1", "row": 1, "col": 2, "text": "规则"},
                            {"coord": "A2", "row": 2, "col": 1, "text": "活动入口"},
                            {"coord": "B2", "row": 2, "col": 2, "text": "按配置开放入口"},
                            {"coord": "A5", "row": 5, "col": 1, "text": "奖励"},
                            {"coord": "B5", "row": 5, "col": 2, "text": "每日领取一次"},
                        ],
                    }
                ],
                "resources": [],
                "raw_manifest": {"provider_response": "provider raw must not leak"},
                "warnings": [],
            },
        )
        await session.commit()
        return run.id


async def _create_run(project_id: int, source_run_id: int, *, strict_mode: bool = False) -> int:
    async with async_session_factory() as session:
        response = await create_generation_run(
            session,
            project_id=project_id,
            created_by=None,
            payload=GenerationRunCreateRequest(
                source_evidence_run_id=source_run_id,
                planning_sheet_name="需求A",
                reference_ids=[],
                strict_mode=strict_mode,
            ),
        )
        await session.commit()
        return response.id


async def _load_run(run_id: int) -> GenerationRunRecord:
    async with async_session_factory() as session:
        run = await session.get(GenerationRunRecord, run_id)
        assert run is not None
        return run


async def _count_rows(run_id: int, model: type[Any]) -> int:
    async with async_session_factory() as session:
        result = await session.execute(select(func.count(model.id)).where(model.run_id == run_id))
        return int(result.scalar_one() or 0)


async def _load_audit(run_id: int) -> CoverageAuditRecord:
    async with async_session_factory() as session:
        audit = (
            await session.execute(
                select(CoverageAuditRecord).where(
                    CoverageAuditRecord.run_id == run_id
                )
            )
        ).scalar_one()
        return audit


def _patch_successful_providers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    atom_fail_on_reward_once: bool = False,
    calls: dict[str, list[str]] | None = None,
) -> None:
    calls = calls if calls is not None else {}
    calls.setdefault("atoms", [])
    calls.setdefault("blueprints", [])
    calls.setdefault("cases", [])
    reward_failures_left = 1 if atom_fail_on_reward_once else 0

    async def fake_atom_provider(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal reward_failures_left
        prompt = kwargs["user_prompt"]
        calls["atoms"].append(prompt)
        assert kwargs["api_key"] == "sk-orchestrator-secret"
        if "每日领取一次" in prompt:
            if reward_failures_left:
                reward_failures_left -= 1
                from backend.app.ai.providers import ProviderConnectionError

                raise ProviderConnectionError(
                    "invalid_json",
                    "raw_response prompt sk-orchestrator-secret D:/secret/provider.txt",
                    502,
                )
            return {
                "atoms": [
                    {
                        "atom_type": "reward",
                        "text": "奖励每日领取一次",
                        "source_sheet": "需求A",
                        "source_rows": [5, 5],
                        "source_columns": ["模块", "规则"],
                        "source_excerpt": "奖励 | 每日领取一次",
                        "confidence": 0.9,
                        "merge_key": "reward:daily",
                    }
                ]
            }, {"latency_ms": 2}
        return {
            "atoms": [
                {
                    "atom_type": "entry",
                    "text": "活动入口按配置开放",
                    "source_sheet": "需求A",
                    "source_rows": [2, 2],
                    "source_columns": ["模块", "规则"],
                    "source_excerpt": "活动入口 | 按配置开放入口",
                    "confidence": 0.91,
                    "merge_key": "entry:open",
                }
            ]
        }, {"latency_ms": 1}

    async def fake_blueprint_provider(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompt = kwargs["user_prompt"]
        calls["blueprints"].append(prompt)
        modules: list[dict[str, Any]] = []
        traces: list[dict[str, Any]] = []
        if "ATOM-0001" in prompt:
            modules.append({"name": "活动入口", "atom_ids": ["ATOM-0001"]})
            traces.append({"atom_id": "ATOM-0001", "blueprint_node": "活动入口"})
        if "ATOM-0002" in prompt:
            modules.append({"name": "奖励领取", "atom_ids": ["ATOM-0002"]})
            traces.append({"atom_id": "ATOM-0002", "blueprint_node": "奖励领取"})
        return {
            "modules": modules,
            "flows": [],
            "requirement_traces": traces,
            "coverage_dimensions": modules,
            "risks": [],
            "unmapped_requirements": [],
            "unsupported_or_unfounded_test_points": [],
            "open_questions": [],
            "warnings": [],
        }, {"latency_ms": 3, "raw_response": "raw prompt sk-orchestrator-secret D:/secret.txt"}

    async def fake_case_provider(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompt = kwargs["user_prompt"]
        calls["cases"].append(prompt)
        if "ATOM-0002" in prompt:
            return {
                "cases": [
                    {
                        "case_id": "TC-REWARD",
                        "module": "奖励领取",
                        "title": "奖励每日仅可领取一次",
                        "steps": "领取后再次点击领取",
                        "expected_results": "重复领取被拦截",
                        "source_requirement": "奖励每日领取一次",
                        "atom_ids": ["ATOM-0002"],
                    }
                ],
                "warnings": [],
            }, {}
        return {
            "cases": [
                {
                    "case_id": "TC-ENTRY",
                    "module": "活动入口",
                    "title": "活动入口按配置展示",
                    "steps": "进入主界面查看活动入口",
                    "expected_results": "入口展示",
                    "source_requirement": "活动入口按配置开放",
                    "atom_ids": ["ATOM-0001"],
                }
            ],
            "warnings": [],
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.requirement_atoms.call_provider_json",
        fake_atom_provider,
    )
    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_blueprint.call_provider_json",
        fake_blueprint_provider,
    )
    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_cases.call_provider_json",
        fake_case_provider,
    )


@pytest.mark.anyio
async def test_orchestrator_happy_path_completes_generation_run(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.test_cases.full_generation_orchestrator import (
        run_generation_run_orchestrator,
    )

    await _seed_project_ai(test_project_id)
    source_run_id = await _seed_source_evidence_run(test_project_id)
    run_id = await _create_run(test_project_id, source_run_id)
    _patch_successful_providers(monkeypatch)

    async with async_session_factory() as session:
        await run_generation_run_orchestrator(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    run = await _load_run(run_id)
    audit = await _load_audit(run_id)
    assert run.status == "completed"
    assert run.total_chunks == 2
    assert run.completed_chunks == 2
    assert run.failed_chunks == 0
    assert run.atom_count == 2
    assert run.case_count == 2
    assert audit.status == "completed"
    assert audit.covered_atoms == 2
    assert await _count_rows(run_id, GenerationChunkRecord) == 2
    assert await _count_rows(run_id, RequirementAtomRecord) == 2
    assert await _count_rows(run_id, GenerationCaseRecord) == 2


@pytest.mark.anyio
async def test_generation_run_api_returns_queued_and_schedules_background_task(
    auth_client,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_run_id = await _seed_source_evidence_run(test_project_id)
    scheduled: list[dict[str, Any]] = []

    async def fake_background_task(**kwargs: Any) -> None:
        scheduled.append(kwargs)

    monkeypatch.setattr(
        "backend.app.api.test_cases_api.run_generation_run_background_task",
        fake_background_task,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generation-runs",
        json={
            "source_evidence_run_id": source_run_id,
            "planning_sheet_name": "需求A",
            "reference_ids": [],
            "strict_mode": False,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "queued"
    assert scheduled == [
        {
            "project_id": test_project_id,
            "run_id": data["id"],
            "retry_failed_chunks_only": False,
        }
    ]


@pytest.mark.anyio
async def test_orchestrator_marks_run_failed_when_project_ai_missing(
    test_db,
    test_project_id: int,
) -> None:
    from backend.app.test_cases.full_generation_orchestrator import (
        run_generation_run_orchestrator,
    )

    source_run_id = await _seed_source_evidence_run(test_project_id)
    run_id = await _create_run(test_project_id, source_run_id)

    async with async_session_factory() as session:
        await run_generation_run_orchestrator(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    run = await _load_run(run_id)
    assert run.status == "failed"
    assert "项目级 AI 凭据" in run.error_summary
    assert "raw_response" not in run.stage_payload_json


@pytest.mark.anyio
async def test_orchestrator_respects_cancel_during_extracting_and_skips_cases(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.test_cases.full_generation_orchestrator import (
        run_generation_run_orchestrator,
    )
    from backend.app.test_cases.generation_runs import cancel_generation_run

    await _seed_project_ai(test_project_id)
    source_run_id = await _seed_source_evidence_run(test_project_id)
    run_id = await _create_run(test_project_id, source_run_id)

    async def fake_extract(db, *, project_id: int, run_id: int, context: Any, **_: Any) -> list[Any]:
        await cancel_generation_run(
            db,
            project_id=project_id,
            run_id=run_id,
            cancelled_by=None,
        )
        return []

    async def forbidden_cases(**_: Any) -> list[Any]:
        raise AssertionError("case generation must not run after cancellation")

    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_orchestrator.extract_and_merge_requirement_atoms_for_run",
        fake_extract,
    )
    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_orchestrator.generate_test_cases_for_run",
        forbidden_cases,
    )

    async with async_session_factory() as session:
        await run_generation_run_orchestrator(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    run = await _load_run(run_id)
    assert run.status == "cancelled"
    assert await _count_rows(run_id, GenerationCaseRecord) == 0


@pytest.mark.anyio
async def test_retry_failed_chunks_reopens_partial_run_and_completes(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.test_cases.full_generation_orchestrator import (
        run_generation_run_orchestrator,
    )

    await _seed_project_ai(test_project_id)
    source_run_id = await _seed_source_evidence_run(test_project_id)
    run_id = await _create_run(test_project_id, source_run_id)
    calls: dict[str, list[str]] = {}
    _patch_successful_providers(monkeypatch, atom_fail_on_reward_once=True, calls=calls)

    async with async_session_factory() as session:
        await run_generation_run_orchestrator(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    first_run = await _load_run(run_id)
    assert first_run.status == "partial_completed"
    assert first_run.failed_chunks == 1
    assert first_run.atom_count == 1

    async with async_session_factory() as session:
        response = await retry_failed_generation_chunks(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await run_generation_run_orchestrator(
            session,
            project_id=test_project_id,
            run_id=run_id,
            retry_failed_chunks_only=True,
        )
        await session.commit()

    retried_run = await _load_run(run_id)
    assert response.retried_chunk_count == 1
    assert retried_run.status == "completed"
    assert retried_run.failed_chunks == 0
    assert retried_run.atom_count == 2
    assert retried_run.case_count == 2
    retry_prompts = calls["atoms"][2:]
    assert len(retry_prompts) == 1
    assert "每日领取一次" in retry_prompts[0]
    assert "按配置开放入口" not in retry_prompts[0]


@pytest.mark.anyio
async def test_create_generation_run_rejects_expired_source_evidence(
    auth_client,
    test_project_id: int,
) -> None:
    source_run_id = await _seed_source_evidence_run(
        test_project_id,
        expires_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1),
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generation-runs",
        json={
            "source_evidence_run_id": source_run_id,
            "planning_sheet_name": "需求A",
            "reference_ids": [],
        },
    )

    assert response.status_code == 409
    assert "证据已过期" in response.json()["detail"]
