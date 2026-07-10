"""Structure-first chunking for V3 Generation Runs."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import TestCaseGenerationChunkRecord
from backend.app.test_cases.full_generation_context import (
    FullPlanningSheetContext,
    FullPlanningSheetFactRow,
    FullPlanningSheetVisualEvidence,
)
from backend.app.test_cases.generation_runs import update_generation_run_stage


DEFAULT_MAX_FACT_ROWS = 120
DEFAULT_MAX_CHARS = 30_000
DEFAULT_OVERLAP_FACT_ROWS = 8

_HEADER_WORDS = frozenset(
    {
        "模块",
        "规则",
        "条件",
        "奖励",
        "阶段",
        "说明",
        "类型",
        "功能",
        "功能点",
        "需求",
        "描述",
        "配置",
        "字段",
        "值",
        "状态",
        "时间",
        "限制",
        "操作",
        "结果",
        "优先级",
    }
)
_ANCHOR_ROW_PATTERNS = (
    re.compile(r"anchor=[A-Z]+(\d+)", re.IGNORECASE),
    re.compile(r"\brow=(\d+)\b", re.IGNORECASE),
    re.compile(r"\bR(\d+)C\d+\b", re.IGNORECASE),
)
_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"']+")
_URL_RE = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)
_SENSITIVE_TERMS = (
    "provider_response",
    "raw_response",
    "provider response",
    "raw response",
    "prompt",
    "token",
    "secret",
    "password",
    "api_key",
)


@dataclass(frozen=True)
class GenerationChunk:
    """Safe internal chunk boundary for later V3 AI stages."""

    chunk_key: str
    sheet_name: str
    row_start: int | None
    row_end: int | None
    column_start: int | None
    column_end: int | None
    title_hints: list[str]
    fact_count: int
    char_count: int
    resource_refs: list[str]
    status: str = "queued"
    structure_hints: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Segment:
    rows: list[FullPlanningSheetFactRow]
    split_reasons: list[str]


def build_generation_chunks(
    context: FullPlanningSheetContext,
    *,
    max_fact_rows: int = DEFAULT_MAX_FACT_ROWS,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_fact_rows: int = DEFAULT_OVERLAP_FACT_ROWS,
) -> list[GenerationChunk]:
    """Build safe, structure-first chunks without persisting or calling AI."""
    rows = sorted(context.all_fact_rows, key=lambda item: item.row_index)
    if not rows:
        return []

    structural_segments = _split_by_structure(rows)
    chunks: list[GenerationChunk] = []
    for segment in structural_segments:
        chunks.extend(
            _split_segment_by_limits(
                segment,
                sheet_name=context.sheet_name,
                max_fact_rows=max(1, int(max_fact_rows)),
                max_chars=max(1, int(max_chars)),
            )
        )

    _apply_overlap_hints(chunks, overlap_fact_rows=max(0, int(overlap_fact_rows)))
    _assign_visual_evidence_refs(chunks, context.adopted_visual_evidence_summaries)
    return chunks


async def persist_generation_chunks(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    chunks: list[GenerationChunk],
) -> None:
    """Replace persisted chunk boundaries for one project-scoped Generation Run."""
    await db.execute(
        delete(TestCaseGenerationChunkRecord).where(
            TestCaseGenerationChunkRecord.project_id == project_id,
            TestCaseGenerationChunkRecord.run_id == run_id,
        )
    )
    for index, chunk in enumerate(chunks):
        db.add(
            TestCaseGenerationChunkRecord(
                project_id=project_id,
                run_id=run_id,
                chunk_index=index,
                source_row_start=chunk.row_start,
                source_row_end=chunk.row_end,
                source_column_start=chunk.column_start,
                source_column_end=chunk.column_end,
                title_hint=_first_title_hint(chunk.title_hints),
                status=chunk.status,
                structure_hints_json=json.dumps(
                    _safe_payload(chunk.structure_hints),
                    ensure_ascii=False,
                ),
            )
        )
    await db.flush()


async def chunk_full_planning_sheet_context_for_run(
    db: AsyncSession,
    *,
    project_id: int,
    run_id: int,
    context: FullPlanningSheetContext,
    max_fact_rows: int = DEFAULT_MAX_FACT_ROWS,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_fact_rows: int = DEFAULT_OVERLAP_FACT_ROWS,
) -> list[GenerationChunk]:
    """Build and persist chunks, then update the Generation Run chunking progress."""
    chunks = build_generation_chunks(
        context,
        max_fact_rows=max_fact_rows,
        max_chars=max_chars,
        overlap_fact_rows=overlap_fact_rows,
    )
    await persist_generation_chunks(
        db,
        project_id=project_id,
        run_id=run_id,
        chunks=chunks,
    )
    await update_generation_run_stage(
        db,
        project_id=project_id,
        run_id=run_id,
        status="chunking",
        total_chunks=len(chunks),
        completed_chunks=0,
        failed_chunks=0,
        stage_payload={
            "chunking": {
                "sheet_name": _safe_text(context.sheet_name),
                "chunk_count": len(chunks),
                "fact_count": sum(chunk.fact_count for chunk in chunks),
                "char_count": sum(chunk.char_count for chunk in chunks),
                "row_ranges": [
                    {
                        "chunk_key": chunk.chunk_key,
                        "row_start": chunk.row_start,
                        "row_end": chunk.row_end,
                    }
                    for chunk in chunks
                ],
            }
        },
    )
    return chunks


def _split_by_structure(rows: list[FullPlanningSheetFactRow]) -> list[_Segment]:
    segments: list[_Segment] = []
    current_rows: list[FullPlanningSheetFactRow] = []
    current_header_signature: list[str] | None = None
    current_reasons = ["start"]

    for row in rows:
        if not current_rows:
            current_rows = [row]
            current_header_signature = _header_signature(row)
            continue

        reason = _split_reason(
            previous_row=current_rows[-1],
            next_row=row,
            current_header_signature=current_header_signature,
        )
        if reason is not None:
            segments.append(_Segment(rows=current_rows, split_reasons=current_reasons))
            current_rows = [row]
            current_reasons = [reason]
            current_header_signature = _header_signature(row)
            continue

        current_rows.append(row)
        if current_header_signature is None:
            current_header_signature = _header_signature(row)

    if current_rows:
        segments.append(_Segment(rows=current_rows, split_reasons=current_reasons))
    return segments


def _split_reason(
    *,
    previous_row: FullPlanningSheetFactRow,
    next_row: FullPlanningSheetFactRow,
    current_header_signature: list[str] | None,
) -> str | None:
    if next_row.row_index > previous_row.row_index + 1:
        return "blank_row_gap"
    if _is_title_row(next_row):
        return "title_row"
    if (
        next_row.source_unit_title != previous_row.source_unit_title
        or next_row.evidence_status != previous_row.evidence_status
    ):
        return "source_unit_boundary"

    next_header_signature = _header_signature(next_row)
    if (
        next_header_signature is not None
        and current_header_signature is not None
        and next_header_signature != current_header_signature
    ):
        return "header_change"
    return None


def _split_segment_by_limits(
    segment: _Segment,
    *,
    sheet_name: str,
    max_fact_rows: int,
    max_chars: int,
) -> list[GenerationChunk]:
    chunks: list[GenerationChunk] = []
    current_rows: list[FullPlanningSheetFactRow] = []
    current_chars = 0
    current_reasons = list(segment.split_reasons)
    current_warnings: list[str] = []

    for row in segment.rows:
        row_chars = _row_char_count(row)
        limit_reason = _limit_split_reason(
            current_rows=current_rows,
            current_chars=current_chars,
            next_row_chars=row_chars,
            max_fact_rows=max_fact_rows,
            max_chars=max_chars,
        )
        if limit_reason is not None:
            chunks.append(
                _make_chunk(
                    sheet_name=sheet_name,
                    rows=current_rows,
                    split_reasons=current_reasons,
                    warnings=current_warnings,
                )
            )
            current_rows = []
            current_chars = 0
            current_reasons = [limit_reason]
            current_warnings = []

        current_rows.append(row)
        current_chars += row_chars
        if row_chars > max_chars:
            current_warnings.append(
                f"第 {row.row_index} 行超过 chunk 字符软预算，已作为完整单行保留。"
            )

    if current_rows:
        chunks.append(
            _make_chunk(
                sheet_name=sheet_name,
                rows=current_rows,
                split_reasons=current_reasons,
                warnings=current_warnings,
            )
        )
    return chunks


def _limit_split_reason(
    *,
    current_rows: list[FullPlanningSheetFactRow],
    current_chars: int,
    next_row_chars: int,
    max_fact_rows: int,
    max_chars: int,
) -> str | None:
    if not current_rows:
        return None
    if len(current_rows) >= max_fact_rows:
        return "row_window"
    if current_chars + next_row_chars > max_chars:
        return "char_budget"
    return None


def _make_chunk(
    *,
    sheet_name: str,
    rows: list[FullPlanningSheetFactRow],
    split_reasons: list[str],
    warnings: list[str],
) -> GenerationChunk:
    row_indexes = [row.row_index for row in rows]
    column_indexes = [
        cell.col
        for row in rows
        for cell in row.cells
        if cell.value.strip()
    ]
    title_hints = _title_hints(rows)
    header_signature = _first_header_signature(rows)
    row_start = min(row_indexes) if row_indexes else None
    row_end = max(row_indexes) if row_indexes else None
    column_start = min(column_indexes) if column_indexes else None
    column_end = max(column_indexes) if column_indexes else None
    char_count = sum(_row_char_count(row) for row in rows)
    chunk_key = _chunk_key(
        sheet_name=sheet_name,
        row_start=row_start,
        row_end=row_end,
        column_start=column_start,
        column_end=column_end,
    )
    structure_hints: dict[str, Any] = {
        "chunk_key": chunk_key,
        "sheet_name": _safe_text(sheet_name),
        "fact_count": len(rows),
        "char_count": char_count,
        "resource_refs": [],
        "split_reasons": _safe_list(split_reasons),
        "covered_row_indexes": row_indexes,
        "previous_overlap_hint": None,
        "next_overlap_hint": None,
        "title_hints": _safe_list(title_hints),
        "warnings": _safe_list(warnings),
    }
    if header_signature is not None:
        structure_hints["header_signature"] = _safe_list(header_signature)
    return GenerationChunk(
        chunk_key=chunk_key,
        sheet_name=sheet_name,
        row_start=row_start,
        row_end=row_end,
        column_start=column_start,
        column_end=column_end,
        title_hints=title_hints,
        fact_count=len(rows),
        char_count=char_count,
        resource_refs=[],
        structure_hints=structure_hints,
    )


def _apply_overlap_hints(chunks: list[GenerationChunk], *, overlap_fact_rows: int) -> None:
    if overlap_fact_rows <= 0:
        return
    for index, chunk in enumerate(chunks):
        if index > 0:
            previous_rows = chunks[index - 1].structure_hints["covered_row_indexes"]
            chunk.structure_hints["previous_overlap_hint"] = {
                "row_indexes": previous_rows[-overlap_fact_rows:],
                "source_chunk_key": chunks[index - 1].chunk_key,
            }
        if index < len(chunks) - 1:
            current_rows = chunk.structure_hints["covered_row_indexes"]
            chunk.structure_hints["next_overlap_hint"] = {
                "row_indexes": current_rows[-overlap_fact_rows:],
                "target_chunk_key": chunks[index + 1].chunk_key,
            }


def _assign_visual_evidence_refs(
    chunks: list[GenerationChunk],
    visuals: list[FullPlanningSheetVisualEvidence],
) -> None:
    if not chunks:
        return
    for visual in visuals:
        ref = _safe_text(visual.ref)
        if not ref:
            continue
        anchor_row = _visual_anchor_row(visual)
        target_chunk = _chunk_for_anchor_row(chunks, anchor_row)
        if target_chunk is None:
            target_chunk = chunks[0]
            target_chunk.structure_hints["warnings"].append(
                f"视觉证据 {ref} 无法解析锚点，已放入首个 chunk。"
            )
        _append_unique(target_chunk.resource_refs, ref)
        _append_unique(target_chunk.structure_hints["resource_refs"], ref)


def _chunk_for_anchor_row(
    chunks: list[GenerationChunk],
    anchor_row: int | None,
) -> GenerationChunk | None:
    if anchor_row is None:
        return None
    for chunk in chunks:
        if chunk.row_start is not None and chunk.row_end is not None:
            if chunk.row_start <= anchor_row <= chunk.row_end:
                return chunk
    return None


def _visual_anchor_row(visual: FullPlanningSheetVisualEvidence) -> int | None:
    position = str(visual.position or "")
    for pattern in _ANCHOR_ROW_PATTERNS:
        match = pattern.search(position)
        if match:
            return int(match.group(1))
    return None


def _header_signature(row: FullPlanningSheetFactRow) -> list[str] | None:
    values = [cell.value.strip() for cell in row.cells if cell.value.strip()]
    if len(values) < 2:
        return None
    if not all(1 <= len(value) <= 20 for value in values):
        return None
    values_match_columns = all(
        cell.value.strip() == cell.column_name.strip()
        for cell in row.cells
        if cell.value.strip()
    )
    values_are_header_words = all(value in _HEADER_WORDS for value in values)
    if values_match_columns or values_are_header_words:
        return values
    return None


def _first_header_signature(rows: list[FullPlanningSheetFactRow]) -> list[str] | None:
    for row in rows:
        signature = _header_signature(row)
        if signature is not None:
            return signature
    return None


def _is_title_row(row: FullPlanningSheetFactRow) -> bool:
    non_empty_cells = [cell for cell in row.cells if cell.value.strip()]
    if len(non_empty_cells) != 1:
        return False
    cell = non_empty_cells[0]
    value = cell.value.strip()
    return cell.col == 1 and 1 <= len(value) <= 40 and not _looks_like_sentence(value)


def _looks_like_sentence(value: str) -> bool:
    return any(marker in value for marker in ("。", "，", "；", ";", "：", ":"))


def _title_hints(rows: list[FullPlanningSheetFactRow]) -> list[str]:
    hints: list[str] = []
    for row in rows:
        if not _is_title_row(row):
            continue
        value = row.cells[0].value.strip()
        _append_unique(hints, _safe_text(value))
    return hints[:5]


def _row_char_count(row: FullPlanningSheetFactRow) -> int:
    return sum(len(cell.value.strip()) for cell in row.cells if cell.value.strip())


def _chunk_key(
    *,
    sheet_name: str,
    row_start: int | None,
    row_end: int | None,
    column_start: int | None,
    column_end: int | None,
) -> str:
    return (
        f"{_safe_text(sheet_name)}:"
        f"rows:{row_start or 0}-{row_end or 0}:"
        f"cols:{column_start or 0}-{column_end or 0}"
    )


def _first_title_hint(title_hints: list[str]) -> str:
    if not title_hints:
        return ""
    return _safe_text(title_hints[0])[:255]


def _safe_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_payload(item) for item in value]
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, int | float | bool) or value is None:
        return value
    return _safe_text(str(value))


def _safe_list(values: list[str]) -> list[str]:
    return [_safe_text(value) for value in values if _safe_text(value)]


def _safe_text(value: str) -> str:
    text = str(value or "")
    text = _URL_RE.sub("[url]", text)
    text = _WINDOWS_PATH_RE.sub("[path]", text)
    for term in _SENSITIVE_TERMS:
        text = re.sub(re.escape(term), "[redacted]", text, flags=re.IGNORECASE)
    return text.strip()


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)
