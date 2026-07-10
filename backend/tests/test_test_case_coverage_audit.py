"""Coverage Audit and one-pass supplement service tests."""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest
from sqlalchemy import select

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
from backend.app.test_cases.coverage_audit import run_coverage_audit_for_run
from backend.app.test_cases.generation_runs import (
    GenerationRunError,
    build_generation_run_export_placeholder,
)


async def _seed_project_ai(project_id: int, *, api_key: str = "sk-audit-secret") -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectAiCredentialRecord(
                project_id=project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret(api_key),
                extra_headers_json='{"X-Test":"coverage"}',
                enabled=True,
            )
        )
        await session.commit()


def _blueprint(atom_ids: list[str]) -> dict[str, Any]:
    return {
        "modules": [
            {"name": f"模块{index}", "atom_ids": [atom_id]}
            for index, atom_id in enumerate(atom_ids, start=1)
        ],
        "flows": [],
        "requirement_traces": [],
        "coverage_dimensions": [],
        "risks": [],
        "unmapped_requirements": [],
        "unsupported_or_unfounded_test_points": [],
        "open_questions": [],
        "warnings": [],
    }


async def _seed_run(
    project_id: int,
    *,
    strict_mode: bool = False,
    atoms: list[dict[str, Any]] | None = None,
    cases: list[dict[str, Any]] | None = None,
    chunk_statuses: list[str] | None = None,
    audit_unfounded_candidates: list[dict[str, Any]] | None = None,
) -> int:
    atoms = atoms or [
        {"atom_id": "ATOM-0001", "requirement_text": "活动入口按配置开放"},
        {"atom_id": "ATOM-0002", "requirement_text": "奖励每日领取一次"},
    ]
    cases = cases or []
    chunk_statuses = chunk_statuses or ["completed"]
    async with async_session_factory() as session:
        source_run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type="local_file",
            source_url="https://demo.invalid/audit.xlsx",
            source_token="source-token",
            source_identifier="audit-source",
            source_title="audit.xlsx",
            status="ready",
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(source_run)
        await session.flush()
        official_atom_ids = [
            atom["atom_id"]
            for atom in atoms
            if atom.get("coverage_status", "unmapped") != "unfounded_candidate"
            and atom["atom_id"].startswith("ATOM-")
        ]
        run = GenerationRunRecord(
            project_id=project_id,
            source_evidence_run_id=source_run.id,
            status="generating_cases",
            planning_sheet_name="需求A",
            reference_ids_json="[]",
            strict_mode=strict_mode,
            total_chunks=len(chunk_statuses),
            completed_chunks=sum(1 for status in chunk_statuses if status == "completed"),
            failed_chunks=sum(1 for status in chunk_statuses if status == "failed"),
            atom_count=len(official_atom_ids),
            case_count=len(cases),
            stage_payload_json=json.dumps(
                {"blueprint": _blueprint(official_atom_ids), "case_generation": {"status": "completed"}},
                ensure_ascii=False,
            ),
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(run)
        await session.flush()
        for index, status in enumerate(chunk_statuses):
            session.add(
                GenerationChunkRecord(
                    run_id=run.id,
                    project_id=project_id,
                    chunk_index=index,
                    source_row_start=index + 1,
                    source_row_end=index + 1,
                    title_hint=f"chunk-{index}",
                    status=status,
                )
            )
        for index, atom in enumerate(atoms, start=1):
            session.add(
                RequirementAtomRecord(
                    run_id=run.id,
                    project_id=project_id,
                    atom_id=atom["atom_id"],
                    atom_type=atom.get("atom_type", "rule"),
                    requirement_text=atom["requirement_text"],
                    source_sheet_name="需求A",
                    source_row_start=index,
                    source_row_end=index,
                    source_columns_json=json.dumps(["模块", "规则"], ensure_ascii=False),
                    cell_excerpt=atom.get("cell_excerpt", atom["requirement_text"]),
                    visual_evidence_refs_json=json.dumps(
                        atom.get("visual_evidence_refs", []),
                        ensure_ascii=False,
                    ),
                    coverage_status=atom.get("coverage_status", "unmapped"),
                    merge_group_id=atom.get("merge_group_id", atom["atom_id"]),
                )
            )
        for case in cases:
            session.add(
                GenerationCaseRecord(
                    run_id=run.id,
                    project_id=project_id,
                    case_id=case["case_id"],
                    fields_json=json.dumps(case.get("fields", {}), ensure_ascii=False),
                    atom_refs_json=json.dumps(case.get("atom_refs", []), ensure_ascii=False),
                    status="official",
                )
            )
        if audit_unfounded_candidates is not None:
            session.add(
                CoverageAuditRecord(
                    run_id=run.id,
                    project_id=project_id,
                    status="pending",
                    unfounded_case_count=len(audit_unfounded_candidates),
                    unfounded_candidates_json=json.dumps(
                        audit_unfounded_candidates,
                        ensure_ascii=False,
                    ),
                )
            )
        await session.commit()
        return run.id


async def _load_run(run_id: int) -> GenerationRunRecord:
    async with async_session_factory() as session:
        run = await session.get(GenerationRunRecord, run_id)
        assert run is not None
        return run


async def _load_audit(run_id: int) -> CoverageAuditRecord:
    async with async_session_factory() as session:
        audit = (
            await session.execute(
                select(CoverageAuditRecord).where(CoverageAuditRecord.run_id == run_id)
            )
        ).scalar_one()
        return audit


async def _load_cases(run_id: int) -> list[GenerationCaseRecord]:
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(GenerationCaseRecord)
                    .where(GenerationCaseRecord.run_id == run_id)
                    .order_by(GenerationCaseRecord.case_id)
                )
            ).scalars()
        )


