"""AI-Assisted Snapshot Brief 后端接口测试。"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from backend.app.ai.credentials import PROJECT_AI_UNAVAILABLE_MESSAGE
from backend.app.ai.providers import ProviderConnectionError
from backend.app.database import async_session_factory
from backend.app.models import ExecutionRunRecord, ProjectAiCredentialRecord
from backend.app.security.crypto import encrypt_secret
from backend.app.test_cases import planning_snapshot


def _snapshot_payload() -> dict[str, Any]:
    return {
        "source_summary": "上传 Excel：planning.xlsx",
        "sheet_name": "策划案",
        "columns": ["模块", "需求点", "备注"],
        "rows": [
            {
                "row_index": 1,
                "cells": [
                    {
                        "row_index": 1,
                        "column_index": 1,
                        "column_name": "模块",
                        "value": "模块",
                    },
                    {
                        "row_index": 1,
                        "column_index": 2,
                        "column_name": "需求点",
                        "value": "需求点",
                    },
                ],
            },
            {
                "row_index": 2,
                "cells": [
                    {
                        "row_index": 2,
                        "column_index": 1,
                        "column_name": "模块",
                        "value": "活动入口",
                    },
                    {
                        "row_index": 2,
                        "column_index": 2,
                        "column_name": "需求点",
                        "value": "按配置开放入口",
                    },
                    {
                        "row_index": 2,
                        "column_index": 3,
                        "column_name": "备注",
                        "value": "入口图未读取",
                    },
                ],
            },
        ],
        "non_empty_cell_count": 5,
        "truncated": False,
        "warnings": [],
    }


def _brief_request() -> dict[str, Any]:
    return {
        "planning_snapshot": _snapshot_payload(),
    }


async def _seed_project_ai(
    project_id: int,
    *,
    enabled: bool = True,
    api_key: str = "sk-brief-secret",
) -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectAiCredentialRecord(
                project_id=project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret(api_key),
                extra_headers_json='{"X-Brief":"1"}',
                enabled=enabled,
            )
        )
        await session.commit()


async def _execution_run_count() -> int:
    async with async_session_factory() as session:
        result = await session.execute(select(func.count(ExecutionRunRecord.id)))
        return int(result.scalar_one())


def _load_snapshot_brief_module() -> ModuleType:
    try:
        return importlib.import_module("backend.app.test_cases.snapshot_brief")
    except ModuleNotFoundError as error:
        if error.name == "backend.app.test_cases.snapshot_brief":
            pytest.fail(
                "Expected backend.app.test_cases.snapshot_brief service module "
                "for AI-Assisted Snapshot Brief."
            )
        raise


def _patch_snapshot_brief_provider(
    monkeypatch: pytest.MonkeyPatch,
    fake_call_provider_json: Any,
) -> None:
    snapshot_brief = _load_snapshot_brief_module()
    monkeypatch.setattr(snapshot_brief, "call_provider_json", fake_call_provider_json)


@pytest.mark.anyio
async def test_planning_snapshot_brief_success_uses_project_ai(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """brief 接口使用项目级 AI，返回 Markdown 整理稿和 warnings。"""
    await _seed_project_ai(test_project_id)
    calls: list[dict[str, Any]] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        calls.append(kwargs)
        assert kwargs["api_key"] == "sk-brief-secret"
        assert kwargs["extra_headers"] == {"X-Brief": "1"}
        assert "Planning Sheet Snapshot" in kwargs["user_prompt"]
        assert "核心目标" in kwargs["user_prompt"]
        assert "来源索引" in kwargs["user_prompt"]
        assert "行 2" in kwargs["user_prompt"]
        assert "按配置开放入口" in kwargs["user_prompt"]
        return {
            "brief_markdown": (
                "## 核心目标\n"
                "- 按配置开放活动入口。\n\n"
                "## 来源索引\n"
                "- 行 2：活动入口 | 按配置开放入口"
            ),
            "warnings": [
                {
                    "source": "snapshot_brief",
                    "level": "info",
                    "message": "整理稿仅作为辅助上下文。",
                }
            ],
        }, {"latency_ms": 9}

    _patch_snapshot_brief_provider(monkeypatch, fake_call_provider_json)

    response = await auth_client.post(
        "/api/v1/test-cases/planning-snapshot/brief",
        json=_brief_request(),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["brief_markdown"].startswith("## 核心目标")
    assert "行 2" in payload["data"]["brief_markdown"]
    assert payload["data"]["warnings"][0]["source"] == "snapshot_brief"
    assert len(calls) == 1


@pytest.mark.anyio
async def test_planning_snapshot_brief_accepts_string_warnings_from_provider(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实模型可能把 warnings 返回成字符串数组，后端应规范化而不是让整理稿失败。"""
    await _seed_project_ai(test_project_id)

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        return {
            "brief_markdown": (
                "## 核心目标\n"
                "- 按配置开放活动入口。\n\n"
                "## 来源索引\n"
                "- 行 2：活动入口 | 按配置开放入口"
            ),
            "warnings": ["整理稿仅作为辅助上下文。"],
        }, {"latency_ms": 9}

    _patch_snapshot_brief_provider(monkeypatch, fake_call_provider_json)

    response = await auth_client.post(
        "/api/v1/test-cases/planning-snapshot/brief",
        json=_brief_request(),
    )

    assert response.status_code == 200, response.text
    warning = response.json()["data"]["warnings"][0]
    assert warning == {
        "source": "snapshot_brief",
        "level": "warning",
        "message": "整理稿仅作为辅助上下文。",
    }


