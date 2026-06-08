"""AI prompt 构造输入的轻量 builder。"""

from __future__ import annotations

from typing import Any

from backend.app.ai.prompts import SUPPORTED_RULE_TYPES
from backend.app.api.schemas import VariableTag


RULE_DISPLAY_NAMES = {
    "not_null": "非空校验",
    "unique": "唯一校验",
    "fixed_value_compare": "固定值比较",
    "regex_check": "正则校验",
    "sequence_order_check": "顺序校验",
    "cross_table_mapping": "包含校验",
    "composite_condition_check": "组合分支校验",
    "dual_composite_compare": "跨组变量校验",
    "multi_composite_pipeline_check": "多组串行校验",
    "multi_composite_mapping_check": "多组映射校验",
    "package_items_compare": "IAP礼包校验",
    "event_task_reward": "节日任务奖励校验",
    "event_task_validation": "节日任务奖励校验（兼容）",
}


def prompt_variable_metadata(variables: list[VariableTag]) -> list[dict[str, Any]]:
    """把变量池变量压缩成 prompt 所需 metadata。"""

    return [
        {
            "tag": variable.tag,
            "source_id": variable.source_id,
            "sheet": variable.sheet,
            "variable_kind": variable.variable_kind,
            "column": variable.column,
            "columns": variable.columns,
            "key_column": variable.key_column,
            "expected_type": variable.expected_type,
        }
        for variable in variables
    ]


def rule_library_summary() -> list[dict[str, str]]:
    """返回当前 AI 支持规则清单，供 prompt 和优化接口复用。"""

    return [
        {
            "rule_type": rule_type,
            "display_name": RULE_DISPLAY_NAMES.get(rule_type, rule_type),
        }
        for rule_type in SUPPORTED_RULE_TYPES
    ]
