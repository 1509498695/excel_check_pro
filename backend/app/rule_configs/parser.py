"""config_lookup 中文 Markdown 解析与结构校验。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class RuleConfigValidationResult:
    """规则配置结构校验结果。"""

    ok: bool
    parsed_config_json: dict[str, Any]
    errors: list[str]
    summary: dict[str, Any]


class RuleConfigParseError(ValueError):
    """规则配置 Markdown 结构错误。"""


_TOP_KEYS = {"查询类型", "数据根", "配置文件"}
_PAGE_KEYS = {"分页名称", "匹配字段", "输出字段"}
_REFERENCE_KEYS = {"引用分页名称", "引用规则", "显示内容"}
_FORMATTER_KEYS = {"格式", "时区"}
_OLD_KEYS = {"分页", "名称", "名称字段", "引用", "字段", "显示名"}
_ENGLISH_KEYS = {
    "query_type",
    "query_root",
    "file",
    "pages",
    "page",
    "name",
    "id_field",
    "name_field",
    "output_fields",
    "field",
    "display_name",
    "references",
    "reference",
    "join",
    "type",
    "value",
}
_KEY_VALUE_RE = re.compile(r"^([^:：]+)[:：](.*)$")
_BULLET_RE = re.compile(r"^(?P<indent>\s*)-\s*(?P<body>.+?)\s*$")
_JOIN_RE = re.compile(r"^([^.=\s]+)\.([^.=\s]+)=([^.=\s]+)\.([^.=\s]+)$")
_DISPLAY_EXPR_RE = re.compile(r"^([^./\s]+)\.([^./\s]+)(?:/(\d+(?:\.\d+)?))?$")


def validate_config_lookup_markdown(
    content_md: str,
    *,
    allowed_query_roots: set[str],
) -> RuleConfigValidationResult:
    """校验 config_lookup 新语法 Markdown，返回结构化结果。"""
    try:
        parsed_config = parse_config_lookup_markdown(
            content_md,
            allowed_query_roots=allowed_query_roots,
        )
    except RuleConfigParseError as exc:
        return RuleConfigValidationResult(
            ok=False,
            parsed_config_json={},
            errors=[str(exc)],
            summary={},
        )
    return RuleConfigValidationResult(
        ok=True,
        parsed_config_json=parsed_config,
        errors=[],
        summary=build_config_lookup_summary(parsed_config),
    )


def parse_config_lookup_markdown(
    content_md: str,
    *,
    allowed_query_roots: set[str],
) -> dict[str, Any]:
    """解析 config_lookup 新语法 Markdown，返回确定性的内部 JSON。"""
    lines = _normalize_lines(content_md)
    if any(line.strip() == "---" for line in lines):
        raise RuleConfigParseError("单条查询规则不允许使用 --- 多查询类型分隔符")

    raw_pages, top_values = _collect_blocks(lines)
    query_type = _require_top_value(top_values, "查询类型")
    query_root = _require_top_value(top_values, "数据根")
    file_name = _require_top_value(top_values, "配置文件")
    if query_root not in allowed_query_roots:
        raise RuleConfigParseError(f"数据根 alias 不存在：{query_root}")
    _validate_safe_relative_path(file_name, field_label="配置文件")
    if not raw_pages:
        raise RuleConfigParseError("至少需要配置一个分页")

    pages = [_parse_page(page) for page in raw_pages]
    return {
        "rule_family": "config_lookup",
        "query_type": query_type,
        "query_root": query_root,
        "file": file_name,
        "pages": pages,
    }


def build_config_lookup_summary(parsed_config: dict[str, Any]) -> dict[str, Any]:
    """生成前端结构校验展示摘要。"""
    pages = parsed_config.get("pages")
    page_items = pages if isinstance(pages, list) else []
    page_names = [
        str(page.get("name") or "")
        for page in page_items
        if isinstance(page, dict) and page.get("name")
    ]
    references: list[dict[str, str]] = []
    for page in page_items:
        if not isinstance(page, dict):
            continue
        for field in _list_output_fields(page):
            reference = field.get("reference")
            if isinstance(reference, dict):
                references.append(
                    {
                        "page": str(page.get("name") or ""),
                        "label": str(field.get("label") or ""),
                        "reference_page": str(reference.get("page") or ""),
                        "join": str(reference.get("join") or ""),
                        "display_expression": str(reference.get("display_expression") or ""),
                    }
                )
    return {
        "query_type": parsed_config.get("query_type") or "",
        "query_types": [parsed_config.get("query_type") or ""],
        "query_root": parsed_config.get("query_root") or "",
        "query_roots": [parsed_config.get("query_root") or ""],
        "primary_file": parsed_config.get("file") or "",
        "primary_files": [parsed_config.get("file") or ""],
        "pages": [{"query_type": parsed_config.get("query_type") or "", "names": page_names}],
        "references": references,
    }


def _normalize_lines(content_md: str) -> list[str]:
    return content_md.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _collect_blocks(lines: list[str]) -> tuple[list[list[tuple[int, int, str]]], dict[str, str]]:
    top_values: dict[str, str] = {}
    pages: list[list[tuple[int, int, str]]] = []
    current_page: list[tuple[int, int, str]] | None = None

    for line_no, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        bullet = _BULLET_RE.match(raw_line)
        if bullet is None:
            key, value = _parse_key_value(raw_line.strip(), line_no=line_no)
            _reject_invalid_key(key, line_no=line_no)
            if key not in _TOP_KEYS:
                raise RuleConfigParseError(f"第 {line_no} 行不支持的顶层配置项：{key}")
            if key in top_values:
                raise RuleConfigParseError(f"第 {line_no} 行重复配置项：{key}")
            top_values[key] = value
            continue

        indent = len(bullet.group("indent"))
        body = bullet.group("body").strip()
        key, value = _parse_optional_key_value(body, line_no=line_no)
        _reject_invalid_key(key, line_no=line_no)

        if key == "分页名称":
            current_page = [(line_no, indent, body)]
            pages.append(current_page)
            continue
        if current_page is None:
            raise RuleConfigParseError(f"第 {line_no} 行分页字段必须出现在 分页名称 之后")
        current_page.append((line_no, indent, body))

    return pages, top_values


def _parse_page(raw_page: list[tuple[int, int, str]]) -> dict[str, Any]:
    name = ""
    match_fields_seen = False
    output_fields_seen = False
    match_fields: list[dict[str, str]] = []
    fields: list[dict[str, Any]] = []
    current_field: dict[str, Any] | None = None
    current_field_indent = 0
    current_section = ""

    for line_no, indent, body in raw_page:
        key, value = _parse_optional_key_value(body, line_no=line_no)
        _reject_invalid_key(key, line_no=line_no)
        if key == "分页名称":
            if name:
                raise RuleConfigParseError(f"第 {line_no} 行重复配置 分页名称")
            if not value:
                raise RuleConfigParseError(f"第 {line_no} 行 分页名称 不能为空")
            name = value
            continue
        if key == "匹配字段":
            if match_fields_seen:
                raise RuleConfigParseError(f"第 {line_no} 行重复配置 匹配字段")
            if value:
                raise RuleConfigParseError(f"第 {line_no} 行 匹配字段 不应带值")
            match_fields_seen = True
            current_section = "match"
            current_field = None
            continue
        if key == "输出字段":
            if output_fields_seen:
                raise RuleConfigParseError(f"第 {line_no} 行重复配置 输出字段")
            if value:
                raise RuleConfigParseError(f"第 {line_no} 行 输出字段 不应带值")
            output_fields_seen = True
            current_section = "output"
            current_field = None
            continue
        if current_section == "match":
            match_fields.append(_parse_match_field(key, value, line_no=line_no))
            continue
        is_field_child = current_field is not None and indent > current_field_indent
        if is_field_child and key in _REFERENCE_KEYS:
            if current_field is None:
                raise RuleConfigParseError(f"第 {line_no} 行引用配置必须跟在输出字段之后")
            reference = current_field.setdefault("reference", {})
            reference[key] = value
            continue
        if is_field_child and key in _FORMATTER_KEYS:
            if current_field is None:
                raise RuleConfigParseError(f"第 {line_no} 行格式配置必须跟在输出字段之后")
            formatter = current_field.setdefault("formatter", {})
            formatter[key] = value
            continue
        if is_field_child and _looks_like_value_map_key(key):
            value_map = current_field.setdefault("value_map", {})
            value_map[key] = value
            continue

        if current_section != "output" or not output_fields_seen:
            raise RuleConfigParseError(f"第 {line_no} 行输出字段必须出现在 输出字段 之后")
        field = _parse_output_field(key, value, line_no=line_no)
        fields.append(field)
        current_field = field
        current_field_indent = indent

    if not name:
        raise RuleConfigParseError("每个分页必须配置 分页名称")
    if not match_fields_seen:
        raise RuleConfigParseError(f"分页 {name} 必须配置 匹配字段")
    if not output_fields_seen or not fields:
        raise RuleConfigParseError(f"分页 {name} 必须配置 输出字段")

    id_fields = [field for field in match_fields if field.get("kind") == "id"]
    if not id_fields:
        raise RuleConfigParseError(f"分页 {name} 的 匹配字段 必须配置 ID字段")
    text_match_fields = [field for field in match_fields if field.get("kind") != "id"]
    if not text_match_fields:
        raise RuleConfigParseError(f"分页 {name} 的 匹配字段 必须配置至少一个文本匹配字段")

    for field in fields:
        _normalize_field_reference(
            field,
            current_page_name=name,
            line_no=int(field.get("_line_no") or 0),
        )
        _normalize_field_formatter(
            field,
            line_no=int(field.get("_line_no") or 0),
        )

    return {
        "name": name,
        "id_match_field": id_fields[0]["field"],
        "text_match_fields": [
            {"label": field["label"], "field": field["field"]} for field in text_match_fields
        ],
        "candidate_label_field": text_match_fields[0]["field"],
        "output_fields": [_strip_field_kind(field) for field in fields],
    }


def _parse_match_field(key: str, value: str, *, line_no: int) -> dict[str, str]:
    if not value:
        raise RuleConfigParseError(f"第 {line_no} 行匹配字段缺少字段名：{key}")
    return {
        "label": key,
        "field": value,
        "kind": "id" if key == "ID字段" else "field",
    }


def _parse_output_field(key: str, value: str, *, line_no: int) -> dict[str, Any]:
    if not value:
        raise RuleConfigParseError(f"第 {line_no} 行输出字段缺少字段名：{key}")
    field = {
        "label": key,
        "field": value,
        "kind": "id" if key == "ID字段" else "field",
        "_line_no": line_no,
    }
    return field


def _normalize_field_reference(
    field: dict[str, Any],
    *,
    current_page_name: str,
    line_no: int,
) -> None:
    raw_reference = field.get("reference")
    if not isinstance(raw_reference, dict):
        return
    ref_page = str(raw_reference.get("引用分页名称") or "").strip()
    join = str(raw_reference.get("引用规则") or "").strip()
    display_expression = str(raw_reference.get("显示内容") or "").strip()
    if not ref_page:
        raise RuleConfigParseError(f"第 {line_no} 行引用字段缺少 引用分页名称")
    if not join:
        raise RuleConfigParseError(f"第 {line_no} 行引用字段缺少 引用规则")
    if not display_expression:
        raise RuleConfigParseError(f"第 {line_no} 行引用字段缺少 显示内容")

    join_match = _JOIN_RE.match(join)
    if join_match is None:
        raise RuleConfigParseError("引用规则必须是 Page.Field=Page.Field")
    left_page, _left_field, right_page, _right_field = join_match.groups()
    if left_page != current_page_name:
        raise RuleConfigParseError("引用规则左侧分页必须等于当前分页名称")
    if right_page != ref_page:
        raise RuleConfigParseError("引用规则右侧分页必须等于引用分页名称")

    expr_match = _DISPLAY_EXPR_RE.match(display_expression)
    if expr_match is None:
        raise RuleConfigParseError("显示内容只支持 Page.Field 或 Page.Field/数字")
    expr_page, _expr_field, _divisor = expr_match.groups()
    if expr_page != ref_page:
        raise RuleConfigParseError("显示内容分页必须等于引用分页名称")

    field["reference"] = {
        "page": ref_page,
        "join": join,
        "display_expression": display_expression,
    }


def _normalize_field_formatter(field: dict[str, Any], *, line_no: int) -> None:
    raw_formatter = field.get("formatter")
    if not isinstance(raw_formatter, dict):
        return

    format_name = str(raw_formatter.get("格式") or "").strip()
    timezone_name = str(raw_formatter.get("时区") or "Asia/Shanghai").strip()
    if not format_name:
        raise RuleConfigParseError(f"第 {line_no} 行格式配置缺少 格式")
    if format_name != "时间戳秒":
        raise RuleConfigParseError("格式 只支持 时间戳秒")
    if timezone_name != "Asia/Shanghai":
        raise RuleConfigParseError("时区 只支持 Asia/Shanghai")
    field["formatter"] = {
        "type": "timestamp_seconds",
        "timezone": "Asia/Shanghai",
    }


def _strip_field_kind(field: dict[str, Any]) -> dict[str, Any]:
    cleaned = {key: value for key, value in field.items() if key not in {"kind", "_line_no"}}
    if "value_map" in cleaned and not cleaned["value_map"]:
        cleaned.pop("value_map")
    return cleaned


def _parse_key_value(body: str, *, line_no: int) -> tuple[str, str]:
    match = _KEY_VALUE_RE.match(body)
    if match is None:
        raise RuleConfigParseError(f"第 {line_no} 行必须使用 中文配置项: 值")
    key = match.group(1).strip()
    value = match.group(2).strip()
    if not key:
        raise RuleConfigParseError(f"第 {line_no} 行配置项不能为空")
    return key, value


def _parse_optional_key_value(body: str, *, line_no: int) -> tuple[str, str]:
    match = _KEY_VALUE_RE.match(body)
    if match is None:
        key = body.strip()
        if not key:
            raise RuleConfigParseError(f"第 {line_no} 行配置项不能为空")
        return key, ""
    return _parse_key_value(body, line_no=line_no)


def _reject_invalid_key(key: str, *, line_no: int) -> None:
    normalized = key.strip()
    if normalized in _OLD_KEYS:
        raise RuleConfigParseError(f"第 {line_no} 行旧语法字段不再支持：{normalized}")
    if normalized.lower() in _ENGLISH_KEYS:
        raise RuleConfigParseError(f"第 {line_no} 行不支持英文配置项：{normalized}")


def _looks_like_value_map_key(key: str) -> bool:
    return (
        key not in _REFERENCE_KEYS
        and key not in _FORMATTER_KEYS
        and key not in _PAGE_KEYS
        and key != "分页名称"
    )


def _validate_safe_relative_path(value: str, *, field_label: str) -> None:
    if not value:
        raise RuleConfigParseError(f"缺少必填字段：{field_label}")
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        raise RuleConfigParseError(f"{field_label} 必须是相对路径，不能是 URL")
    if PureWindowsPath(value).drive:
        raise RuleConfigParseError(f"{field_label} 必须是相对路径，不能包含盘符")
    posix = PurePosixPath(value.replace("\\", "/"))
    if posix.is_absolute() or PureWindowsPath(value).is_absolute():
        raise RuleConfigParseError(f"{field_label} 必须是相对路径，不能是绝对路径")
    if ".." in posix.parts:
        raise RuleConfigParseError(f"{field_label} 必须是相对路径，不能包含 ..")


def _require_top_value(top_values: dict[str, str], key: str) -> str:
    value = top_values.get(key, "").strip()
    if not value:
        raise RuleConfigParseError(f"缺少必填字段：{key}")
    return value


def _list_output_fields(page: dict[str, Any]) -> list[dict[str, Any]]:
    output_fields = page.get("output_fields")
    if not isinstance(output_fields, list):
        return []
    return [field for field in output_fields if isinstance(field, dict)]
