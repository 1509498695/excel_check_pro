from __future__ import annotations

import asyncio
from typing import Any

import pytest

from backend.app.ai.credentials import PROJECT_AI_UNAVAILABLE_MESSAGE
from backend.app.ai.providers import ProviderConnectionError
from backend.app.database import async_session_factory
from backend.app.models import ProjectAiCredentialRecord
from backend.app.security.crypto import encrypt_secret
from backend.app.api.fixed_rules_schemas import (
    EventTaskPlanRow,
    EventTaskPreviewResult,
    EventTaskPreviewRewardItem,
)
from backend.app.services.event_task_ai_advisor import (
    EventTaskAiAdvisorContext,
    advise_event_task_validation,
)
from backend.app.services.event_task_reward_validator import validate_event_task_rewards
from backend.app.services.event_task_variable_parser import parseEventTaskVariables


class _FakeAiClient:
    def __init__(self) -> None:
        self.calls = 0
        self.last_user_prompt = ""

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        del system_prompt, json_schema
        self.calls += 1
        self.last_user_prompt = user_prompt
        return {
            "suggestions": [
                {
                    "type": "field_mapping_suggestion",
                    "confidence": 0.86,
                    "suggestions": [
                        {
                            "event_task_field_mapping": {
                                "header_row_index": 2,
                                "task_group_id": "活动ID",
                                "task_id": "序号",
                                "task_desc": "条件",
                                "loot_groups": [
                                    {
                                        "item_id": "奖励ID",
                                        "count": "奖励数量",
                                        "name": "奖励名称",
                                    }
                                ],
                            }
                        }
                    ],
                    "reason": "表头别名不在规则识别范围内。",
                    "requiresUserConfirm": True,
                }
            ],
            "warnings": [],
        }


def _preview_success() -> EventTaskPreviewResult:
    return EventTaskPreviewResult(
        parse_status="success",
        task_group_ids=["26051802"],
        total_rows=2,
        parsed_rows=1,
        detail_row_count=1,
        reward_group_count=1,
        raw_values=[["任务id", "任务要求", "道具ID", "数量"], ["26051802", "累计登陆1天", "2087", "1"]],
        rows=[
            EventTaskPlanRow(
                row_index=2,
                task_group_id="26051802",
                task_id="1",
                task_desc="累计登陆1天",
                rewards=[
                    EventTaskPreviewRewardItem(
                        type="item",
                        item_id=2087,
                        itemId=2087,
                        count=1,
                    )
                ],
            )
        ],
    )


def _preview_failed() -> EventTaskPreviewResult:
    return EventTaskPreviewResult(
        parse_status="failed",
        total_rows=2,
        reward_group_count=0,
        raw_values=[["活动ID", "条件", "奖励ID", "奖励数量"], ["26051802", "累计登陆1天", "2087", "1"]],
        errors=["任务表头缺少字段：task_group_id"],
    )


def test_ai_assist_off_does_not_call_provider() -> None:
    client = _FakeAiClient()

    result = asyncio.run(
        advise_event_task_validation(
            ai_assist_mode="off",
            preview=_preview_failed(),
            sheet_rows=[],
            context=EventTaskAiAdvisorContext(ai_client=client),
        )
    )

    assert client.calls == 0
    assert result.used is False
    assert result.suggestions == []


def test_auto_success_without_trigger_does_not_call_provider() -> None:
    client = _FakeAiClient()

    result = asyncio.run(
        advise_event_task_validation(
            ai_assist_mode="auto",
            preview=_preview_success(),
            sheet_rows=[],
            context=EventTaskAiAdvisorContext(ai_client=client),
        )
    )

    assert client.calls == 0
    assert result.used is False
    assert result.suggestions == []


def test_auto_parse_failure_calls_provider_for_field_mapping_suggestion() -> None:
    client = _FakeAiClient()

    result = asyncio.run(
        advise_event_task_validation(
            ai_assist_mode="auto",
            preview=_preview_failed(),
            sheet_rows=_preview_failed().raw_values,
            context=EventTaskAiAdvisorContext(ai_client=client),
        )
    )

    assert client.calls == 1
    assert result.used is True
    assert result.suggestions[0].type == "field_mapping_suggestion"
    assert result.suggestions[0].requiresUserConfirm is True
    assert result.suggestions[0].requires_user_confirm is True
    assert result.trigger_reasons


