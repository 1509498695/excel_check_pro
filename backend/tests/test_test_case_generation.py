"""用例生成 V1 无参考 AI 主链路测试。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from backend.app.ai.credentials import PROJECT_AI_UNAVAILABLE_MESSAGE
from backend.app.ai.providers import ProviderConnectionError
from backend.app.database import async_session_factory
from backend.app.models import (
    ExecutionRunRecord,
    Project,
    ProjectAiCredentialRecord,
    TestCaseReferenceFileRecord as ReferenceFileRecord,
)
from backend.app.security.crypto import encrypt_secret
from backend.app.test_cases.constants import STANDARD_CASE_FIELDS


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
                    {
                        "row_index": 1,
                        "column_index": 3,
                        "column_name": "备注",
                        "value": "备注",
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
            {
                "row_index": 3,
                "cells": [
                    {
                        "row_index": 3,
                        "column_index": 1,
                        "column_name": "模块",
                        "value": "奖励领取",
                    },
                    {
                        "row_index": 3,
                        "column_index": 2,
                        "column_name": "需求点",
                        "value": "每日领取一次",
                    },
                    {
                        "row_index": 3,
                        "column_index": 3,
                        "column_name": "备注",
                        "value": "跨日刷新",
                    },
                ],
            },
        ],
        "non_empty_cell_count": 9,
        "truncated": False,
        "warnings": [
            {
                "source": "snapshot",
                "level": "warning",
                "message": "V1 仅读取单元格文本，未读取图片、附件、批注或评论语义。",
            }
        ],
    }


def _generation_request(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "planning_snapshot": _snapshot_payload(),
        "source_evidence_run_id": None,
        "reference_ids": [],
        "primary_reference_id": None,
    }
    payload.update(overrides)
    return payload


async def _seed_project_ai(
    project_id: int,
    *,
    enabled: bool = True,
    api_key: str = "sk-project-secret",
) -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectAiCredentialRecord(
                project_id=project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret(api_key),
                extra_headers_json='{"X-Project":"ExcelCheck"}',
                enabled=enabled,
            )
        )
        await session.commit()


async def _execution_run_count() -> int:
    async with async_session_factory() as session:
        result = await session.execute(select(func.count(ExecutionRunRecord.id)))
        return int(result.scalar_one())


def _excel_reference_profile() -> dict[str, Any]:
    return {
        "source_type": "excel",
        "source_name": "history.xlsx",
        "default_sheet_name": "测试用例",
        "reference_case_count": 2,
        "columns": [
            {"index": 1, "original_name": "历史标题", "standard_field": "title"},
            {"index": 2, "original_name": "历史优先级", "standard_field": "priority"},
        ],
        "sheet_options": [
            {
                "name": "测试用例",
                "reference_case_count": 2,
                "is_default": True,
                "header_row_index": 1,
                "columns": [
                    {"index": 1, "original_name": "历史标题", "standard_field": "title"},
                    {"index": 2, "original_name": "历史优先级", "standard_field": "priority"},
                ],
            },
            {
                "name": "边界用例",
                "reference_case_count": 7,
                "is_default": False,
                "header_row_index": 1,
                "columns": [
                    {"index": 1, "original_name": "历史优先级", "standard_field": "priority"},
                    {"index": 2, "original_name": "历史模块", "standard_field": "module"},
                    {"index": 3, "original_name": "历史未知列", "standard_field": None},
                    {"index": 4, "original_name": "历史步骤", "standard_field": "steps"},
                    {"index": 5, "original_name": "历史标题", "standard_field": "title"},
                ],
            },
        ],
        "warnings": [],
    }


def _text_reference_profile() -> dict[str, Any]:
    return {
        "source_type": "markdown",
        "source_name": "history.md",
        "default_sheet_name": None,
        "reference_case_count": 3,
        "columns": [],
        "sheet_options": [],
        "warnings": [],
    }


async def _seed_reference(
    project_id: int,
    profile: dict[str, Any],
    *,
    filename: str = "history.xlsx",
    deleted: bool = False,
) -> int:
    async with async_session_factory() as session:
        record = ReferenceFileRecord(
            project_id=project_id,
            category_id=None,
            original_filename=filename,
            stored_filename=f"stored-{filename}",
            suffix="." + filename.rsplit(".", 1)[-1],
            size_bytes=128,
            storage_path=f"D:/references/{filename}",
            profile_json=json.dumps(profile, ensure_ascii=False),
            is_recommended_primary=False,
        )
        if deleted:
            from datetime import UTC, datetime

            record.deleted_at = datetime.now(UTC)
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record.id


async def _seed_foreign_project_reference(profile: dict[str, Any]) -> int:
    async with async_session_factory() as session:
        project = Project(name="foreign-reference-project", description="")
        session.add(project)
        await session.flush()
        project_id = project.id
    return await _seed_reference(project_id, profile, filename="foreign.xlsx")


@pytest.mark.anyio
async def test_missing_project_ai_returns_chinese_configuration_error(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未配置项目级 AI 时返回中文配置错误，且不调用 provider。"""
    called = False

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal called
        called = True
        return {}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(),
    )

    assert response.status_code == 400
    assert PROJECT_AI_UNAVAILABLE_MESSAGE in response.json()["detail"]
    assert called is False


