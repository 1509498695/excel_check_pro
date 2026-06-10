"""工作台持久化接口：按 project_id + user_id 隔离。"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.fixed_rules_schemas import (
    EventTaskAiSuggestionRequest,
    FixedRulesConfig,
    EventTaskPreviewDetailRow,
    EventTaskPreviewRequest,
    EventTaskPreviewResponse,
    EventTaskPreviewResult,
    EventTaskPreviewSampleRow,
    EventTaskRewardValidationRequest,
    PackageItemsPreviewDetailRow,
    PackageItemsPreviewFieldMapping,
    PackageItemsPreviewRequest,
    PackageItemsPreviewResponse,
    PackageItemsPreviewResult,
)
from backend.app.api.schemas import DataSource, VariableTag
from backend.app.auth.dependencies import CurrentUserContext, get_current_user
from backend.app.database import get_db
from backend.app.fixed_rules.service import run_saved_fixed_rules_svn_update
from backend.app.integrations.feishu_client import FeishuClientError
from backend.app.loaders.feishu_reader import FeishuSheetError
from backend.app.models import WorkbenchConfigRecord
from backend.app.services.package_items_parser import preview_package_items_from_feishu
from backend.app.services.event_task_parser import (
    load_event_task_config_frame,
    preview_event_tasks_from_feishu,
)
from backend.app.services.event_task_ai_advisor import (
    EventTaskAiAdviceResult,
    EventTaskAiAdvisorContext,
    advise_event_task_validation,
)
from backend.app.services.event_task_variable_parser import parseEventTaskVariables
from backend.app.services.event_task_reward_validator import (
    EventTaskExtraVariableTask,
    EventTaskRewardValidationSummary,
    EventTaskRewardValidationTaskResult,
    validateEventTaskRewards,
)
from backend.app.services.reward_parser import RewardCountMismatch, RewardItem

router = APIRouter(prefix="/workbench", tags=["workbench"])

_SOURCE_FIELDS = ("id", "type", "path", "url", "pathOrUrl", "token")
_SKIPPED_ROW_WARNING_PATTERN = re.compile(r"^跳过第\s*\d+\s*行")


def _build_workbench_svn_update_config(payload: object) -> FixedRulesConfig:
    """从个人校验持久化配置中提取 SVN 更新需要的最小配置。"""
    if not isinstance(payload, dict):
        raise ValueError("个人校验配置格式不正确。")

    raw_sources = payload.get("sources")
    raw_svn_presets = payload.get("svn_path_replacement_presets")
    raw_selected_svn_preset = payload.get("selected_svn_path_replacement_preset")
    config_payload = {
        "version": 6,
        "configured": bool(payload),
        "sources": raw_sources if isinstance(raw_sources, list) else [],
        "svn_path_replacement_presets": raw_svn_presets
        if isinstance(raw_svn_presets, list)
        else [],
        "selected_svn_path_replacement_preset": raw_selected_svn_preset
        if isinstance(raw_selected_svn_preset, str)
        else None,
    }
    return FixedRulesConfig.model_validate(config_payload)


async def _load_workbench_config_payload(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
) -> dict[str, Any]:
    result = await db.execute(
        select(WorkbenchConfigRecord).where(
            WorkbenchConfigRecord.project_id == project_id,
            WorkbenchConfigRecord.user_id == user_id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise ValueError("当前个人校验尚未配置工作台。")

    try:
        payload = json.loads(record.config_json)
    except json.JSONDecodeError as exc:
        raise ValueError("个人校验配置读取失败：配置内容不是合法 JSON。") from exc
    if not isinstance(payload, dict):
        raise ValueError("个人校验配置格式不正确。")
    return payload


async def _load_workbench_feishu_source(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    source_id: str,
) -> DataSource:
    payload = await _load_workbench_config_payload(
        db,
        project_id=project_id,
        user_id=user_id,
    )
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        raise ValueError("个人校验数据源配置格式不正确。")

    source_payload: dict[str, Any] | None = None
    for raw_source in raw_sources:
        if not isinstance(raw_source, dict):
            continue
        if str(raw_source.get("id") or "").strip() != source_id:
            continue
        source_payload = {
            field_name: raw_source.get(field_name)
            for field_name in _SOURCE_FIELDS
            if field_name in raw_source
        }
        break

    if source_payload is None:
        raise ValueError(f"未找到飞书数据源：{source_id}")

    try:
        source = DataSource.model_validate(source_payload)
    except ValidationError as exc:
        raise ValueError(f"数据源 '{source_id}' 配置格式不正确。") from exc

    if source.type != "feishu":
        raise ValueError(f"数据源 '{source_id}' 不是飞书数据源")
    return source


async def _load_workbench_variable_context(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    variable_tag: str,
) -> tuple[DataSource, VariableTag]:
    payload = await _load_workbench_config_payload(
        db,
        project_id=project_id,
        user_id=user_id,
    )
    raw_sources = payload.get("sources")
    raw_variables = payload.get("variables")
    if not isinstance(raw_sources, list) or not isinstance(raw_variables, list):
        raise ValueError("个人校验变量配置格式不正确。")

    variable_payload: dict[str, Any] | None = None
    for raw_variable in raw_variables:
        if not isinstance(raw_variable, dict):
            continue
        if str(raw_variable.get("tag") or "").strip() == variable_tag:
            variable_payload = dict(raw_variable)
            break
    if variable_payload is None:
        raise ValueError(f"未找到任务配置组合变量：{variable_tag}")

    try:
        variable = VariableTag.model_validate(variable_payload)
    except ValidationError as exc:
        raise ValueError(f"任务配置组合变量 '{variable_tag}' 格式不正确。") from exc

    source_payload: dict[str, Any] | None = None
    for raw_source in raw_sources:
        if not isinstance(raw_source, dict):
            continue
        if str(raw_source.get("id") or "").strip() == variable.source_id:
            source_payload = {
                field_name: raw_source.get(field_name)
                for field_name in _SOURCE_FIELDS
                if field_name in raw_source
            }
            break
    if source_payload is None:
        raise ValueError(f"未找到任务配置组合变量来源：{variable.source_id}")

    try:
        source = DataSource.model_validate(source_payload)
    except ValidationError as exc:
        raise ValueError(f"任务配置组合变量来源 '{variable.source_id}' 格式不正确。") from exc
    return source, variable


def _split_package_id_filter(value: str | None) -> list[str]:
    package_ids: list[str] = []
    seen: set[str] = set()
    for raw_item in (value or "").replace("，", ",").split(","):
        package_id = raw_item.strip()
        if not package_id or package_id in seen:
            continue
        seen.add(package_id)
        package_ids.append(package_id)
    return package_ids


def _build_package_items_field_mapping(
    preview: PackageItemsPreviewResult,
) -> PackageItemsPreviewFieldMapping | None:
    mapping = preview.field_mapping
    first_range = preview.detail_ranges[0] if preview.detail_ranges else None
    if not any((mapping.package_id, mapping.item_id, mapping.count, first_range)):
        return None
    return PackageItemsPreviewFieldMapping(
        package_id_column=mapping.package_id,
        item_id_column=mapping.item_id,
        count_column=mapping.count,
        header_row_index=first_range.header_row if first_range else None,
        detail_start_row_index=first_range.start_row if first_range else None,
        detail_end_row_index=first_range.end_row if first_range else None,
    )


def _filter_package_preview_rows(
    preview_rows: list[PackageItemsPreviewDetailRow],
    *,
    requested_package_ids: list[str],
) -> list[PackageItemsPreviewDetailRow]:
    requested_set = set(requested_package_ids)
    return [row for row in preview_rows if row.package_id in requested_set]


def _filter_package_preview_warnings(
    warnings: list[str],
    *,
    parse_status: str,
) -> list[str]:
    if parse_status != "success":
        return warnings
    return [
        warning
        for warning in warnings
        if not _SKIPPED_ROW_WARNING_PATTERN.match(warning)
    ]


def _build_package_items_preview_response(
    preview: PackageItemsPreviewResult,
    payload: PackageItemsPreviewRequest,
) -> PackageItemsPreviewResponse:
    errors = list(preview.errors)
    warnings = _filter_package_preview_warnings(
        list(preview.warnings),
        parse_status=preview.parse_status,
    )
    selected_rows = list(preview.detail_rows)
    selected_package_ids = list(preview.package_ids)

    if payload.validation_scope == "specified":
        requested_ids = _split_package_id_filter(payload.package_id_filter)
        if not requested_ids:
            errors.append("请填写要预览的礼包 ID。")
            selected_rows = []
            selected_package_ids = []
        else:
            selected_rows = _filter_package_preview_rows(
                preview.detail_rows,
                requested_package_ids=requested_ids,
            )
            available_ids = {row.package_id for row in preview.detail_rows}
            available_ids.update(preview.package_ids)
            selected_package_ids = [
                package_id for package_id in requested_ids if package_id in available_ids
            ]
            missing_ids = [
                package_id for package_id in requested_ids if package_id not in available_ids
            ]
            if missing_ids:
                errors.append(f"未找到指定礼包 ID：{', '.join(missing_ids)}")

    success = preview.parse_status == "success" and not errors
    message = "解析成功。" if success else _preview_failure_message(errors)
    parse_strategy_used = "ai" if preview.parse_mode == "ai" else "manual"

    return PackageItemsPreviewResponse(
        success=success,
        message=message,
        warnings=warnings,
        errors=errors,
        field_mapping=_build_package_items_field_mapping(preview),
        package_ids=selected_package_ids,
        detail_row_count=len(selected_rows),
        preview_rows=selected_rows,
        raw_sheet_name=preview.raw_sheet_name,
        parse_strategy_used=parse_strategy_used,
        ai_used=preview.ai_used,
    )


def _preview_failure_message(errors: list[str]) -> str:
    if errors:
        return errors[0]
    return "解析失败，请检查飞书 Sheet 表头和数据。"


def _build_package_items_preview_failure(message: str) -> PackageItemsPreviewResponse:
    return PackageItemsPreviewResponse(
        success=False,
        message=message,
        errors=[message],
        package_ids=[],
        detail_row_count=0,
        preview_rows=[],
    )


def _split_task_group_id_filter(value: str | None) -> list[str]:
    task_group_ids: list[str] = []
    seen: set[str] = set()
    for raw_item in (value or "").replace("，", ",").split(","):
        task_group_id = raw_item.strip()
        if not task_group_id or task_group_id in seen:
            continue
        seen.add(task_group_id)
        task_group_ids.append(task_group_id)
    return task_group_ids


def _filter_event_task_preview_rows(
    preview_rows: list[EventTaskPreviewDetailRow],
    *,
    requested_task_group_ids: list[str],
) -> list[EventTaskPreviewDetailRow]:
    requested_set = set(requested_task_group_ids)
    return [row for row in preview_rows if row.task_group_id in requested_set]


def _build_event_task_sample_rows(
    preview_rows: list[EventTaskPreviewDetailRow],
    *,
    limit: int = 5,
) -> list[EventTaskPreviewSampleRow]:
    return [
        EventTaskPreviewSampleRow(
            rowIndex=row.row_index,
            taskGroupId=row.task_group_id,
            taskId=row.task_id,
            day=row.day,
            desc=row.task_desc,
            rewards=list(row.rewards),
            rawLoot=row.loot,
            warnings=list(row.warnings),
        )
        for row in preview_rows[:limit]
    ]


def _build_event_task_preview_response(
    preview: EventTaskPreviewResult,
    payload: EventTaskPreviewRequest,
    *,
    ai_advice: EventTaskAiAdviceResult | None = None,
) -> EventTaskPreviewResponse:
    errors = list(preview.errors)
    warnings = list(preview.warnings)
    selected_rows = list(preview.detail_rows)
    selected_task_group_ids = list(preview.task_group_ids)

    if payload.validation_scope == "specified":
        requested_ids = _split_task_group_id_filter(payload.task_group_id_filter)
        if not requested_ids:
            errors.append("请填写要预览的任务组 ID。")
            selected_rows = []
            selected_task_group_ids = []
        else:
            selected_rows = _filter_event_task_preview_rows(
                preview.detail_rows,
                requested_task_group_ids=requested_ids,
            )
            available_ids = {row.task_group_id for row in preview.detail_rows if row.task_group_id}
            selected_task_group_ids = [
                task_group_id for task_group_id in requested_ids if task_group_id in available_ids
            ]
            missing_ids = [
                task_group_id for task_group_id in requested_ids if task_group_id not in available_ids
            ]
            if missing_ids:
                errors.append(f"未找到指定任务组 ID：{', '.join(missing_ids)}")

    success = preview.parse_status == "success" and not errors
    message = "解析成功。" if success else _event_task_preview_failure_message(errors)
    parsed_rows = len(selected_rows)
    return EventTaskPreviewResponse(
        success=success,
        message=message,
        warnings=warnings,
        errors=errors,
        taskGroupIds=selected_task_group_ids,
        task_group_ids=selected_task_group_ids,
        totalRows=preview.total_rows,
        total_rows=preview.total_rows,
        parsedRows=parsed_rows,
        parsed_rows=parsed_rows,
        detail_row_count=parsed_rows,
        rewardGroupCount=preview.reward_group_count,
        reward_group_count=preview.reward_group_count,
        sampleRows=_build_event_task_sample_rows(selected_rows),
        preview_rows=selected_rows,
        rawSheetName=preview.raw_sheet_name,
        raw_sheet_name=preview.raw_sheet_name,
        parse_strategy_used="manual",
        ai_used=False,
        aiSuggestions=list(ai_advice.suggestions) if ai_advice else [],
        ai_suggestions=list(ai_advice.suggestions) if ai_advice else [],
        aiSuggestionWarnings=list(ai_advice.warnings) if ai_advice else [],
        ai_suggestion_warnings=list(ai_advice.warnings) if ai_advice else [],
        aiSuggestionUsed=ai_advice.used if ai_advice else False,
        ai_suggestion_used=ai_advice.used if ai_advice else False,
    )


def _event_task_preview_failure_message(errors: list[str]) -> str:
    if errors:
        return errors[0]
    return "解析失败，请检查飞书 Sheet 表头和数据。"


def _build_event_task_preview_failure(
    message: str,
    *,
    ai_advice: EventTaskAiAdviceResult | None = None,
) -> EventTaskPreviewResponse:
    return EventTaskPreviewResponse(
        success=False,
        message=message,
        errors=[message],
        taskGroupIds=[],
        task_group_ids=[],
        totalRows=0,
        total_rows=0,
        parsedRows=0,
        parsed_rows=0,
        detail_row_count=0,
        rewardGroupCount=0,
        reward_group_count=0,
        sampleRows=[],
        preview_rows=[],
        ai_used=False,
        aiSuggestions=list(ai_advice.suggestions) if ai_advice else [],
        ai_suggestions=list(ai_advice.suggestions) if ai_advice else [],
        aiSuggestionWarnings=list(ai_advice.warnings) if ai_advice else [],
        ai_suggestion_warnings=list(ai_advice.warnings) if ai_advice else [],
        aiSuggestionUsed=ai_advice.used if ai_advice else False,
        ai_suggestion_used=ai_advice.used if ai_advice else False,
    )


def _build_event_task_variable_data(
    frame: Any,
    *,
    task_group_field: str = "INT_ID",
    task_id_field: str = "INT_TaskID",
    task_desc_field: str = "STR_Desc",
    task_loot_field: str = "STR_Loot",
) -> dict[str, dict[str, Any]]:
    required_fields = [task_group_field, task_id_field, task_desc_field, task_loot_field]
    missing_fields = [field for field in required_fields if field not in frame.columns]
    if missing_fields:
        raise ValueError(f"组合变量缺少字段：{', '.join(missing_fields)}")

    variable_data: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        task_group_id = _normalize_id_text(row[task_group_field]) or ""
        row_index = _normalize_id_text(row.get("_row_index")) or "0"
        variable_key = str(row.get("__key__") or "").strip() or f"{task_group_id}_{row_index}"
        variable_data[variable_key] = {
            "INT_TaskID": row[task_id_field],
            "STR_Title": row["STR_Title"] if "STR_Title" in row.index else None,
            "STR_Desc": row[task_desc_field],
            "STR_Loot": row[task_loot_field],
        }
    return variable_data


def _build_event_task_validation_response(
    summary: EventTaskRewardValidationSummary,
    *,
    warnings: list[str],
    errors: list[str],
    raw_sheet_name: str | None,
    ai_advice: EventTaskAiAdviceResult | None = None,
) -> dict[str, Any]:
    return {
        "success": not errors,
        "message": "校验完成。" if not errors else errors[0],
        "warnings": warnings,
        "errors": errors,
        "total": summary.total,
        "passCount": summary.pass_count,
        "pass_count": summary.pass_count,
        "failCount": summary.fail_count,
        "fail_count": summary.fail_count,
        "unmatchedCount": summary.unmatched_count,
        "unmatched_count": summary.unmatched_count,
        "warningCount": summary.warning_count,
        "warning_count": summary.warning_count,
        "results": [
            _serialize_event_task_validation_result(result)
            for result in summary.results
        ],
        "extraVariableTasks": [
            _serialize_extra_variable_task(task)
            for task in summary.extra_variable_tasks
        ],
        "extra_variable_tasks": [
            _serialize_extra_variable_task(task)
            for task in summary.extra_variable_tasks
        ],
        "rawSheetName": raw_sheet_name,
        "raw_sheet_name": raw_sheet_name,
        **_serialize_event_task_ai_advice(ai_advice),
    }


def _build_event_task_validation_failure(
    message: str,
    *,
    ai_advice: EventTaskAiAdviceResult | None = None,
) -> dict[str, Any]:
    return {
        "success": False,
        "message": message,
        "warnings": [],
        "errors": [message],
        "total": 0,
        "passCount": 0,
        "pass_count": 0,
        "failCount": 0,
        "fail_count": 0,
        "unmatchedCount": 0,
        "unmatched_count": 0,
        "warningCount": 0,
        "warning_count": 0,
        "results": [],
        "extraVariableTasks": [],
        "extra_variable_tasks": [],
        "rawSheetName": None,
        "raw_sheet_name": None,
        **_serialize_event_task_ai_advice(ai_advice),
    }


def _serialize_event_task_ai_advice(
    advice: EventTaskAiAdviceResult | None,
) -> dict[str, Any]:
    suggestions = [
        suggestion.model_dump(mode="json")
        for suggestion in (advice.suggestions if advice else [])
    ]
    warnings = list(advice.warnings) if advice else []
    used = advice.used if advice else False
    return {
        "aiSuggestions": suggestions,
        "ai_suggestions": suggestions,
        "aiSuggestionWarnings": warnings,
        "ai_suggestion_warnings": warnings,
        "aiSuggestionUsed": used,
        "ai_suggestion_used": used,
    }


async def _build_event_task_ai_advice(
    *,
    ai_assist_mode: str,
    preview: EventTaskPreviewResult,
    db: AsyncSession,
    project_id: int,
    validation_summary: EventTaskRewardValidationSummary | None = None,
    force: bool = False,
) -> EventTaskAiAdviceResult:
    return await advise_event_task_validation(
        ai_assist_mode=ai_assist_mode,
        preview=preview,
        sheet_rows=preview.raw_values,
        sheet_name=preview.raw_sheet_name,
        validation_summary=validation_summary,
        force=force,
        context=EventTaskAiAdvisorContext(db=db, project_id=project_id),
    )


def _serialize_event_task_validation_result(
    result: EventTaskRewardValidationTaskResult,
) -> dict[str, Any]:
    return {
        "taskGroupId": result.task_group_id,
        "task_group_id": result.task_group_id,
        "taskDesc": result.task_desc,
        "task_desc": result.task_desc,
        "feishuRowIndex": result.feishu_row_index,
        "feishu_row_index": result.feishu_row_index,
        "variableKey": result.variable_key,
        "variable_key": result.variable_key,
        "variableTaskId": result.variable_task_id,
        "variable_task_id": result.variable_task_id,
        "matchStrategy": result.match_strategy,
        "match_strategy": result.match_strategy,
        "status": result.status,
        "expectedRewards": [_serialize_reward_item(reward) for reward in result.expected_rewards],
        "expected_rewards": [_serialize_reward_item(reward) for reward in result.expected_rewards],
        "actualRewards": [_serialize_reward_item(reward) for reward in result.actual_rewards],
        "actual_rewards": [_serialize_reward_item(reward) for reward in result.actual_rewards],
        "missingRewards": [_serialize_reward_item(reward) for reward in result.missing_rewards],
        "missing_rewards": [_serialize_reward_item(reward) for reward in result.missing_rewards],
        "extraRewards": [_serialize_reward_item(reward) for reward in result.extra_rewards],
        "extra_rewards": [_serialize_reward_item(reward) for reward in result.extra_rewards],
        "countMismatches": [
            _serialize_count_mismatch(mismatch) for mismatch in result.count_mismatches
        ],
        "count_mismatches": [
            _serialize_count_mismatch(mismatch) for mismatch in result.count_mismatches
        ],
        "duplicateWarnings": list(result.duplicate_warnings),
        "duplicate_warnings": list(result.duplicate_warnings),
        "parseWarnings": list(result.parse_warnings),
        "parse_warnings": list(result.parse_warnings),
        "errorMessage": result.error_message,
        "error_message": result.error_message,
    }


def _serialize_extra_variable_task(task: EventTaskExtraVariableTask) -> dict[str, Any]:
    return {
        "taskGroupId": task.task_group_id,
        "task_group_id": task.task_group_id,
        "taskDesc": task.task_desc,
        "task_desc": task.task_desc,
        "variableKey": task.variable_key,
        "variable_key": task.variable_key,
        "variableTaskId": task.variable_task_id,
        "variable_task_id": task.variable_task_id,
        "actualRewards": [_serialize_reward_item(reward) for reward in task.actual_rewards],
        "actual_rewards": [_serialize_reward_item(reward) for reward in task.actual_rewards],
        "parseWarnings": list(task.parse_warnings),
        "parse_warnings": list(task.parse_warnings),
    }


def _serialize_reward_item(reward: RewardItem) -> dict[str, Any]:
    return {
        "type": reward.type,
        "item_id": reward.item_id,
        "itemId": reward.item_id,
        "count": reward.count,
        "name": reward.name,
        "source": reward.source,
    }


def _serialize_count_mismatch(mismatch: RewardCountMismatch) -> dict[str, Any]:
    return {
        "item_id": mismatch.item_id,
        "itemId": mismatch.item_id,
        "expected_count": mismatch.expected_count,
        "expectedCount": mismatch.expected_count,
        "actual_count": mismatch.actual_count,
        "actualCount": mismatch.actual_count,
    }


def _normalize_id_text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"[+-]?\d+", text):
        return str(int(text))
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        return str(int(float(text)))
    return text


@router.get("/config")
async def get_workbench_config(
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """读取当前用户在当前项目下的工作台配置。"""
    project_id = ctx.require_project_member()

    result = await db.execute(
        select(WorkbenchConfigRecord).where(
            WorkbenchConfigRecord.project_id == project_id,
            WorkbenchConfigRecord.user_id == ctx.user_id,
        )
    )
    record = result.scalar_one_or_none()

    config = json.loads(record.config_json) if record else {}
    return {"code": 200, "msg": "ok", "data": config}


@router.put("/config")
async def save_workbench_config(
    payload: dict[str, Any],
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """保存工作台配置（前端 2 秒防抖自动调用）。"""
    project_id = ctx.require_project_member()

    result = await db.execute(
        select(WorkbenchConfigRecord).where(
            WorkbenchConfigRecord.project_id == project_id,
            WorkbenchConfigRecord.user_id == ctx.user_id,
        )
    )
    record = result.scalar_one_or_none()

    config_str = json.dumps(payload, ensure_ascii=False)

    if record:
        record.config_json = config_str
    else:
        record = WorkbenchConfigRecord(
            project_id=project_id,
            user_id=ctx.user_id,
            config_json=config_str,
        )
    db.add(record)
    await db.commit()

    return {"code": 200, "msg": "ok"}


@router.post("/package-items/preview")
async def preview_workbench_package_items(
    payload: PackageItemsPreviewRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """预览个人校验礼包规划 Sheet 的解析结果，不保存规则、不执行校验。"""
    project_id = ctx.require_project_member()

    try:
        source = await _load_workbench_feishu_source(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            source_id=payload.feishu_source_id,
        )
        preview = await preview_package_items_from_feishu(
            source,
            sheet_id=payload.sheet_id,
            parse_strategy=payload.parse_strategy,
            ai_parse_mode=payload.ai_parse_mode,
            db=db,
            project_id=project_id,
        )
        response = _build_package_items_preview_response(preview, payload)
    except (
        ValueError,
        FileNotFoundError,
        ImportError,
        FeishuClientError,
        FeishuSheetError,
    ) as exc:
        response = _build_package_items_preview_failure(str(exc))

    return {
        "code": 200,
        "msg": "ok",
        "data": response.model_dump(mode="json"),
    }


@router.post("/event-tasks/preview")
async def preview_workbench_event_tasks(
    payload: EventTaskPreviewRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """预览个人校验节日任务飞书 Sheet 的解析结果，不保存规则、不执行校验。"""
    project_id = ctx.require_project_member()

    try:
        source = await _load_workbench_feishu_source(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            source_id=payload.feishu_source_id,
        )
        config_source: DataSource | None = None
        config_variable: VariableTag | None = None
        if payload.config_variable_tag:
            config_source, config_variable = await _load_workbench_variable_context(
                db,
                project_id=project_id,
                user_id=ctx.user_id,
                variable_tag=payload.config_variable_tag,
            )
        preview = await preview_event_tasks_from_feishu(
            source,
            sheet_id=payload.sheet_id,
            config_source=config_source,
            config_variable=config_variable,
            parse_strategy=payload.parse_strategy,
            ai_parse_mode=payload.ai_parse_mode,
            key_delimiter=payload.key_delimiter or "_",
            fallback_match_field=payload.fallback_match_field or "INT_TaskID",
            db=db,
            project_id=project_id,
            event_task_field_mapping=payload.event_task_field_mapping,
        )
        ai_advice = await _build_event_task_ai_advice(
            ai_assist_mode=payload.ai_assist_mode,
            preview=preview,
            db=db,
            project_id=project_id,
        )
        response = _build_event_task_preview_response(preview, payload, ai_advice=ai_advice)
    except (
        ValueError,
        FileNotFoundError,
        ImportError,
        FeishuClientError,
        FeishuSheetError,
    ) as exc:
        response = _build_event_task_preview_failure(str(exc))

    return {
        "code": 200,
        "msg": "ok",
        "data": response.model_dump(mode="json"),
    }


@router.post("/event-tasks/validate")
async def validate_workbench_event_tasks(
    payload: EventTaskRewardValidationRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """即时校验个人节日任务奖励配置，不保存规则。"""
    project_id = ctx.require_project_member()

    try:
        source = await _load_workbench_feishu_source(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            source_id=payload.feishu_source_id,
        )
        config_source, config_variable = await _load_workbench_variable_context(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            variable_tag=payload.config_variable_tag,
        )
        preview = await preview_event_tasks_from_feishu(
            source,
            sheet_id=payload.sheet_id,
            parse_strategy=payload.parse_strategy,
            ai_parse_mode=payload.ai_parse_mode,
            key_delimiter=payload.key_delimiter or "_",
            fallback_match_field=payload.fallback_match_field or "INT_TaskID",
            db=db,
            project_id=project_id,
            event_task_field_mapping=payload.event_task_field_mapping,
        )
        if preview.parse_status != "success":
            ai_advice = await _build_event_task_ai_advice(
                ai_assist_mode=payload.ai_assist_mode,
                preview=preview,
                db=db,
                project_id=project_id,
            )
            messages = [*preview.errors, *preview.warnings]
            response = _build_event_task_validation_failure(
                "；".join(messages) if messages else "节日任务飞书 Sheet 解析失败。",
                ai_advice=ai_advice,
            )
        elif not preview.rows:
            ai_advice = await _build_event_task_ai_advice(
                ai_assist_mode=payload.ai_assist_mode,
                preview=preview,
                db=db,
                project_id=project_id,
            )
            response = _build_event_task_validation_failure(
                "Sheet 为空或未识别到节日任务明细。",
                ai_advice=ai_advice,
            )
        else:
            config_frame = await load_event_task_config_frame(
                config_source,
                config_variable,
                db=db,
                project_id=project_id,
            )
            if config_frame.empty:
                response = _build_event_task_validation_failure("组合变量为空。")
            else:
                variable_data = _build_event_task_variable_data(config_frame)
                variable_tasks = parseEventTaskVariables(variable_data)
                task_group_filter = (
                    _split_task_group_id_filter(payload.task_group_id_filter)
                    if payload.validation_scope == "specified"
                    else []
                )
                if payload.validation_scope == "specified" and not task_group_filter:
                    response = _build_event_task_validation_failure("请填写要校验的任务组 ID。")
                else:
                    summary = validateEventTaskRewards(
                        {
                            "feishuTasks": list(preview.rows),
                            "variableTasks": variable_tasks,
                            "matchStrategy": payload.match_strategy,
                            "scope": (
                                {"taskGroupIds": task_group_filter}
                                if task_group_filter
                                else "all"
                            ),
                        }
                    )
                    ai_advice = await _build_event_task_ai_advice(
                        ai_assist_mode=payload.ai_assist_mode,
                        preview=preview,
                        validation_summary=summary,
                        db=db,
                        project_id=project_id,
                    )
                    response = _build_event_task_validation_response(
                        summary,
                        warnings=list(preview.warnings),
                        errors=[],
                        raw_sheet_name=preview.raw_sheet_name,
                        ai_advice=ai_advice,
                    )
    except (
        ValueError,
        FileNotFoundError,
        ImportError,
        FeishuClientError,
        FeishuSheetError,
    ) as exc:
        response = _build_event_task_validation_failure(str(exc))

    return {
        "code": 200,
        "msg": "ok",
        "data": response,
    }


@router.post("/event-tasks/ai-suggestions")
async def suggest_workbench_event_task_ai(
    payload: EventTaskAiSuggestionRequest,
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """主动请求节日任务 AI 辅助建议，不改变解析和校验结果。"""
    project_id = ctx.require_project_member()

    try:
        source = await _load_workbench_feishu_source(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            source_id=payload.feishu_source_id,
        )
        config_source, config_variable = await _load_workbench_variable_context(
            db,
            project_id=project_id,
            user_id=ctx.user_id,
            variable_tag=payload.config_variable_tag,
        )
        preview = await preview_event_tasks_from_feishu(
            source,
            sheet_id=payload.sheet_id,
            config_source=config_source,
            config_variable=config_variable,
            parse_strategy=payload.parse_strategy,
            ai_parse_mode=payload.ai_parse_mode,
            key_delimiter=payload.key_delimiter or "_",
            fallback_match_field=payload.fallback_match_field or "INT_TaskID",
            db=db,
            project_id=project_id,
            event_task_field_mapping=payload.event_task_field_mapping,
        )
        summary: EventTaskRewardValidationSummary | None = None
        if payload.analysis_context == "validation" and preview.parse_status == "success" and preview.rows:
            config_frame = await load_event_task_config_frame(
                config_source,
                config_variable,
                db=db,
                project_id=project_id,
            )
            if not config_frame.empty:
                variable_data = _build_event_task_variable_data(config_frame)
                task_group_filter = (
                    _split_task_group_id_filter(payload.task_group_id_filter)
                    if payload.validation_scope == "specified"
                    else []
                )
                summary = validateEventTaskRewards(
                    {
                        "feishuTasks": list(preview.rows),
                        "variableTasks": parseEventTaskVariables(variable_data),
                        "matchStrategy": payload.match_strategy,
                        "scope": (
                            {"taskGroupIds": task_group_filter}
                            if task_group_filter
                            else "all"
                        ),
                    }
                )
        advice = await _build_event_task_ai_advice(
            ai_assist_mode=payload.ai_assist_mode,
            preview=preview,
            validation_summary=summary,
            db=db,
            project_id=project_id,
            force=True,
        )
        response = {
            "success": True,
            "message": "AI 分析完成。" if advice.used else "未生成 AI 建议。",
            **_serialize_event_task_ai_advice(advice),
        }
    except (
        ValueError,
        FileNotFoundError,
        ImportError,
        FeishuClientError,
        FeishuSheetError,
    ) as exc:
        response = {
            "success": False,
            "message": str(exc),
            **_serialize_event_task_ai_advice(None),
        }

    return {
        "code": 200,
        "msg": "ok",
        "data": response,
    }


@router.post("/svn-update")
async def trigger_workbench_svn_update(
    ctx: CurrentUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """对当前用户个人校验配置中的 SVN 数据源执行更新。"""
    project_id = ctx.require_project_member()

    result = await db.execute(
        select(WorkbenchConfigRecord).where(
            WorkbenchConfigRecord.project_id == project_id,
            WorkbenchConfigRecord.user_id == ctx.user_id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=400, detail="当前个人校验尚未配置工作台")

    try:
        raw_config = json.loads(record.config_json)
        config = _build_workbench_svn_update_config(raw_config)
        update_result = run_saved_fixed_rules_svn_update(
            config,
            user_scope=ctx.user.username,
        )
    except (
        json.JSONDecodeError,
        FileNotFoundError,
        ValueError,
        ImportError,
        NotImplementedError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "code": 200,
        "msg": "ok",
        "data": update_result,
    }
