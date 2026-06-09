"""配置表查询规则 Markdown 解析器。

第一阶段只解析固定中文配置项并做结构校验，不读取 SVN 或 Excel。
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any


class RuleConfigParseError(ValueError):
    """规则配置 Markdown 无法解析或结构不合法。"""


_SUPPORTED_TOP_KEYS = {"查询类型", "数据根", "配置文件", "分页", "引用"}
_SUPPORTED_ITEM_KEYS = {
    "名称",
    "ID字段",
    "名称字段",
    "输出字段",
    "字段",
    "显示名",
    "配置文件",
    "分页",
    "关联",
}
_FORBIDDEN_ENGLISH_KEYS = {
    "query_root",
    "query_type",
    "type",
    "value",
    "file",
    "sheet",
    "fields",
    "output_fields",
}
_KEY_VALUE_RE = re.compile(r"^(?P<indent>\s*)(?P<dash>-\s*)?(?P<key>[^:：]+)[:：]\s*(?P<value>.*)$")
_PLAIN_LIST_RE = re.compile(r"^(?P<indent>\s*)-\s*(?P<value>[^:：]+?)\s*$")
_QUERY_ROOT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def parse_config_lookup_markdown(content_md: str) -> dict[str, Any]:
    """解析 config_lookup 中文 Markdown，返回确定性的内部 JSON。"""
    blocks = _split_definition_blocks(content_md)
    if not blocks:
        raise RuleConfigParseError("规则内容不能为空")

    queries = [_parse_definition_block(block) for block in blocks]
    seen_query_types: set[str] = set()
    for query in queries:
        query_type = query["query_type"]
        if query_type in seen_query_types:
            raise RuleConfigParseError(f"查询类型重复：{query_type}")
        seen_query_types.add(query_type)

    return {"rule_family": "config_lookup", "queries": queries}


def _split_definition_blocks(content_md: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw_line in content_md.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        if line.strip() == "---":
            if current:
                blocks.append(current)
                current = []
            continue
        if not line.strip():
            current.append(line)
            continue
        current.append(line)
    if current:
        blocks.append(current)
    return [block for block in blocks if any(line.strip() for line in block)]


def _parse_definition_block(lines: list[str]) -> dict[str, Any]:
    query: dict[str, Any] = {
        "query_type": "",
        "query_root": "",
        "file": "",
        "pages": [],
        "references": [],
    }
    section: str | None = None
    current_item: dict[str, Any] | None = None
    output_owner: dict[str, Any] | None = None
    last_output_field: dict[str, str | None] | None = None

    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue

        key_match = _KEY_VALUE_RE.match(line)
        plain_match = _PLAIN_LIST_RE.match(line)
        if key_match is None and plain_match is None:
            raise RuleConfigParseError(f"第 {line_no} 行无法解析：{line.strip()}")

        if plain_match is not None and key_match is None:
            if output_owner is None:
                raise RuleConfigParseError(f"第 {line_no} 行列表项不在输出字段中")
            _append_output_field(output_owner, plain_match.group("value").strip(), None)
            last_output_field = output_owner["output_fields"][-1]
            continue

        if key_match is None:
            raise RuleConfigParseError(f"第 {line_no} 行无法解析")

        indent = len(key_match.group("indent"))
        has_dash = bool(key_match.group("dash"))
        key = key_match.group("key").strip()
        value = key_match.group("value").strip()

        _ensure_supported_key(key, line_no, indent)

        if indent == 0 and not has_dash:
            current_item = None
            output_owner = None
            last_output_field = None
            if key == "查询类型":
                query["query_type"] = _require_value(key, value, line_no)
            elif key == "数据根":
                query["query_root"] = _normalize_query_root(_require_value(key, value, line_no))
            elif key == "配置文件":
                query["file"] = _normalize_safe_path(_require_value(key, value, line_no), key, line_no)
            elif key == "分页":
                section = "pages"
            elif key == "引用":
                section = "references"
            continue

        if section not in {"pages", "references"}:
            raise RuleConfigParseError(f"第 {line_no} 行必须位于分页或引用配置下")

        if has_dash:
            if key == "字段":
                if output_owner is None:
                    raise RuleConfigParseError(f"第 {line_no} 行字段必须位于输出字段下")
                _append_output_field(output_owner, _require_value(key, value, line_no), None)
                last_output_field = output_owner["output_fields"][-1]
                continue
            if key != "名称":
                raise RuleConfigParseError(f"第 {line_no} 行列表项必须以名称或字段开始")
            current_item = _new_section_item(section, _require_value(key, value, line_no))
            query["pages" if section == "pages" else "references"].append(current_item)
            output_owner = None
            last_output_field = None
            continue

        if key == "显示名":
            if last_output_field is None:
                raise RuleConfigParseError(f"第 {line_no} 行显示名必须跟随字段配置")
            last_output_field["display_name"] = _require_value(key, value, line_no)
            continue

        if current_item is None:
            raise RuleConfigParseError(f"第 {line_no} 行缺少所属条目")

        if key == "输出字段":
            current_item.setdefault("output_fields", [])
            output_owner = current_item
            last_output_field = None
            continue

        output_owner = None
        last_output_field = None
        _assign_item_key(current_item, key, value, line_no)

    _validate_query(query)
    return query


def _ensure_supported_key(key: str, line_no: int, indent: int) -> None:
    normalized = key.strip()
    if normalized in _FORBIDDEN_ENGLISH_KEYS or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", normalized):
        raise RuleConfigParseError(f"第 {line_no} 行不支持英文配置项：{normalized}")
    allowed = _SUPPORTED_TOP_KEYS if indent == 0 else _SUPPORTED_ITEM_KEYS
    if normalized not in allowed:
        raise RuleConfigParseError(f"第 {line_no} 行存在未知配置项：{normalized}")


def _require_value(key: str, value: str, line_no: int) -> str:
    if not value.strip():
        raise RuleConfigParseError(f"第 {line_no} 行 {key} 不能为空")
    return value.strip()


def _normalize_query_root(value: str) -> str:
    if not _QUERY_ROOT_RE.fullmatch(value):
        raise RuleConfigParseError(f"数据根 alias 不合法：{value}")
    return value


def _normalize_safe_path(value: str, key: str, line_no: int) -> str:
    normalized = value.strip().replace("\\", "/")
    if not normalized:
        raise RuleConfigParseError(f"第 {line_no} 行 {key} 不能为空")
    if re.match(r"^[A-Za-z]:/", normalized) or normalized.startswith("/"):
        raise RuleConfigParseError(f"第 {line_no} 行 {key} 不能使用绝对路径")
    parts = PurePosixPath(normalized).parts
    if any(part in {"..", ""} for part in parts):
        raise RuleConfigParseError(f"第 {line_no} 行 {key} 不能包含父目录逃逸")
    return normalized


def _new_section_item(section: str, name: str) -> dict[str, Any]:
    if section == "pages":
        return {
            "name": name,
            "id_field": "",
            "name_field": "",
            "output_fields": [],
        }
    return {
        "name": name,
        "file": "",
        "page": "",
        "join": "",
        "output_fields": [],
    }


def _assign_item_key(item: dict[str, Any], key: str, value: str, line_no: int) -> None:
    required_value = _require_value(key, value, line_no)
    if key == "ID字段":
        item["id_field"] = required_value
    elif key == "名称字段":
        item["name_field"] = required_value
    elif key == "配置文件":
        item["file"] = _normalize_safe_path(required_value, key, line_no)
    elif key == "分页":
        item["page"] = required_value
    elif key == "关联":
        item["join"] = required_value
    elif key == "名称":
        item["name"] = required_value
    else:
        raise RuleConfigParseError(f"第 {line_no} 行配置项位置不正确：{key}")


def _append_output_field(owner: dict[str, Any], field: str, display_name: str | None) -> None:
    owner.setdefault("output_fields", [])
    owner["output_fields"].append({"field": field, "display_name": display_name})


def _validate_query(query: dict[str, Any]) -> None:
    for key, label in (
        ("query_type", "查询类型"),
        ("query_root", "数据根"),
        ("file", "配置文件"),
    ):
        if not query[key]:
            raise RuleConfigParseError(f"缺少必填字段：{label}")
    if not query["pages"]:
        raise RuleConfigParseError("分页不能为空")

    page_names: set[str] = set()
    for page in query["pages"]:
        if not page["name"]:
            raise RuleConfigParseError("分页名称不能为空")
        if page["name"] in page_names:
            raise RuleConfigParseError(f"分页名称重复：{page['name']}")
        page_names.add(page["name"])
        if not page["id_field"]:
            raise RuleConfigParseError(f"分页 {page['name']} 缺少 ID字段")
        if not page["name_field"]:
            raise RuleConfigParseError(f"分页 {page['name']} 缺少 名称字段")
        if not page["output_fields"]:
            raise RuleConfigParseError(f"分页 {page['name']} 输出字段不能为空")

    reference_names: set[str] = set()
    for reference in query["references"]:
        if reference["name"] in reference_names:
            raise RuleConfigParseError(f"引用名称重复：{reference['name']}")
        reference_names.add(reference["name"])
        for key, label in (("file", "配置文件"), ("page", "分页"), ("join", "关联")):
            if not reference[key]:
                raise RuleConfigParseError(f"引用 {reference['name']} 缺少 {label}")
        if not reference["output_fields"]:
            raise RuleConfigParseError(f"引用 {reference['name']} 输出字段不能为空")