@pytest.mark.anyio
async def test_disabled_project_ai_returns_chinese_configuration_error(
    auth_client: AsyncClient,
    test_project_id: int,
) -> None:
    """禁用项目级 AI 时返回同一类中文配置错误。"""
    await _seed_project_ai(test_project_id, enabled=False)

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(),
    )

    assert response.status_code == 400
    assert PROJECT_AI_UNAVAILABLE_MESSAGE in response.json()["detail"]


@pytest.mark.anyio
async def test_no_reference_generation_calls_provider_twice_and_computes_stats(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无参考输入也能生成；provider 调两次，统计和追踪由代码侧确认。"""
    await _seed_project_ai(test_project_id)
    calls: list[dict[str, Any]] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        calls.append(kwargs)
        assert kwargs["api_key"] == "sk-project-secret"
        assert kwargs["extra_headers"] == {"X-Project": "ExcelCheck"}
        assert "未选择参考案例" in kwargs["user_prompt"]
        assert "项目级 QA 知识库" in kwargs["user_prompt"]
        if len(calls) == 1:
            return {
                "modules": [{"name": "活动入口"}, {"name": "奖励领取"}],
                "flows": [{"name": "进入活动并领取奖励"}],
                "requirement_traces": [
                    {
                        "source_row_index": 2,
                        "source_fragment": "活动入口 | 按配置开放入口",
                        "blueprint_node": "活动入口",
                    }
                ],
                "coverage_dimensions": [{"name": "生命周期"}, {"name": "时间刷新"}],
                "risks": [{"name": "入口图语义未读取"}],
                "unmapped_requirements": [],
                "unsupported_or_unfounded_test_points": [],
                "open_questions": [],
                "warnings": [
                    {
                        "source": "blueprint",
                        "level": "warning",
                        "message": "入口图语义未读取，需人工确认。",
                    }
                ],
            }, {"latency_ms": 11}
        return {
            "cases": [
                {
                    "case_id": "",
                    "module": "活动入口",
                    "feature": "入口开放",
                    "scenario": "按配置开放入口",
                    "title": "活动入口按配置展示",
                    "preconditions": "活动配置已开启",
                    "steps": "进入主界面并查看活动入口",
                    "expected_results": "活动入口按配置展示",
                    "priority": "P1",
                    "case_type": "功能",
                    "source_requirement": "按配置开放入口",
                    "remarks": "",
                },
                {
                    "case_id": "MODEL-ID",
                    "module": "奖励领取",
                    "feature": "每日领取",
                    "scenario": "每日领取一次",
                    "title": "奖励每日仅可领取一次",
                    "preconditions": "玩家满足领取条件",
                    "steps": "领取奖励后再次点击领取",
                    "expected_results": "首次成功，重复领取被拦截",
                    "priority": "P2",
                    "case_type": "边界",
                    "source_requirement": "每日领取一次",
                    "remarks": "",
                },
            ],
            "warnings": [
                {
                    "source": "cases",
                    "level": "warning",
                    "message": "未使用参考案例增强。",
                }
            ],
            "requirement_trace": [
                {
                    "source_row_index": 2,
                    "source_fragment": "按配置开放入口",
                    "blueprint_node": "活动入口",
                    "case_id": "TC-001",
                }
            ],
            "stats": {"total": 999, "priority_counts": {"P0": 999}},
        }, {"latency_ms": 17}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )
    before_count = await _execution_run_count()

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(reference_ids=[], primary_reference_id=None),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    data = payload["data"]
    assert payload["code"] == 200
    assert len(calls) == 2
    assert data["cases"][0]["case_id"] == "TC-001"
    assert data["cases"][1]["case_id"] == "MODEL-ID"
    assert data["stats"]["total"] == 2
    assert data["stats"]["priority_counts"] == {"P1": 1, "P2": 1}
    assert data["stats"]["module_counts"] == {"活动入口": 1, "奖励领取": 1}
    assert data["stats"]["case_type_counts"] == {"功能": 1, "边界": 1}
    assert data["stats"]["warning_count"] == 3
    assert data["method_context"]["method_name"] == "QA Case Method"
    assert "V1 未接入项目级 QA 知识库" in data["method_context"]["knowledge_library_note"]
    assert data["export_columns"][:3] == ["case_id", "module", "feature"]
    assert any("未读取图片" in item["message"] for item in data["warnings"])
    assert any("入口图语义未读取" in item["message"] for item in data["warnings"])
    assert any("未使用参考案例增强" in item["message"] for item in data["warnings"])
    assert data["requirement_trace"][0]["source_row_index"] == 2
    assert "按配置开放入口" in data["requirement_trace"][0]["source_fragment"]
    assert await _execution_run_count() == before_count


@pytest.mark.anyio
async def test_generation_normalizes_provider_warning_strings(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """兼容 provider 将 warnings 返回为字符串列表，避免蓝图校验直接失败。"""
    await _seed_project_ai(test_project_id)
    calls: list[dict[str, Any]] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        calls.append(kwargs)
        if len(calls) == 1:
            return {
                "modules": ["活动入口"],
                "flows": ["进入活动"],
                "warnings": ["入口图语义未读取，需人工确认。"],
            }, {}
        return {
            "cases": [],
            "warnings": ["未使用参考案例增强。"],
            "requirement_trace": [],
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(reference_ids=[], primary_reference_id=None),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(calls) == 2
    assert {
        "source": "blueprint",
        "level": "warning",
        "message": "入口图语义未读取，需人工确认。",
    } in data["warnings"]
    assert {
        "source": "cases",
        "level": "warning",
        "message": "未使用参考案例增强。",
    } in data["warnings"]
    assert data["stats"]["warning_count"] == 3


@pytest.mark.anyio
async def test_generation_normalizes_provider_warning_description_objects(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """兼容 provider 将 warnings 返回为 {id, description} 对象。"""
    await _seed_project_ai(test_project_id)
    calls: list[dict[str, Any]] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        calls.append(kwargs)
        if len(calls) == 1:
            return {
                "modules": ["活动入口"],
                "flows": ["进入活动"],
                "warnings": [
                    {
                        "id": "W1",
                        "description": "图片资源未采纳，不能作为需求事实。",
                    }
                ],
            }, {}
        return {
            "cases": [],
            "warnings": [
                {
                    "id": "W2",
                    "description": "未使用参考案例增强。",
                }
            ],
            "requirement_trace": [],
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(reference_ids=[], primary_reference_id=None),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(calls) == 2
    assert {
        "source": "blueprint",
        "level": "warning",
        "message": "图片资源未采纳，不能作为需求事实。",
    } in data["warnings"]
    assert {
        "source": "cases",
        "level": "warning",
        "message": "未使用参考案例增强。",
    } in data["warnings"]
    assert data["stats"]["warning_count"] == 3


@pytest.mark.anyio
async def test_generation_normalizes_blueprint_mapping_fields(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """兼容 provider 将蓝图列表字段返回为 key-object 映射。"""
    await _seed_project_ai(test_project_id)
    calls: list[dict[str, Any]] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        calls.append(kwargs)
        if len(calls) == 1:
            return {
                "modules": {
                    "hero_resonance": {"description": "英雄共鸣系统"},
                },
                "flows": {
                    "open_panel": {"steps": ["打开入口", "查看界面"]},
                },
                "coverage_dimensions": {
                    "lifecycle": ["入口", "解锁", "关闭"],
                },
                "risks": {},
                "warnings": [],
            }, {}
        return {
            "cases": [],
            "warnings": [],
            "requirement_trace": [],
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(reference_ids=[], primary_reference_id=None),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["blueprint"]["modules"][0]["name"] == "hero_resonance"
    assert data["blueprint"]["flows"][0]["name"] == "open_panel"
    assert data["blueprint"]["coverage_dimensions"][0]["name"] == "lifecycle"


@pytest.mark.anyio
async def test_generation_truncates_oversized_snapshot_prompt(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """超大快照进入生成前必须按 prompt 预算截断，避免模型返回失控。"""
    await _seed_project_ai(test_project_id)
    large_rows = []
    for index in range(1, 2200):
        large_rows.append(
            {
                "row_index": index,
                "cells": [
                    {
                        "row_index": index,
                        "column_index": 1,
                        "column_name": "模块",
                        "value": "英雄共鸣",
                    },
                    {
                        "row_index": index,
                        "column_index": 2,
                        "column_name": "需求点",
                        "value": f"需求-{index:04d}-" + ("长文本" * 30),
                    },
                    {
                        "row_index": index,
                        "column_index": 3,
                        "column_name": "证据状态",
                        "value": "table",
                    },
                ],
            }
        )
    snapshot = {
        "source_summary": "local_file:xlsx：large.xlsx",
        "sheet_name": "Source Evidence",
        "columns": ["模块", "需求点", "证据状态"],
        "rows": large_rows,
        "non_empty_cell_count": len(large_rows) * 3,
        "truncated": False,
        "warnings": [],
    }
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompt = kwargs["user_prompt"]
        prompts.append(prompt)
        assert len(prompt) < 90_000
        assert "生成输入超过预算" in prompt
        assert "需求-0001" in prompt
        assert "需求-2199" not in prompt
        if len(prompts) == 1:
            return {"modules": [], "flows": [], "warnings": []}, {}
        return {"cases": [], "warnings": [], "requirement_trace": []}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(planning_snapshot=snapshot),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(prompts) == 2
    assert any("生成输入超过预算" in warning["message"] for warning in data["warnings"])


@pytest.mark.anyio
async def test_generation_normalizes_provider_case_lists_and_trace_aliases(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """兼容 provider 将步骤返回为列表、将追踪关系返回为 requirement_id/cases。"""
    await _seed_project_ai(test_project_id)
    calls: list[dict[str, Any]] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        calls.append(kwargs)
        if len(calls) == 1:
            return {
                "modules": ["英雄共鸣系统"],
                "flows": ["打开英雄共鸣界面"],
                "warnings": [],
            }, {}
        return {
            "cases": [
                {
                    "case_id": "TC-001",
                    "module": "英雄共鸣系统",
                    "feature": "功能入口",
                    "scenario": "启示之眼未建造",
                    "title": "未建造启示之眼时无法打开英雄共鸣",
                    "preconditions": "主城等级≥9级，未建造启示之眼",
                    "steps": [
                        "1. 检查已拥有英雄界面是否有共鸣入口",
                        "2. 尝试点击可能出现的入口",
                    ],
                    "expected_results": ["界面无共鸣入口", "无法打开英雄共鸣界面"],
                    "priority": "P1",
                    "case_type": "功能测试",
                    "source_requirement": "R1",
                    "planning_answer": 10,
                }
            ],
            "warnings": [],
            "requirement_trace": [
                {
                    "requirement_id": "R1",
                    "blueprint_node": "英雄共鸣系统",
                    "cases": ["TC-001"],
                }
            ],
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(reference_ids=[], primary_reference_id=None),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["cases"][0]["steps"] == (
        "1. 检查已拥有英雄界面是否有共鸣入口\n"
        "2. 尝试点击可能出现的入口"
    )
    assert data["cases"][0]["expected_results"] == "界面无共鸣入口\n无法打开英雄共鸣界面"
    assert data["cases"][0]["planning_answer"] == "10"
    assert data["requirement_trace"][0] == {
        "source_row_index": None,
        "source_fragment": "R1",
        "blueprint_node": "英雄共鸣系统",
        "case_id": "TC-001",
    }


@pytest.mark.anyio
async def test_generation_normalizes_null_requirement_trace_to_empty_list(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """兼容 provider 将 requirement_trace 返回为 null。"""
    await _seed_project_ai(test_project_id)
    calls: list[dict[str, Any]] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        calls.append(kwargs)
        if len(calls) == 1:
            return {
                "modules": ["英雄共鸣系统"],
                "flows": ["打开英雄共鸣界面"],
                "warnings": [],
            }, {}
        return {
            "cases": [
                {
                    "case_id": "TC-001",
                    "module": "英雄共鸣系统",
                    "feature": "功能入口",
                    "scenario": "启示之眼未建造",
                    "title": "未建造启示之眼时无法打开英雄共鸣",
                    "steps": "检查入口",
                    "expected_results": "无法打开英雄共鸣界面",
                    "source_requirement": "R1",
                }
            ],
            "warnings": [],
            "requirement_trace": None,
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(reference_ids=[], primary_reference_id=None),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["cases"][0]["case_id"] == "TC-001"
    assert data["requirement_trace"][0]["case_id"] == "TC-001"
    assert data["requirement_trace"][0]["source_fragment"]


@pytest.mark.anyio
async def test_supplementary_references_without_primary_do_not_select_primary(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """只选附加参考、未指定主参考时生成成功，且不隐式挑第一条或最新。"""
    await _seed_project_ai(test_project_id)
    reference_id = await _seed_reference(test_project_id, _excel_reference_profile())
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompts.append(kwargs["user_prompt"])
        assert "未指定主参考" in kwargs["user_prompt"]
        assert "不要自动选择最新、第一条或推荐主参考" in kwargs["user_prompt"]
        if len(prompts) == 1:
            return {"modules": [], "flows": [], "warnings": []}, {}
        return {"cases": [], "warnings": [], "requirement_trace": []}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(reference_ids=[reference_id], primary_reference_id=None),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(prompts) == 2
    assert data["export_columns"] == list(STANDARD_CASE_FIELDS)
    assert data["primary_reference_profile"] is None
    assert data["reference_context"]["primary_reference_id"] is None


@pytest.mark.anyio
async def test_primary_reference_must_belong_to_selected_reference_ids(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """主参考必须属于 reference_ids，不能提交游离主参考。"""
    await _seed_project_ai(test_project_id)
    reference_id = await _seed_reference(test_project_id, _excel_reference_profile())
    called = False

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal called
        called = True
        return {}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(reference_ids=[], primary_reference_id=reference_id),
    )

    assert response.status_code == 400
    assert "主参考案例必须属于已选参考案例集合" in response.json()["detail"]
    assert called is False


@pytest.mark.anyio
async def test_cross_project_reference_is_rejected(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """跨项目参考案例不能被当前项目生成请求使用。"""
    await _seed_project_ai(test_project_id)
    foreign_reference_id = await _seed_foreign_project_reference(_excel_reference_profile())
    called = False

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal called
        called = True
        return {}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(
            reference_ids=[foreign_reference_id],
            primary_reference_id=foreign_reference_id,
        ),
    )

    assert response.status_code == 400
    assert "参考案例不存在或已删除" in response.json()["detail"]
    assert called is False


@pytest.mark.anyio
async def test_excel_primary_reference_sheet_controls_reference_count_and_export_columns(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Excel 主参考按选中 Sheet 使用画像，并据此生成导出字段顺序。"""
    await _seed_project_ai(test_project_id)
    reference_id = await _seed_reference(test_project_id, _excel_reference_profile())
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompts.append(kwargs["user_prompt"])
        assert "参考案例不是需求来源" in kwargs["user_prompt"]
        assert "字段顺序、层级、粒度、命名和历史风格参考" in kwargs["user_prompt"]
        assert "边界用例" in kwargs["user_prompt"]
        assert "参考用例数量：7" in kwargs["user_prompt"]
        if len(prompts) == 1:
            return {"modules": [], "flows": [], "warnings": []}, {}
        return {"cases": [], "warnings": [], "requirement_trace": []}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(
            reference_ids=[reference_id],
            primary_reference_id=reference_id,
            primary_reference_sheet_name="边界用例",
        ),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["primary_reference_profile"]["selected_sheet_name"] == "边界用例"
    assert data["primary_reference_profile"]["reference_case_count"] == 7
    assert data["export_columns"][:4] == ["priority", "module", "steps", "title"]
    assert "历史未知列" not in data["export_columns"]


@pytest.mark.anyio
async def test_markdown_primary_reference_rejects_non_empty_sheet_name(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Markdown/TXT 主参考没有 Sheet，公共请求不得传非空 Sheet 名。"""
    await _seed_project_ai(test_project_id)
    reference_id = await _seed_reference(
        test_project_id,
        _text_reference_profile(),
        filename="history.md",
    )
    called = False

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal called
        called = True
        return {}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(
            reference_ids=[reference_id],
            primary_reference_id=reference_id,
            primary_reference_sheet_name="测试用例",
        ),
    )

    assert response.status_code == 400
    assert "当前主参考没有 Sheet" in response.json()["detail"]
    assert called is False


@pytest.mark.anyio
async def test_provider_error_is_sanitized(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider 错误返回给前端前必须脱敏完整 API Key。"""
    await _seed_project_ai(test_project_id)

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        raise ProviderConnectionError(
            "unknown",
            "上游拒绝了 API Key sk-project-secret，请检查配置。",
            status_code=502,
        )

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(),
    )

    assert response.status_code == 502
    assert "sk-project-secret" not in response.text
    assert "sk-***cret" in response.text


@pytest.mark.anyio
async def test_snapshot_brief_markdown_is_auxiliary_context_in_generation_prompts(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """生成接口接收顶层整理稿，并在两阶段 prompt 中标为辅助上下文。"""
    await _seed_project_ai(test_project_id)
    prompts: list[str] = []
    brief_markdown = (
        "## 核心目标\n"
        "- 活动入口按配置开放。\n\n"
        "## 来源索引\n"
        "- 行 2：活动入口 | 按配置开放入口"
    )

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompts.append(kwargs["user_prompt"])
        assert "AI 快照整理稿" in kwargs["user_prompt"]
        assert "辅助上下文" in kwargs["user_prompt"]
        assert "需求来源只能来自 Planning Sheet Snapshot" in kwargs["user_prompt"]
        assert brief_markdown in kwargs["user_prompt"]
        assert "行 2" in kwargs["user_prompt"]
        assert "按配置开放入口" in kwargs["user_prompt"]
        if len(prompts) == 1:
            return {"modules": [], "flows": [], "warnings": []}, {}
        return {"cases": [], "warnings": [], "requirement_trace": []}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(
            reference_ids=[],
            primary_reference_id=None,
            snapshot_brief_markdown=brief_markdown,
        ),
    )

    assert response.status_code == 200, response.text
    assert len(prompts) == 2


@pytest.mark.anyio
async def test_generation_without_snapshot_brief_does_not_use_generation_options_brief(
    auth_client: AsyncClient,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未提交顶层整理稿时，后端不得从 generation_options 取整理稿上下文。"""
    await _seed_project_ai(test_project_id)
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompts.append(kwargs["user_prompt"])
        assert "AI 快照整理稿" not in kwargs["user_prompt"]
        assert "不应参与生成的整理稿" not in kwargs["user_prompt"]
        if len(prompts) == 1:
            return {"modules": [], "flows": [], "warnings": []}, {}
        return {"cases": [], "warnings": [], "requirement_trace": []}, {}

    monkeypatch.setattr(
        "backend.app.test_cases.generation.call_provider_json",
        fake_call_provider_json,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json=_generation_request(
            reference_ids=[],
            primary_reference_id=None,
            generation_options={
                "snapshot_brief_markdown": "不应参与生成的整理稿",
            },
        ),
    )

    assert response.status_code == 200, response.text
    assert len(prompts) == 2


@pytest.mark.anyio
async def test_generation_rejects_public_knowledge_context(
    auth_client: AsyncClient,
) -> None:
    """V1 公共请求不得传入项目级 QA 知识库上下文。"""
    payload = {
        **_generation_request(),
        "knowledge_context": {"raw": "用户手工注入知识"},
    }

    response = await auth_client.post("/api/v1/test-cases/generate", json=payload)

    assert response.status_code == 400
    assert "V1 不接收用户传入的知识库上下文" in response.json()["detail"]
