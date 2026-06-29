"""用例生成 V1 Excel 导出测试。"""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy import func, select

from backend.app.database import async_session_factory
from backend.app.models import ExecutionRunRecord
from backend.app.test_cases.constants import STANDARD_CASE_FIELD_LABELS, STANDARD_CASE_FIELDS


def _blueprint() -> dict[str, Any]:
    return {
        "modules": [{"name": "活动入口"}, {"name": "奖励领取"}],
        "flows": [{"name": "进入活动并领取奖励"}],
        "requirement_traces": [
            {
                "source_row_index": 2,
                "source_fragment": "按配置开放入口",
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
    }


def _cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "TC-001",
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
            "config_source": "ActivityConfig",
            "planning_answer": "",
            "initial_status": "未执行",
            "bug_link": "",
            "remarks": "入口图需人工确认",
        },
        {
            "case_id": "TC-002",
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
            "config_source": "",
            "planning_answer": "",
            "initial_status": "未执行",
            "bug_link": "",
            "remarks": "",
        },
    ]


def _warnings() -> list[dict[str, str]]:
    return [
        {
            "source": "snapshot",
            "level": "warning",
            "message": "V1 仅读取单元格文本，未读取图片、附件、批注或评论语义。",
        },
        {
            "source": "cases",
            "level": "warning",
            "message": "未使用参考案例增强。",
        },
    ]


def _stats() -> dict[str, Any]:
    return {
        "total": 2,
        "priority_counts": {"P1": 1, "P2": 1},
        "module_counts": {"活动入口": 1, "奖励领取": 1},
        "case_type_counts": {"功能": 1, "边界": 1},
        "warning_count": 2,
    }


def _export_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "blueprint": _blueprint(),
        "cases": _cases(),
        "warnings": _warnings(),
        "stats": _stats(),
        "export_columns": list(STANDARD_CASE_FIELDS),
        "source_summary": "上传 Excel：planning.xlsx / 策划案",
    }
    payload.update(overrides)
    return payload


def _load_response_workbook(response) -> Any:
    return load_workbook(BytesIO(response.content))


async def _execution_run_count() -> int:
    async with async_session_factory() as session:
        result = await session.execute(select(func.count(ExecutionRunRecord.id)))
        return int(result.scalar_one())


@pytest.mark.anyio
async def test_export_returns_xlsx_with_three_sheets_and_standard_fields(
    auth_client: AsyncClient,
) -> None:
    """无主参考时按标准字段顺序导出三个 Sheet。"""
    before_count = await _execution_run_count()

    response = await auth_client.post(
        "/api/v1/test-cases/export",
        json=_export_payload(),
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment;" in response.headers["content-disposition"]
    assert "test-cases-" in response.headers["content-disposition"]
    assert response.headers["content-disposition"].endswith('.xlsx"')

    workbook = _load_response_workbook(response)
    assert workbook.sheetnames == ["测试用例", "用例蓝图", "生成说明"]
    case_sheet = workbook["测试用例"]
    assert [cell.value for cell in case_sheet[1]] == [
        STANDARD_CASE_FIELD_LABELS[field] for field in STANDARD_CASE_FIELDS
    ]
    assert case_sheet["A2"].value == "TC-001"
    assert case_sheet["E2"].value == "活动入口按配置展示"
    assert workbook["用例蓝图"]["A1"].value == "区块"
    assert workbook["生成说明"]["A1"].value == "项目"
    assert any(
        "未读取图片" in str(row[2].value)
        for row in workbook["生成说明"].iter_rows(min_row=2)
        if row[0].value == "warning"
    )
    assert await _execution_run_count() == before_count


@pytest.mark.anyio
async def test_export_respects_primary_reference_profile_and_ignores_unknown_columns(
    auth_client: AsyncClient,
) -> None:
    """有主参考字段画像时只采用可映射标准字段，未知列不强行生成。"""
    response = await auth_client.post(
        "/api/v1/test-cases/export",
        json=_export_payload(
            primary_reference_profile={
                "name": "历史活动用例.xlsx",
                "columns": [
                    {"original_name": "历史标题", "standard_field": "title"},
                    {"original_name": "历史未知列", "standard_field": ""},
                    {"original_name": "历史优先级", "standard_field": "priority"},
                    {"original_name": "历史预期", "standard_field": "expected_results"},
                ],
                "raw_prompt": "sk-secret should never appear",
                "provider_response": {"api_key": "sk-secret"},
            }
        ),
    )

    assert response.status_code == 200, response.text
    workbook = _load_response_workbook(response)
    headers = [cell.value for cell in workbook["测试用例"][1]]

    assert headers[:3] == ["用例标题", "优先级", "预期结果"]
    assert "历史未知列" not in headers
    assert STANDARD_CASE_FIELD_LABELS["case_id"] in headers
    assert STANDARD_CASE_FIELD_LABELS["module"] in headers
    assert workbook["测试用例"]["A2"].value == "活动入口按配置展示"
    assert workbook["测试用例"]["B2"].value == "P1"
    workbook_text = "\n".join(
        str(cell.value)
        for sheet in workbook.worksheets
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )
    assert "sk-secret" not in workbook_text
    assert "raw_prompt" not in workbook_text
    assert "provider_response" not in workbook_text


@pytest.mark.anyio
async def test_export_uses_selected_excel_reference_sheet_columns(
    auth_client: AsyncClient,
) -> None:
    """完整 Excel 主参考画像传入导出时，应按选中 Sheet 的可识别字段排序。"""
    response = await auth_client.post(
        "/api/v1/test-cases/export",
        json=_export_payload(
            primary_reference_profile={
                "source_type": "excel",
                "source_name": "历史活动用例.xlsx",
                "default_sheet_name": "测试用例",
                "selected_sheet_name": "边界用例",
                "reference_case_count": 7,
                "columns": [
                    {"original_name": "默认标题", "standard_field": "title"},
                ],
                "sheet_options": [
                    {
                        "name": "测试用例",
                        "reference_case_count": 2,
                        "header_row_index": 1,
                        "columns": [
                            {"original_name": "默认标题", "standard_field": "title"},
                        ],
                    },
                    {
                        "name": "边界用例",
                        "reference_case_count": 7,
                        "header_row_index": 1,
                        "columns": [
                            {"original_name": "历史优先级", "standard_field": "priority"},
                            {"original_name": "历史模块", "standard_field": "module"},
                            {"original_name": "历史未知列", "standard_field": None},
                            {"original_name": "历史步骤", "standard_field": "steps"},
                            {"original_name": "历史标题", "standard_field": "title"},
                        ],
                    },
                ],
            }
        ),
    )

    assert response.status_code == 200, response.text
    workbook = _load_response_workbook(response)
    headers = [cell.value for cell in workbook["测试用例"][1]]

    assert headers[:4] == ["优先级", "功能模块", "操作步骤", "用例标题"]
    assert "历史未知列" not in headers
    assert STANDARD_CASE_FIELD_LABELS["case_id"] in headers
