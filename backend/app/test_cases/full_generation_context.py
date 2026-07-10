"""Full Planning Sheet Context builder for V3 generation runs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    SourceEvidenceResourceRecord,
    SourceEvidenceRunRecord,
    SourceEvidenceVisualObservationRecord,
)
from backend.app.test_cases.schemas import GenerationWarning, ParsedSourceCell, ParsedSourceUnit
from backend.app.test_cases.source_evidence import (
    SourceEvidenceError,
    _deduplicate_warnings,
    _ensure_run_can_be_used,
    _find_sheet_unit,
    _load_parsed_source_for_context,
    _manifest_warnings,
    _resolve_safe_context_sheet_name,
    _safe_context_resources_for_sheet,
    _source_summary,
    get_project_source_evidence_run,
    list_project_source_evidence_resources,
    validate_source_evidence_for_generation,
)


@dataclass(frozen=True)
class FullPlanningSheetFactCell:
    """A single non-empty source cell inside a full planning sheet fact row."""

    row: int
    col: int
    coord: str
    column_name: str
    value: str


@dataclass(frozen=True)
class FullPlanningSheetFactRow:
    """A physical source row grouped from full selected planning sheet cells."""

    row_index: int
    source_unit_title: str
    evidence_status: str
    cells: list[FullPlanningSheetFactCell] = field(default_factory=list)


@dataclass(frozen=True)
class FullPlanningSheetVisualEvidence:
    """Safe adopted visual evidence summary scoped to the selected planning sheet."""

    id: int
    resource_id: int
    ref: str
    position: str
    summary: str
    visible_text: str
    confidence: float | None
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FullPlanningSheetContext:
    """Complete selected planning sheet context for a V3 full-generation run."""

    source_summary: str
    sheet_name: str
    columns: list[str] = field(default_factory=list)
    all_fact_rows: list[FullPlanningSheetFactRow] = field(default_factory=list)
    adopted_visual_evidence_summaries: list[FullPlanningSheetVisualEvidence] = field(
        default_factory=list
    )
    warnings: list[GenerationWarning] = field(default_factory=list)


async def build_full_planning_sheet_context(
    db: AsyncSession,
    *,
    project_id: int,
    source_evidence_run_id: int,
    planning_sheet_name: str,
) -> FullPlanningSheetContext:
    """Build full selected Planning Sheet context without snapshot or prompt budgets."""
    run = await get_project_source_evidence_run(
        db,
        project_id=project_id,
        run_id=source_evidence_run_id,
    )
    _ensure_full_context_run_ready(run)

    parsed = _load_parsed_source_for_context(
        project_id=project_id,
        run_id=run.id,
        source_type=run.source_type,
    )
    if parsed is None:
        raise SourceEvidenceError(409, "Source Evidence 详情已不可用，请重新读取来源。")

    sheet_name = _resolve_safe_context_sheet_name(
        parsed,
        planning_sheet_name,
        require_sheet_name_for_multi_sheet=True,
    )
    selected_sheet_unit = _find_sheet_unit(parsed, sheet_name) if sheet_name != "Source Evidence" else None
    resources = await list_project_source_evidence_resources(
        db,
        project_id=project_id,
        run_id=run.id,
    )
    scoped_resources = _safe_context_resources_for_sheet(
        resources,
        selected_unit=selected_sheet_unit,
        sheet_name=sheet_name,
    )
    base_warnings = _deduplicate_warnings(
        [
            *_manifest_warnings(run),
            *parsed.warnings,
        ]
    )
    adopted_ids, scope_warnings = await _selected_sheet_adopted_visual_ids(
        db,
        project_id=project_id,
        run=run,
        scoped_resources=scoped_resources,
    )
    visual_validate = await validate_source_evidence_for_generation(
        db,
        project_id=project_id,
        run=run,
        parsed=parsed,
        resources=resources,
        scoped_resources=scoped_resources,
        selected_sheet_unit=selected_sheet_unit,
        sheet_name=sheet_name,
        adopted_visual_evidence_ids=adopted_ids,
        existing_warnings=base_warnings,
    )
    fact_rows, columns = _build_fact_rows(
        selected_sheet_unit=selected_sheet_unit,
        parsed_title=parsed.title,
        markdown=parsed.markdown,
    )
    return FullPlanningSheetContext(
        source_summary=_source_summary(run, parsed),
        sheet_name=sheet_name,
        columns=columns,
        all_fact_rows=fact_rows,
        adopted_visual_evidence_summaries=[
            FullPlanningSheetVisualEvidence(
                id=item.id,
                resource_id=item.resource_id,
                ref=item.ref,
                position=item.position,
                summary=item.summary,
                visible_text=item.visible_text,
                confidence=item.confidence,
                limitations=item.limitations,
            )
            for item in visual_validate.adopted_evidence
        ],
        warnings=_deduplicate_warnings(
            [
                *base_warnings,
                *scope_warnings,
                *visual_validate.warnings,
            ]
        ),
    )


def _ensure_full_context_run_ready(run: SourceEvidenceRunRecord) -> None:
    _ensure_run_can_be_used(run)
    if run.status not in {"ready", "vision_pending"}:
        raise SourceEvidenceError(409, "Source Evidence Run 尚未 ready，不能构造 Full Planning Sheet Context。")


async def _selected_sheet_adopted_visual_ids(
    db: AsyncSession,
    *,
    project_id: int,
    run: SourceEvidenceRunRecord,
    scoped_resources: list[SourceEvidenceResourceRecord],
) -> tuple[list[int], list[GenerationWarning]]:
    scoped_resource_ids = {
        resource.id for resource in scoped_resources if resource.id is not None
    }
    result = await db.execute(
        select(SourceEvidenceVisualObservationRecord).where(
            SourceEvidenceVisualObservationRecord.project_id == project_id,
            SourceEvidenceVisualObservationRecord.run_id == run.id,
            SourceEvidenceVisualObservationRecord.status == "adopted",
        )
    )
    adopted_records = list(result.scalars().all())
    included_ids: list[int] = []
    excluded_count = 0
    for record in adopted_records:
        if record.resource_id in scoped_resource_ids:
            included_ids.append(record.id)
            continue
        excluded_count += 1

    warnings: list[GenerationWarning] = []
    if excluded_count:
        warnings.append(
            GenerationWarning(
                source="visual_validate",
                level="warning",
                message=f"{excluded_count} 个其他 Sheet 的已采纳视觉证据未进入 Full Planning Sheet Context。",
            )
        )
    return included_ids, warnings


def _build_fact_rows(
    *,
    selected_sheet_unit: ParsedSourceUnit | None,
    parsed_title: str,
    markdown: str,
) -> tuple[list[FullPlanningSheetFactRow], list[str]]:
    if selected_sheet_unit is not None:
        if selected_sheet_unit.cells:
            return _build_sheet_cell_fact_rows(selected_sheet_unit)
        if selected_sheet_unit.rows:
            return _build_structured_unit_fact_rows(selected_sheet_unit)
        return [], []
    return _build_text_fact_rows(parsed_title=parsed_title, markdown=markdown)


def _build_sheet_cell_fact_rows(
    unit: ParsedSourceUnit,
) -> tuple[list[FullPlanningSheetFactRow], list[str]]:
    cells_by_row: dict[int, list[ParsedSourceCell]] = defaultdict(list)
    for cell in unit.cells:
        text = str(cell.text or "").strip()
        if not text:
            continue
        cells_by_row[cell.row].append(cell)

    column_indexes = sorted({cell.col for cells in cells_by_row.values() for cell in cells})
    header_by_col = {
        cell.col: str(cell.text or "").strip()
        for cell in cells_by_row.get(1, [])
        if str(cell.text or "").strip()
    }
    column_name_by_col = {
        col: header_by_col.get(col) or f"Column {col}" for col in column_indexes
    }
    rows = [
        FullPlanningSheetFactRow(
            row_index=row_index,
            source_unit_title=unit.title,
            evidence_status="table",
            cells=[
                FullPlanningSheetFactCell(
                    row=cell.row,
                    col=cell.col,
                    coord=cell.coord,
                    column_name=column_name_by_col[cell.col],
                    value=str(cell.text or "").strip(),
                )
                for cell in sorted(cells, key=lambda item: item.col)
            ],
        )
        for row_index, cells in sorted(cells_by_row.items())
        if cells
    ]
    return rows, [column_name_by_col[col] for col in column_indexes]


def _build_structured_unit_fact_rows(
    unit: ParsedSourceUnit,
) -> tuple[list[FullPlanningSheetFactRow], list[str]]:
    rows: list[FullPlanningSheetFactRow] = []
    columns: list[str] = []
    for index, row in enumerate(unit.rows, start=1):
        fields = row.get("fields", row) if isinstance(row, dict) else row
        if not isinstance(fields, dict):
            value = _safe_json_text(fields)
            if not value:
                continue
            columns = columns or ["Content"]
            rows.append(
                FullPlanningSheetFactRow(
                    row_index=index,
                    source_unit_title=unit.title,
                    evidence_status="table",
                    cells=[
                        FullPlanningSheetFactCell(
                            row=index,
                            col=1,
                            coord=str(row.get("record_id") or index) if isinstance(row, dict) else str(index),
                            column_name="Content",
                            value=value,
                        )
                    ],
                )
            )
            continue
        row_cells = []
        for col, (key, value) in enumerate(fields.items(), start=1):
            text = _safe_json_text(value)
            if not text:
                continue
            column_name = str(key)
            if column_name not in columns:
                columns.append(column_name)
            row_cells.append(
                FullPlanningSheetFactCell(
                    row=index,
                    col=col,
                    coord=f"{index}:{column_name}",
                    column_name=column_name,
                    value=text,
                )
            )
        if row_cells:
            rows.append(
                FullPlanningSheetFactRow(
                    row_index=index,
                    source_unit_title=unit.title,
                    evidence_status="table",
                    cells=row_cells,
                )
            )
    return rows, columns


def _build_text_fact_rows(
    *,
    parsed_title: str,
    markdown: str,
) -> tuple[list[FullPlanningSheetFactRow], list[str]]:
    rows = [
        FullPlanningSheetFactRow(
            row_index=index,
            source_unit_title=parsed_title,
            evidence_status="text",
            cells=[
                FullPlanningSheetFactCell(
                    row=index,
                    col=1,
                    coord=f"L{index}",
                    column_name="Content",
                    value=line,
                )
            ],
        )
        for index, line in enumerate(_iter_text_lines(markdown), start=1)
    ]
    return rows, ["Content"] if rows else []


def _iter_text_lines(markdown: str) -> list[str]:
    lines: list[str] = []
    for raw_line in str(markdown or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# Source:") or line.startswith("URL:") or line.startswith("Type:"):
            continue
        if "<image " in line or "<attachment " in line:
            continue
        lines.append(line)
    return lines


def _safe_json_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)
