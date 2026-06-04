"""本地 Excel 数据读取工具。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any, TypeVar

import pandas as pd

from backend.app.api.schemas import DataSource, VariableTag
from backend.config import settings


LOCAL_SOURCE_TYPES = {"local_excel"}
ItemT = TypeVar("ItemT")
LOCAL_FILE_DENIED_MESSAGE = (
    "本地 Excel 路径不在服务端允许读取的目录内。请使用上传文件、SVN/飞书数据源，"
    "或由管理员配置 LOCAL_FILE_ROOT_ALLOWLIST。"
)


class LocalFileAccessDeniedError(PermissionError):
    """本地文件路径未通过服务端 allowlist 校验。"""


def load_local_variables(
    sources: list[DataSource], variables: list[VariableTag]
) -> dict[str, pd.DataFrame]:
    """按变量标签聚合读取本地 Excel 数据切片。"""
    if not variables:
        return {}

    _ensure_unique_tags(variables)

    source_map = {source.id: source for source in sources}
    grouped_variables: dict[str, list[VariableTag]] = defaultdict(list)

    for variable in variables:
        source = source_map.get(variable.source_id)
        if source is None:
            raise ValueError(
                f"Variable tag '{variable.tag}' references unknown source_id "
                f"'{variable.source_id}'."
            )
        if source.type not in LOCAL_SOURCE_TYPES:
            continue
        grouped_variables[variable.source_id].append(variable)

    loaded_variables: dict[str, pd.DataFrame] = {}

    for source_id, variables_for_source in grouped_variables.items():
        source_frames = load_variables_by_source(source_map[source_id], variables_for_source)
        overlap_tags = set(loaded_variables).intersection(source_frames)
        if overlap_tags:
            raise ValueError(
                "Duplicate variable tags produced while loading source "
                f"'{source_id}': {sorted(overlap_tags)}."
            )
        loaded_variables.update(source_frames)

    return loaded_variables


def read_source_metadata(source: DataSource) -> dict[str, Any]:
    """读取 Excel 数据源的 Sheet 与列结构，用于变量池下拉构建。"""
    _ensure_metadata_supported(source)
    source_path = _resolve_source_path(source)

    try:
        workbook = pd.ExcelFile(
            source_path,
            engine=_get_excel_engine(source_path),
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Excel 数据源 '{source.id}' 文件不存在：'{source_path}'。"
        ) from exc
    except ImportError as exc:
        raise ImportError(_build_excel_dependency_error(source_path)) from exc
    except ValueError as exc:
        raise ValueError(f"读取 Excel 数据源 '{source.id}' 失败：{exc}") from exc

    sheets: list[dict[str, Any]] = []
    for sheet_name in workbook.sheet_names:
        try:
            sheet_frame = workbook.parse(sheet_name=sheet_name, nrows=0)
        except ValueError as exc:
            raise ValueError(
                f"读取 Excel 数据源 '{source.id}' 的 Sheet '{sheet_name}' 失败：{exc}"
            ) from exc

        sheets.append(
            {
                "name": sheet_name,
                "columns": [str(column) for column in sheet_frame.columns.tolist()],
            }
        )

    return {
        "source_id": source.id,
        "source_type": source.type,
        "sheets": sheets,
    }


def preview_source_column(
    source: DataSource,
    *,
    sheet_name: str,
    column_name: str,
    limit: int | None = None,
) -> dict[str, Any]:
    """返回指定列的预览数据，供变量详情弹窗展示。"""
    _ensure_metadata_supported(source)
    source_path = _resolve_source_path(source)

    if not sheet_name.strip():
        raise ValueError("变量详情预览缺少 Sheet 名称。")
    if not column_name.strip():
        raise ValueError("变量详情预览缺少列名。")

    try:
        workbook = _open_excel_workbook(source_path, source.id)
        resolved_sheet_name, available_columns = _resolve_excel_sheet_columns(
            workbook,
            source_id=source.id,
            requested_sheet_name=sheet_name,
        )
        resolved_column_name = _resolve_identifier_from_available(
            column_name,
            available_columns,
            identifier_label="列名",
            context=f"Excel 数据源 '{source.id}' 的 Sheet '{resolved_sheet_name}'",
        )
        dataframe = workbook.parse(
            sheet_name=resolved_sheet_name,
            usecols=[resolved_column_name],
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Excel 数据源 '{source.id}' 文件不存在：'{source_path}'。"
        ) from exc
    except ImportError as exc:
        raise ImportError(_build_excel_dependency_error(source_path)) from exc
    except ValueError as exc:
        raise ValueError(
            f"读取 Excel 数据源 '{source.id}' 的 Sheet '{sheet_name}' 列 "
            f"'{column_name}' 失败：{exc}"
        ) from exc

    total_rows = int(len(dataframe))
    preview_limit = max(1, limit) if limit is not None else total_rows
    preview_frame = dataframe if limit is None else dataframe.head(preview_limit)
    preview_rows = [
        {
            "row_index": int(row_index),
            "value": _normalize_preview_value(value),
        }
        for row_index, value in zip(
            preview_frame.index + 2,
            preview_frame[resolved_column_name].tolist(),
        )
    ]

    return {
        "variable_kind": "single",
        "source_id": source.id,
        "source_type": source.type,
        "source_path": str(source_path),
        "sheet": resolved_sheet_name,
        "column": resolved_column_name,
        "preview_rows": preview_rows,
        "total_rows": total_rows,
        "loaded_rows": len(preview_rows),
        "loaded_all_rows": len(preview_rows) == total_rows,
        "preview_limit": preview_limit,
    }


def preview_composite_variable(
    source: DataSource,
    *,
    sheet_name: str,
    columns: list[str],
    key_column: str,
    append_index_to_key: bool = False,
    page: int | None = None,
    size: int | None = None,
) -> dict[str, Any]:
    """返回同一数据源同一 Sheet 内多列组合后的 JSON 映射预览。"""
    _ensure_metadata_supported(source)
    source_path = _resolve_source_path(source)

    preview_columns = [column for column in columns if column and column.strip()]
    preview_columns = _unique_preserve_order(preview_columns)

    if not sheet_name.strip():
        raise ValueError("组合变量预览缺少 Sheet 名称。")
    if len(preview_columns) < 2:
        raise ValueError("组合变量至少需要选择 2 列。")
    if not key_column.strip():
        raise ValueError("组合变量缺少 key 列。")
    if key_column not in preview_columns:
        raise ValueError("组合变量的 key 列必须包含在关联列中。")

    try:
        workbook = _open_excel_workbook(source_path, source.id)
        resolved_sheet_name, available_columns = _resolve_excel_sheet_columns(
            workbook,
            source_id=source.id,
            requested_sheet_name=sheet_name,
        )
        resolved_preview_columns = _resolve_identifiers_from_available(
            preview_columns,
            available_columns,
            identifier_label="列名",
            context=f"Excel 数据源 '{source.id}' 的 Sheet '{resolved_sheet_name}'",
        )
        resolved_key_column = _resolve_identifier_from_available(
            key_column,
            available_columns,
            identifier_label="key 列",
            context=f"Excel 数据源 '{source.id}' 的 Sheet '{resolved_sheet_name}'",
        )
        key_dataframe = workbook.parse(
            sheet_name=resolved_sheet_name,
            usecols=[resolved_key_column],
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Excel 数据源 '{source.id}' 文件不存在：'{source_path}'。"
        ) from exc
    except ImportError as exc:
        raise ImportError(_build_excel_dependency_error(source_path)) from exc
    except ValueError as exc:
        raise ValueError(
            f"读取 Excel 数据源 '{source.id}' 的 Sheet '{sheet_name}' 组合列 "
            f"{preview_columns} 失败：{exc}"
        ) from exc

    if resolved_key_column not in resolved_preview_columns:
        raise ValueError("组合变量的 key 列必须包含在关联列中。")

    key_series = key_dataframe[resolved_key_column]
    total_rows = int(len(key_dataframe))
    total_keys = _count_non_empty_composite_keys(key_series)
    (
        resolved_page,
        page_size,
        total_pages,
        page_start,
        page_end,
        is_paginated,
    ) = _resolve_composite_preview_page(
        page=page,
        size=size,
        total_keys=total_keys,
    )
    duplicate_keys_preview = _find_duplicate_composite_keys(key_series)
    has_duplicate_keys = bool(duplicate_keys_preview)

    if has_duplicate_keys and not append_index_to_key:
        mapping: dict[str, dict[str, Any]] = {}
        loaded_rows = 0
    else:
        if is_paginated:
            page_row_indices = _select_composite_key_row_indices(
                key_series,
                start=page_start,
                end=page_end,
            )
            dataframe = _read_composite_preview_page(
                workbook,
                sheet_name=resolved_sheet_name,
                columns=resolved_preview_columns,
                row_indices=page_row_indices,
            )
        else:
            dataframe = workbook.parse(
                sheet_name=resolved_sheet_name,
                usecols=resolved_preview_columns,
            )
        mapping, loaded_rows = _build_composite_mapping(
            dataframe,
            columns=resolved_preview_columns,
            key_column=resolved_key_column,
            append_index_to_key=append_index_to_key,
        )

    return {
        "variable_kind": "composite",
        "source_id": source.id,
        "source_type": source.type,
        "source_path": str(source_path),
        "sheet": resolved_sheet_name,
        "columns": resolved_preview_columns,
        "key_column": resolved_key_column,
        "append_index_to_key": append_index_to_key,
        "has_duplicate_keys": has_duplicate_keys,
        "duplicate_keys_preview": duplicate_keys_preview,
        "mapping": mapping,
        "total_rows": total_rows,
        "total_keys": total_keys,
        "page": resolved_page,
        "page_size": page_size,
        "total_pages": total_pages,
        "loaded_rows": loaded_rows,
        "loaded_all_rows": loaded_rows == total_keys,
    }


def load_variables_by_source(
    source: DataSource, variables_for_source: list[VariableTag]
) -> dict[str, pd.DataFrame]:
    """按数据源类型分发到具体的本地读取实现。"""
    if source.type == "local_excel":
        return read_local_excel(source, variables_for_source)
    if source.type == "local_csv":
        raise ValueError("CSV 数据源已不再支持，请删除后改用 Excel 或 SVN Excel。")
    if source.type == "svn":
        # 远端 URL → 缓存文件 / 本地工作副本路径 → 按后缀分发到 Excel 读取。
        resolved_path = _resolve_source_path(source)
        suffix = resolved_path.suffix.lower()
        if suffix in {".xls", ".xlsx"}:
            return read_local_excel(source, variables_for_source)
        raise ValueError(
            f"SVN 数据源 '{source.id}' 文件后缀 '{suffix}' 暂不支持，仅支持 .xls / .xlsx。"
        )
    raise ValueError(
        f"Source '{source.id}' has unsupported local loader type '{source.type}'."
    )


def read_local_excel(
    source: DataSource, variables_for_source: list[VariableTag]
) -> dict[str, pd.DataFrame]:
    """读取 Excel 中指定 sheet 的指定列，并按 tag 返回结果。"""
    if not variables_for_source:
        return {}

    source_path = _resolve_source_path(source)
    variables_by_sheet: dict[str, list[VariableTag]] = defaultdict(list)

    for variable in variables_for_source:
        if not variable.sheet.strip():
            raise ValueError(
                f"Excel source '{source.id}' requires a non-empty sheet for "
                f"variable tag '{variable.tag}'."
            )
        variables_by_sheet[variable.sheet].append(variable)

    workbook = _open_excel_workbook(source_path, source.id)
    loaded_variables: dict[str, pd.DataFrame] = {}

    for requested_sheet_name, sheet_variables in variables_by_sheet.items():
        resolved_sheet_name, available_columns = _resolve_excel_sheet_columns(
            workbook,
            source_id=source.id,
            requested_sheet_name=requested_sheet_name,
        )
        requested_columns = _collect_requested_columns(sheet_variables)
        resolved_columns = _resolve_identifiers_from_available(
            requested_columns,
            available_columns,
            identifier_label="列名",
            context=f"Excel source '{source.id}' sheet '{resolved_sheet_name}'",
        )
        try:
            dataframe = workbook.parse(
                sheet_name=resolved_sheet_name,
                usecols=resolved_columns,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Excel source '{source.id}' file not found: '{source_path}'."
            ) from exc
        except ImportError as exc:
            raise ImportError(_build_excel_dependency_error(source_path)) from exc
        except ValueError as exc:
            raise ValueError(
                f"Failed to read Excel source '{source.id}', sheet '{resolved_sheet_name}', "
                f"columns {resolved_columns}: {exc}"
            ) from exc

        _merge_loaded_variables(
            loaded_variables,
            dataframe=dataframe,
            variables_for_group=sheet_variables,
            source_id=source.id,
            group_label=f"sheet '{resolved_sheet_name}'",
        )

    return loaded_variables


def _ensure_metadata_supported(source: DataSource) -> None:
    """放行 local_excel 与 svn（HTTP）数据源；其它类型仍拒绝元数据/预览。"""
    if source.type == "local_excel":
        return
    if source.type == "svn":
        return
    raise ValueError("变量池下拉提取目前仅支持 Excel 与 SVN（HTTP）数据源。")


def _ensure_excel_metadata_source(source: DataSource) -> None:
    """兼容旧调用名，保留一个薄封装。"""
    _ensure_metadata_supported(source)


def _open_excel_workbook(source_path: Path, source_id: str) -> pd.ExcelFile:
    """打开 Excel 工作簿并统一错误消息。"""
    try:
        return pd.ExcelFile(
            source_path,
            engine=_get_excel_engine(source_path),
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Excel 数据源 '{source_id}' 文件不存在：'{source_path}'。"
        ) from exc
    except ImportError as exc:
        raise ImportError(_build_excel_dependency_error(source_path)) from exc
    except ValueError as exc:
        raise ValueError(f"读取 Excel 数据源 '{source_id}' 失败：{exc}") from exc


def _resolve_excel_sheet_columns(
    workbook: pd.ExcelFile,
    *,
    source_id: str,
    requested_sheet_name: str,
) -> tuple[str, list[str]]:
    """解析真实 Sheet 名并返回该 Sheet 的原始列名列表。"""
    resolved_sheet_name = _resolve_identifier_from_available(
        requested_sheet_name,
        [str(sheet_name) for sheet_name in workbook.sheet_names],
        identifier_label="Sheet",
        context=f"Excel 数据源 '{source_id}'",
    )
    try:
        sheet_frame = workbook.parse(sheet_name=resolved_sheet_name, nrows=0)
    except ValueError as exc:
        raise ValueError(
            f"读取 Excel 数据源 '{source_id}' 的 Sheet '{resolved_sheet_name}' 失败：{exc}"
        ) from exc

    return resolved_sheet_name, [str(column) for column in sheet_frame.columns.tolist()]


def _ensure_unique_tags(variables: list[VariableTag]) -> None:
    """保证 tag 在整次请求中全局唯一。"""
    seen_tags: set[str] = set()
    duplicate_tags: set[str] = set()

    for variable in variables:
        if variable.tag in seen_tags:
            duplicate_tags.add(variable.tag)
        seen_tags.add(variable.tag)

    if duplicate_tags:
        raise ValueError(
            f"Duplicate variable tags are not allowed: {sorted(duplicate_tags)}."
        )


def _resolve_source_path(
    source: DataSource,
    *,
    user_scope: str | None = None,
    force_refresh: bool = False,
) -> Path:
    """解析数据源真实文件路径。

    - 本地 Excel 源：直接展开 path/pathOrUrl。
    - SVN 源：远端 URL 走 svn_cache 落到本地缓存文件；本地工作副本路径透传。
    """
    if source.type == "svn":
        # 延迟导入以避免与 svn_manager / svn_credentials 形成循环依赖。
        from backend.app.loaders.svn_cache import is_remote_svn_locator, prepare_remote_svn_source

        raw_locator = (source.pathOrUrl or source.path or source.url or "").strip()
        resolved_svn_path = prepare_remote_svn_source(
            source,
            user_scope=user_scope,
            force_refresh=force_refresh,
        )
        if not is_remote_svn_locator(raw_locator):
            _ensure_path_allowed(resolved_svn_path)
        return resolved_svn_path

    raw_path = source.path or source.pathOrUrl
    if not raw_path:
        raise ValueError(
            f"Local source '{source.id}' must provide 'path' or 'pathOrUrl'."
        )

    source_path = Path(raw_path).expanduser()
    resolved_path = _resolve_for_allowlist(source_path)
    _ensure_path_allowed(resolved_path)
    if not resolved_path.exists():
        raise FileNotFoundError(
            f"Local source '{source.id}' file not found: '{resolved_path}'."
        )
    if not resolved_path.is_file():
        raise ValueError(
            f"Local source '{source.id}' path is not a file: '{resolved_path}'."
        )
    return resolved_path


def _resolve_local_path(source: DataSource) -> Path:
    """兼容旧调用名，保留一个薄封装。"""
    return _resolve_source_path(source)


def effective_local_file_root_allowlist() -> tuple[Path, ...]:
    """返回显式本地白名单与系统托管缓存目录的合并结果。"""
    return tuple(
        _resolve_for_allowlist(path)
        for path in (
            *settings.local_file_root_allowlist,
            settings.runtime_upload_dir,
            settings.svn_cache_dir,
        )
    )


def is_path_in_local_file_allowlist(path: Path) -> bool:
    """判断路径是否位于服务端允许读取的本地根目录内。"""
    resolved_path = _resolve_for_allowlist(path)
    return any(
        resolved_path == allowed_root or _is_relative_to(resolved_path, allowed_root)
        for allowed_root in effective_local_file_root_allowlist()
    )


def ensure_directory_in_local_file_allowlist(path: Path) -> Path:
    """校验本地目录是否位于 allowlist 内，供目录校验接口复用。"""
    resolved_path = _resolve_for_allowlist(path)
    _ensure_path_allowed(resolved_path)
    return resolved_path


def _ensure_path_allowed(path: Path) -> None:
    if not is_path_in_local_file_allowlist(path):
        raise LocalFileAccessDeniedError(LOCAL_FILE_DENIED_MESSAGE)


def _resolve_for_allowlist(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _get_variable_kind(variable: VariableTag) -> str:
    """读取变量类型，兼容旧请求默认视为单个变量。"""
    return variable.variable_kind or "single"


def _collect_requested_columns(variables: list[VariableTag]) -> list[str]:
    """聚合一组变量真正依赖的列名。"""
    requested_columns: list[str] = []

    for variable in variables:
        if _get_variable_kind(variable) == "composite":
            columns = [
                column
                for column in (variable.columns or [])
                if column and column.strip()
            ]
            if len(columns) < 2:
                raise ValueError(
                    f"Composite variable '{variable.tag}' must provide at least two columns."
                )
            requested_columns.extend(columns)
            continue

        column_name = variable.column or ""
        if not column_name.strip():
            raise ValueError(f"Variable '{variable.tag}' is missing column.")
        requested_columns.append(column_name)

    return _unique_preserve_order(requested_columns)


def _resolve_identifier_from_available(
    requested_value: str,
    available_values: Iterable[str],
    *,
    identifier_label: str,
    context: str,
) -> str:
    """优先按原始值匹配，找不到时兼容 trim 后的唯一候选。"""
    available_list = [str(item) for item in available_values]
    if requested_value in available_list:
        return requested_value

    normalized_requested = requested_value.strip()
    if not normalized_requested:
        raise ValueError(f"{context} 缺少{identifier_label}。")

    matched_values = [
        candidate
        for candidate in available_list
        if candidate.strip() == normalized_requested
    ]
    if len(matched_values) == 1:
        return matched_values[0]
    if len(matched_values) > 1:
        raise ValueError(
            f"{context} 中的{identifier_label}“{requested_value}”在忽略首尾空白后匹配到多个候选：{matched_values}。"
        )

    raise ValueError(
        f"{context} 中未找到{identifier_label}“{requested_value}”。"
    )


def _resolve_identifiers_from_available(
    requested_values: Iterable[str],
    available_values: Iterable[str],
    *,
    identifier_label: str,
    context: str,
) -> list[str]:
    """批量解析真实标识符，并保持顺序去重。"""
    resolved_values: list[str] = []
    seen_values: set[str] = set()

    for requested_value in requested_values:
        resolved_value = _resolve_identifier_from_available(
            requested_value,
            available_values,
            identifier_label=identifier_label,
            context=context,
        )
        if resolved_value in seen_values:
            continue
        resolved_values.append(resolved_value)
        seen_values.add(resolved_value)

    return resolved_values


def _merge_loaded_variables(
    target: dict[str, pd.DataFrame],
    *,
    dataframe: pd.DataFrame,
    variables_for_group: list[VariableTag],
    source_id: str,
    group_label: str,
) -> None:
    """将批量读取结果拆成按 tag 索引的单变量或组合变量结果。"""
    for variable in variables_for_group:
        if variable.tag in target:
            raise ValueError(
                f"Duplicate variable tag '{variable.tag}' encountered while "
                f"loading source '{source_id}'."
            )

        if _get_variable_kind(variable) == "composite":
            columns = [column for column in (variable.columns or []) if column and column.strip()]
            key_column = variable.key_column or ""

            if len(columns) < 2:
                raise ValueError(
                    f"Composite variable '{variable.tag}' must provide at least two columns."
                )
            if not key_column.strip():
                raise ValueError(
                    f"Composite variable '{variable.tag}' must provide key_column."
                )
            resolved_columns = _resolve_identifiers_from_available(
                columns,
                [str(column) for column in dataframe.columns.tolist()],
                identifier_label="列名",
                context=f"Source '{source_id}' {group_label} for composite variable '{variable.tag}'",
            )
            resolved_key_column = _resolve_identifier_from_available(
                key_column,
                [str(column) for column in dataframe.columns.tolist()],
                identifier_label="key 列",
                context=f"Source '{source_id}' {group_label} for composite variable '{variable.tag}'",
            )
            if resolved_key_column not in resolved_columns:
                raise ValueError(
                    f"Composite variable '{variable.tag}' requires key_column '{key_column}' "
                    "to be included in columns."
                )

            target[variable.tag] = _build_composite_variable_frame(
                dataframe,
                columns=resolved_columns,
                key_column=resolved_key_column,
                append_index_to_key=variable.append_index_to_key,
            )
            continue

        column_name = variable.column or ""
        resolved_column_name = _resolve_identifier_from_available(
            column_name,
            [str(column) for column in dataframe.columns.tolist()],
            identifier_label="列名",
            context=f"Source '{source_id}' {group_label} for variable tag '{variable.tag}'",
        )
        target[variable.tag] = _build_variable_frame(dataframe, resolved_column_name)


def _build_variable_frame(dataframe: pd.DataFrame, column_name: str) -> pd.DataFrame:
    """返回单列 DataFrame，并统一附带真实表格行号。"""
    variable_frame = dataframe[[column_name]].copy()
    variable_frame["_row_index"] = variable_frame.index + 2
    return variable_frame


def _build_composite_variable_frame(
    dataframe: pd.DataFrame,
    *,
    columns: list[str],
    key_column: str,
    append_index_to_key: bool = False,
) -> pd.DataFrame:
    """把组合变量展开为可执行的行集，并注入内部 `__key__` 字段。"""
    frame = dataframe[columns].copy()
    frame["__key__"] = _build_composite_runtime_keys(
        frame[key_column],
        append_index_to_key=append_index_to_key,
    )
    frame["_row_index"] = frame.index + 2
    ordered_columns = _unique_preserve_order(["__key__", *columns, "_row_index"])
    return frame[ordered_columns].reset_index(drop=True)


def _resolve_composite_preview_page(
    *,
    page: int | None,
    size: int | None,
    total_keys: int,
) -> tuple[int, int, int, int, int, bool]:
    """统一解析组合变量预览分页；未传分页时保持全量预览兼容行为。"""
    if page is None and size is None:
        return 1, total_keys, 1, 0, total_keys, False

    resolved_page = max(1, page or 1)
    page_size = max(1, size or 200)
    total_pages = max(1, (total_keys + page_size - 1) // page_size)
    page_start = (resolved_page - 1) * page_size
    return (
        resolved_page,
        page_size,
        total_pages,
        page_start,
        page_start + page_size,
        True,
    )


def _count_non_empty_composite_keys(source_series: pd.Series) -> int:
    """统计组合变量 key 列中会进入映射的非空 key 数量。"""
    normalized_values = source_series.apply(_normalize_preview_value)
    return sum(1 for value in normalized_values.tolist() if not _is_empty_preview_value(value))


def _select_composite_key_row_indices(
    source_series: pd.Series,
    *,
    start: int,
    end: int,
) -> list[int]:
    """按非空 key 的顺序选出当前预览页对应的原始数据行索引。"""
    selected_indices: list[int] = []
    valid_key_position = 0
    normalized_values = source_series.apply(_normalize_preview_value)

    for row_index, value in normalized_values.items():
        if _is_empty_preview_value(value):
            continue
        if start <= valid_key_position < end:
            selected_indices.append(int(row_index))
        valid_key_position += 1
        if valid_key_position >= end:
            break

    return selected_indices


def _read_composite_preview_page(
    workbook: pd.ExcelFile,
    *,
    sheet_name: str,
    columns: list[str],
    row_indices: list[int],
) -> pd.DataFrame:
    """只读取当前预览页需要的数据行，并恢复为原始 0-based 行索引。"""
    if not row_indices:
        return pd.DataFrame(columns=columns)

    selected_indices = set(row_indices)

    def _skip_unselected_data_rows(excel_row_index: int) -> bool:
        if excel_row_index == 0:
            return False
        return (excel_row_index - 1) not in selected_indices

    dataframe = workbook.parse(
        sheet_name=sheet_name,
        usecols=columns,
        skiprows=_skip_unselected_data_rows,
    )
    dataframe.index = row_indices[: len(dataframe)]
    return dataframe


def _build_composite_mapping(
    dataframe: pd.DataFrame,
    *,
    columns: list[str],
    key_column: str,
    append_index_to_key: bool = False,
) -> tuple[dict[str, dict[str, Any]], int]:
    """基于 key 列把多列聚合成字典结构，并排除 key 列本身。"""
    mapping: dict[str, dict[str, Any]] = {}
    loaded_rows = 0

    composite_keys = _build_composite_runtime_keys(
        dataframe[key_column],
        append_index_to_key=append_index_to_key,
    )

    for row_index, row in dataframe[columns].iterrows():
        key = composite_keys.loc[row_index]
        if key is None:
            continue
        if key in mapping:
            raise ValueError(
                f"组合变量的 key 列 '{key_column}' 存在重复值 '{key}'，无法生成唯一映射。"
            )

        mapping[key] = {
            column: _normalize_preview_value(row[column])
            for column in columns
            if column != key_column
        }
        loaded_rows += 1

    return mapping, loaded_rows


def _build_composite_runtime_keys(
    source_series: pd.Series,
    *,
    append_index_to_key: bool,
) -> pd.Series:
    """按统一口径生成组合变量运行时 key。"""
    normalized_values = source_series.apply(_normalize_preview_value)
    runtime_keys: list[str | None] = []

    for row_position, value in normalized_values.items():
        if _is_empty_preview_value(value):
            runtime_keys.append(None)
            continue

        key = str(value)
        runtime_keys.append(f"{key}_{row_position}" if append_index_to_key else key)

    return pd.Series(runtime_keys, index=source_series.index, dtype=object)


def _has_duplicate_composite_keys(source_series: pd.Series) -> bool:
    """判断原始 key 列在未追加序号前是否存在重复值。"""
    return bool(_find_duplicate_composite_keys(source_series))


def _find_duplicate_composite_keys(source_series: pd.Series) -> list[str]:
    """返回原始 key 列在未追加序号前的重复值预览。"""
    normalized_values = source_series.apply(_normalize_preview_value)
    seen_values: set[str] = set()
    duplicate_values: list[str] = []

    for value in normalized_values.tolist():
        if value is None:
            continue

        key = str(value)
        if key in seen_values and key not in duplicate_values:
            duplicate_values.append(key)
            continue
        seen_values.add(key)

    return duplicate_values[:5]


def _get_excel_engine(source_path: Path) -> str:
    """按扩展名显式选择 Excel 引擎。"""
    if source_path.suffix.lower() == ".xls":
        return "xlrd"
    return "openpyxl"


def _build_excel_dependency_error(source_path: Path) -> str:
    """生成 Excel 依赖缺失时的统一提示。"""
    if source_path.suffix.lower() == ".xls":
        return (
            "读取 .xls 文件需要安装 xlrd 依赖，请执行 "
            "`pip install -r backend/requirements.txt` 或单独安装 `xlrd`。"
        )

    return (
        "读取 .xlsx 文件需要安装 openpyxl 依赖，请执行 "
        "`pip install -r backend/requirements.txt` 或单独安装 `openpyxl`。"
    )


def _is_empty_preview_value(value: Any) -> bool:
    """判断预览值是否为空，用于组合变量过滤空 key。"""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _normalize_preview_value(value: Any) -> Any:
    """把 Pandas/Numpy 值转换为可直接返回给前端的 JSON 兼容结构。"""
    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            return value

    return value


def _unique_preserve_order(items: Iterable[ItemT]) -> list[ItemT]:
    """去重但保持原有顺序，避免 usecols 顺序被打乱。"""
    return list(dict.fromkeys(items))
