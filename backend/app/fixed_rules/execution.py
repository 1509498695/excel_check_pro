"""固定规则执行入口。"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.fixed_rules_schemas import FixedRulesConfig
from backend.app.execution_pipeline import run_execution_pipeline
from backend.app.fixed_rules.config_loader import load_fixed_rules_config, parse_raw_fixed_rules_config
from backend.app.fixed_rules.config_normalizer import validate_and_normalize_fixed_rules_config
from backend.app.fixed_rules.db_service import load_fixed_rules_config_from_db
from backend.app.fixed_rules.package_items_runtime import prepare_package_items_runtime_config
from backend.app.fixed_rules.task_tree_builder import build_fixed_rules_task_tree, _get_ordered_rules
from backend.app.models import Project
from backend.app.result_store import persist_execution_result
from backend.app.utils.formatter import build_execution_response


def execute_saved_fixed_rules(
    config: FixedRulesConfig | None = None,
    selected_rule_ids: list[str] | None = None,
) -> dict[str, object]:
    """执行固定规则。如果传入 config 则直接使用，否则从文件加载。"""
    if config is None:
        config = load_fixed_rules_config()
    ordered_rules = _get_ordered_rules(config, selected_rule_ids=selected_rule_ids)
    if not ordered_rules:
        raise ValueError("当前没有可执行的固定规则，请先配置规则再执行。")
    task_tree = build_fixed_rules_task_tree(config, selected_rule_ids=selected_rule_ids)
    start = time.perf_counter()
    execution_artifacts = run_execution_pipeline(task_tree)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    total_rows_scanned = sum(
        len(frame) for frame in execution_artifacts["loaded_variables"].values()
    )
    return build_execution_response(
        abnormal_results=execution_artifacts["abnormal_results"],
        execution_time_ms=elapsed_ms,
        total_rows_scanned=total_rows_scanned,
        failed_sources=execution_artifacts["failed_sources"],
        msg="Execution Completed",
    )


async def execute_fixed_rules_for_project(
    db: AsyncSession,
    project_id: int,
    *,
    user_scope: str | None = None,
    selected_rule_ids: list[str] | None = None,
) -> dict[str, Any]:
    """以项目级配置执行项目校验，落库后返回执行摘要。

    供 ``/fixed-rules/execute`` 与飞书机器人事件入口共用，确保两者执行链路、
    持久化、协议字段完全一致。

    - 配置读取失败或不存在 → 抛 ``ValueError("当前项目尚未配置固定规则")``。
    - 其余 ``FileNotFoundError`` / ``ValueError`` / ``ImportError`` /
      ``NotImplementedError`` 由调用层翻译为 4xx；本函数不吞这些异常。
    - ``user_scope`` 预留 SVN 凭据维度（与 ``run_saved_fixed_rules_svn_update``
      保持一致），当前 ``run_execution_pipeline`` 还未消费该字段，本期保持透传。
    """
    raw = await load_fixed_rules_config_from_db(db, project_id)
    if raw is None:
        raise ValueError("当前项目尚未配置固定规则")

    parsed = parse_raw_fixed_rules_config(raw)
    config = validate_and_normalize_fixed_rules_config(parsed)
    runtime_preparation = await prepare_package_items_runtime_config(
        config,
        db=db,
        project_id=project_id,
        selected_rule_ids=selected_rule_ids,
    )
    task_tree = build_fixed_rules_task_tree(
        runtime_preparation.config,
        selected_rule_ids=selected_rule_ids,
    )

    start = time.perf_counter()
    execution_artifacts = run_execution_pipeline(
        task_tree,
        project_id=project_id,
        preloaded_variable_frames=runtime_preparation.preloaded_variable_frames,
    )
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    abnormal_results = execution_artifacts["abnormal_results"]
    total_rows_scanned = sum(
        len(frame) for frame in execution_artifacts["loaded_variables"].values()
    )
    failed_sources = execution_artifacts["failed_sources"]

    result_id = await persist_execution_result(
        db,
        scope_type="fixed_rules",
        project_id=project_id,
        user_id=None,
        abnormal_results=abnormal_results,
        execution_time_ms=elapsed_ms,
        total_rows_scanned=total_rows_scanned,
        failed_sources=failed_sources,
    )

    project = await db.get(Project, project_id)
    project_name = project.name if project is not None else f"项目 {project_id}"

    return {
        "result_id": result_id,
        "total_rows_scanned": total_rows_scanned,
        "failed_sources": failed_sources,
        "abnormal_results": abnormal_results,
        "execution_time_ms": elapsed_ms,
        "project_name": project_name,
        "package_items_parse": runtime_preparation.parse_metadata,
    }
