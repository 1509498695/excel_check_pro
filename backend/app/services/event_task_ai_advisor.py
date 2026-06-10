"""EventTask AI 辅助建议服务。

AI 只返回字段映射、匹配候选和错误解释建议；最终解析与校验仍由确定性代码完成。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
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
from backend.app.api.fixed_rules_schemas import (
    EventTaskAiSuggestion,
    EventTaskPreviewResult,
)
from backend.app.services.event_task_reward_validator import (
    EventTaskRewardValidationSummary,
    EventTaskRewardValidationTaskResult,
)

UNMATCHED_COUNT_TRIGGER = 5
UNMATCHED_RATIO_TRIGGER = 0.2
PROMPT_VERSION = "event-task-ai-advisor-v1"


class EventTaskAiAdvisorClient(Protocol):
    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any] | str:
        """返回模型 JSON 对象或原始文本。"""


@dataclass(frozen=True)
class EventTaskAiAdvisorContext:
    db: AsyncSession | None = None
    project_id: int | None = None
    ai_client: EventTaskAiAdvisorClient | None = None
    max_rows: int = 80
    max_results: int = 40


@dataclass(frozen=True)
class EventTaskAiAdviceResult:
    suggestions: list[EventTaskAiSuggestion]
    warnings: list[str]
    used: bool
    trigger_reasons: list[str]


class _AiSuggestionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestions: list[EventTaskAiSuggestion] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("warnings", mode="before")
    @classmethod
    def _normalize_warnings(cls, value: object) -> object:
        if value is None:
            return []
        return value


class _DefaultEventTaskAiAdvisorClient:
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


async def advise_event_task_validation(
    *,
    ai_assist_mode: str,
    preview: EventTaskPreviewResult,
    sheet_rows: list[list[Any]],
    sheet_name: str | None = None,
    validation_summary: EventTaskRewardValidationSummary | None = None,
    force: bool = False,
    context: EventTaskAiAdvisorContext | Mapping[str, Any] | None = None,
) -> EventTaskAiAdviceResult:
    """按策略生成 AI 辅助建议，不修改预览或校验结果。"""

    normalized_mode = (ai_assist_mode or "auto").strip()
    if normalized_mode == "off":
        return EventTaskAiAdviceResult([], [], False, [])

    trigger_reasons = _build_trigger_reasons(preview, validation_summary)
    if not force and normalized_mode != "auto":
        return EventTaskAiAdviceResult([], [], False, trigger_reasons)
    if not force and not trigger_reasons:
        return EventTaskAiAdviceResult([], [], False, [])

    advisor_context = _coerce_context(context)
    try:
        ai_client = _resolve_ai_client(advisor_context)
        response = await ai_client.complete_json(
            system_prompt=_build_system_prompt(),
            user_prompt=_build_user_prompt(
                sheet_name=sheet_name or preview.raw_sheet_name or "未命名 Sheet",
                trigger_reasons=trigger_reasons or ["用户主动请求 AI 分析当前结果。"],
                sheet_rows=sheet_rows,
                preview=preview,
                validation_summary=validation_summary,
                max_rows=advisor_context.max_rows,
                max_results=advisor_context.max_results,
            ),
            json_schema=_get_ai_suggestion_json_schema(),
        )
    except (AiProviderInvalid, AiProviderNotConfigured) as exc:
        if force:
            raise AiProviderNotConfigured(PROJECT_AI_UNAVAILABLE_MESSAGE) from exc
        return EventTaskAiAdviceResult([], [PROJECT_AI_UNAVAILABLE_MESSAGE], False, trigger_reasons)
    except ProviderConnectionError as exc:
        message = sanitize_ai_error(exc.message)
        if force:
            raise ValueError(message) from exc
        return EventTaskAiAdviceResult([], [message], False, trigger_reasons)

    try:
        payload = _validate_ai_payload(response)
    except ValueError as exc:
        return EventTaskAiAdviceResult([], [str(exc)], False, trigger_reasons)

    return EventTaskAiAdviceResult(payload.suggestions, payload.warnings, True, trigger_reasons)


def _build_trigger_reasons(
    preview: EventTaskPreviewResult,
    validation_summary: EventTaskRewardValidationSummary | None,
) -> list[str]:
    reasons: list[str] = []
    if preview.parse_status != "success":
        text = "；".join([*preview.errors, *preview.warnings]) or "飞书表格解析失败。"
        reasons.append(f"飞书解析失败：{text}")
    if any(not row.task_group_id for row in preview.rows):
        reasons.append("存在任务组ID为空的飞书任务行。")
    if any(not row.task_desc for row in preview.rows):
        reasons.append("存在任务描述为空的飞书任务行。")
    if preview.reward_group_count == 0:
        reasons.append("未识别到奖励列。")

    if validation_summary is not None and validation_summary.total:
        unmatched_ratio = validation_summary.unmatched_count / validation_summary.total
        if (
            validation_summary.unmatched_count >= UNMATCHED_COUNT_TRIGGER
            and unmatched_ratio >= UNMATCHED_RATIO_TRIGGER
        ):
            reasons.append(
                f"未匹配任务较多：{validation_summary.unmatched_count}/{validation_summary.total}。"
            )
        if _has_reward_type_difference(validation_summary.results):
            reasons.append("奖励差异中出现 res 与 item 类型差异。")
    return reasons


def _has_reward_type_difference(results: list[EventTaskRewardValidationTaskResult]) -> bool:
    for result in results:
        rewards = [
            *result.expected_rewards,
            *result.actual_rewards,
            *result.missing_rewards,
            *result.extra_rewards,
        ]
        types = {(reward.type or "item").strip() for reward in rewards}
        if "res" in types and "item" in types:
            return True
        expected_by_id = {reward.item_id: reward.type or "item" for reward in result.expected_rewards}
        for reward in result.actual_rewards:
            expected_type = expected_by_id.get(reward.item_id)
            if expected_type and expected_type != (reward.type or "item"):
                return True
    return False


def _coerce_context(
    raw_context: EventTaskAiAdvisorContext | Mapping[str, Any] | None,
) -> EventTaskAiAdvisorContext:
    if raw_context is None:
        return EventTaskAiAdvisorContext()
    if isinstance(raw_context, EventTaskAiAdvisorContext):
        return raw_context
    return EventTaskAiAdvisorContext(
        db=raw_context.get("db"),
        project_id=raw_context.get("project_id"),
        ai_client=raw_context.get("ai_client"),
        max_rows=int(raw_context.get("max_rows") or 80),
        max_results=int(raw_context.get("max_results") or 40),
    )


def _resolve_ai_client(context: EventTaskAiAdvisorContext) -> EventTaskAiAdvisorClient:
    if context.ai_client is not None:
        return context.ai_client
    if context.db is None or context.project_id is None:
        raise AiProviderNotConfigured(PROJECT_AI_UNAVAILABLE_MESSAGE)
    return _DefaultEventTaskAiAdvisorClient(db=context.db, project_id=context.project_id)


def _validate_ai_payload(response: dict[str, Any] | str) -> _AiSuggestionPayload:
    if isinstance(response, str):
        try:
            payload = extract_json_object(response)
        except (ValueError, ProviderConnectionError) as exc:
            raise ValueError("AI 建议返回不是有效 JSON。") from exc
    else:
        payload = response
    try:
        normalized = _normalize_requires_user_confirm(payload)
        return _AiSuggestionPayload.model_validate(normalized)
    except ValidationError as exc:
        raise ValueError(f"AI 建议结构无效：{exc.errors()[0]['msg']}") from exc


def _normalize_requires_user_confirm(payload: dict[str, Any]) -> dict[str, Any]:
    suggestions = payload.get("suggestions")
    if isinstance(suggestions, list):
        next_suggestions: list[Any] = []
        for item in suggestions:
            if isinstance(item, dict):
                requires_confirm = bool(
                    item.get("requiresUserConfirm", item.get("requires_user_confirm", True))
                )
                item = {
                    **item,
                    "requiresUserConfirm": requires_confirm,
                    "requires_user_confirm": requires_confirm,
                }
            next_suggestions.append(item)
        return {**payload, "suggestions": next_suggestions}
    return payload


def _build_system_prompt() -> str:
    return (
        "你是节日任务奖励校验的 AI 辅助顾问，只能给建议，不能给最终校验结论。"
        "严禁修改、覆盖或判定最终校验结果；最终结果只能由确定性规则解析、"
        "组合变量解析、compareRewardSets 和 validateEventTaskRewards 产生。"
        "不得解析组合变量 STR_Loot，不得把语义相似当成通过，不得绕过奖励集合比较。"
        "你可以建议飞书字段映射、可能匹配项、失败原因解释和修复建议。"
        "字段映射建议必须要求用户确认。只输出符合 JSON schema 的 JSON。"
    )


def _build_user_prompt(
    *,
    sheet_name: str,
    trigger_reasons: list[str],
    sheet_rows: list[list[Any]],
    preview: EventTaskPreviewResult,
    validation_summary: EventTaskRewardValidationSummary | None,
    max_rows: int,
    max_results: int,
) -> str:
    snapshot = {
        "prompt_version": PROMPT_VERSION,
        "sheet_name": sheet_name,
        "trigger_reasons": trigger_reasons,
        "sheet_rows": _sample_sheet_rows(sheet_rows, max_rows=max_rows),
        "preview": {
            "parse_status": preview.parse_status,
            "errors": preview.errors,
            "warnings": preview.warnings[:40],
            "task_group_ids": preview.task_group_ids[:30],
            "parsed_rows": preview.parsed_rows,
            "reward_group_count": preview.reward_group_count,
            "sample_rows": [
                {
                    "row_index": row.row_index,
                    "task_group_id": row.task_group_id,
                    "task_id": row.task_id,
                    "task_desc": row.task_desc,
                    "rewards": [reward.model_dump(mode="json") for reward in row.rewards],
                    "warnings": row.warnings,
                }
                for row in preview.rows[:20]
            ],
        },
        "validation": _build_validation_snapshot(validation_summary, max_results=max_results),
    }
    return (
        "请基于以下上下文输出 AI 建议。不要输出最终校验是否通过；不要解析 STR_Loot；"
        "字段映射建议应放在 type=field_mapping_suggestion 的 suggestions 中，并包含 "
        "event_task_field_mapping 对象。\n"
        f"{json.dumps(snapshot, ensure_ascii=False)}"
    )


def _sample_sheet_rows(sheet_rows: list[list[Any]], *, max_rows: int) -> list[dict[str, Any]]:
    return [
        {"row_index": index + 1, "values": row}
        for index, row in enumerate(sheet_rows[:max_rows])
    ]


def _build_validation_snapshot(
    summary: EventTaskRewardValidationSummary | None,
    *,
    max_results: int,
) -> dict[str, Any] | None:
    if summary is None:
        return None
    return {
        "total": summary.total,
        "pass_count": summary.pass_count,
        "fail_count": summary.fail_count,
        "unmatched_count": summary.unmatched_count,
        "warning_count": summary.warning_count,
        "results": [
            {
                "task_group_id": result.task_group_id,
                "task_desc": result.task_desc,
                "feishu_row_index": result.feishu_row_index,
                "variable_key": result.variable_key,
                "status": result.status,
                "missing_rewards": [reward.__dict__ for reward in result.missing_rewards],
                "extra_rewards": [reward.__dict__ for reward in result.extra_rewards],
                "count_mismatches": [
                    mismatch.__dict__ for mismatch in result.count_mismatches
                ],
                "parse_warnings": result.parse_warnings,
                "error_message": result.error_message,
            }
            for result in summary.results[:max_results]
        ],
    }


def _get_ai_suggestion_json_schema() -> dict[str, Any]:
    suggestion_types = [
        "field_mapping_suggestion",
        "match_suggestion",
        "error_explanation",
    ]
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "suggestions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "type": {"type": "string", "enum": suggestion_types},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "suggestions": {
                            "type": "array",
                            "items": {"type": "object", "additionalProperties": True},
                        },
                        "reason": {"type": "string"},
                        "requiresUserConfirm": {"type": "boolean"},
                        "requires_user_confirm": {"type": "boolean"},
                    },
                    "required": [
                        "type",
                        "confidence",
                        "suggestions",
                        "reason",
                        "requiresUserConfirm",
                        "requires_user_confirm",
                    ],
                },
            },
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["suggestions", "warnings"],
    }
