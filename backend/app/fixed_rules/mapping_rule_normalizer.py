"""多组合变量映射规则归一化。"""

from __future__ import annotations

from backend.app.api.fixed_rules_schemas import (
    FixedRulesConfigIssue,
    MultiCompositeMappingConfig,
    MultiCompositeMappingExclusionRange,
    MultiCompositeMappingFilter,
    MultiCompositeMappingNode,
)
from backend.app.api.schemas import VariableTag
from backend.app.fixed_rules.config_common import (
    SUPPORTED_COMPOSITE_FILTER_OPERATORS,
    _append_config_issue,
    _collect_composite_available_fields,
    _normalize_display_field,
)
from backend.app.fixed_rules.composite_rule_normalizer import _normalize_composite_conditions
from backend.app.rules.domain.operators import parse_expected_value_set


def _normalize_multi_composite_mapping_config(
    *,
    rule_id: str,
    mapping_config: MultiCompositeMappingConfig | None,
    variable_map: dict[str, VariableTag],
    allow_legacy_mapping_config: bool = False,
    config_issues: list[FixedRulesConfigIssue] | None = None,
    issue_keys: set[tuple[str, str | None, str | None, str | None, str]] | None = None,
) -> MultiCompositeMappingConfig:
    """校验并规范多组映射校验配置。"""
    if mapping_config is None:
        raise ValueError(f"规则 '{rule_id}' 缺少 mapping_config。")
    if not mapping_config.nodes:
        raise ValueError(f"规则 '{rule_id}' 至少需要一个映射节点。")

    normalized_nodes: list[MultiCompositeMappingNode] = []
    seen_node_ids: set[str] = set()

    for node_index, node in enumerate(mapping_config.nodes, start=1):
        node_id = node.node_id.strip()
        variable_tag = (node.variable_tag or "").strip()
        if not node_id:
            raise ValueError(f"规则 '{rule_id}' 的映射节点 {node_index} 缺少 node_id。")
        if node_id in seen_node_ids:
            raise ValueError(
                f"规则 '{rule_id}' 的映射节点存在重复 node_id '{node_id}'。"
            )
        if not variable_tag:
            raise ValueError(f"规则 '{rule_id}' 的映射节点 {node_index} 缺少 variable_tag。")
        if variable_tag not in variable_map:
            raise ValueError(
                f"规则 '{rule_id}' 的映射节点 {node_index} 引用了不存在的组合变量 '{variable_tag}'。"
            )

        variable = variable_map[variable_tag]
        if (variable.variable_kind or "single") != "composite":
            raise ValueError(
                f"规则 '{rule_id}' 的映射节点 {node_index} 引用了单变量 '{variable_tag}'，"
                "多组映射校验仅支持组合变量。"
            )

        available_fields = _collect_composite_available_fields(variable)
        display_field = _normalize_display_field(
            rule_id=rule_id,
            variable=variable,
            display_field=node.display_field,
        )
        filters = _normalize_multi_composite_mapping_filters(
            rule_id=rule_id,
            conditions=node.filters,
            node_index=node_index,
            available_fields=available_fields,
            allow_legacy_mapping_config=allow_legacy_mapping_config,
            config_issues=config_issues,
            issue_keys=issue_keys,
        )
        if not filters:
            if allow_legacy_mapping_config and _has_legacy_mapping_node_content(node):
                normalized_nodes.append(
                    MultiCompositeMappingNode(
                        node_id=node_id,
                        variable_tag=variable_tag,
                        display_field=display_field,
                        filters=[],
                    )
                )
                seen_node_ids.add(node_id)
                continue
            raise ValueError(f"规则 '{rule_id}' 的映射节点 {node_index} 至少需要一条筛选条件。")

        normalized_nodes.append(
            MultiCompositeMappingNode(
                node_id=node_id,
                variable_tag=variable_tag,
                display_field=display_field,
                filters=filters,
            )
        )
        seen_node_ids.add(node_id)

    return MultiCompositeMappingConfig(nodes=normalized_nodes)


def _has_legacy_mapping_node_content(node: MultiCompositeMappingNode) -> bool:
    """识别旧版字段检查配置，读取时允许丢弃，保存时仍要求重配筛选。"""
    return bool(node.field_checks or node.field or node.ranges)


