"""固定规则导入变量映射测试。"""

from __future__ import annotations

from backend.app.api.schemas import CompositeCondition, VariableTag
from backend.app.fixed_rules.importer.variable_mapper import (
    remap_variable_source,
    variable_same_definition,
)


def _composite_variable(filters: list[CompositeCondition] | None = None) -> VariableTag:
    return VariableTag(
        tag="[items-composite]",
        source_id="src_items",
        sheet="items",
        variable_kind="composite",
        columns=["INT_ID", "Name"],
        key_column="INT_ID",
        filters=filters or [],
        expected_type="json",
    )


def test_variable_same_definition_includes_composite_filters() -> None:
    """筛选条件不同的组合变量应视为不同定义。"""
    without_filters = _composite_variable()
    with_filters = _composite_variable(
        [
            CompositeCondition(
                condition_id="env-prod",
                field="Env",
                operator="eq",
                value_source="literal",
                expected_value="prod",
            )
        ]
    )

    assert variable_same_definition(without_filters, with_filters) is False


def test_remap_variable_source_copies_composite_filters() -> None:
    """导入变量改写数据源时应完整保留筛选定义。"""
    variable = _composite_variable(
        [
            CompositeCondition(
                condition_id="env-field",
                field="Env",
                operator="eq",
                value_source="field",
                expected_field="TargetEnv",
            )
        ]
    )

    remapped = remap_variable_source(variable, "project_src")

    assert remapped.source_id == "project_src"
    assert remapped.filters == variable.filters
