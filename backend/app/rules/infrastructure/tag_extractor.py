"""5 种 rule_type 的依赖 tag 提取器。

每个 ``rule_type`` 在注册时通过 ``register_rule(..., dependent_tags=...)`` 显式
绑定一个提取器，供 ``execute_api._filter_executable_rules`` 在加载阶段统一
判定「规则依赖的 source 是否已成功加载」。

异常文案逐字保留与原 ``execute_api._extract_rule_tags`` 一致，避免破坏现有
基线测试与 baseline 快照。
"""

from __future__ import annotations

from collections.abc import Callable

from backend.app.api.schemas import ValidationRule


TagExtractor = Callable[[ValidationRule], list[str]]


def by_target_tags(rule: ValidationRule) -> list[str]:
    """``not_null`` / ``unique``：从 ``params.target_tags`` 中提取多 tag。"""
    target_tags = rule.params.get("target_tags")
    if not isinstance(target_tags, list) or not target_tags:
        raise ValueError(
            f"Rule '{rule.rule_type}' requires non-empty params.target_tags."
        )
    if not all(isinstance(tag, str) and tag for tag in target_tags):
        raise ValueError(
            f"Rule '{rule.rule_type}' requires params.target_tags to be a string list."
        )
    return target_tags


def by_dict_and_target_tag(rule: ValidationRule) -> list[str]:
    """``cross_table_mapping``：从 ``params.dict_tag`` / ``target_tag`` 中提取双 tag。"""
    dict_tag = rule.params.get("dict_tag")
    target_tag = rule.params.get("target_tag")
    if not isinstance(dict_tag, str) or not dict_tag:
        raise ValueError("Rule 'cross_table_mapping' requires params.dict_tag.")
    if not isinstance(target_tag, str) or not target_tag:
        raise ValueError("Rule 'cross_table_mapping' requires params.target_tag.")
    return [dict_tag, target_tag]


def by_reference_and_target_tag(rule: ValidationRule) -> list[str]:
    """``dual_composite_compare``：提取左右 tag；同变量模式允许返回重复 tag。"""
    reference_tag = rule.params.get("reference_tag")
    target_tag = rule.params.get("target_tag")
    if not isinstance(reference_tag, str) or not reference_tag:
        raise ValueError("Rule 'dual_composite_compare' requires params.reference_tag.")
    if not isinstance(target_tag, str) or not target_tag:
        raise ValueError("Rule 'dual_composite_compare' requires params.target_tag.")
    return [reference_tag, target_tag]


def by_left_and_right_tag(rule: ValidationRule) -> list[str]:
    """``package_items_compare``：从 ``params.left_tag`` / ``right_tag`` 中提取双 tag。"""
    left_tag = rule.params.get("left_tag")
    right_tag = rule.params.get("right_tag")
    if not isinstance(left_tag, str) or not left_tag:
        raise ValueError("Rule 'package_items_compare' requires params.left_tag.")
    if not isinstance(right_tag, str) or not right_tag:
        raise ValueError("Rule 'package_items_compare' requires params.right_tag.")
    return [left_tag, right_tag]


def by_pipeline_node_tags(rule: ValidationRule) -> list[str]:
    """``multi_composite_pipeline_check``：从 ``params.pipeline_config.nodes`` 中提取全部节点 tag。"""
    return _by_config_node_tags(
        rule,
        config_key="pipeline_config",
        rule_label="multi_composite_pipeline_check",
    )


def by_mapping_node_tags(rule: ValidationRule) -> list[str]:
    """``multi_composite_mapping_check``：从 ``params.mapping_config.nodes`` 中提取全部节点 tag。"""
    return _by_config_node_tags(
        rule,
        config_key="mapping_config",
        rule_label="multi_composite_mapping_check",
    )


def _by_config_node_tags(
    rule: ValidationRule,
    *,
    config_key: str,
    rule_label: str,
) -> list[str]:
    config = rule.params.get(config_key)
    if not isinstance(config, dict):
        raise ValueError(
            f"Rule '{rule_label}' requires params.{config_key}."
        )
    nodes = config.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError(
            f"Rule '{rule_label}' requires non-empty params.{config_key}.nodes."
        )

    tags: list[str] = []
    seen_tags: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError(
                f"Rule '{rule_label}' provides invalid params.{config_key}.nodes."
            )
        variable_tag = node.get("variable_tag")
        if not isinstance(variable_tag, str) or not variable_tag.strip():
            raise ValueError(
                f"Rule '{rule_label}' requires each node to provide variable_tag."
            )
        normalized_tag = variable_tag.strip()
        if normalized_tag in seen_tags:
            continue
        tags.append(normalized_tag)
        seen_tags.add(normalized_tag)
    return tags


def by_target_tag(rule: ValidationRule) -> list[str]:
    """``fixed_value_compare`` / ``composite_condition_check``：单 tag 提取。

    文案与原 ``fixed_value_compare`` 在 ``execute_api._extract_rule_tags`` 中的硬编码
    版本完全一致；同时也与 ``composite_condition_check`` handler 内部
    ``_get_fixed_rule_param`` 抛出的文案一致，避免重复触发同义异常时出现差异。
    """
    target_tag = rule.params.get("target_tag")
    if not isinstance(target_tag, str) or not target_tag:
        raise ValueError(f"Rule '{rule.rule_type}' requires params.target_tag.")
    return [target_tag]


def no_tags(rule: ValidationRule) -> list[str]:
    """占位规则（如 ``regex``）：当前不依赖任何变量 tag。"""
    return []
