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
    FixedRulesConfig,
    PackageItemsPreviewDetailRow,
    PackageItemsPreviewFieldMapping,
    PackageItemsPreviewRequest,
    PackageItemsPreviewResponse,
    PackageItemsPreviewResult,
)
from backend.app.api.schemas import DataSource
from backend.app.auth.dependencies import CurrentUserContext, get_current_user
from backend.app.database import get_db
from backend.app.fixed_rules.service import run_saved_fixed_rules_svn_update
from backend.app.integrations.feishu_client import FeishuClientError
from backend.app.loaders.feishu_reader import FeishuSheetError
from backend.app.models import WorkbenchConfigRecord
from backend.app.services.package_items_parser import preview_package_items_from_feishu

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
            user_id=ctx.user_id,
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
