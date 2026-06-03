"""规则元数据注册表。

该模块只承载规则类型的静态元信息，执行调度仍由
``backend.app.rules.engine_core.RULE_REGISTRY`` 负责。把展示名、分类和未来
模板入口先集中起来，避免后续“快速添加规则 / 规则推荐”继续散落在调用方。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RuleCategory = Literal[
    "basic",
    "sequence",
    "cross",
    "composite",
    "dual_composite",
    "pipeline",
    "mapping",
    "package_items",
]


@dataclass(frozen=True)
class RuleMetadata:
    """规则类型的非执行元数据。"""

    rule_type: str
    display_name: str
    category: RuleCategory


RULE_METADATA: dict[str, RuleMetadata] = {
    "not_null": RuleMetadata("not_null", "非空校验", "basic"),
    "unique": RuleMetadata("unique", "唯一校验", "basic"),
    "fixed_value_compare": RuleMetadata("fixed_value_compare", "固定值比较", "basic"),
    "regex_check": RuleMetadata("regex_check", "正则校验", "basic"),
    "sequence_order_check": RuleMetadata("sequence_order_check", "顺序校验", "sequence"),
    "cross_table_mapping": RuleMetadata("cross_table_mapping", "包含校验", "cross"),
    "composite_condition_check": RuleMetadata(
        "composite_condition_check",
        "组合分支校验",
        "composite",
    ),
    "dual_composite_compare": RuleMetadata(
        "dual_composite_compare",
        "跨组变量校验",
        "dual_composite",
    ),
    "multi_composite_pipeline_check": RuleMetadata(
        "multi_composite_pipeline_check",
        "多组串行校验",
        "pipeline",
    ),
    "multi_composite_mapping_check": RuleMetadata(
        "multi_composite_mapping_check",
        "多组映射校验",
        "mapping",
    ),
    "package_items_compare": RuleMetadata(
        "package_items_compare",
        "IAP礼包校验",
        "package_items",
    ),
}


def get_rule_metadata(rule_type: str) -> RuleMetadata:
    """按 rule_type 读取规则元信息。"""

    return RULE_METADATA[rule_type]
