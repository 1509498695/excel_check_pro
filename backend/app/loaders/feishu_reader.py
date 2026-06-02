"""飞书数据源读取占位实现。"""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import pandas as pd

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from backend.app.api.schemas import DataSource, VariableTag


@dataclass(frozen=True)
class FeishuSheetLocator:
    """飞书电子表格定位信息。"""

    spreadsheet_token: str
    sheet_id: str | None
    normalized_url: str
    url_type: str = "sheet"


class FeishuSheetError(RuntimeError):
    """飞书电子表格 URL 解析错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return self.message


_SUPPORTED_DOMAINS = ("feishu.cn", "larksuite.com")
_UNSUPPORTED_PATH_MARKERS = ("/base/", "/docx/", "/docs/")
_EMPTY_URL_MESSAGE = "请输入飞书电子表格 URL"
_INVALID_URL_MESSAGE = "请输入合法的飞书电子表格链接"
_UNSUPPORTED_URL_MESSAGE = "第一版仅支持飞书电子表格链接，不支持多维表格或文档表格链接"
_TOKEN_PARSE_MESSAGE = "无法从链接中解析电子表格 token"
_FEISHU_PERMISSION_MESSAGE = "机器人暂无该表格权限，请发送授权请求到群。"


def parse_feishu_sheet_url(url: str) -> FeishuSheetLocator:
    """解析飞书电子表格 URL，返回表格 token、sheet id 与规范化链接。"""
    raw_url = (url or "").strip()
    if not raw_url:
        raise FeishuSheetError("empty_url", _EMPTY_URL_MESSAGE)

    parsed = urlparse(raw_url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise FeishuSheetError("invalid_url", _INVALID_URL_MESSAGE)

    host = (parsed.hostname or "").lower()
    if not any(
        host == domain or host.endswith(f".{domain}")
        for domain in _SUPPORTED_DOMAINS
    ):
        raise FeishuSheetError("invalid_url", _INVALID_URL_MESSAGE)

    normalized_path = _normalize_path(parsed.path)
    if _contains_unsupported_path(normalized_path):
        raise FeishuSheetError("unsupported_url", _UNSUPPORTED_URL_MESSAGE)

    path_segments = [segment for segment in normalized_path.split("/") if segment]
    if not path_segments or path_segments[0] not in {"sheets", "wiki"}:
        raise FeishuSheetError("invalid_url", _INVALID_URL_MESSAGE)

    spreadsheet_token = path_segments[1].strip() if len(path_segments) > 1 else ""
    if not spreadsheet_token:
        raise FeishuSheetError("token_parse_failed", _TOKEN_PARSE_MESSAGE)

    sheet_id = _extract_sheet_id(parsed.query)
    url_type = path_segments[0]
    normalized_url = (
        _build_normalized_url(
            host=host,
            spreadsheet_token=spreadsheet_token,
            sheet_id=sheet_id,
        )
        if url_type == "sheets"
        else _build_normalized_wiki_url(
            host=host,
            wiki_token=spreadsheet_token,
            sheet_id=sheet_id,
        )
    )
    return FeishuSheetLocator(
        spreadsheet_token=spreadsheet_token,
        sheet_id=sheet_id,
        normalized_url=normalized_url,
        url_type="sheet" if url_type == "sheets" else "wiki",
    )


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    return path if path.startswith("/") else f"/{path}"


def _contains_unsupported_path(path: str) -> bool:
    path_with_slashes = path if path.endswith("/") else f"{path}/"
    return any(marker in path_with_slashes for marker in _UNSUPPORTED_PATH_MARKERS)


def _extract_sheet_id(query: str) -> str | None:
    values = parse_qs(query, keep_blank_values=True).get("sheet") or []
    if not values:
        return None
    sheet_id = values[0].strip()
    return sheet_id or None


def _build_normalized_url(
    *,
    host: str,
    spreadsheet_token: str,
    sheet_id: str | None,
) -> str:
    query = urlencode({"sheet": sheet_id}) if sheet_id else ""
    return urlunparse(("https", host, f"/sheets/{spreadsheet_token}", "", query, ""))


def _build_normalized_wiki_url(
    *,
    host: str,
    wiki_token: str,
    sheet_id: str | None,
) -> str:
    query = urlencode({"sheet": sheet_id}) if sheet_id else ""
    return urlunparse(("https", host, f"/wiki/{wiki_token}", "", query, ""))


async def read_feishu_source_metadata(
    source: DataSource,
    *,
    db: AsyncSession,
    project_id: int,
) -> dict[str, Any]:
    """读取飞书电子表格 Sheet 与列结构，用于变量池下拉构建。"""
    from backend.app.integrations.feishu_client import (
        FEISHU_INVALID_URL,
        FeishuClientError,
        list_spreadsheet_sheets,
        read_sheet_header_columns,
        resolve_wiki_sheet_locator,
    )

    raw_url = source.pathOrUrl or source.url or source.path or ""
    try:
        locator = parse_feishu_sheet_url(raw_url)
    except FeishuSheetError as exc:
        raise FeishuClientError(FEISHU_INVALID_URL, str(exc)) from exc

    locator = await resolve_wiki_sheet_locator(db, project_id, locator)
    sheets = await list_spreadsheet_sheets(db, project_id, locator)
    metadata_sheets: list[dict[str, Any]] = []
    for sheet in sheets:
        columns = await read_sheet_header_columns(
            db,
            project_id,
            locator,
            sheet=sheet,
        )
        metadata_sheets.append(
            {
                "name": sheet.title,
                "sheet_id": sheet.sheet_id,
                "columns": columns,
            }
        )

    return {
        "source_id": source.id,
        "source_type": source.type,
        "sheets": metadata_sheets,
        "authorization_status": "authorized",
    }


async def preview_feishu_source_column(
    source: DataSource,
    *,
    sheet_name: str,
    column_name: str,
    limit: int | None = None,
    db: AsyncSession,
    project_id: int,
) -> dict[str, Any]:
    """返回飞书电子表格指定列预览，结构对齐 Excel/SVN 预览接口。"""
    from backend.app.integrations.feishu_client import read_sheet_values

    if not sheet_name.strip():
        raise ValueError("变量详情预览缺少 Sheet 名称。")
    if not column_name.strip():
        raise ValueError("变量详情预览缺少列名。")

    locator = _parse_source_locator(source)
    selected_sheet = await _resolve_feishu_sheet(
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
    resolved_column_name, column_index = _resolve_feishu_column(
        column_name,
        table.columns,
    )
    data_rows = table.raw_values[1:] if table.raw_values else []
    indexed_data_rows = _filter_feishu_rows_with_non_empty_column(
        data_rows,
        column_index=column_index,
    )
    total_rows = len(data_rows)
    preview_limit = max(1, limit) if limit is not None else total_rows
    preview_rows = [
        {
            "row_index": row_number,
            "value": _normalize_feishu_preview_value(
                row[column_index] if column_index < len(row) else None
            ),
        }
        for row_number, row in _iter_feishu_preview_rows(
            indexed_data_rows,
            limit=limit,
        )
    ]

    return {
        "variable_kind": "single",
        "source_id": source.id,
        "source_type": source.type,
        "sheet": selected_sheet.title,
        "column": resolved_column_name,
        "preview_rows": preview_rows,
        "total_rows": total_rows,
        "loaded_rows": len(preview_rows),
        "loaded_all_rows": len(preview_rows) == total_rows,
        "preview_limit": preview_limit,
    }


async def preview_feishu_composite_variable(
    source: DataSource,
    *,
    sheet_name: str,
    columns: list[str],
    key_column: str,
    append_index_to_key: bool = False,
    db: AsyncSession,
    project_id: int,
) -> dict[str, Any]:
    """返回飞书电子表格组合变量预览，结构对齐 Excel/SVN 预览接口。"""
    from backend.app.integrations.feishu_client import read_sheet_values

    preview_columns = [column for column in columns if column and column.strip()]
    preview_columns = _unique_preserve_order(preview_columns)

    if not sheet_name.strip():
        raise ValueError("组合变量预览缺少 Sheet 名称。")
    if len(preview_columns) < 2:
        raise ValueError("组合变量至少需要选择 2 列。")
    if not key_column.strip():
        raise ValueError("组合变量缺少 key 列。")
    if key_column not in preview_columns:
        raise ValueError("主键列必须包含在组合列中。")

    locator = _parse_source_locator(source)
    selected_sheet = await _resolve_feishu_sheet(
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
    resolved_preview_columns = _resolve_feishu_columns(
        preview_columns,
        table.columns,
    )
    resolved_key_column, key_column_index = _resolve_feishu_column(
        key_column,
        table.columns,
    )
    if resolved_key_column not in resolved_preview_columns:
        raise ValueError("主键列必须包含在组合列中。")

    column_indexes = {
        column: table.columns.index(column)
        for column in resolved_preview_columns
    }
    data_rows = table.raw_values[1:] if table.raw_values else []
    duplicate_keys_preview = _find_duplicate_feishu_composite_keys(
        data_rows,
        key_column_index=key_column_index,
    )
    has_duplicate_keys = bool(duplicate_keys_preview)

    if has_duplicate_keys and not append_index_to_key:
        mapping: dict[str, dict[str, Any]] = {}
        loaded_rows = 0
    else:
        mapping, loaded_rows = _build_feishu_composite_mapping(
            data_rows,
            columns=resolved_preview_columns,
            column_indexes=column_indexes,
            key_column=resolved_key_column,
            key_column_index=key_column_index,
            append_index_to_key=append_index_to_key,
        )

    return {
        "variable_kind": "composite",
        "source_id": source.id,
        "source_type": source.type,
        "sheet": selected_sheet.title,
        "columns": resolved_preview_columns,
        "key_column": resolved_key_column,
        "has_duplicate_keys": has_duplicate_keys,
        "duplicate_keys_preview": duplicate_keys_preview,
        "mapping": mapping,
        "total_rows": len(data_rows),
        "loaded_rows": loaded_rows,
        "loaded_all_rows": loaded_rows == len(data_rows),
    }


def load_feishu_variables_by_source(
    source: DataSource,
    variables_for_source: list[VariableTag],
    *,
    project_id: int | None = None,
) -> dict[str, pd.DataFrame]:
    """同步加载飞书变量切片，供执行流水线调用。"""
    try:
        return _run_async_blocking(
            _load_feishu_variables_by_source_async(
                source,
                variables_for_source,
                project_id=project_id,
            )
        )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(_format_feishu_loader_error(source.id, exc)) from exc


async def _load_feishu_variables_by_source_async(
    source: DataSource,
    variables_for_source: list[VariableTag],
    *,
    project_id: int | None,
) -> dict[str, pd.DataFrame]:
    from backend.app.database import async_session_factory
    from backend.app.integrations.feishu_client import read_sheet_values

    if not variables_for_source:
        return {}
    if project_id is None:
        raise ValueError(
            _format_feishu_loader_error(
                source.id,
                "项目上下文不可用，无法读取飞书应用配置。",
            )
        )

    locator = _parse_source_locator(source)
    variables_by_sheet: dict[str, list[VariableTag]] = defaultdict(list)
    for variable in variables_for_source:
        if not variable.sheet.strip():
            raise ValueError(
                _format_feishu_loader_error(
                    source.id,
                    f"变量 '{variable.tag}' 缺少 Sheet。",
                )
            )
        variables_by_sheet[variable.sheet].append(variable)

    loaded_variables: dict[str, pd.DataFrame] = {}
    async with async_session_factory() as db:
        for requested_sheet_name, sheet_variables in variables_by_sheet.items():
            try:
                selected_sheet = await _resolve_feishu_sheet(
                    db=db,
                    project_id=project_id,
                    locator=locator,
                    requested_sheet=requested_sheet_name,
                )
                table = await read_sheet_values(
                    db,
                    project_id,
                    locator,
                    sheet_id=selected_sheet.sheet_id,
                )
                dataframe = _build_feishu_dataframe(table.columns, table.raw_values)
                _merge_feishu_loaded_variables(
                    loaded_variables,
                    dataframe=dataframe,
                    variables_for_group=sheet_variables,
                    source_id=source.id,
                    group_label=f"Sheet '{selected_sheet.title}'",
                )
            except Exception as exc:
                raise ValueError(_format_feishu_loader_error(source.id, exc)) from exc

    return loaded_variables


def _run_async_blocking(coro):
    """在同步流水线中运行 async 飞书客户端。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - 透传线程内异常
            result["error"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _build_feishu_dataframe(
    columns: list[str],
    raw_values: list[list[Any]],
) -> pd.DataFrame:
    data_rows = raw_values[1:] if raw_values else []
    normalized_rows = [
        {
            column: _normalize_feishu_preview_value(
                row[index] if index < len(row) else None
            )
            for index, column in enumerate(columns)
        }
        for row in data_rows
    ]
    dataframe = pd.DataFrame(normalized_rows, columns=columns, dtype=object)
    return dataframe.where(pd.notna(dataframe), None)


def _filter_feishu_rows_with_non_empty_column(
    data_rows: list[list[Any]],
    *,
    column_index: int,
) -> list[tuple[int, list[Any]]]:
    return [
        (index + 2, row)
        for index, row in enumerate(data_rows)
        if not _is_empty_feishu_preview_value(
            _normalize_feishu_preview_value(_get_feishu_row_value(row, column_index))
        )
    ]


def _merge_feishu_loaded_variables(
    target: dict[str, pd.DataFrame],
    *,
    dataframe: pd.DataFrame,
    variables_for_group: list[VariableTag],
    source_id: str,
    group_label: str,
) -> None:
    for variable in variables_for_group:
        if variable.tag in target:
            raise ValueError(f"变量标签重复：{variable.tag}")

        if _get_variable_kind(variable) == "composite":
            columns = [
                column
                for column in (variable.columns or [])
                if column and column.strip()
            ]
            key_column = variable.key_column or ""
            if len(columns) < 2:
                raise ValueError(f"组合变量 '{variable.tag}' 至少需要选择 2 列。")
            if not key_column.strip():
                raise ValueError(f"组合变量 '{variable.tag}' 缺少 key 列。")
            if key_column not in columns:
                raise ValueError("主键列必须包含在组合列中。")

            resolved_columns = _resolve_feishu_columns(
                columns,
                [str(column) for column in dataframe.columns.tolist()],
            )
            resolved_key_column, _key_index = _resolve_feishu_column(
                key_column,
                [str(column) for column in dataframe.columns.tolist()],
            )
            if resolved_key_column not in resolved_columns:
                raise ValueError("主键列必须包含在组合列中。")

            target[variable.tag] = _build_feishu_composite_variable_frame(
                dataframe,
                columns=resolved_columns,
                key_column=resolved_key_column,
                append_index_to_key=variable.append_index_to_key,
            )
            continue

        column_name = variable.column or ""
        resolved_column_name, _index = _resolve_feishu_column(
            column_name,
            [str(column) for column in dataframe.columns.tolist()],
        )
        target[variable.tag] = _build_feishu_variable_frame(
            dataframe,
            resolved_column_name,
        )


def _get_variable_kind(variable: VariableTag) -> str:
    return variable.variable_kind or "single"


def _build_feishu_variable_frame(
    dataframe: pd.DataFrame,
    column_name: str,
) -> pd.DataFrame:
    variable_frame = dataframe[[column_name]].copy()
    variable_frame["_row_index"] = variable_frame.index + 2
    return variable_frame


def _build_feishu_composite_variable_frame(
    dataframe: pd.DataFrame,
    *,
    columns: list[str],
    key_column: str,
    append_index_to_key: bool,
) -> pd.DataFrame:
    frame = dataframe[columns].copy()
    frame["__key__"] = _build_feishu_runtime_keys(
        frame[key_column],
        append_index_to_key=append_index_to_key,
    )
    frame = frame.loc[frame["__key__"].notna()].copy()
    frame["_row_index"] = frame.index + 2
    ordered_columns = _unique_preserve_order(["__key__", *columns, "_row_index"])
    return frame[ordered_columns].reset_index(drop=True)


def _build_feishu_runtime_keys(
    source_series: pd.Series,
    *,
    append_index_to_key: bool,
) -> pd.Series:
    runtime_keys: list[str | None] = []
    for row_position, value in enumerate(source_series.tolist()):
        normalized_value = _normalize_feishu_preview_value(value)
        if _is_empty_feishu_preview_value(normalized_value):
            runtime_keys.append(None)
            continue

        key = str(normalized_value)
        runtime_keys.append(f"{key}_{row_position}" if append_index_to_key else key)
    return pd.Series(runtime_keys, index=source_series.index, dtype=object)


def _format_feishu_loader_error(source_id: str, error: object) -> str:
    from backend.app.integrations.feishu_client import (
        FEISHU_DOCUMENT_PERMISSION_DENIED,
        FeishuClientError,
    )

    if isinstance(error, FeishuClientError):
        message = (
            _FEISHU_PERMISSION_MESSAGE
            if error.code == FEISHU_DOCUMENT_PERMISSION_DENIED
            else error.message
        )
    else:
        message = str(error)
    return f"读取飞书数据源 '{source_id}' 失败：{message}"


def _parse_source_locator(source: DataSource) -> FeishuSheetLocator:
    from backend.app.integrations.feishu_client import (
        FEISHU_INVALID_URL,
        FeishuClientError,
    )

    raw_url = source.pathOrUrl or source.url or source.path or ""
    try:
        return parse_feishu_sheet_url(raw_url)
    except FeishuSheetError as exc:
        raise FeishuClientError(FEISHU_INVALID_URL, str(exc)) from exc


async def _resolve_feishu_sheet(
    *,
    db: AsyncSession,
    project_id: int,
    locator: FeishuSheetLocator,
    requested_sheet: str,
):
    from backend.app.integrations.feishu_client import list_spreadsheet_sheets

    requested_value = requested_sheet.strip()
    sheets = await list_spreadsheet_sheets(db, project_id, locator)
    for sheet in sheets:
        if sheet.title == requested_sheet or sheet.sheet_id == requested_sheet:
            return sheet

    trimmed_matches = [
        sheet
        for sheet in sheets
        if sheet.title.strip() == requested_value or sheet.sheet_id.strip() == requested_value
    ]
    if len(trimmed_matches) == 1:
        return trimmed_matches[0]

    raise ValueError(f"未找到指定 Sheet：{requested_sheet}")


def _resolve_feishu_column(
    requested_column: str,
    available_columns: list[str],
) -> tuple[str, int]:
    if requested_column in available_columns:
        return requested_column, available_columns.index(requested_column)

    normalized_requested = requested_column.strip()
    matches = [
        (index, column)
        for index, column in enumerate(available_columns)
        if column.strip() == normalized_requested
    ]
    if len(matches) == 1:
        index, column = matches[0]
        return column, index

    raise ValueError(f"未找到指定列：{requested_column}")


def _resolve_feishu_columns(
    requested_columns: list[str],
    available_columns: list[str],
) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for column in requested_columns:
        resolved_column, _index = _resolve_feishu_column(column, available_columns)
        if resolved_column in seen:
            continue
        resolved.append(resolved_column)
        seen.add(resolved_column)
    return resolved


def _iter_feishu_preview_rows(
    data_rows: list[tuple[int, list[Any]]],
    *,
    limit: int | None,
) -> list[tuple[int, list[Any]]]:
    preview_count = max(1, limit) if limit is not None else len(data_rows)
    return data_rows[:preview_count]


def _normalize_feishu_preview_value(value: Any) -> Any:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if value == "":
        return None
    return value


def _is_empty_feishu_preview_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _get_feishu_row_value(row: list[Any], column_index: int) -> Any:
    return row[column_index] if column_index < len(row) else None


def _find_duplicate_feishu_composite_keys(
    data_rows: list[list[Any]],
    *,
    key_column_index: int,
) -> list[str]:
    seen_values: set[str] = set()
    duplicate_values: list[str] = []
    for row in data_rows:
        value = _normalize_feishu_preview_value(
            _get_feishu_row_value(row, key_column_index)
        )
        if _is_empty_feishu_preview_value(value):
            continue

        key = str(value)
        if key in seen_values and key not in duplicate_values:
            duplicate_values.append(key)
            continue
        seen_values.add(key)
    return duplicate_values[:5]


def _build_feishu_composite_mapping(
    data_rows: list[list[Any]],
    *,
    columns: list[str],
    column_indexes: dict[str, int],
    key_column: str,
    key_column_index: int,
    append_index_to_key: bool,
) -> tuple[dict[str, dict[str, Any]], int]:
    mapping: dict[str, dict[str, Any]] = {}
    loaded_rows = 0

    for row_position, row in enumerate(data_rows):
        key_value = _normalize_feishu_preview_value(
            _get_feishu_row_value(row, key_column_index)
        )
        if _is_empty_feishu_preview_value(key_value):
            continue

        key = str(key_value)
        runtime_key = f"{key}_{row_position}" if append_index_to_key else key
        if runtime_key in mapping:
            raise ValueError(
                f"组合变量的 key 列 '{key_column}' 存在重复值 '{runtime_key}'，无法生成唯一映射。"
            )

        mapping[runtime_key] = {
            column: _normalize_feishu_preview_value(
                _get_feishu_row_value(row, column_indexes[column])
            )
            for column in columns
            if column != key_column
        }
        loaded_rows += 1

    return mapping, loaded_rows


def _unique_preserve_order(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def read_feishu_sheet(*args: object, **kwargs: object) -> None:
    """预留飞书 Open API 读取入口，当前尚未实现。"""
    raise NotImplementedError("Feishu loading is not implemented yet.")
