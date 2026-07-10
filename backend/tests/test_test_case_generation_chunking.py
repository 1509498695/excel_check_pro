"""Generation Run structure-first chunking tests."""

from __future__ import annotations

import datetime
import json

import pytest
from sqlalchemy import select

from backend.app.database import async_session_factory
from backend.app.models import (
    SourceEvidenceRunRecord,
    TestCaseGenerationChunkRecord as GenerationChunkRecord,
    TestCaseGenerationRunRecord as GenerationRunRecord,
)
from backend.app.test_cases.full_generation_context import (
    FullPlanningSheetContext,
    FullPlanningSheetFactCell,
    FullPlanningSheetFactRow,
    FullPlanningSheetVisualEvidence,
)
from backend.app.test_cases.generation_chunking import (
    build_generation_chunks,
    chunk_full_planning_sheet_context_for_run,
)


def _cell(
    row_index: int,
    col: int,
    value: str,
    *,
    column_name: str | None = None,
) -> FullPlanningSheetFactCell:
    return FullPlanningSheetFactCell(
        row=row_index,
        col=col,
        coord=f"{chr(64 + min(col, 26))}{row_index}",
        column_name=column_name or f"Column {col}",
        value=value,
    )


def _row(
    row_index: int,
    values: list[str],
    *,
    unit_title: str = "需求A",
    evidence_status: str = "table",
    column_names: list[str] | None = None,
) -> FullPlanningSheetFactRow:
    return FullPlanningSheetFactRow(
        row_index=row_index,
        source_unit_title=unit_title,
        evidence_status=evidence_status,
        cells=[
            _cell(
                row_index,
                col,
                value,
                column_name=(column_names or [])[col - 1]
                if column_names and col <= len(column_names)
                else None,
            )
            for col, value in enumerate(values, start=1)
        ],
    )


def _context(
    rows: list[FullPlanningSheetFactRow],
    *,
    visuals: list[FullPlanningSheetVisualEvidence] | None = None,
) -> FullPlanningSheetContext:
    return FullPlanningSheetContext(
        source_summary="Full context for chunking tests",
        sheet_name="需求A",
        columns=["模块", "规则", "奖励"],
        all_fact_rows=rows,
        adopted_visual_evidence_summaries=visuals or [],
        warnings=[],
    )


def _covered_rows(chunks) -> list[int]:
    covered: list[int] = []
    for chunk in chunks:
        covered.extend(chunk.structure_hints["covered_row_indexes"])
    return covered


def _long_row(row_index: int) -> FullPlanningSheetFactRow:
    return _row(
        row_index,
        [
            f"模块 {row_index} 的完整需求描述，文本足够长避免被当成标题",
            f"规则 {row_index} 的完整需求描述，文本足够长避免被当成表头",
        ],
    )


@pytest.mark.anyio
async def test_title_rows_split_chunks_and_title_starts_new_chunk(test_db) -> None:
    rows = [
        _row(1, ["活动入口"]),
        _row(2, ["入口", "完成新手任务后展示入口"]),
        _row(3, ["入口", "活动结束后隐藏入口"]),
        _row(4, ["奖励规则"]),
        _row(5, ["奖励", "每日首次完成任务发放奖励"]),
        _row(6, ["奖励", "重复完成不再发放奖励"]),
    ]

    chunks = build_generation_chunks(_context(rows), max_fact_rows=120)

    assert len(chunks) == 2
    assert [(chunk.row_start, chunk.row_end) for chunk in chunks] == [(1, 3), (4, 6)]
    assert chunks[0].title_hints == ["活动入口"]
    assert chunks[1].title_hints == ["奖励规则"]
    assert chunks[1].structure_hints["split_reasons"] == ["title_row"]


@pytest.mark.anyio
async def test_blank_row_gap_splits_chunks_without_crossing_section(test_db) -> None:
    rows = [
        _row(1, ["模块", "规则"], column_names=["模块", "规则"]),
        _row(2, ["入口", "开启活动"]),
        _row(6, ["奖励", "领取奖励"]),
        _row(7, ["奖励", "补领奖励"]),
    ]

    chunks = build_generation_chunks(_context(rows), max_fact_rows=120)

    assert [(chunk.row_start, chunk.row_end) for chunk in chunks] == [(1, 2), (6, 7)]
    assert chunks[1].structure_hints["split_reasons"] == ["blank_row_gap"]


@pytest.mark.anyio
async def test_header_signature_change_splits_chunks_and_keeps_new_header(test_db) -> None:
    rows = [
        _row(1, ["模块", "规则"], column_names=["模块", "规则"]),
        _row(2, ["入口", "开启活动"]),
        _row(3, ["入口", "关闭活动"]),
        _row(4, ["阶段", "条件", "奖励"], column_names=["阶段", "条件", "奖励"]),
        _row(5, ["第一阶段", "累计登录 1 天", "金币"]),
        _row(6, ["第二阶段", "累计登录 2 天", "钻石"]),
    ]

    chunks = build_generation_chunks(_context(rows), max_fact_rows=120)

    assert [(chunk.row_start, chunk.row_end) for chunk in chunks] == [(1, 3), (4, 6)]
    assert chunks[1].structure_hints["split_reasons"] == ["header_change"]
    assert chunks[1].structure_hints["header_signature"] == ["阶段", "条件", "奖励"]


