"""用例生成 V1 策划案快照读取。"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.schemas import DataSource
from backend.app.integrations.feishu_client import read_sheet_values
from backend.app.loaders import feishu_reader
from backend.app.loaders.local_reader import (
    _open_excel_workbook,
    _resolve_identifier_from_available,
    _resolve_source_path,
)
from backend.app.test_cases.schemas import (
    GenerationWarning,
    PlanningSnapshotCell,
    PlanningSnapshotRequest,
    PlanningSnapshotResponse,
    PlanningSnapshotRow,
)


IMAGE_ATTACHMENT_UNREAD_WARNING = (
    "V1 仅读取单元格文本，未读取图片、附件、批注或评论语义。"
)


async def build_planning_snapshot(
    payload: PlanningSnapshotRequest,
    *,
    db: AsyncSession,
    project_id: int,
) -> PlanningSnapshotResponse:
    """按来源类型读取一个 Planning Sheet，并生成受控快照。"""
    if payload.source_type == "uploaded_excel":
        source_summary, sheet_name, raw_values = read_uploaded_excel_planning_values(
            payload.source,
            sheet_name=payload.sheet_name,
        )
        return build_snapshot_from_values(
            raw_values,
            source_summary=source_summary,
            sheet_name=sheet_name,
            limits=payload.limits,
        )

    if payload.source_type == "feishu":
        source_summary, sheet_name, raw_values = await read_feishu_planning_values(
            db=db,
            project_id=project_id,
            source=payload.source,
            sheet_name=payload.sheet_name,
        )
        return build_snapshot_from_values(
            raw_values,
            source_summary=source_summary,
            sheet_name=sheet_name,
            limits=payload.limits,
        )

    raise ValueError(f"暂不支持的策划案来源类型：{payload.source_type}")


def read_uploaded_excel_planning_values(
    source: DataSource,
    *,
    sheet_name: str,
) -> tuple[str, str, list[list[Any]]]:
    """读取浏览器上传 Excel 对应的单个 Sheet。"""
    if source.type != "local_excel":
        raise ValueError("上传策划案快照仅支持 local_excel 数据源。")

    source_path = _resolve_source_path(source)
    workbook = _open_excel_workbook(source_path, source.id)
    resolved_sheet_name = _resolve_identifier_from_available(
        sheet_name,
        [str(name) for name in workbook.sheet_names],
        identifier_label="Sheet",
        context=f"策划案 Excel '{source.id}'",
    )
    try:
        dataframe = workbook.parse(
            sheet_name=resolved_sheet_name,
            header=None,
            dtype=object,
        )
    except ValueError as exc:
        raise ValueError(
            f"读取策划案 Excel '{source.id}' 的 Sheet '{resolved_sheet_name}' 失败：{exc}"
        ) from exc

    return (
        f"上传 Excel：{source_path.name}",
        resolved_sheet_name,
        _dataframe_to_raw_values(dataframe),
    )


async def read_feishu_planning_values(
    *,
    db: AsyncSession,
    project_id: int,
    source: DataSource,
    sheet_name: str,
) -> tuple[str, str, list[list[Any]]]:
    """读取飞书电子表格单个 Sheet；测试可 monkeypatch 该适配函数。"""
    if source.type != "feishu":
        raise ValueError("飞书策划案快照仅支持 feishu 数据源。")

    locator = feishu_reader._parse_source_locator(source)
    selected_sheet = await feishu_reader._resolve_feishu_sheet(
        db=db,
        project_id=project_id,
        locator=locator,
        requested_sheet=sheet_name,
    )
    table = await read_sheet_values(
        db,
        project_id,
        locator,
        sheet_id=selected_sheet.sheet_id,
    )
    source_summary = f"飞书电子表格：{source.id}"
    return source_summary, table.sheet_title, table.raw_values


def build_snapshot_from_values(
    raw_values: list[list[Any]],
    *,
    source_summary: str,
    sheet_name: str,
    limits,
) -> PlanningSnapshotResponse:
    """将二维表值转换为预算内快照，并把所有截断显式写入 warnings。"""
    warnings: list[GenerationWarning] = [
        GenerationWarning(
            source="snapshot",
            level="warning",
            message=IMAGE_ATTACHMENT_UNREAD_WARNING,
        )
    ]
    limit_truncated = False

    total_rows = len(raw_values)
    total_columns = max((len(row) for row in raw_values), default=0)
    if total_rows == 0 or total_columns == 0:
        warnings.append(
            GenerationWarning(
                source="snapshot",
                level="warning",
                message=f"所选 Sheet“{sheet_name}”为空。",
            )
        )
        return PlanningSnapshotResponse(
            source_summary=source_summary,
            sheet_name=sheet_name,
            rows=[],
            columns=[],
            non_empty_cell_count=0,
            truncated=False,
            warnings=warnings,
        )

    selected_row_count = min(total_rows, limits.max_rows)
    selected_column_count = min(total_columns, limits.max_columns)
    if total_rows > limits.max_rows:
        limit_truncated = True
        warnings.append(
            GenerationWarning(
                source="snapshot",
                level="warning",
                message=f"读取 {total_rows} 行，纳入前 {limits.max_rows} 行。",
            )
        )
    if total_columns > limits.max_columns:
        limit_truncated = True
        warnings.append(
            GenerationWarning(
                source="snapshot",
                level="warning",
                message=f"读取 {total_columns} 列，纳入前 {limits.max_columns} 列。",
            )
        )

    candidate_matrix = _slice_values(
        raw_values,
        row_count=selected_row_count,
        column_count=selected_column_count,
    )
    candidate_non_empty_count = sum(
        1
        for row in candidate_matrix
        for value in row
        if not _is_empty_text(_normalize_snapshot_text(value))
    )
    if candidate_non_empty_count > limits.max_non_empty_cells:
        limit_truncated = True
        warnings.append(
            GenerationWarning(
                source="snapshot",
                level="warning",
                message=(
                    f"读取 {candidate_non_empty_count} 个非空单元格，"
                    f"纳入前 {limits.max_non_empty_cells} 个。"
                ),
            )
        )

    rows: list[PlanningSnapshotRow] = []
    included_non_empty_count = 0
    total_chars = 0
    cell_text_truncated_count = 0
    total_char_truncated = False
    columns = _derive_columns(candidate_matrix, limits.max_cell_chars)

    for row_offset, raw_row in enumerate(candidate_matrix, start=1):
        cells: list[PlanningSnapshotCell] = []
        for column_offset, raw_value in enumerate(raw_row, start=1):
            text = _normalize_snapshot_text(raw_value)
            cell_truncated = False
            if _is_empty_text(text):
                cells.append(
                    PlanningSnapshotCell(
                        row_index=row_offset,
                        column_index=column_offset,
                        column_name=columns[column_offset - 1],
                        value="",
                    )
                )
                continue

            if included_non_empty_count >= limits.max_non_empty_cells:
                limit_truncated = True
                continue
            included_non_empty_count += 1

            if len(text) > limits.max_cell_chars:
                text = text[: limits.max_cell_chars]
                cell_truncated = True
                cell_text_truncated_count += 1
                limit_truncated = True

            remaining_chars = limits.max_chars - total_chars
            if remaining_chars <= 0:
                total_char_truncated = True
                limit_truncated = True
                continue
            if len(text) > remaining_chars:
                text = text[:remaining_chars]
                cell_truncated = True
                total_char_truncated = True
                limit_truncated = True
            total_chars += len(text)

            cells.append(
                PlanningSnapshotCell(
                    row_index=row_offset,
                    column_index=column_offset,
                    column_name=columns[column_offset - 1],
                    value=text,
                    truncated=cell_truncated,
                )
            )
        rows.append(PlanningSnapshotRow(row_index=row_offset, cells=cells))

    if cell_text_truncated_count:
        warnings.append(
            GenerationWarning(
                source="snapshot",
                level="warning",
                message=(
                    f"{cell_text_truncated_count} 个超长单元格已截断到 "
                    f"{limits.max_cell_chars} 字符。"
                ),
            )
        )
    if total_char_truncated:
        warnings.append(
            GenerationWarning(
                source="snapshot",
                level="warning",
                message=(
                    f"快照内容超过 {limits.max_chars} 个总字符，"
                    "超出部分未纳入 AI 输入。"
                ),
            )
        )

    return PlanningSnapshotResponse(
        source_summary=source_summary,
        sheet_name=sheet_name,
        rows=rows,
        columns=columns,
        non_empty_cell_count=included_non_empty_count,
        truncated=limit_truncated,
        warnings=warnings,
    )


def _dataframe_to_raw_values(dataframe: pd.DataFrame) -> list[list[Any]]:
    if dataframe.empty and len(dataframe.columns) == 0:
        return []
    return dataframe.where(pd.notna(dataframe), None).values.tolist()


def _slice_values(
    raw_values: list[list[Any]],
    *,
    row_count: int,
    column_count: int,
) -> list[list[Any]]:
    matrix: list[list[Any]] = []
    for row in raw_values[:row_count]:
        matrix.append(
            [row[index] if index < len(row) else None for index in range(column_count)]
        )
    return matrix


def _derive_columns(matrix: list[list[Any]], max_cell_chars: int) -> list[str]:
    if not matrix:
        return []
    columns: list[str] = []
    first_row = matrix[0]
    for index, raw_value in enumerate(first_row, start=1):
        name = _normalize_snapshot_text(raw_value).strip()
        if not name:
            name = f"Column {index}"
        columns.append(name[:max_cell_chars])
    return columns


def _normalize_snapshot_text(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "" if value is None else str(value)


def _is_empty_text(value: str) -> bool:
    return not value.strip()
