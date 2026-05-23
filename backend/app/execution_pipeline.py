"""共享执行流水线：加载数据源、过滤规则并运行引擎。"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd

from backend.app.api.schemas import DataSource, TaskTree, ValidationRule, VariableTag
from backend.app.loaders.feishu_reader import load_feishu_variables_by_source
from backend.app.loaders.local_reader import load_variables_by_source
from backend.app.loaders.svn_manager import sync_svn_source
from backend.app.rules.engine_core import RULE_REGISTRY, execute_rules
from backend.config import settings


def run_execution_pipeline(
    task_tree: TaskTree,
    *,
    project_id: int | None = None,
) -> dict[str, Any]:
    """执行完整主干流程，并返回规则执行所需的中间结果。"""
    source_map = _build_source_map(task_tree.sources)
    grouped_variables = _group_variables_by_source(task_tree.variables, source_map)
    load_result = _load_sources_concurrently(
        source_map,
        grouped_variables,
        project_id=project_id,
    )
    executable_rules = _filter_executable_rules(
        _filter_rules_by_selected_ids(task_tree.rules, task_tree.selected_rule_ids),
        grouped_variables=grouped_variables,
        loaded_variables=load_result["loaded_variables"],
        failed_sources=set(load_result["failed_sources"]),
    )

    executable_task_tree = task_tree.model_copy(update={"rules": executable_rules})
    abnormal_results = execute_rules(
        executable_task_tree,
        load_result["loaded_variables"],
    )

    return {
        "loaded_variables": load_result["loaded_variables"],
        "failed_sources": load_result["failed_sources"],
        "abnormal_results": abnormal_results,
    }


def filter_rules_by_selected_ids(
    rules: list[ValidationRule],
    selected_rule_ids: list[str] | None,
) -> list[ValidationRule]:
    """按传入的 rule_id 子集过滤本次需要执行的规则。"""
    return _filter_rules_by_selected_ids(rules, selected_rule_ids)


def _filter_rules_by_selected_ids(
    rules: list[ValidationRule],
    selected_rule_ids: list[str] | None,
) -> list[ValidationRule]:
    if selected_rule_ids is None:
        return rules

    selected_rule_id_set = {
        rule_id.strip()
        for rule_id in selected_rule_ids
        if isinstance(rule_id, str) and rule_id.strip()
    }
    if not selected_rule_id_set:
        return []

    return [
        rule
        for rule in rules
        if isinstance(rule.rule_id, str) and rule.rule_id.strip() in selected_rule_id_set
    ]


def _build_source_map(sources: list[DataSource]) -> dict[str, DataSource]:
    source_map: dict[str, DataSource] = {}

    for source in sources:
        if source.id in source_map:
            raise ValueError(f"Duplicate source id is not allowed: '{source.id}'.")
        source_map[source.id] = source

    return source_map


def _group_variables_by_source(
    variables: list[VariableTag], source_map: dict[str, DataSource]
) -> dict[str, list[VariableTag]]:
    grouped_variables: dict[str, list[VariableTag]] = defaultdict(list)
    seen_tags: set[str] = set()

    for variable in variables:
        if variable.tag in seen_tags:
            raise ValueError(
                f"Duplicate variable tags are not allowed: '{variable.tag}'."
            )
        seen_tags.add(variable.tag)

        if variable.source_id not in source_map:
            raise ValueError(
                f"Variable tag '{variable.tag}' references unknown source_id "
                f"'{variable.source_id}'."
            )
        grouped_variables[variable.source_id].append(variable)

    return grouped_variables


def _load_sources_concurrently(
    source_map: dict[str, DataSource],
    grouped_variables: dict[str, list[VariableTag]],
    *,
    project_id: int | None = None,
) -> dict[str, Any]:
    loaded_variables: dict[str, pd.DataFrame] = {}
    failed_sources: list[str] = []

    source_ids = [
        source_id for source_id in source_map if grouped_variables.get(source_id)
    ]
    if not source_ids:
        return {"loaded_variables": {}, "failed_sources": []}

    with ThreadPoolExecutor(
        max_workers=settings.default_thread_pool_size
    ) as executor:
        future_map = {
            executor.submit(
                _load_single_source,
                source_map[source_id],
                grouped_variables[source_id],
                project_id,
            ): source_id
            for source_id in source_ids
        }

        for future in as_completed(future_map):
            source_id = future_map[future]
            try:
                source_frames = future.result()
            except ImportError as exc:
                raise ValueError(str(exc)) from exc
            except (FileNotFoundError, ValueError, NotImplementedError):
                failed_sources.append(source_id)
                continue

            overlap_tags = set(loaded_variables).intersection(source_frames)
            if overlap_tags:
                raise ValueError(
                    f"Duplicate variable tags produced while loading sources: "
                    f"{sorted(overlap_tags)}."
                )
            loaded_variables.update(source_frames)

    return {
        "loaded_variables": loaded_variables,
        "failed_sources": failed_sources,
    }


def _load_single_source(
    source: DataSource,
    variables_for_source: list[VariableTag],
    project_id: int | None = None,
) -> dict[str, pd.DataFrame]:
    if source.type == "local_excel":
        return load_variables_by_source(source, variables_for_source)

    if source.type == "local_csv":
        raise ValueError("CSV 数据源已不再支持，请删除后改用 Excel 或 SVN Excel。")

    if source.type == "feishu":
        return load_feishu_variables_by_source(
            source,
            variables_for_source,
            project_id=project_id,
        )

    if source.type == "svn":
        # 远端 URL 直接走缓存机制；本地工作副本仍走旧 sync_svn_source 触发 svn update。
        from backend.app.loaders.svn_cache import is_remote_svn_locator

        locator = (source.pathOrUrl or source.path or source.url or "").strip()
        if not is_remote_svn_locator(locator):
            sync_svn_source(source=source)
        return load_variables_by_source(source, variables_for_source)

    raise ValueError(f"Unsupported source type: '{source.type}'.")


def _filter_executable_rules(
    rules: list[ValidationRule],
    *,
    grouped_variables: dict[str, list[VariableTag]],
    loaded_variables: dict[str, pd.DataFrame],
    failed_sources: set[str],
) -> list[ValidationRule]:
    tag_to_source_id = {
        variable.tag: source_id
        for source_id, variables in grouped_variables.items()
        for variable in variables
    }

    executable_rules: list[ValidationRule] = []
    for rule in rules:
        _ensure_rule_supported(rule)
        dependent_tags = _extract_rule_tags(rule)

        missing_tags = [tag for tag in dependent_tags if tag not in tag_to_source_id]
        if missing_tags:
            raise ValueError(
                f"Rule '{rule.rule_type}' references unknown tag(s): {missing_tags}."
            )

        if any(tag_to_source_id[tag] in failed_sources for tag in dependent_tags):
            continue

        unresolved_tags = [tag for tag in dependent_tags if tag not in loaded_variables]
        if unresolved_tags:
            raise ValueError(
                f"Rule '{rule.rule_type}' depends on unloaded tag(s): {unresolved_tags}."
            )

        executable_rules.append(rule)

    return executable_rules


def _ensure_rule_supported(rule: ValidationRule) -> None:
    if rule.rule_type not in RULE_REGISTRY:
        raise ValueError(f"Unsupported rule_type: '{rule.rule_type}'.")


def _extract_rule_tags(rule: ValidationRule) -> list[str]:
    return RULE_REGISTRY[rule.rule_type].dependent_tags(rule)