@pytest.mark.anyio
async def test_planning_snapshot_brief_missing_project_ai_does_not_call_provider(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """项目级 AI 未配置时返回配置错误，且不调用 provider。"""
    called = False

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal called
        called = True
        return {}, {}

    monkeypatch.setattr(
        "backend.app.ai.providers.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/planning-snapshot/brief",
        json=_brief_request(),
    )

    assert response.status_code == 400
    assert PROJECT_AI_UNAVAILABLE_MESSAGE in response.json()["detail"]
    assert called is False


@pytest.mark.anyio
async def test_planning_snapshot_brief_disabled_project_ai_returns_configuration_error(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """项目级 AI 已禁用时返回同一类中文配置错误。"""
    await _seed_project_ai(test_project_id, enabled=False)

    response = await auth_client.post(
        "/api/v1/test-cases/planning-snapshot/brief",
        json=_brief_request(),
    )

    assert response.status_code == 400
    assert PROJECT_AI_UNAVAILABLE_MESSAGE in response.json()["detail"]


@pytest.mark.anyio
async def test_planning_snapshot_brief_provider_error_is_sanitized(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI 错误返回前必须脱敏 API Key、Base URL、prompt 和 provider 原文。"""
    await _seed_project_ai(test_project_id)

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        raise ProviderConnectionError(
            "upstream",
            (
                "Base URL https://private-provider.example/v1 rejected API Key "
                "sk-brief-secret. FULL_BRIEF_PROMPT=核心目标模板。"
                " RAW_PROVIDER_RESPONSE={\"error\":\"secret stack\"}"
            ),
            status_code=502,
        )

    _patch_snapshot_brief_provider(monkeypatch, fake_call_provider_json)

    response = await auth_client.post(
        "/api/v1/test-cases/planning-snapshot/brief",
        json=_brief_request(),
    )

    assert response.status_code == 502
    body = response.text
    assert "sk-brief-secret" not in body
    assert "https://private-provider.example/v1" not in body
    assert "FULL_BRIEF_PROMPT" not in body
    assert "RAW_PROVIDER_RESPONSE" not in body


@pytest.mark.anyio
async def test_planning_snapshot_brief_does_not_persist_or_read_original_file(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """brief 只消费页面提交的 snapshot，不读取原文件，也不创建历史记录。"""
    await _seed_project_ai(test_project_id)

    async def fail_if_snapshot_is_read(**_: Any) -> Any:
        raise AssertionError("brief 接口不得重新读取原始策划案文件")

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        return {
            "brief_markdown": "## 核心目标\n- 活动入口。\n\n## 来源索引\n- 行 2",
            "warnings": [],
        }, {}

    from backend.app.api import test_cases_api

    monkeypatch.setattr(
        planning_snapshot,
        "build_planning_snapshot",
        fail_if_snapshot_is_read,
    )
    monkeypatch.setattr(
        test_cases_api,
        "build_planning_snapshot",
        fail_if_snapshot_is_read,
    )
    _patch_snapshot_brief_provider(monkeypatch, fake_call_provider_json)
    before_count = await _execution_run_count()

    response = await auth_client.post(
        "/api/v1/test-cases/planning-snapshot/brief",
        json=_brief_request(),
    )

    assert response.status_code == 200, response.text
    assert await _execution_run_count() == before_count
