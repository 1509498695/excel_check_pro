"""AI 辅助识别礼包规划表结构的独立服务。

本模块只返回结构识别建议，不参与礼包明细抽取、不接入固定规则执行链路。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.credentials import (
    AiProviderInvalid,
    AiProviderNotConfigured,
    PROJECT_AI_UNAVAILABLE_MESSAGE,
    decrypt_credential_key,
    load_project_credential,
    parse_extra_headers,
    sanitize_ai_error,
)
from backend.app.ai.providers import ProviderConnectionError, call_provider_json, extract_json_object


DEFAULT_MAX_ROWS = 200
DEFAULT_MAX_COLUMNS = 50
DEFAULT_CELL_MAX_CHARS = 80
DEFAULT_REASONING_MAX_CHARS = 240
PROMPT_VERSION = "package-items-ai-parser-v2"
_REQUIRED_FIELDS = ("package_id", "item_id", "count")


class PackageAiParseError(ValueError):
    """礼包规划表 AI 结构识别失败。"""


class PackageAiUnavailableError(PackageAiParseError):
    """项目级 AI 不可用，调用方可按自动/显式模式分流。"""


class PackageItemsAiClient(Protocol):
    """可替换的 AI 调用接口，测试中通过 fake client 注入。"""

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any] | str:
        """返回模型 JSON 对象或原始文本。"""


@dataclass(frozen=True)
class PackageAiParseRuleContext:
    """AI 结构识别上下文。"""

    db: AsyncSession | None = None
    project_id: int | None = None
    ai_client: PackageItemsAiClient | None = None
    max_rows: int = DEFAULT_MAX_ROWS
    max_columns: int = DEFAULT_MAX_COLUMNS
    cell_max_chars: int = DEFAULT_CELL_MAX_CHARS


class PackageAiDetailRange(BaseModel):
    """AI 建议的单段明细区域。"""

    model_config = ConfigDict(extra="forbid")

    header_row: int = Field(ge=1)
    start_row: int = Field(ge=1)
    end_row: int = Field(ge=1)


class PackageAiParseSuggestion(BaseModel):
    """AI 对礼包规划表结构的识别建议。"""

    model_config = ConfigDict(extra="forbid")

    header_rows: list[int] = Field(default_factory=list)
    detail_ranges: list[PackageAiDetailRange] = Field(default_factory=list)
    field_mapping: dict[str, str]
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    reasoning_summary: str = ""

    @field_validator("warnings", mode="before")
    @classmethod
    def _normalize_warnings(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return value

    @field_validator("reasoning_summary", mode="before")
    @classmethod
    def _strip_reasoning_summary(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class _DefaultPackageItemsAiClient:
    """复用项目已有 AI provider 的默认 client。"""

    def __init__(self, *, db: AsyncSession, project_id: int) -> None:
        self._db = db
        self._project_id = project_id

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any] | str:
        credential = await load_project_credential(self._db, self._project_id)
        api_key = decrypt_credential_key(credential)
        try:
            raw_result, _meta = await call_provider_json(
                provider_preset=credential.provider_preset,  # type: ignore[arg-type]
                base_url=credential.base_url,
                model=credential.model,
                api_key=api_key,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_schema=json_schema,
                extra_headers=parse_extra_headers(credential.extra_headers_json),
                timeout_seconds=30.0,
            )
        except ProviderConnectionError as exc:
            raise ProviderConnectionError(
                exc.category,
                sanitize_ai_error(exc.message, api_key),
                exc.status_code,
            ) from exc
        return raw_result


async def parse_package_sheet_with_ai(
    sheet_matrix: list[list[Any]],
    sheet_name: str,
    rule_context: PackageAiParseRuleContext | Mapping[str, Any] | None = None,
) -> PackageAiParseSuggestion:
    """调用 AI 识别礼包规划表结构，并校验返回建议。"""
    context = _coerce_rule_context(rule_context)
    ai_client = _resolve_ai_client(context)
    snapshot = _build_sheet_snapshot(
        sheet_matrix,
        max_rows=context.max_rows,
        max_columns=context.max_columns,
        cell_max_chars=context.cell_max_chars,
    )
    try:
        response = await ai_client.complete_json(
            system_prompt=_build_system_prompt(),
            user_prompt=_build_user_prompt(
                sheet_name=sheet_name,
                sheet_snapshot=snapshot,
            ),
            json_schema=_get_suggestion_json_schema(),
        )
    except PackageAiParseError:
        raise
    except ProviderConnectionError as exc:
        raise PackageAiParseError(sanitize_ai_error(exc.message)) from exc
    except (AiProviderInvalid, AiProviderNotConfigured) as exc:
        raise PackageAiUnavailableError(PROJECT_AI_UNAVAILABLE_MESSAGE) from exc
    payload = _parse_ai_payload(response)
    suggestion = _validate_suggestion_payload(payload, sheet_matrix)
    return suggestion


def _coerce_rule_context(
    raw_context: PackageAiParseRuleContext | Mapping[str, Any] | None,
) -> PackageAiParseRuleContext:
    if raw_context is None:
        return PackageAiParseRuleContext()
    if isinstance(raw_context, PackageAiParseRuleContext):
        return raw_context
    return PackageAiParseRuleContext(
        db=raw_context.get("db"),
        project_id=raw_context.get("project_id"),
        ai_client=raw_context.get("ai_client"),
        max_rows=int(raw_context.get("max_rows") or DEFAULT_MAX_ROWS),
        max_columns=int(raw_context.get("max_columns") or DEFAULT_MAX_COLUMNS),
        cell_max_chars=int(raw_context.get("cell_max_chars") or DEFAULT_CELL_MAX_CHARS),
    )


def _resolve_ai_client(context: PackageAiParseRuleContext) -> PackageItemsAiClient:
    if context.ai_client is not None:
        return context.ai_client
    if context.db is None or context.project_id is None:
        raise PackageAiParseError("缺少 AI 调用上下文：请提供 ai_client，或同时提供 db 和 project_id。")
    return _DefaultPackageItemsAiClient(db=context.db, project_id=context.project_id)


def _parse_ai_payload(response: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    if not isinstance(response, str):
        raise PackageAiParseError("AI 返回结构不合法：响应必须是 JSON 对象或文本。")
    try:
        return extract_json_object(response)
    except ProviderConnectionError as exc:
        raise PackageAiParseError(exc.message) from exc


def _validate_suggestion_payload(
    payload: dict[str, Any],
    sheet_matrix: list[list[Any]],
) -> PackageAiParseSuggestion:
    try:
        suggestion = PackageAiParseSuggestion.model_validate(payload)
    except ValidationError as exc:
        raise PackageAiParseError(f"AI 返回结构不合法：{exc.errors()[0]['msg']}") from exc

    row_count = len(sheet_matrix)
    _validate_header_rows(suggestion.header_rows, row_count=row_count)
    _validate_detail_ranges(suggestion.detail_ranges, row_count=row_count)
    _validate_field_mapping(suggestion.field_mapping)
    suggestion.reasoning_summary = _clip_text(
        suggestion.reasoning_summary,
        DEFAULT_REASONING_MAX_CHARS,
    )
    return suggestion


def _validate_header_rows(header_rows: list[int], *, row_count: int) -> None:
    if not header_rows:
        raise PackageAiParseError("AI 返回缺少 header_rows。")
    for row_index in header_rows:
        if row_index < 1:
            raise PackageAiParseError(f"header_rows 包含非法行号：{row_index}。")
        if row_index > row_count:
            raise PackageAiParseError(f"header_rows 行号越界：{row_index}。")


def _validate_detail_ranges(
    detail_ranges: list[PackageAiDetailRange],
    *,
    row_count: int,
) -> None:
    if not detail_ranges:
        raise PackageAiParseError("AI 返回缺少 detail_ranges。")
    for detail_range in detail_ranges:
        if detail_range.header_row > row_count:
            raise PackageAiParseError(f"detail_ranges.header_row 越界：{detail_range.header_row}。")
        if detail_range.start_row <= detail_range.header_row:
            raise PackageAiParseError("detail_ranges.start_row 必须大于 header_row。")
        if detail_range.end_row < detail_range.start_row:
            raise PackageAiParseError("detail_ranges.end_row 必须大于等于 start_row。")
        if detail_range.end_row > row_count:
            raise PackageAiParseError(
                f"detail_ranges 范围越界：{detail_range.start_row}-{detail_range.end_row}。"
            )


def _validate_field_mapping(field_mapping: dict[str, str]) -> None:
    missing = [field for field in _REQUIRED_FIELDS if field not in field_mapping]
    if missing:
        raise PackageAiParseError(f"field_mapping 缺少字段：{'、'.join(missing)}。")
    for field in _REQUIRED_FIELDS:
        value = field_mapping.get(field)
        if not isinstance(value, str) or not value.strip():
            raise PackageAiParseError(f"field_mapping.{field} 必须是非空字符串。")
        field_mapping[field] = value.strip()


def _build_sheet_snapshot(
    sheet_matrix: list[list[Any]],
    *,
    max_rows: int,
    max_columns: int,
    cell_max_chars: int,
) -> dict[str, Any]:
    clipped_rows = sheet_matrix[: max(1, max_rows)]
    rows: list[dict[str, Any]] = []
    empty_range_start: int | None = None
    empty_range_end: int | None = None

    for row_offset, row in enumerate(clipped_rows):
        row_index = row_offset + 1
        if _is_empty_row(row):
            if empty_range_start is None:
                empty_range_start = row_index
            empty_range_end = row_index
            continue
        _flush_empty_rows(rows, empty_range_start, empty_range_end)
        empty_range_start = None
        empty_range_end = None
        rows.append(
            {
                "row_index": row_index,
                "cells": [
                    _clip_text(_cell_text(value), cell_max_chars)
                    for value in row[: max(1, max_columns)]
                ],
            }
        )

    _flush_empty_rows(rows, empty_range_start, empty_range_end)
    return {
        "row_count": len(sheet_matrix),
        "column_count": max((len(row) for row in sheet_matrix), default=0),
        "included_rows": len(clipped_rows),
        "included_columns": max(1, max_columns),
        "rows": rows,
    }


def _flush_empty_rows(
    rows: list[dict[str, Any]],
    start_row: int | None,
    end_row: int | None,
) -> None:
    if start_row is None or end_row is None:
        return
    item: dict[str, Any] = {"row_index": start_row, "empty": True}
    if end_row > start_row:
        item["repeat_until_row"] = end_row
    rows.append(item)


def _build_system_prompt() -> str:
    return (
        "你是 Excel/飞书 Sheet 结构识别器。输入是带原始 1-based 行号的飞书 Sheet 二维表。"
        "任务只识别礼包明细区域和字段映射，不做最终校验判断，不判断礼包配置是否一致。"
        "严禁输出自然语言正文、Markdown、解释文本或最终校验结论，只输出符合 JSON schema 的 JSON 对象。"
        "Sheet 可能包含礼包总览区、价格/资源/价值换算区、说明文字、空行、多个礼包明细区域、公式列显示值。"
        "礼包明细表头通常包含礼包id/礼包ID/package_id/packageId、道具ID/道具id/item_id/itemId、个数/数量/count/num。"
        "detail_ranges 必须只覆盖礼包明细数据行，不包含表头、说明行、空行或汇总行。"
        "field_mapping 必须使用表头中的原始字段名。行号必须使用输入中的原始行号。"
        "如果不确定，请将 confidence 设为小于 0.7，并在 warnings 中说明不确定原因。"
        "不要输出完整推理，只在 reasoning_summary 中给出一句简短依据。"
    )


def _build_user_prompt(*, sheet_name: str, sheet_snapshot: dict[str, Any]) -> str:
    return (
        "请识别礼包明细结构，并只返回符合 JSON schema 的 JSON。\n"
        "输出字段必须包含 header_rows、detail_ranges、field_mapping、confidence、warnings、reasoning_summary。\n"
        "行号使用原始 Sheet 的 1-based 行号；detail_ranges 需要包含对应 header_row，"
        "start_row/end_row 只能覆盖明细数据行。"
        "field_mapping 返回表头中的原始字段名，不要返回推测字段名或最终明细数据。\n"
        "如果无法稳定判断，请设置 confidence < 0.7，并在 warnings 中写明原因。\n"
        f"Sheet 名称：{sheet_name or '未命名 Sheet'}\n"
        f"Sheet 内容：{json.dumps(sheet_snapshot, ensure_ascii=False)}"
    )


def _get_suggestion_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "header_rows": {"type": "array", "items": {"type": "integer", "minimum": 1}},
            "detail_ranges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "header_row": {"type": "integer", "minimum": 1},
                        "start_row": {"type": "integer", "minimum": 1},
                        "end_row": {"type": "integer", "minimum": 1},
                    },
                    "required": ["header_row", "start_row", "end_row"],
                },
            },
            "field_mapping": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "package_id": {"type": "string"},
                    "item_id": {"type": "string"},
                    "count": {"type": "string"},
                },
                "required": ["package_id", "item_id", "count"],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "reasoning_summary": {"type": "string"},
        },
        "required": [
            "header_rows",
            "detail_ranges",
            "field_mapping",
            "confidence",
            "warnings",
            "reasoning_summary",
        ],
    }


def _is_empty_row(row: list[Any]) -> bool:
    return not any(_cell_text(value) for value in row)


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clip_text(value: str, max_chars: int) -> str:
    normalized_max_chars = max(1, max_chars)
    if len(value) <= normalized_max_chars:
        return value
    return f"{value[:normalized_max_chars]}..."
