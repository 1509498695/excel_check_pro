"""Variable mapping helpers for workbench-to-fixed-rules import."""

from __future__ import annotations

from backend.app.api.schemas import VariableTag
from backend.app.fixed_rules.importer.schemas import ImportConflict, ImportItemResult


def variable_same_definition(left: VariableTag, right: VariableTag) -> bool:
    """Return whether two variables point at the same source/sheet/fields."""
    return (
        left.source_id == right.source_id
        and left.sheet == right.sheet
        and (left.variable_kind or "single") == (right.variable_kind or "single")
        and (left.column or "") == (right.column or "")
        and (left.columns or []) == (right.columns or [])
        and (left.key_column or "") == (right.key_column or "")
        and (left.filters or []) == (right.filters or [])
        and bool(left.append_index_to_key) == bool(right.append_index_to_key)
    )


def remap_variable_source(variable: VariableTag, next_source_id: str) -> VariableTag:
    """Copy a personal variable and point it at the mapped project source id."""
    return VariableTag(
        tag=variable.tag,
        source_id=next_source_id,
        sheet=variable.sheet,
        variable_kind=variable.variable_kind or "single",
        column=variable.column,
        columns=variable.columns,
        key_column=variable.key_column,
        filters=variable.filters,
        append_index_to_key=variable.append_index_to_key,
        expected_type=variable.expected_type,
    )


def map_variables(
    personal_variables: list[VariableTag],
    project_variables: list[VariableTag],
    *,
    source_id_map: dict[str, str],
    skipped_source_ids: set[str],
    tag_resolutions: dict[str, str],
) -> tuple[list[VariableTag], dict[str, str], list[ImportItemResult], list[ImportConflict], set[str]]:
    """Map personal variables into the project config."""
    project_by_tag = {variable.tag: variable for variable in project_variables}
    existing_tags = set(project_by_tag)
    imported_variables: list[VariableTag] = []
    tag_map: dict[str, str] = {}
    results: list[ImportItemResult] = []
    conflicts: list[ImportConflict] = []
    skipped_tags: set[str] = set()

    for variable in personal_variables:
        if variable.source_id in skipped_source_ids or variable.source_id not in source_id_map:
            skipped_tags.add(variable.tag)
            results.append(
                ImportItemResult(
                    item_id=variable.tag,
                    status="skipped",
                    message="变量依赖的数据源已跳过。",
                )
            )
            continue

        requested_tag = tag_resolutions.get(variable.tag, variable.tag).strip() or variable.tag
        next_variable = remap_variable_source(variable, source_id_map[variable.source_id])
        if requested_tag != variable.tag:
            next_variable = next_variable.model_copy(update={"tag": requested_tag})

        existing = project_by_tag.get(next_variable.tag)
        if existing and variable_same_definition(next_variable, existing):
            tag_map[variable.tag] = existing.tag
            results.append(
                ImportItemResult(
                    item_id=variable.tag,
                    status="reuse",
                    message="项目校验已存在同定义变量，复用。",
                    next_id=existing.tag,
                )
            )
            continue

        if existing:
            next_variable = next_variable.model_copy(
                update={
                    "tag": make_unique_variable_tag(next_variable.tag, existing_tags),
                }
            )

        if next_variable.tag in existing_tags:
            next_variable = next_variable.model_copy(
                update={
                    "tag": make_unique_variable_tag(next_variable.tag, existing_tags),
                }
            )

        existing_tags.add(next_variable.tag)
        tag_map[variable.tag] = next_variable.tag
        imported_variables.append(next_variable)
        results.append(
            ImportItemResult(
                item_id=variable.tag,
                status="new",
                message="变量 tag 冲突，已自动追加“-导入”后缀。"
                if next_variable.tag != variable.tag
                else "新增变量。",
                next_id=next_variable.tag,
            )
        )

    return imported_variables, tag_map, results, conflicts, skipped_tags


def make_unique_variable_tag(tag: str, existing_tags: set[str]) -> str:
    """Create a unique variable tag by appending -导入 while preserving bracket tags."""
    normalized = tag.strip() or "[variable]"
    if normalized.startswith("[") and normalized.endswith("]"):
        base = f"{normalized[:-1]}-导入]"
    else:
        base = f"{normalized}-导入"
    if base not in existing_tags:
        return base
    index = 2
    while True:
        if normalized.startswith("[") and normalized.endswith("]"):
            candidate = f"{normalized[:-1]}-导入-{index}]"
        else:
            candidate = f"{normalized}-导入-{index}"
        if candidate not in existing_tags:
            return candidate
        index += 1
