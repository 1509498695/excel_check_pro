"""用例生成 V1 策划案快照接口测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from httpx import AsyncClient
from openpyxl import Workbook
from sqlalchemy import func, select

from backend.app.database import async_session_factory
from backend.app.integrations.feishu_client import (
    FEISHU_DOCUMENT_PERMISSION_DENIED,
    FeishuClientError,
)
from backend.app.models import ExecutionRunRecord
from backend.app.test_cases import planning_snapshot


def _write_planning_workbook(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(
            [
                ["模块", "需求点", "备注"],
                ["活动入口", "按配置开放入口", "入口图未读取"],
                ["奖励领取", "每日领取一次", "跨日刷新"],
            ]
        ).to_excel(writer, sheet_name="策划案", index=False, header=False)
        pd.DataFrame([["不应读取"]]).to_excel(
            writer,
            sheet_name="其它 Sheet",
            index=False,
            header=False,
        )
    return path


def _write_empty_workbook(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "空策划"
    workbook.save(path)
    return path


def _write_large_workbook(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = [
        ["超长单元格ABCDEFGHIJ", "需求点11111", "额外列1", "额外列2"],
        ["第二行模块", "第二行需求", "额外列3", "额外列4"],
        ["第三行模块", "第三行需求", "额外列5", "额外列6"],
    ]
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(values).to_excel(
            writer,
            sheet_name="超限策划",
            index=False,
            header=False,
        )
    return path


async def _execution_run_count() -> int:
    async with async_session_factory() as session:
        result = await session.execute(select(func.count(ExecutionRunRecord.id)))
        return int(result.scalar_one())


def _uploaded_excel_payload(path: Path, *, sheet_name: str = "策划案") -> dict[str, Any]:
    return {
        "source_type": "uploaded_excel",
        "source": {
            "id": "plan-source",
            "type": "local_excel",
            "pathOrUrl": str(path),
        },
        "sheet_name": sheet_name,
    }


def _warning_messages(payload: dict[str, Any]) -> list[str]:
    return [str(item["message"]) for item in payload["data"]["warnings"]]


@pytest.mark.anyio
async def test_excel_planning_snapshot_reads_selected_sheet(
    auth_client: AsyncClient,
    tmp_path: Path,
) -> None:
    """Excel 快照读取指定 Sheet，并保留原始行列和值。"""
    workbook_path = _write_planning_workbook(tmp_path / "planning.xlsx")

    response = await auth_client.post(
        "/api/v1/test-cases/planning-snapshot",
        json=_uploaded_excel_payload(workbook_path),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["code"] == 200
    data = payload["data"]
    assert data["sheet_name"] == "策划案"
    assert data["columns"] == ["模块", "需求点", "备注"]
    assert data["non_empty_cell_count"] == 9
    assert data["truncated"] is False
    assert data["rows"][0]["row_index"] == 1
    assert data["rows"][0]["cells"][0] == {
        "row_index": 1,
        "column_index": 1,
        "column_name": "模块",
        "value": "模块",
        "truncated": False,
    }
    assert data["rows"][1]["cells"][1]["value"] == "按配置开放入口"
    assert any("未读取图片" in message for message in _warning_messages(payload))


@pytest.mark.anyio
async def test_empty_excel_planning_sheet_returns_empty_snapshot_warning(
    auth_client: AsyncClient,
    tmp_path: Path,
) -> None:
    """空 Sheet 返回空快照，并显式给出 warning。"""
    workbook_path = _write_empty_workbook(tmp_path / "empty.xlsx")

    response = await auth_client.post(
        "/api/v1/test-cases/planning-snapshot",
        json=_uploaded_excel_payload(workbook_path, sheet_name="空策划"),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    data = payload["data"]
    assert data["rows"] == []
    assert data["columns"] == []
    assert data["non_empty_cell_count"] == 0
    warning_messages = _warning_messages(payload)
    assert any("为空" in message for message in warning_messages)
    assert any("未读取图片" in message for message in warning_messages)


@pytest.mark.anyio
async def test_excel_snapshot_limits_return_visible_warnings(
    auth_client: AsyncClient,
    tmp_path: Path,
) -> None:
    """行、列、非空单元格、单元格长度和总字符预算超限都必须显式 warning。"""
    workbook_path = _write_large_workbook(tmp_path / "large.xlsx")
    payload = {
        **_uploaded_excel_payload(workbook_path, sheet_name="超限策划"),
        "limits": {
            "max_rows": 2,
            "max_columns": 2,
            "max_non_empty_cells": 3,
            "max_cell_chars": 5,
            "max_chars": 10,
        },
    }

    response = await auth_client.post(
        "/api/v1/test-cases/planning-snapshot",
        json=payload,
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    warning_text = "\n".join(_warning_messages(response.json()))
    assert data["truncated"] is True
    assert len(data["rows"]) == 2
    assert data["columns"] == ["超长单元格", "需求点11"]
    assert "纳入前 2 行" in warning_text
    assert "纳入前 2 列" in warning_text
    assert "非空单元格" in warning_text
    assert "截断到 5 字符" in warning_text
    assert "总字符" in warning_text
    assert data["rows"][0]["cells"][0]["value"] == "超长单元格"
    assert data["rows"][0]["cells"][0]["truncated"] is True


@pytest.mark.anyio
async def test_excel_snapshot_rejects_local_path_outside_allowlist(
    auth_client: AsyncClient,
) -> None:
    """本地 Excel 路径继续复用 local_reader 的 allowlist 安全校验。"""
    response = await auth_client.post(
        "/api/v1/test-cases/planning-snapshot",
        json=_uploaded_excel_payload(Path("C:/outside/planning.xlsx")),
    )

    assert response.status_code == 403
    assert "LOCAL_FILE_ROOT_ALLOWLIST" in response.json()["detail"]


@pytest.mark.anyio
async def test_planning_snapshot_does_not_create_generation_history(
    auth_client: AsyncClient,
    tmp_path: Path,
) -> None:
    """读取快照不应创建执行任务或生成历史记录。"""
    workbook_path = _write_planning_workbook(tmp_path / "planning.xlsx")
    before_count = await _execution_run_count()

    response = await auth_client.post(
        "/api/v1/test-cases/planning-snapshot",
        json=_uploaded_excel_payload(workbook_path),
    )

    assert response.status_code == 200, response.text
    assert await _execution_run_count() == before_count


@pytest.mark.anyio
async def test_feishu_planning_snapshot_uses_monkeypatchable_reader(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """飞书读取通过独立适配函数接入，测试可 monkeypatch 外部客户端。"""

    async def fake_read_feishu_planning_values(**_: Any) -> tuple[str, str, list[list[Any]]]:
        return (
            "飞书电子表格：活动策划",
            "活动 Sheet",
            [["模块", "需求点"], ["活动入口", "按配置开放"]],
        )

    monkeypatch.setattr(
        planning_snapshot,
        "read_feishu_planning_values",
        fake_read_feishu_planning_values,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/planning-snapshot",
        json={
            "source_type": "feishu",
            "source": {
                "id": "plan-feishu",
                "type": "feishu",
                "pathOrUrl": "https://example.feishu.cn/sheets/shtcnxxx",
            },
            "sheet_name": "活动 Sheet",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["source_summary"] == "飞书电子表格：活动策划"
    assert data["sheet_name"] == "活动 Sheet"
    assert data["rows"][1]["cells"][0]["value"] == "活动入口"


@pytest.mark.anyio
async def test_feishu_permission_failure_returns_chinese_error(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """飞书权限不足时转换为页面可展示的中文错误。"""

    async def fake_read_feishu_planning_values(**_: Any) -> tuple[str, str, list[list[Any]]]:
        raise FeishuClientError(FEISHU_DOCUMENT_PERMISSION_DENIED, "forbidden")

    monkeypatch.setattr(
        planning_snapshot,
        "read_feishu_planning_values",
        fake_read_feishu_planning_values,
    )

    response = await auth_client.post(
        "/api/v1/test-cases/planning-snapshot",
        json={
            "source_type": "feishu",
            "source": {
                "id": "plan-feishu",
                "type": "feishu",
                "pathOrUrl": "https://example.feishu.cn/sheets/shtcnxxx",
            },
            "sheet_name": "活动 Sheet",
        },
    )

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["code"] == FEISHU_DOCUMENT_PERMISSION_DENIED
    assert "机器人暂无该表格权限" in detail["msg"]
