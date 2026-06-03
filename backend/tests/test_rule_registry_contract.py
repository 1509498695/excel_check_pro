"""规则元数据与当前能力清单契约测试。"""

from __future__ import annotations

from backend.app.ai import prompts
from backend.app.ai import rule_candidate
from backend.app.ai.compilers import registry as compiler_registry
from backend.app.ai.template import labels
from backend.app.api.fixed_rules_schemas import FixedRuleType
from backend.app.loaders import feishu_reader
from backend.app.rules import engine_core
from backend.app.rules import registry as rule_registry
from backend.app.rules.handlers import fixed as _fixed_handlers  # noqa: F401


def _fixed_rule_types() -> set[str]:
    return set(FixedRuleType.__args__)


def test_package_items_compare_has_rule_metadata_and_handler() -> None:
    """礼包校验已接入执行链路时，展示元数据也必须同步存在。"""
    metadata = rule_registry.RULE_METADATA["package_items_compare"]

    assert metadata.display_name == "IAP礼包校验"
    assert metadata.category == "package_items"
    assert "package_items_compare" in engine_core.RULE_REGISTRY


def test_backend_rule_type_lists_include_package_items_compare() -> None:
    """后端固定规则、AI 提示词和候选识别清单应保持 11 类一致。"""
    expected_rule_types = _fixed_rule_types()

    assert set(rule_registry.RULE_METADATA) == expected_rule_types
    assert set(prompts.SUPPORTED_RULE_TYPES) == expected_rule_types
    assert set(rule_candidate.SUPPORTED_RULE_TYPES) == expected_rule_types
    assert set(labels.SUPPORTED_RULE_TYPES) == expected_rule_types


def test_ai_compiler_registry_includes_package_items_compiler() -> None:
    """已有礼包校验 compiler 不应遗漏在确定性编译分发之外。"""
    compiler_rule_types = {
        rule_type
        for compiler in compiler_registry._COMPILERS
        for rule_type in compiler.rule_types
    }

    assert "package_items_compare" in compiler_rule_types


def test_feishu_reader_does_not_export_placeholder_sheet_reader() -> None:
    """飞书读取模块不再暴露未实现的旧兼容入口。"""
    legacy_reader_name = "_".join(("read", "feishu", "sheet"))

    assert not hasattr(feishu_reader, legacy_reader_name)
