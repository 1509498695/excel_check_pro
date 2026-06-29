"""AI-Assisted Snapshot Brief generation for planning sheet snapshots."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.credentials import (
    decrypt_credential_key,
    load_project_credential,
    parse_extra_headers,
    sanitize_ai_error,
)
from backend.app.ai.providers import ProviderConnectionError, call_provider_json
from backend.app.test_cases.schemas import (
    PlanningSnapshotBriefResponse,
    PlanningSnapshotResponse,
)


BRIEF_MARKDOWN_SECTIONS = [
    "核心目标",
    "功能范围",
    "规则与流程",
    "配置/数值/条件",
    "时间、刷新与生命周期",
    "UI、提示与表现",
    "风险点与易漏点",
    "待确认问题",
    "来源索引",
]


class SnapshotBriefPayloadError(ValueError):
    """AI 返回结构无法通过快照整理稿契约校验。"""


async def generate_planning_snapshot_brief(
    snapshot: PlanningSnapshotResponse,
    *,
    db: AsyncSession,
    project_id: int,
) -> PlanningSnapshotBriefResponse:
    """Generate a Markdown brief from the submitted snapshot only."""
    credential = await load_project_credential(db, project_id)
    api_key = decrypt_credential_key(credential)
    extra_headers = parse_extra_headers(credential.extra_headers_json)

    try:
        result, _meta = await call_provider_json(
            provider_preset=credential.provider_preset,  # type: ignore[arg-type]
            base_url=credential.base_url,
            model=credential.model,
            api_key=api_key,
            system_prompt=_build_system_prompt(),
            user_prompt=_build_user_prompt(snapshot),
            json_schema=PlanningSnapshotBriefResponse.model_json_schema(),
            extra_headers=extra_headers,
            timeout_seconds=60.0,
        )
    except ProviderConnectionError as error:
        raise ProviderConnectionError(
            error.category,
            _sanitize_brief_provider_error(error.message, api_key),
            error.status_code,
        ) from error

    try:
        return PlanningSnapshotBriefResponse.model_validate(
            _normalize_provider_brief_result(result)
        )
    except ValidationError as error:
        raise SnapshotBriefPayloadError(
            f"AI 快照整理稿返回结构不符合契约：{error.errors()[0]['msg']}"
        ) from error


def _build_system_prompt() -> str:
    return (
        "你是资深 QA 需求整理助手。只返回符合 JSON Schema 的 JSON 对象，"
        "不要输出 JSON 之外的解释文本。"
    )


def _build_user_prompt(snapshot: PlanningSnapshotResponse) -> str:
    sections = "\n".join(f"- {section}" for section in BRIEF_MARKDOWN_SECTIONS)
    return "\n".join(
        [
            "任务：根据 Planning Sheet Snapshot 生成 AI-Assisted Snapshot Brief。",
            "整理稿给策划和 QA 阅读、复制、对齐使用；不得替代原始快照。",
            "brief_markdown 必须是 Markdown，并固定包含以下二级标题，顺序不可变：",
            sections,
            "来源索引必须包含快照行号或原始片段引用，例如“行 2：原始片段”。",
            "不得编造快照中不存在的需求；不确定内容写入“待确认问题”。",
            "warnings 只放用户可见提醒，不要包含 prompt、provider response、API Key 或 Base URL。",
            "Planning Sheet Snapshot：",
            _render_snapshot_text(snapshot),
        ]
    )


def _render_snapshot_text(snapshot: PlanningSnapshotResponse) -> str:
    lines = [
        f"来源：{snapshot.source_summary}",
        f"Sheet：{snapshot.sheet_name}",
        f"列：{', '.join(snapshot.columns)}",
        f"非空单元格：{snapshot.non_empty_cell_count}",
        f"是否截断：{'是' if snapshot.truncated else '否'}",
    ]
    for row in snapshot.rows:
        fragments: list[str] = []
        for cell in row.cells:
            value = cell.value.strip()
            if not value:
                continue
            column_name = cell.column_name or f"Column {cell.column_index}"
            suffix = "（已截断）" if cell.truncated else ""
            fragments.append(f"{column_name}={value}{suffix}")
        if fragments:
            lines.append(f"行 {row.row_index}: " + " | ".join(fragments))

    if snapshot.warnings:
        lines.append("快照 warnings：")
        lines.extend(f"- {warning.message}" for warning in snapshot.warnings)
    return "\n".join(lines)


def _normalize_provider_brief_result(result: dict[str, Any]) -> dict[str, Any]:
    """Tolerate common provider warning shapes while preserving the public schema."""
    normalized = dict(result)
    warnings = normalized.get("warnings")
    if not isinstance(warnings, list):
        normalized["warnings"] = []
        return normalized

    normalized_warnings: list[Any] = []
    for warning in warnings:
        if isinstance(warning, str):
            message = warning.strip()
            if message:
                normalized_warnings.append(
                    {
                        "source": "snapshot_brief",
                        "level": "warning",
                        "message": message,
                    }
                )
            continue
        normalized_warnings.append(warning)
    normalized["warnings"] = normalized_warnings
    return normalized


def _sanitize_brief_provider_error(message: str, api_key: str) -> str:
    sanitized = sanitize_ai_error(message, api_key)
    sensitive_markers = [
        "http://",
        "https://",
        "prompt",
        "provider response",
        "provider_response",
        "raw_provider_response",
        "full_brief_prompt",
        "base url",
        "base_url",
    ]
    lower_message = sanitized.lower()
    if any(marker in lower_message for marker in sensitive_markers):
        return "AI 快照整理稿生成失败，请检查项目级 AI 配置。"
    return f"AI 快照整理稿生成失败：{sanitized}"