@pytest.mark.anyio
async def test_fully_covered_atoms_complete_run(test_db, test_project_id: int) -> None:
    run_id = await _seed_run(
        test_project_id,
        cases=[
            {"case_id": "TC-001", "atom_refs": ["ATOM-0001"]},
            {"case_id": "TC-002", "atom_refs": ["ATOM-0002"]},
        ],
    )

    async with async_session_factory() as session:
        audit = await run_coverage_audit_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    run = await _load_run(run_id)
    assert run.status == "completed"
    assert audit.total_atoms == 2
    assert audit.covered_atoms == 2
    assert audit.uncovered_atoms == 0
    assert json.loads(audit.uncovered_atom_ids_json) == []


@pytest.mark.anyio
async def test_uncovered_atoms_trigger_one_supplement_and_complete_when_covered(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    run_id = await _seed_run(
        test_project_id,
        cases=[{"case_id": "TC-001", "atom_refs": ["ATOM-0001"]}],
    )
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompts.append(kwargs["user_prompt"])
        assert kwargs["api_key"] == "sk-audit-secret"
        assert "ATOM-0002" in kwargs["user_prompt"]
        assert "ATOM-0001" not in kwargs["user_prompt"]
        return {
            "cases": [
                {
                    "case_id": "SUP-001",
                    "module": "奖励领取",
                    "title": "补充奖励每日领取一次",
                    "steps": "领取奖励后再次点击领取",
                    "expected_results": "重复领取被拦截",
                    "source_requirement": "奖励每日领取一次",
                    "atom_ids": ["ATOM-0002"],
                }
            ],
            "warnings": [],
        }, {"raw_response": "raw prompt sk-audit-secret D:/secret/provider.txt"}

    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_cases.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        audit = await run_coverage_audit_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    run = await _load_run(run_id)
    cases = await _load_cases(run_id)
    supplement = json.loads(audit.supplement_summary_json)
    persisted_text = run.stage_payload_json + audit.supplement_summary_json + audit.warnings_json
    assert len(prompts) == 1
    assert run.status == "completed"
    assert run.case_count == 2
    assert [case.case_id for case in cases] == ["SUP-001", "TC-001"]
    assert audit.covered_atoms == 2
    assert supplement["attempted"] is True
    assert supplement["generated_case_count"] == 1
    for forbidden in ("raw_response", "prompt", "sk-audit-secret", "D:/secret"):
        assert forbidden not in persisted_text


@pytest.mark.anyio
async def test_supplement_only_runs_once_and_partial_when_still_uncovered(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    run_id = await _seed_run(
        test_project_id,
        cases=[{"case_id": "TC-001", "atom_refs": ["ATOM-0001"]}],
    )
    calls = 0

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal calls
        calls += 1
        return {"cases": [], "warnings": ["没有可补充用例"]}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_cases.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        first_audit = await run_coverage_audit_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    async def forbidden_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        raise AssertionError("supplement must not run twice")

    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_cases.call_provider_json",
        forbidden_call_provider_json,
    )
    async with async_session_factory() as session:
        second_audit = await run_coverage_audit_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    run = await _load_run(run_id)
    assert calls == 1
    assert run.status == "partial_completed"
    assert first_audit.uncovered_atoms == 1
    assert second_audit.uncovered_atoms == 1
    assert json.loads(second_audit.supplement_summary_json)["attempted"] is True


@pytest.mark.anyio
async def test_failed_chunk_marks_partial_even_when_atoms_are_covered(
    test_db,
    test_project_id: int,
) -> None:
    run_id = await _seed_run(
        test_project_id,
        cases=[
            {"case_id": "TC-001", "atom_refs": ["ATOM-0001"]},
            {"case_id": "TC-002", "atom_refs": ["ATOM-0002"]},
        ],
        chunk_statuses=["completed", "failed"],
    )

    async with async_session_factory() as session:
        audit = await run_coverage_audit_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    run = await _load_run(run_id)
    assert run.status == "partial_completed"
    assert audit.failed_chunk_count == 1
    assert json.loads(audit.export_limitations_json)


@pytest.mark.anyio
async def test_strict_export_blocks_uncovered_atoms_but_non_strict_exports_with_warning(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    strict_run_id = await _seed_run(
        test_project_id,
        strict_mode=True,
        cases=[{"case_id": "TC-001", "atom_refs": ["ATOM-0001"]}],
    )
    non_strict_run_id = await _seed_run(
        test_project_id,
        strict_mode=False,
        cases=[{"case_id": "TC-001", "atom_refs": ["ATOM-0001"]}],
    )

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        return {"cases": [], "warnings": ["缺口保留到导出提示"]}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_cases.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        await run_coverage_audit_for_run(
            session,
            project_id=test_project_id,
            run_id=strict_run_id,
        )
        await run_coverage_audit_for_run(
            session,
            project_id=test_project_id,
            run_id=non_strict_run_id,
        )
        await session.commit()

    async with async_session_factory() as session:
        with pytest.raises(GenerationRunError) as strict_error:
            await build_generation_run_export_placeholder(
                session,
                project_id=test_project_id,
                run_id=strict_run_id,
            )
        non_strict = await build_generation_run_export_placeholder(
            session,
            project_id=test_project_id,
            run_id=non_strict_run_id,
        )

    assert strict_error.value.status_code == 409
    assert "覆盖缺口" in strict_error.value.message
    assert non_strict["status"] == "partial_completed"
    assert non_strict["audit_summary"]["uncovered_atoms"] == 1
    assert non_strict["export_limitations"]
    assert non_strict["warnings"]


@pytest.mark.anyio
async def test_unfounded_candidates_do_not_count_as_coverage_atoms(
    test_db,
    test_project_id: int,
) -> None:
    run_id = await _seed_run(
        test_project_id,
        atoms=[
            {"atom_id": "ATOM-0001", "requirement_text": "活动入口按配置开放"},
            {
                "atom_id": "CAND-0001",
                "requirement_text": "无依据等级限制",
                "coverage_status": "unfounded_candidate",
            },
        ],
        cases=[{"case_id": "TC-001", "atom_refs": ["ATOM-0001"]}],
        audit_unfounded_candidates=[
            {"case_id": "BAD-001", "reason": "缺少有效 Requirement Atom 支撑"}
        ],
    )

    async with async_session_factory() as session:
        audit = await run_coverage_audit_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    run = await _load_run(run_id)
    assert run.status == "completed"
    assert audit.total_atoms == 1
    assert audit.covered_atoms == 1
    assert audit.uncovered_atoms == 0
    assert audit.unfounded_case_count == 1
