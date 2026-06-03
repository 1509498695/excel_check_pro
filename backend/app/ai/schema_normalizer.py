"""AI 模型输出 schema 兼容与归一化。"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError


VALID_MISSING_KINDS = {"source", "variable", "rule", "parameter", "ability"}
VALID_MISSING_ACTIONS = {
    "open_source_dialog",
    "open_single_variable_dialog",
    "open_composite_variable_dialog",
    "edit_description",
    "none",
}


def normalize_raw_rule_intent(raw_intent: Any) -> Any:
    """修正常见模型输出包装字段，其余规则协议继续交给 Pydantic 校验。"""

    if not isinstance(raw_intent, dict):
        return raw_intent
    normalized = {**raw_intent}
    for wrapper_key in ("parameters", "params", "arguments"):
        normalized.pop(wrapper_key, None)
    normalized["missing"] = normalize_missing_items(raw_intent.get("missing"))
    for key in ("target", "reference"):
        if key in normalized:
            normalized[key] = normalize_raw_variable_intent(normalized[key])
    return normalized


def normalize_raw_variable_intent(raw_variable: Any) -> Any:
    """兼容模型把变量写成字符串、嵌套对象或旧字段名的情况。"""

    if isinstance(raw_variable, str):
        return {"tag": raw_variable}
    if not isinstance(raw_variable, dict):
        return raw_variable

    normalized = {**raw_variable}
    nested_variable = normalized.pop("variable", None)
    if isinstance(nested_variable, dict):
        normalized = {**nested_variable, **normalized}

    alias_map = {
        "variable_tag": "tag",
        "target_variable_tag": "tag",
        "reference_variable_tag": "tag",
        "pathOrUrl": "path_or_url",
        "path": "path_or_url",
        "url": "path_or_url",
        "source_url": "path_or_url",
        "kind": "variable_kind",
    }
    for source_key, target_key in alias_map.items():
        if source_key in normalized and target_key not in normalized:
            normalized[target_key] = normalized.pop(source_key)
        else:
            normalized.pop(source_key, None)
    if is_placeholder_key_column(normalized.get("key_column")):
        normalized["key_column"] = None
    if isinstance(normalized.get("columns"), list):
        normalized["columns"] = [
            str(column).strip()
            for column in normalized["columns"]
            if isinstance(column, str)
            and column.strip()
            and not is_placeholder_key_column(column)
        ]
    return normalized


def normalize_missing_items(raw_missing: Any) -> list[dict[str, Any]]:
    """把模型返回的 missing 字段统一成前端可消费的 MissingItem dict。"""

    if raw_missing is None:
        return []
    if isinstance(raw_missing, dict):
        candidates = [raw_missing]
    elif isinstance(raw_missing, list):
        candidates = raw_missing
    else:
        candidates = [raw_missing]

    items: list[dict[str, Any]] = []
    for candidate in candidates:
        if isinstance(candidate, dict):
            message = string_or_default(candidate.get("message"), "配置缺口需要补充。")
            prefill = candidate.get("prefill")
            if not isinstance(prefill, dict):
                prefill = {}
            kind = normalize_missing_kind(candidate.get("kind"), message, candidate, prefill)
            suggested_action = normalize_missing_action(
                candidate.get("suggested_action"),
                kind,
                prefill,
            )
        else:
            message = string_or_default(candidate, "配置缺口需要补充。")
            prefill = {}
            kind = infer_missing_kind(message=message, action=None, prefill=prefill)
            suggested_action = infer_missing_action(kind, prefill)
        items.append(
            {
                "kind": kind,
                "message": message,
                "suggested_action": suggested_action,
                "prefill": prefill,
            }
        )
    return items


def summarize_validation_error(error: ValidationError) -> str:
    """把 Pydantic 错误压缩成对用户可读的一行摘要。"""

    first_error = error.errors()[0] if error.errors() else {}
    loc = ".".join(str(item) for item in first_error.get("loc", []))
    msg = first_error.get("msg", "字段校验失败")
    return f"{loc}: {msg}" if loc else str(msg)


def normalize_missing_kind(
    raw_kind: Any,
    message: str,
    raw_item: dict[str, Any],
    prefill: dict[str, Any],
) -> str:
    kind = raw_kind.strip() if isinstance(raw_kind, str) else ""
    if kind in VALID_MISSING_KINDS:
        return kind
    action = raw_item.get("suggested_action")
    return infer_missing_kind(message=message, action=action, prefill=prefill)


def infer_missing_kind(
    *,
    message: str,
    action: Any,
    prefill: dict[str, Any],
) -> str:
    if action == "open_source_dialog":
        return "source"
    if action in {"open_single_variable_dialog", "open_composite_variable_dialog"}:
        return "variable"

    text = message.lower()
    if any(keyword in text for keyword in ("数据源", "source", "svn", "url", "文件", "路径")):
        return "source"
    if any(keyword in text for keyword in ("变量", "字段", "列", "sheet", "工作表", "column")):
        return "variable"
    if any(keyword in text for keyword in ("规则类型", "rule_type", "规则")):
        return "rule"
    if any(keyword in text for keyword in ("能力", "不支持", "无法表达", "不能表达", "unsupported")):
        return "ability"
    if any(key in prefill for key in ("sheet", "column", "columns", "key_column")):
        return "variable"
    if any(key in prefill for key in ("source_id", "pathOrUrl", "path_or_url", "url")):
        return "source"
    return "parameter"


def normalize_missing_action(
    raw_action: Any,
    kind: str,
    prefill: dict[str, Any],
) -> str:
    action = raw_action.strip() if isinstance(raw_action, str) else ""
    if action in VALID_MISSING_ACTIONS:
        return action
    return infer_missing_action(kind, prefill)


def infer_missing_action(kind: str, prefill: dict[str, Any]) -> str:
    if kind == "source":
        return "open_source_dialog"
    if kind == "variable":
        if any(key in prefill for key in ("columns", "key_column")):
            return "open_composite_variable_dialog"
        if any(key in prefill for key in ("sheet", "column", "source_id")):
            return "open_single_variable_dialog"
        return "edit_description"
    if kind in {"rule", "parameter"}:
        return "edit_description"
    return "none"


def string_or_default(value: Any, default: str) -> str:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or default
    if value is None:
        return default
    return str(value).strip() or default


def is_placeholder_key_column(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return normalized in {"", "key", "key字段", "业务key", "业务 key", "无", "none"}
