"""Requirement Atom extraction and merge service tests."""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest
from sqlalchemy import select

from backend.app.ai.providers import ProviderConnectionError
from backend.app.database import async_session_factory
from backend.app.models import (
    ProjectAiCredentialRecord,
    SourceEvidenceRunRecord,
    TestCaseGenerationChunkRecord as GenerationChunkRecord,
    TestCaseGenerationRunRecord as GenerationRunRecord,
    TestCaseRequirementAtomRecord as RequirementAtomRecord,
)
from backend.app.security.crypto import encrypt_secret
from backend.app.test_cases.full_generation_context import (
    FullPlanningSheetContext,
    FullPlanningSheetFactCell,
    FullPlanningSheetFactRow,
    FullPlanningSheetVisualEvidence,
)
from backend.app.test_cases.generation_chunking import (
    build_generation_chunks,
    persist_generation_chunks,
)
from backend.app.test_cases.requirement_atoms import (
    extract_and_merge_requirement_atoms_for_run,
)


def _cell(row: int, col: int, value: str, column_name: str | None = None) -> FullPlanningSheetFactCell:
    return FullPlanningSheetFactCell(
        row=row,
        col=col,
        coord=f"{chr(64 + min(col, 26))}{row}",
        column_name=column_name or f"Column {col}",
        value=value,
    )


def _row(row: int, values: list[str]) -> FullPlanningSheetFactRow:
    columns = ["模块", "规则", "备注"]
    return FullPlanningSheetFactRow(
        row_index=row,
        source_unit_title="需求A",
        evidence_status="table",
        cells=[
            _cell(row, index, value, columns[index - 1] if index <= len(columns) else None)
            for index, value in enumerate(values, start=1)
        ],
    )


def _context(
    rows: list[FullPlanningSheetFactRow],
    *,
    visuals: list[FullPlanningSheetVisualEvidence] | None = None,
) -> FullPlanningSheetContext:
    return FullPlanningSheetContext(
        source_summary="Requirement atom test context",
        sheet_name="需求A",
        columns=["模块", "规则", "备注"],
        all_fact_rows=rows,
        adopted_visual_evidence_summaries=visuals or [],
        warnings=[],
    )


def _visual(
    *,
    id: int = 101,
    ref: str = "sheet_img_2",
    position: str = "excel:sheet=需求A:image=1:anchor=B2",
) -> FullPlanningSheetVisualEvidence:
    return FullPlanningSheetVisualEvidence(
        id=id,
        resource_id=id + 100,
        ref=ref,
        position=position,
        summary="截图显示活动入口按钮。",
        visible_text="活动入口",
        confidence=0.9,
        limitations=[],
    )


async def _seed_project_ai(project_id: int, *, api_key: str = "sk-atom-secret") -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectAiCredentialRecord(
                project_id=project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret(api_key),
                extra_headers_json='{"X-Test":"atoms"}',
                enabled=True,
            )
        )
        await session.commit()


async def _seed_run_with_chunks(
    project_id: int,
    context: FullPlanningSheetContext,
    *,
    max_fact_rows: int = 120,
) -> int:
    async with async_session_factory() as session:
        source_run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type="local_file",
            source_url="https://demo.invalid/atoms.xlsx",
            source_token="source-token",
            source_identifier="requirement-atoms-source",
            source_title="atoms.xlsx",
            status="ready",
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(source_run)
        await session.flush()
        run = GenerationRunRecord(
            project_id=project_id,
            source_evidence_run_id=source_run.id,
            status="chunking",
            planning_sheet_name=context.sheet_name,
            reference_ids_json="[]",
            strict_mode=False,
            total_chunks=0,
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(run)
        await session.flush()
        chunks = build_generation_chunks(
            context,
            max_fact_rows=max_fact_rows,
            max_chars=999_999,
        )
        await persist_generation_chunks(
            session,
            project_id=project_id,
            run_id=run.id,
            chunks=chunks,
        )
        run.total_chunks = len(chunks)
        await session.commit()
        return run.id


async def _load_atoms(run_id: int) -> list[RequirementAtomRecord]:
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(RequirementAtomRecord)
                    .where(RequirementAtomRecord.run_id == run_id)
                    .order_by(RequirementAtomRecord.atom_id)
                )
            ).scalars()
        )


async def _load_chunks(run_id: int) -> list[GenerationChunkRecord]:
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(GenerationChunkRecord)
                    .where(GenerationChunkRecord.run_id == run_id)
                    .order_by(GenerationChunkRecord.chunk_index)
                )
            ).scalars()
        )


async def _load_run(run_id: int) -> GenerationRunRecord:
    async with async_session_factory() as session:
        run = await session.get(GenerationRunRecord, run_id)
        assert run is not None
        return run