def _normalize_multi_composite_mapping_filters(
    *,
    rule_id: str,
    conditions: list[MultiCompositeMappingFilter],
    node_index: int,
    available_fields: list[str],
    allow_legacy_mapping_config: bool = False,
    config_issues: list[FixedRulesConfigIssue] | None = None,
    issue_keys: set[tuple[str, str | None, str | None, str | None, str]] | None = None,
) -> list[MultiCompositeMappingFilter]:
    """校验并规范单个映射节点下的筛选检查列表。"""
    normalized_conditions = _normalize_composite_conditions(
        rule_id=rule_id,
        conditions=conditions,
        section_label=f"映射节点 {node_index} 的筛选条件",
        available_fields=available_fields,
        allowed_operators=SUPPORTED_COMPOSITE_FILTER_OPERATORS,
    )
    normalized_filters: list[MultiCompositeMappingFilter] = []

    for filter_index, condition in enumerate(conditions, start=1):
        normalized_condition = normalized_conditions[filter_index - 1]
        exclusion_ranges = _normalize_multi_composite_mapping_exclusion_ranges(
            rule_id=rule_id,
            node_index=node_index,
            filter_index=filter_index,
            ranges=condition.exclusion_ranges,
            allow_legacy_mapping_config=allow_legacy_mapping_config,
            config_issues=config_issues,
            issue_keys=issue_keys,
        )
        normalized_filters.append(
            MultiCompositeMappingFilter(
                **normalized_condition.model_dump(mode="python"),
                exclusion_ranges=exclusion_ranges,
            )
        )

    return normalized_filters


def _normalize_multi_composite_mapping_exclusion_ranges(
    *,
    rule_id: str,
    node_index: int,
    filter_index: int,
    ranges: list[MultiCompositeMappingExclusionRange],
    allow_legacy_mapping_config: bool = False,
    config_issues: list[FixedRulesConfigIssue] | None = None,
    issue_keys: set[tuple[str, str | None, str | None, str | None, str]] | None = None,
) -> list[MultiCompositeMappingExclusionRange]:
    """校验并规范单条筛选失败后的排除行号范围。"""
    if not ranges:
        return []

    normalized_ranges: list[MultiCompositeMappingExclusionRange] = []
    seen_range_ids: set[str] = set()

    for range_index, row_range in enumerate(ranges, start=1):
        range_id = row_range.range_id.strip()
        start_row = row_range.start_row
        end_row = row_range.end_row
        expected_value = (row_range.expected_value or "").strip()

        if not range_id:
            raise ValueError(
                f"规则 '{rule_id}' 的映射节点 {node_index} 筛选条件 {filter_index} "
                f"第 {range_index} 段排除范围缺少 range_id。"
            )
        if range_id in seen_range_ids:
            raise ValueError(
                f"规则 '{rule_id}' 的映射节点 {node_index} 筛选条件 {filter_index} "
                f"存在重复 range_id '{range_id}'。"
            )
        if start_row <= 0 or end_row <= 0:
            raise ValueError(
                f"规则 '{rule_id}' 的映射节点 {node_index} 筛选条件 {filter_index} "
                f"第 {range_index} 段排除范围行号必须大于 0。"
            )
        if start_row > end_row:
            raise ValueError(
                f"规则 '{rule_id}' 的映射节点 {node_index} 筛选条件 {filter_index} "
                f"第 {range_index} 段排除范围开始行不能大于结束行。"
            )
        if not expected_value:
            message = (
                f"规则 '{rule_id}' 的映射节点 {node_index} 筛选条件 {filter_index} "
                f"第 {range_index} 段排除范围缺少判定值。"
            )
            if allow_legacy_mapping_config and config_issues is not None:
                _append_config_issue(
                    config_issues,
                    issue_keys,
                    rule_id=rule_id,
                    message=f"{message} 请补齐后重新保存或执行。",
                )
            else:
                raise ValueError(message)
        else:
            try:
                parse_expected_value_set(expected_value)
            except ValueError as exc:
                raise ValueError(
                    f"规则 '{rule_id}' 的映射节点 {node_index} 筛选条件 {filter_index} "
                    f"第 {range_index} 段排除范围判定值至少需要一个固定值。"
                ) from exc

        seen_range_ids.add(range_id)
        normalized_ranges.append(
            MultiCompositeMappingExclusionRange(
                range_id=range_id,
                start_row=start_row,
                end_row=end_row,
                expected_value=expected_value or None,
            )
        )

    return normalized_ranges
