"""执行结果持久化与分页查询服务。"""

from __future__ import annotations

import json
from typing import Any, Literal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import ExecutionResultItemRecord, ExecutionRunRecord


ExecutionScope = Literal["workbench", "fixed_rules"]
DEFAULT_RESULT_PAGE_SIZE = 20
MAX_RESULT_PAGE_SIZE = 200
_BASE_RESULT_FIELDS = {
    "level",
    "rule_name",
    "location",
    "row_index",
    "raw_value",
    "display_value",
    "message",
}


def normalize_result_page(page: int | None, size: int | None) -> tuple[int, int]:
    """归一化结果分页参数。"""
    normalized_page = page or 1
    normalized_size = size or DEFAULT_RESULT_PAGE_SIZE
    normalized_page = max(1, normalized_page)
    normalized_size = max(1, min(MAX_RESULT_PAGE_SIZE, normalized_size))
    return normalized_page, normalized_size


def paginate_abnormal_results(
    abnormal_results: list[dict[str, Any]],
    page: int,
    size: int,
) -> list[dict[str, Any]]:
    """对内存中的异常结果做分页切片。"""
    start = (page - 1) * size
    return abnormal_results[start : start + size]


async def persist_execution_result(
    db: AsyncSession,
    *,
    scope_type: ExecutionScope,
    project_id: int,
    user_id: int | None,
    abnormal_results: list[dict[str, Any]],
    execution_time_ms: int,
    total_rows_scanned: int,
    failed_sources: list[str],
) -> int:
    """覆盖保存某个作用域的最近一次执行结果。"""
    previous_run_ids = await _load_scope_run_ids(
        db,
        scope_type=scope_type,
        project_id=project_id,
        user_id=user_id,
    )
    if previous_run_ids:
        await db.execute(
            delete(ExecutionResultItemRecord).where(
                ExecutionResultItemRecord.run_id.in_(previous_run_ids)
            )
        )
        await db.execute(
            delete(ExecutionRunRecord).where(ExecutionRunRecord.id.in_(previous_run_ids))
        )

    run = ExecutionRunRecord(
        scope_type=scope_type,
        project_id=project_id,
        user_id=user_id,
        total_results=len(abnormal_results),
        execution_time_ms=execution_time_ms,
        total_rows_scanned=total_rows_scanned,
        failed_sources_json=json.dumps(failed_sources, ensure_ascii=False),
    )
    db.add(run)
    await db.flush()

    for sort_index, item in enumerate(abnormal_results):
        db.add(
            ExecutionResultItemRecord(
                run_id=run.id,
                sort_index=sort_index,
                level=str(item.get("level", "info")),
                rule_name=str(item.get("rule_name", "")),
                location=str(item.get("location", "")),
                row_index=int(item.get("row_index", 0)),
                raw_value_json=_serialize_raw_value(item.get("raw_value")),
                display_value_json=_serialize_raw_value(item.get("display_value")),
                extra_json=_serialize_result_extra(item),
                message=str(item.get("message", "")),
            )
        )

    await db.commit()
    return run.id


async def fetch_execution_result_page(
    db: AsyncSession,
    *,
    scope_type: ExecutionScope,
    result_id: int,
    project_id: int,
    user_id: int | None,
    page: int,
    size: int,
) -> dict[str, Any] | None:
    """按作用域读取最近一次执行结果的分页切片。"""
    stmt = select(ExecutionRunRecord).where(
        ExecutionRunRecord.id == result_id,
        ExecutionRunRecord.scope_type == scope_type,
        ExecutionRunRecord.project_id == project_id,
    )
    if scope_type == "workbench":
        stmt = stmt.where(ExecutionRunRecord.user_id == user_id)
    else:
        stmt = stmt.where(ExecutionRunRecord.user_id.is_(None))

    run = (await db.execute(stmt)).scalar_one_or_none()
    if run is None:
        return None

    start = (page - 1) * size
    item_stmt = (
        select(ExecutionResultItemRecord)
        .where(ExecutionResultItemRecord.run_id == run.id)
        .order_by(ExecutionResultItemRecord.sort_index.asc())
        .offset(start)
        .limit(size)
    )
    rows = (await db.execute(item_stmt)).scalars().all()

    return {
        "result_id": run.id,
        "total": run.total_results,
        "page": page,
        "size": size,
        "list": [_build_result_item(row) for row in rows],
        "execution_time_ms": run.execution_time_ms,
        "total_rows_scanned": run.total_rows_scanned,
        "failed_sources": _deserialize_failed_sources(run.failed_sources_json),
    }