def test_ai_suggestion_does_not_modify_validation_summary() -> None:
    client = _FakeAiClient()
    summary = validate_event_task_rewards(
        feishu_tasks=_preview_success().rows,
        variable_tasks=parseEventTaskVariables(
            {
                "26051802_0": {
                    "INT_TaskID": 1,
                    "STR_Desc": "累计登陆1天",
                    "STR_Loot": "[{item,2087,2}]",
                }
            }
        ),
    )
    before = (
        summary.total,
        summary.pass_count,
        summary.fail_count,
        summary.results[0].status,
        summary.results[0].count_mismatches[0].actual_count,
    )

    asyncio.run(
        advise_event_task_validation(
            ai_assist_mode="on",
            preview=_preview_success(),
            sheet_rows=_preview_success().raw_values,
            validation_summary=summary,
            force=True,
            context=EventTaskAiAdvisorContext(ai_client=client),
        )
    )

    after = (
        summary.total,
        summary.pass_count,
        summary.fail_count,
        summary.results[0].status,
        summary.results[0].count_mismatches[0].actual_count,
    )
    assert client.calls == 1
    assert after == before


@pytest.mark.anyio
async def test_auto_unconfigured_project_ai_returns_warning(
    test_project_id: int,
) -> None:
    async with async_session_factory() as session:
        result = await advise_event_task_validation(
            ai_assist_mode="auto",
            preview=_preview_failed(),
            sheet_rows=_preview_failed().raw_values,
            context=EventTaskAiAdvisorContext(db=session, project_id=test_project_id),
        )

    assert result.used is False
    assert result.suggestions == []
    assert result.warnings == [PROJECT_AI_UNAVAILABLE_MESSAGE]
    assert result.trigger_reasons


@pytest.mark.anyio
async def test_force_unconfigured_project_ai_raises_user_facing_error(
    test_project_id: int,
) -> None:
    async with async_session_factory() as session:
        with pytest.raises(ValueError, match=PROJECT_AI_UNAVAILABLE_MESSAGE):
            await advise_event_task_validation(
                ai_assist_mode="on",
                preview=_preview_success(),
                sheet_rows=_preview_success().raw_values,
                force=True,
                context=EventTaskAiAdvisorContext(db=session, project_id=test_project_id),
            )


@pytest.mark.anyio
async def test_default_event_task_ai_client_uses_project_credential(
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        captured.update(kwargs)
        return {
            "suggestions": [
                {
                    "type": "field_mapping_suggestion",
                    "confidence": 0.75,
                    "suggestions": [],
                    "reason": "使用项目级 AI 凭据生成建议。",
                    "requiresUserConfirm": True,
                }
            ],
            "warnings": [],
        }, {"latency_ms": 7}

    monkeypatch.setattr(
        "backend.app.services.event_task_ai_advisor.call_provider_json",
        fake_call_provider_json,
    )
    async with async_session_factory() as session:
        session.add(
            ProjectAiCredentialRecord(
                project_id=test_project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret("sk-project-secret"),
                extra_headers_json='{"X-Project":"ExcelCheck"}',
                enabled=True,
            )
        )
        await session.commit()

        result = await advise_event_task_validation(
            ai_assist_mode="auto",
            preview=_preview_failed(),
            sheet_rows=_preview_failed().raw_values,
            context=EventTaskAiAdvisorContext(db=session, project_id=test_project_id),
        )

    assert result.used is True
    assert captured["provider_preset"] == "openai"
    assert captured["base_url"] == "https://api.openai.com/v1"
    assert captured["model"] == "gpt-4o-mini"
    assert captured["api_key"] == "sk-project-secret"
    assert captured["extra_headers"] == {"X-Project": "ExcelCheck"}


@pytest.mark.anyio
async def test_default_event_task_ai_client_sanitizes_provider_error_api_key(
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        raise ProviderConnectionError(
            "unknown",
            "上游拒绝了 API Key sk-project-secret，请检查配置。",
        )

    monkeypatch.setattr(
        "backend.app.services.event_task_ai_advisor.call_provider_json",
        fake_call_provider_json,
    )
    async with async_session_factory() as session:
        session.add(
            ProjectAiCredentialRecord(
                project_id=test_project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret("sk-project-secret"),
                extra_headers_json="{}",
                enabled=True,
            )
        )
        await session.commit()

        result = await advise_event_task_validation(
            ai_assist_mode="auto",
            preview=_preview_failed(),
            sheet_rows=_preview_failed().raw_values,
            context=EventTaskAiAdvisorContext(db=session, project_id=test_project_id),
        )

    assert result.used is False
    assert "sk-project-secret" not in result.warnings[0]
    assert "sk-***cret" in result.warnings[0]
