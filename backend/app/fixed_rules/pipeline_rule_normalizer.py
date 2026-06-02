"""多组合变量串行规则归一化。"""

from __future__ import annotations

from backend.app.api.fixed_rules_schemas import MultiCompositePipelineConfig, MultiCompositePipelineNode
from backend.app.api.schemas import VariableTag
from backend.app.fixed_rules.config_common import (
    SUPPORTED_COMPOSITE_FILTER_OPERATORS,
    SUPPORTED_MULTI_PIPELINE_ASSERTION_OPERATORS,
    _collect_composite_available_fields,
    _normalize_display_field,
)
from backend.app.fixed_rules.composite_rule_normalizer import _normalize_composite_conditions


def _normalize_multi_composite_pipeline_config(
    *,
    rule_id: str,
    pipeline_config: MultiCompositePipelineConfig | None,
    variable_map: dict[str, VariableTag],
) -> MultiCompositePipelineConfig:
    """校验并规范多组合变量串行校验配置。"""
    if pipeline_config is None:
        raise ValueError(f"规则 '{rule_id}' 缺少 pipeline_config。")
    if not pipeline_config.nodes:
        raise ValueError(f"规则 '{rule_id}' 至少需要一个组合变量节点。")

    normalized_nodes: list[MultiCompositePipelineNode] = []
    seen_node_ids: set[str] = set()

    for node_index, node in enumerate(pipeline_config.nodes, start=1):
        node_id = node.node_id.strip()
        variable_tag = (node.variable_tag or "").strip()
        if not node_id:
            raise ValueError(f"规则 '{rule_id}' 的节点 {node_index} 缺少 node_id。")
        if node_id in seen_node_ids:
            raise ValueError(
                f"规则 '{rule_id}' 的节点存在重复 node_id '{node_id}'。"
            )
        if not variable_tag:
            raise ValueError(f"规则 '{rule_id}' 的节点 {node_index} 缺少 variable_tag。")
        if variable_tag not in variable_map:
            raise ValueError(
                f"规则 '{rule_id}' 的节点 {node_index} 引用了不存在的组合变量 '{variable_tag}'。"
            )

        variable = variable_map[variable_tag]
        if (variable.variable_kind or "single") != "composite":
            raise ValueError(
                f"规则 '{rule_id}' 的节点 {node_index} 引用了单变量 '{variable_tag}'，"
                "多组合变量串行校验仅支持组合变量。"
            )

        available_fields = _collect_composite_available_fields(variable)
        display_field = _normalize_display_field(
            rule_id=rule_id,
            variable=variable,
            display_field=node.display_field,
        )
        filters = _normalize_composite_conditions(
            rule_id=rule_id,
            conditions=node.filters,
            section_label=f"节点 {node_index} 的前置过滤",
            available_fields=available_fields,
            allowed_operators=SUPPORTED_COMPOSITE_FILTER_OPERATORS,
        )
        assertions = _normalize_composite_conditions(
            rule_id=rule_id,
            conditions=node.assertions,
            section_label=f"节点 {node_index} 的最终判定",
            available_fields=available_fields,
            allowed_operators=SUPPORTED_MULTI_PIPELINE_ASSERTION_OPERATORS,
        )
        if not assertions:
            raise ValueError(f"规则 '{rule_id}' 的节点 {node_index} 至少需要一条最终判定。")

        normalized_nodes.append(
            MultiCompositePipelineNode(
                node_id=node_id,
                variable_tag=variable_tag,
                display_field=display_field,
                filters=filters,
                assertions=assertions,
            )
        )
        seen_node_ids.add(node_id)

    return MultiCompositePipelineConfig(nodes=normalized_nodes)