@pytest.mark.anyio
async def test_source_unit_boundary_splits_chunks(test_db) -> None:
    rows = [
        _row(1, ["入口", "规则 A"], unit_title="需求A"),
        _row(2, ["入口", "规则 B"], unit_title="需求A"),
        _row(3, ["奖励", "规则 C"], unit_title="需求A-附表"),
        _row(4, ["奖励", "规则 D"], unit_title="需求A-附表"),
    ]

    chunks = build_generation_chunks(_context(rows), max_fact_rows=120)

    assert [(chunk.row_start, chunk.row_end) for chunk in chunks] == [(1, 2), (3, 4)]
    assert chunks[1].structure_hints["split_reasons"] == ["source_unit_boundary"]


@pytest.mark.anyio
async def test_fallback_windows_cover_all_facts_once_with_overlap_hints(test_db) -> None:
    rows = [_long_row(row_index) for row_index in range(1, 306)]

    chunks = build_generation_chunks(
        _context(rows),
        max_fact_rows=120,
        max_chars=999_999,
        overlap_fact_rows=8,
    )

    covered = _covered_rows(chunks)
    assert len(chunks) == 3
    assert covered == list(range(1, 306))
    assert len(covered) == len(set(covered))
    assert [chunk.fact_count for chunk in chunks] == [120, 120, 65]
    assert chunks[0].structure_hints["next_overlap_hint"]["row_indexes"] == list(range(113, 121))
    assert chunks[1].structure_hints["previous_overlap_hint"]["row_indexes"] == list(range(113, 121))
    assert chunks[1].structure_hints["next_overlap_hint"]["row_indexes"] == list(range(233, 241))


@pytest.mark.anyio
async def test_visual_resources_are_assigned_by_anchor_row_with_safe_fallback(test_db) -> None:
    rows = [_long_row(row_index) for row_index in range(1, 181)]
    visuals = [
        FullPlanningSheetVisualEvidence(
            id=1,
            resource_id=11,
            ref="sheet_img_row_130",
            position="excel:sheet=需求A:image=1:anchor=B130",
            summary="第 130 行截图摘要",
            visible_text="第 130 行截图摘要",
            confidence=0.9,
            limitations=[],
        ),
        FullPlanningSheetVisualEvidence(
            id=2,
            resource_id=12,
            ref="sheet_img_unknown",
            position="docx:block:image",
            summary="无法解析锚点截图",
            visible_text="无法解析锚点截图",
            confidence=0.8,
            limitations=[],
        ),
    ]

    chunks = build_generation_chunks(
        _context(rows, visuals=visuals),
        max_fact_rows=120,
        max_chars=999_999,
    )

    assert chunks[0].resource_refs == ["sheet_img_unknown"]
    assert chunks[1].resource_refs == ["sheet_img_row_130"]
    assert "无法解析" in json.dumps(chunks[0].structure_hints["warnings"], ensure_ascii=False)


@pytest.mark.anyio
async def test_chunking_persists_chunks_and_updates_run_progress(
    test_db,
    test_project_id: int,
) -> None:
    source_run_id = await _seed_source_evidence_run(test_project_id)
    run_id = await _seed_generation_run(test_project_id, source_run_id)
    visuals = [
        FullPlanningSheetVisualEvidence(
            id=1,
            resource_id=21,
            ref="sheet_img_row_130",
            position="excel:sheet=需求A:image=1:anchor=B130",
            summary="截图摘要 provider_response token raw_response prompt D:/secret",
            visible_text="截图文字",
            confidence=0.9,
            limitations=[],
        )
    ]
    context = _context(
        [_long_row(row_index) for row_index in range(1, 261)],
        visuals=visuals,
    )

    async with async_session_factory() as session:
        chunks = await chunk_full_planning_sheet_context_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
            context=context,
            max_fact_rows=120,
            max_chars=999_999,
        )
        await session.commit()

    assert len(chunks) == 3
    async with async_session_factory() as session:
        run = await session.get(GenerationRunRecord, run_id)
        records = list(
            (
                await session.execute(
                    select(GenerationChunkRecord)
                    .where(GenerationChunkRecord.run_id == run_id)
                    .order_by(GenerationChunkRecord.chunk_index)
                )
            ).scalars()
        )

    assert run is not None
    assert run.status == "chunking"
    assert run.total_chunks == 3
    assert run.completed_chunks == 0
    assert run.failed_chunks == 0
    assert len(records) == 3
    first_payload = json.loads(records[0].structure_hints_json)
    second_payload = json.loads(records[1].structure_hints_json)
    assert {
        "chunk_key",
        "fact_count",
        "char_count",
        "resource_refs",
        "covered_row_indexes",
    }.issubset(first_payload)
    assert second_payload["resource_refs"] == ["sheet_img_row_130"]
    persisted_text = json.dumps(
        [json.loads(record.structure_hints_json) for record in records],
        ensure_ascii=False,
    )
    for forbidden in (
        "provider_response",
        "raw_response",
        "prompt",
        "D:/secret",
        "token",
    ):
        assert forbidden not in persisted_text


async def _seed_source_evidence_run(project_id: int) -> int:
    async with async_session_factory() as session:
        run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type="local_file",
            source_url="https://demo.invalid/source.xlsx",
            source_token="source-token",
            source_identifier="chunking-source",
            source_title="chunking-source.xlsx",
            status="ready",
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(run)
        await session.commit()
        return run.id


async def _seed_generation_run(project_id: int, source_run_id: int) -> int:
    async with async_session_factory() as session:
        run = GenerationRunRecord(
            project_id=project_id,
            source_evidence_run_id=source_run_id,
            status="queued",
            planning_sheet_name="需求A",
            reference_ids_json="[]",
            strict_mode=False,
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(run)
        await session.commit()
        return run.id
