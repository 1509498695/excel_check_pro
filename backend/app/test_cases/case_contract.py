"""V3 canonical test-case field contract shared by generation, audit, and rendering."""

from __future__ import annotations

from typing import Any

from backend.app.test_cases.constants import CANONICAL_PRIMARY_MODULES


_MODULE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("开关/入口", ("开关", "入口", "开放", "开启", "关闭", "解锁")),
    ("界面", ("界面", "页面", "面板", "弹窗", "展示", "显示", "ui")),
    ("按钮", ("按钮", "点击", "操作")),
    ("数值/配置", ("数值", "配置", "概率", "上限", "下限", "公式", "档位")),
    ("奖励/消耗", ("奖励", "消耗", "返还", "扣除", "道具", "邮件到账")),
    ("红点/提示", ("红点", "提示", "飘字", "报错", "toast")),
    ("文本/多语言", ("文本", "文案", "多语言", "键值", "key", "富文本")),
    ("兼容", ("兼容", "回归", "共存", "跨服", "赛季", "迁移")),
    ("特殊操作", ("弱网", "重登", "重复点击", "并发", "稳定性", "性能")),
    ("常规测试点", ("常规", "适配", "资源质量")),
)


def normalize_primary_module(value: Any, *, fallback_text: str = "") -> str:
    """Return one execution-view module without accepting reference-defined enums."""
    candidate = _text(value)
    if candidate in CANONICAL_PRIMARY_MODULES:
        return candidate
    haystack = f"{candidate} {_text(fallback_text)}".lower()
    for module, keywords in _MODULE_KEYWORDS:
        if any(keyword.lower() in haystack for keyword in keywords):
            return module
    return "功能"


def canonical_case_fields(fields: dict[str, Any], *, case_id: str = "") -> dict[str, str]:
    """Map new or legacy Generation Run fields into the canonical xlsx contract."""
    title = _first_text(fields, "title", "scenario", "feature")
    source_note = _first_text(fields, "source_requirement", "config_source")
    remarks = _first_text(fields, "remarks")
    if not remarks and source_note:
        remarks = f"来源：{source_note}"
    primary_module = normalize_primary_module(
        _first_text(fields, "primary_module", "module"),
        fallback_text=" ".join(
            [
                title,
                _first_text(fields, "feature"),
                _first_text(fields, "scenario"),
                _first_text(fields, "case_type"),
            ]
        ),
    )
    return {
        "case_id": _text(case_id or fields.get("case_id")),
        "primary_module": primary_module,
        "secondary_module": _first_text(
            fields,
            "secondary_module",
            "feature",
            "module",
        )
        or primary_module,
        "checkpoint": _first_text(fields, "checkpoint", "scenario", "title")
        or "功能验证",
        "preconditions": _first_text(fields, "preconditions") or "无特殊前置条件",
        "steps": _first_text(fields, "steps") or title,
        "expected_results": _first_text(fields, "expected_results"),
        "priority": normalize_priority(fields.get("priority")),
        "remarks": remarks,
    }


def normalize_priority(value: Any) -> str:
    candidate = _text(value).upper()
    return candidate if candidate in {"P0", "P1", "P2", "P3"} else "P2"


def _first_text(fields: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(fields.get(key))
        if value:
            return value
    return ""


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()