@pytest.mark.anyio
async def test_single_chunk_extracts_official_atoms_and_updates_run(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    context = _context(
        [
            _row(1, ["模块", "规则", "备注"]),
            _row(2, ["活动入口", "按配置开放入口", "入口按钮"]),
        ]
    )
    run_id = await _seed_run_with_chunks(test_project_id, context)
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompts.append(kwargs["user_prompt"])
        assert kwargs["api_key"] == "sk-atom-secret"
        assert kwargs["extra_headers"] == {"X-Test": "atoms"}
        assert "只能从当前 chunk facts 和已采纳视觉证据抽取" in kwargs["user_prompt"]
        assert "参考案例、常识或旧知识" in kwargs["user_prompt"]
        assert "按配置开放入口" in kwargs["user_prompt"]
        return {
            "atoms": [
                {
                    "atom_type": "entry",
                    "text": "活动入口按配置开放",
                    "source_sheet": "需求A",
                    "source_rows": [2, 2],
                    "source_columns": ["模块", "规则"],
                    "source_excerpt": "活动入口 | 按配置开放入口",
                    "visual_evidence_ids": [],
                    "confidence": 0.91,
                    "warnings": [],
                    "merge_key": "entry:activity-open",
                    "is_unfounded_candidate": False,
                }
            ],
            "warnings": [],
        }, {"latency_ms": 15, "usage": {"total_tokens": 100}}

    monkeypatch.setattr(
        "backend.app.test_cases.requirement_atoms.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        await extract_and_merge_requirement_atoms_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
            context=context,
        )
        await session.commit()

    atoms = await _load_atoms(run_id)
    chunks = await _load_chunks(run_id)
    run = await _load_run(run_id)
    assert len(prompts) == 1
    assert run.status == "merging_atoms"
    assert run.atom_count == 1
    assert run.completed_chunks == 1
    assert run.failed_chunks == 0
    assert chunks[0].status == "completed"
    assert atoms[0].atom_id == "ATOM-0001"
    assert atoms[0].atom_type == "entry"
    assert atoms[0].requirement_text == "活动入口按配置开放"
    assert atoms[0].merge_group_id == "entry:activity-open"
    assert atoms[0].coverage_status == "unmapped"
    assert json.loads(atoms[0].source_columns_json) == ["模块", "规则"]


@pytest.mark.anyio
async def test_duplicate_atoms_are_merged_with_conflict_warning(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    context = _context(
        [
            _row(1, ["活动入口", "按配置开放入口", ""]),
            _row(2, ["活动入口", "配置关闭时隐藏入口", ""]),
        ]
    )
    run_id = await _seed_run_with_chunks(test_project_id, context, max_fact_rows=1)

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        chunk_index = len(fake_call_provider_json.calls)
        fake_call_provider_json.calls.append(kwargs)
        text = "活动入口按配置开放" if chunk_index == 0 else "活动入口按配置开放但关闭时隐藏"
        row = 1 if chunk_index == 0 else 2
        return {
            "atoms": [
                {
                    "atom_type": "entry",
                    "text": text,
                    "source_sheet": "需求A",
                    "source_rows": [row, row],
                    "source_columns": ["模块", "规则"],
                    "source_excerpt": text,
                    "confidence": 0.86,
                    "warnings": [],
                    "merge_key": "entry:activity-open",
                    "is_unfounded_candidate": False,
                }
            ],
        }, {"latency_ms": 3}

    fake_call_provider_json.calls = []
    monkeypatch.setattr(
        "backend.app.test_cases.requirement_atoms.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        await extract_and_merge_requirement_atoms_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
            context=context,
        )
        await session.commit()

    atoms = await _load_atoms(run_id)
    assert len(atoms) == 1
    assert atoms[0].source_row_start == 1
    assert atoms[0].source_row_end == 2
    warnings = json.dumps(json.loads(atoms[0].warnings_json), ensure_ascii=False)
    assert "重复" in warnings
    assert "冲突" in warnings


@pytest.mark.anyio
async def test_invalid_provider_json_marks_failed_chunk_and_continues(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    context = _context(
        [
            _row(1, ["活动入口", "按配置开放入口", ""]),
            _row(2, ["奖励", "每日领取一次", ""]),
        ]
    )
    run_id = await _seed_run_with_chunks(test_project_id, context, max_fact_rows=1)

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        call_index = len(fake_call_provider_json.calls)
        fake_call_provider_json.calls.append(kwargs)
        if call_index == 0:
            raise ProviderConnectionError(
                "invalid_json",
                "raw_response prompt sk-atom-secret D:/secret/provider.txt",
                502,
            )
        return {
            "atoms": [
                {
                    "atom_type": "reward",
                    "text": "奖励每日领取一次",
                    "source_sheet": "需求A",
                    "source_rows": [2, 2],
                    "source_columns": ["模块", "规则"],
                    "source_excerpt": "每日领取一次",
                    "confidence": 0.9,
                    "merge_key": "reward:daily",
                }
            ]
        }, {"latency_ms": 7, "usage": {"total_tokens": 11}}

    fake_call_provider_json.calls = []
    monkeypatch.setattr(
        "backend.app.test_cases.requirement_atoms.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        await extract_and_merge_requirement_atoms_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
            context=context,
        )
        await session.commit()

    chunks = await _load_chunks(run_id)
    run = await _load_run(run_id)
    atoms = await _load_atoms(run_id)
    assert [chunk.status for chunk in chunks] == ["failed", "completed"]
    assert run.status == "merging_atoms"
    assert run.failed_chunks == 1
    assert run.atom_count == 1
    assert len(atoms) == 1
    persisted_text = "\n".join(
        [
            run.stage_payload_json,
            *(chunk.error_summary + chunk.structure_hints_json for chunk in chunks),
        ]
    )
    for forbidden in ("raw_response", "prompt", "sk-atom-secret", "D:/secret", "provider.txt"):
        assert forbidden not in persisted_text


@pytest.mark.anyio
async def test_empty_atoms_adds_warning_without_official_atoms(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    context = _context([_row(1, ["活动入口", "只是一段说明", ""])])
    run_id = await _seed_run_with_chunks(test_project_id, context)

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        return {"atoms": [], "warnings": ["没有可抽取的需求原子"]}, {"latency_ms": 1}

    monkeypatch.setattr(
        "backend.app.test_cases.requirement_atoms.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        await extract_and_merge_requirement_atoms_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
            context=context,
        )
        await session.commit()

    run = await _load_run(run_id)
    chunks = await _load_chunks(run_id)
    assert await _load_atoms(run_id) == []
    assert run.atom_count == 0
    assert run.warning_count >= 1
    assert chunks[0].status == "completed"
    assert "未抽取" in chunks[0].structure_hints_json


@pytest.mark.anyio
async def test_unfounded_candidate_is_persisted_but_not_counted_as_official(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    context = _context([_row(1, ["活动入口", "按配置开放入口", ""])])
    run_id = await _seed_run_with_chunks(test_project_id, context)

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        return {
            "atoms": [
                {
                    "atom_type": "rule",
                    "text": "玩家达到 10 级才能进入活动",
                    "source_sheet": "需求A",
                    "source_rows": [],
                    "source_columns": [],
                    "source_excerpt": "",
                    "confidence": 0.3,
                    "merge_key": "unfounded:level",
                    "is_unfounded_candidate": True,
                }
            ]
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.requirement_atoms.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        await extract_and_merge_requirement_atoms_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
            context=context,
        )
        await session.commit()

    atoms = await _load_atoms(run_id)
    run = await _load_run(run_id)
    assert len(atoms) == 1
    assert atoms[0].atom_id == "CAND-0001"
    assert atoms[0].coverage_status == "unfounded_candidate"
    assert run.atom_count == 0


@pytest.mark.anyio
async def test_adopted_visual_evidence_can_create_visual_fact_atom(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    visual = _visual(id=101, ref="sheet_img_2")
    context = _context(
        [_row(1, ["活动入口", "按配置开放入口", ""]), _row(2, ["UI", "入口截图", ""])],
        visuals=[visual],
    )
    run_id = await _seed_run_with_chunks(test_project_id, context)

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        assert "sheet_img_2" in kwargs["user_prompt"]
        return {
            "atoms": [
                {
                    "atom_type": "visual_fact",
                    "text": "截图显示活动入口按钮",
                    "source_sheet": "需求A",
                    "source_rows": [2, 2],
                    "source_columns": ["规则"],
                    "source_excerpt": "入口截图",
                    "visual_evidence_ids": [101],
                    "confidence": 0.88,
                    "merge_key": "visual:sheet-img-2",
                }
            ]
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.requirement_atoms.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        await extract_and_merge_requirement_atoms_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
            context=context,
        )
        await session.commit()

    atoms = await _load_atoms(run_id)
    assert len(atoms) == 1
    assert atoms[0].atom_type == "visual_fact"
    assert json.loads(atoms[0].visual_evidence_refs_json) == ["sheet_img_2"]


@pytest.mark.anyio
async def test_unadopted_or_cross_chunk_visual_ref_is_removed_from_provider_output(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    context = _context([_row(1, ["活动入口", "按配置开放入口", ""])])
    run_id = await _seed_run_with_chunks(test_project_id, context)

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        return {
            "atoms": [
                {
                    "atom_type": "visual_fact",
                    "text": "未采纳图片声称存在红点",
                    "source_sheet": "需求A",
                    "source_rows": [1, 1],
                    "source_columns": ["模块"],
                    "source_excerpt": "活动入口",
                    "visual_evidence_ids": ["unadopted_img"],
                    "confidence": 0.7,
                    "merge_key": "visual:bad",
                }
            ]
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.requirement_atoms.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        await extract_and_merge_requirement_atoms_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
            context=context,
        )
        await session.commit()

    atoms = await _load_atoms(run_id)
    assert len(atoms) == 1
    assert atoms[0].coverage_status == "unfounded_candidate"
    assert json.loads(atoms[0].visual_evidence_refs_json) == []
    warnings = json.dumps(json.loads(atoms[0].warnings_json), ensure_ascii=False)
    assert "未采纳" in warnings or "非当前 chunk" in warnings
