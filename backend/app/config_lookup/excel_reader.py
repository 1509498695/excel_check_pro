"""配置表查询 Excel 读取与单元格规范化。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


class ConfigLookupExcelError(ValueError):
    """Excel 读取或配置字段错误。"""


def read_excel_sheet(file_path: Path, sheet_name: str) -> list[dict[str, Any]]:
    """读取 Excel sheet，保留原始列名并把空值规范为空字符串。"""

    try:
        excel = pd.ExcelFile(file_path, engine=_get_excel_engine(file_path))
    except Exception as exc:  # pragma: no cover - pandas 会按文件格式抛多类异常
        raise ConfigLookupExcelError(f"配置文件无法读取：{file_path.name}") from exc

    resolved_sheet = _resolve_sheet_name(excel.sheet_names, sheet_name)
    if resolved_sheet is None:
        raise ConfigLookupExcelError(f"配置分页不存在：{sheet_name}")

    frame = excel.parse(resolved_sheet, dtype=object)
    frame = frame.where(pd.notna(frame), "")
    rows: list[dict[str, Any]] = []
    for raw_row in frame.to_dict(orient="records"):
        rows.append({str(key): value for key, value in raw_row.items()})
    return rows


def get_cell(row: dict[str, Any], field_name: str) -> Any:
    """按字段名读取单元格，先精确匹配，再尝试去空格匹配。"""

    if field_name in row:
        return row[field_name]
    wanted = field_name.strip()
    for key, value in row.items():
        if key.strip() == wanted:
            return value
    raise ConfigLookupExcelError(f"配置字段不存在：{field_name}")


def normalize_cell_value(value: Any) -> str:
    """把 Excel 值规范为适合 ID/名称比较与输出的字符串。"""

    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def _resolve_sheet_name(sheet_names: list[str], expected: str) -> str | None:
    if expected in sheet_names:
        return expected
    stripped = expected.strip()
    for name in sheet_names:
        if name.strip() == stripped:
            return name
    return None


def _get_excel_engine(file_path: Path) -> str | None:
    suffix = file_path.suffix.lower()
    if suffix == ".xls":
        return "xlrd"
    if suffix in {".xlsx", ".xlsm"}:
        return "openpyxl"
    return None