async def fetch_execution_result_export(
    db: AsyncSession,
    *,
    scope_type: ExecutionScope,
    result_id: int,
    project_id: int,
    user_id: int | None,
) -> dict[str, Any] | None:
    """按作用域读取一次执行结果的完整导出数据。"""
    stmt = select(ExecutionRunRecord).where(
        ExecutionRunRecord.id == result_id,
        ExecutionRunRecord.scope_type == scope_type,
        ExecutionRunRecord.project_id == project_id,
    )
    if scope_type == "workbench":
        stmt = stmt.where(ExecutionRunRecord.user_id == user_id)
    else:
        stmt = stmt.where(ExecutionRunRecord.user_id.is_(None))

    run = (await db.execute(stmt)).scalar_one_or_none()
    if run is None:
        return None

    item_stmt = (
        select(ExecutionResultItemRecord)
        .where(ExecutionResultItemRecord.run_id == run.id)
        .order_by(ExecutionResultItemRecord.sort_index.asc())
    )
    rows = (await db.execute(item_stmt)).scalars().all()

    return {
        "result_id": run.id,
        "total": run.total_results,
        "created_at": run.created_at,
        "execution_time_ms": run.execution_time_ms,
        "total_rows_scanned": run.total_rows_scanned,
        "failed_sources": _deserialize_failed_sources(run.failed_sources_json),
        "list": [_build_result_item(row) for row in rows],
    }


async def _load_scope_run_ids(
    db: AsyncSession,
    *,
    scope_type: ExecutionScope,
    project_id: int,
    user_id: int | None,
) -> list[int]:
    stmt = select(ExecutionRunRecord.id).where(
        ExecutionRunRecord.scope_type == scope_type,
        ExecutionRunRecord.project_id == project_id,
    )
    if scope_type == "workbench":
        stmt = stmt.where(ExecutionRunRecord.user_id == user_id)
    else:
        stmt = stmt.where(ExecutionRunRecord.user_id.is_(None))
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _serialize_raw_value(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False)


def _serialize_result_extra(item: dict[str, Any]) -> str:
    extra = {
        key: value
        for key, value in item.items()
        if key not in _BASE_RESULT_FIELDS
    }
    return _serialize_raw_value(extra)


def _build_result_item(row: ExecutionResultItemRecord) -> dict[str, Any]:
    item = {
        "level": row.level,
        "rule_name": row.rule_name,
        "location": row.location,
        "row_index": row.row_index,
        "raw_value": _deserialize_raw_value(row.raw_value_json),
        "display_value": _deserialize_raw_value(row.display_value_json),
        "message": row.message,
    }
    extra = _deserialize_result_extra(row.extra_json)
    item.update(extra)
    return item


def _deserialize_raw_value(raw_value_json: str | None) -> Any:
    if not isinstance(raw_value_json, str):
        return raw_value_json
    try:
        return json.loads(raw_value_json)
    except json.JSONDecodeError:
        return raw_value_json


def _deserialize_result_extra(extra_json: str | None) -> dict[str, Any]:
    payload = _deserialize_raw_value(extra_json)
    return payload if isinstance(payload, dict) else {}


def _deserialize_failed_sources(failed_sources_json: str) -> list[str]:
    try:
        payload = json.loads(failed_sources_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload]
