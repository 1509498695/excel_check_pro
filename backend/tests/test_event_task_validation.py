"""节日任务校验解析、预览与执行测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.integrations.feishu_client import FeishuSheetTable
from backend.app.services.event_task_parser import (
    build_event_task_config_rows,
    parse_event_task_sheet,
)
from backend.run import app


_PREVIEW_URL = "/api/v1/workbench/event-tasks/preview"


def _create_event_task_workbook(
    target_path: Path,
    *,
    left_rows: list[dict[str, Any]] | None = None,
    right_rows: list[dict[str, Any]],
) -> Path:
    with pd.ExcelWriter(target_path, engine="openpyxl") as writer:
        if left_rows is not None:
            pd.DataFrame(left_rows).to_excel(writer, sheet_name="task_plan", index=False)
        pd.DataFrame(right_rows).to_excel(writer, sheet_name="EventTask", index=False)
    return target_path


def _build_execute_payload(workbook_path: Path) -> dict[str, Any]:
    return {
        "sources": [
            {
                "id": "src-event-task",
                "type": "local_excel",
                "path": str(workbook_path),
            }
        ],
        "variables": [
            {
                "tag": "[task-plan]",
                "source_id": "src-event-task",
                "sheet": "task_plan",
                "variable_kind": "composite",
                "columns": ["任务组ID", "INT_TaskID", "任务描述", "STR_Loot"],
                "key_column": "任务组ID",
                "append_index_to_key": True,
            },
            {
                "tag": "[EventTask]",
                "source_id": "src-event-task",
                "sheet": "EventTask",
                "variable_kind": "composite",
                "columns": ["INT_ID", "INT_TaskID", "STR_Desc", "STR_Loot"],
                "key_column": "INT_ID",
                "append_index_to_key": True,
            },
        ],
        "rules": [
            {
                "rule_type": "event_task_validation",
                "params": {
                    "left_tag": "[task-plan]",
                    "right_tag": "[EventTask]",
                    "rule_name": "节日任务校验",
                    "left_task_group_field": "任务组ID",
                    "left_task_id_field": "INT_TaskID",
                    "left_task_desc_field": "任务描述",
                    "left_task_loot_field": "STR_Loot",
                    "right_task_group_field": "INT_ID",
                    "right_task_id_field": "INT_TaskID",
                    "right_task_desc_field": "STR_Desc",
                    "right_task_loot_field": "STR_Loot",
                },
            }
        ],
    }


async def _execute_event_task_compare(payload: dict[str, Any]) -> list[dict[str, Any]]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/api/v1/engine/execute", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200
    return body["data"]["abnormal_results"]


def _sheet_table(raw_values: list[list[Any]]) -> FeishuSheetTable:
    return FeishuSheetTable(
        spreadsheet_token="shtcnabc123",
        sheet_id="gid_task",
        sheet_title="节日任务表",
        range="gid_task!A1:D20",
        columns=[],
        rows=[],
        raw_values=raw_values,
    )


def _patch_sheet_values(
    monkeypatch: pytest.MonkeyPatch,
    raw_values: list[list[Any]],
) -> None:
    from backend.app.integrations import feishu_client

    async def _read_values(*_args, **kwargs):
        assert kwargs["sheet_id"] == "gid_task"
        assert kwargs["value_render_option"] == "FormattedValue"
        return _sheet_table(raw_values)

    monkeypatch.setattr(feishu_client, "read_sheet_values", _read_values)


async def _seed_workbench_event_task_config(
    auth_client: AsyncClient,
    *,
    workbook_path: Path,
    variable_tag: str = "[EventTask]",
    columns: list[str] | None = None,
) -> None:
    resolved_columns = columns or ["INT_ID", "INT_TaskID", "STR_Desc", "STR_Loot"]
    response = await auth_client.put(
        "/api/v1/workbench/config",
        json={
            "sources": [
                {
                    "id": "feishu-task",
                    "type": "feishu",
                    "pathOrUrl": "https://demo.feishu.cn/sheets/shtcnabc123",
                },
                {
                    "id": "event-task-config",
                    "type": "local_excel",
                    "path": str(workbook_path),
                },
            ],
            "variables": [
                {
                    "tag": variable_tag,
                    "source_id": "event-task-config",
                    "sheet": "EventTask",
                    "variable_kind": "composite",
                    "columns": resolved_columns,
                    "key_column": "INT_ID",
                    "append_index_to_key": True,
                }
            ],
            "ruleGroups": [],
            "orchestrationRules": [],
        },
    )
    assert response.status_code == 200, response.text


async def _post_event_task_preview(
    auth_client: AsyncClient,
    *,
    config_variable_tag: str = "[EventTask]",
    validation_scope: str = "all",
    task_group_id_filter: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "feishu_source_id": "feishu-task",
        "feishu_sheet_id": "gid_task",
        "config_variable_tag": config_variable_tag,
        "parse_strategy": "group_desc",
        "ai_parse_mode": "disabled",
        "validation_scope": validation_scope,
    }
    if task_group_id_filter is not None:
        payload["task_group_id_filter"] = task_group_id_filter

    response = await auth_client.post(_PREVIEW_URL, json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_parse_event_task_sheet_extracts_group_id_and_rows() -> None:
    result = parse_event_task_sheet(
        [
            ["任务组ID", "INT_TaskID", "任务描述", "STR_Loot"],
            ["26051802", "4476", "累计登陆1天", "{item,16001,1}"],
            ["26051803", "4477", "累计登陆2天", "{item,16002,1}"],
        ]
    )

    assert result.parse_status == "success"
    assert result.task_group_ids == ["26051802", "26051803"]
    assert result.detail_row_count == 2
    assert result.rows[0].task_group_id == "26051802"
    assert result.rows[0].task_id == "4476"


def test_parse_event_task_sheet_supports_original_wide_reward_table() -> None:
    result = parse_event_task_sheet(
        [
            [
                "",
                "",
                "",
                "道具1",
                "",
                "",
                "",
                "道具2",
                "",
                "",
                "",
                "道具3",
                "",
                "",
                "",
            ],
            [
                "任务id",
                "天数",
                "任务要求",
                "道具ID",
                "道具名称",
                "数量",
                "价值类型",
                "道具ID",
                "道具名称",
                "数量",
                "价值类型",
                "道具ID",
                "道具名称",
                "数量",
                "价值类型",
            ],
            [
                "26051802",
                "1",
                "累计登陆1天",
                "2087",
                "金色箱子钥匙",
                "1",
                "核心",
                "3",
                "黄金+150000",
                "1",
                "非核心",
                "",
                "",
                "",
                "",
            ],
        ]
    )

    assert result.parse_status == "success"
    assert result.task_group_ids == ["26051802"]
    assert result.rows[0].task_group_id == "26051802"
    assert result.rows[0].task_id is None
    assert result.rows[0].task_desc == "累计登陆1天"
    assert result.rows[0].loot == "{item,2087,1},{item,3,1}"


def test_event_task_config_rows_extract_task_group_from_key_prefix() -> None:
    frame = pd.DataFrame(
        [
            {
                "__key__": "26051802_4476",
                "INT_ID": "99999999",
                "INT_TaskID": "4476",
                "STR_Desc": "累计登陆1天",
                "STR_Loot": "{item,16001,1}",
                "_row_index": 7,
            }
        ],
        dtype=object,
    )

    rows, warnings = build_event_task_config_rows(frame)

    assert warnings == []
    assert rows[0].task_group_id == "26051802"
    assert rows[0].config_key == "26051802_4476"
    assert rows[0].row_index == 7


@pytest.mark.anyio
async def test_workbench_event_task_preview_returns_matching_rows(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workbook_path = _create_event_task_workbook(
        tmp_path / "event_task_config.xlsx",
        right_rows=[
            {
                "INT_ID": 26051802,
                "INT_TaskID": 4476,
                "STR_Desc": "累计登陆1天",
                "STR_Loot": "{item,16001,1}",
            },
            {
                "INT_ID": 26051803,
                "INT_TaskID": 4477,
                "STR_Desc": "累计登陆2天",
                "STR_Loot": "{item,16002,1}",
            },
        ],
    )
    await _seed_workbench_event_task_config(auth_client, workbook_path=workbook_path)
    _patch_sheet_values(
        monkeypatch,
        [
            ["任务组ID", "INT_TaskID", "任务描述", "STR_Loot"],
            ["26051802", "4476", "累计登陆1天", "{item,16001,1}"],
            ["26051803", "4477", "累计登陆2天", "{item,16002,1}"],
        ],
    )

    data = await _post_event_task_preview(auth_client)

    assert data["success"] is True
    assert data["task_group_ids"] == ["26051802", "26051803"]
    assert data["detail_row_count"] == 2
    assert data["preview_rows"][0]["task_group_id"] == "26051802"
    assert data["preview_rows"][0]["match_type"] == "group_desc"
    assert data["preview_rows"][0]["config_key"].startswith("26051802_")
    assert data["raw_sheet_name"] == "节日任务表"


@pytest.mark.anyio
async def test_workbench_event_task_preview_supports_original_table_with_figure_two_config(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_tag = "[edv-EventTask-INT_ID-mapping]"
    workbook_path = _create_event_task_workbook(
        tmp_path / "event_task_config.xlsx",
        right_rows=[
            {
                "INT_ID": 26051802,
                "INT_TaskID": 4476,
                "STR_Title": "累计登陆",
                "STR_Desc": "累计登陆1天",
                "STR_Loot": "{item,2087,1},{item,3,1}",
            }
        ],
    )
    await _seed_workbench_event_task_config(
        auth_client,
        workbook_path=workbook_path,
        variable_tag=config_tag,
        columns=["INT_ID", "INT_TaskID", "STR_Title", "STR_Desc", "STR_Loot"],
    )
    _patch_sheet_values(
        monkeypatch,
        [
            [
                "",
                "",
                "",
                "道具1",
                "",
                "",
                "",
                "道具2",
                "",
                "",
                "",
            ],
            [
                "任务id",
                "天数",
                "任务要求",
                "道具ID",
                "道具名称",
                "数量",
                "价值类型",
                "道具ID",
                "道具名称",
                "数量",
                "价值类型",
            ],
            [
                "26051802",
                "1",
                "累计登陆1天",
                "2087",
                "金色箱子钥匙",
                "1",
                "核心",
                "3",
                "黄金+150000",
                "1",
                "非核心",
            ],
        ],
    )

    data = await _post_event_task_preview(
        auth_client,
        config_variable_tag=config_tag,
    )

    assert data["success"] is True
    assert data["task_group_ids"] == ["26051802"]
    assert data["detail_row_count"] == 1
    assert data["preview_rows"][0]["task_group_id"] == "26051802"
    assert data["preview_rows"][0]["task_desc"] == "累计登陆1天"
    assert data["preview_rows"][0]["loot"] == "{item,2087,1},{item,3,1}"
    assert data["preview_rows"][0]["match_type"] == "group_desc"
    assert data["preview_rows"][0]["config_key"].startswith("26051802_")


@pytest.mark.anyio
async def test_workbench_event_task_preview_filters_specified_group(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workbook_path = _create_event_task_workbook(
        tmp_path / "event_task_config.xlsx",
        right_rows=[
            {
                "INT_ID": 26051802,
                "INT_TaskID": 4476,
                "STR_Desc": "累计登陆1天",
                "STR_Loot": "{item,16001,1}",
            }
        ],
    )
    await _seed_workbench_event_task_config(auth_client, workbook_path=workbook_path)
    _patch_sheet_values(
        monkeypatch,
        [
            ["任务组ID", "INT_TaskID", "任务描述", "STR_Loot"],
            ["26051802", "4476", "累计登陆1天", "{item,16001,1}"],
            ["26051803", "4477", "累计登陆2天", "{item,16002,1}"],
        ],
    )

    data = await _post_event_task_preview(
        auth_client,
        validation_scope="specified",
        task_group_id_filter="26051803",
    )

    assert data["success"] is True
    assert data["task_group_ids"] == ["26051803"]
    assert data["detail_row_count"] == 1
    assert data["preview_rows"][0]["task_group_id"] == "26051803"


@pytest.mark.anyio
async def test_execute_engine_event_task_validation_reports_mismatch_and_missing(
    tmp_path: Path,
) -> None:
    workbook_path = _create_event_task_workbook(
        tmp_path / "event_task_execute.xlsx",
        left_rows=[
            {
                "任务组ID": 26051802,
                "INT_TaskID": 4476,
                "任务描述": "累计登陆1天",
                "STR_Loot": "{item,16001,1}",
            },
            {
                "任务组ID": 26051802,
                "INT_TaskID": 4477,
                "任务描述": "累计登陆2天",
                "STR_Loot": "{item,16002,1}",
            },
        ],
        right_rows=[
            {
                "INT_ID": 26051802,
                "INT_TaskID": 4476,
                "STR_Desc": "累计登陆1天",
                "STR_Loot": "{item,16001,9}",
            },
            {
                "INT_ID": 26051802,
                "INT_TaskID": 4477,
                "STR_Desc": "累计登录2天",
                "STR_Loot": "{item,16002,1}",
            },
            {
                "INT_ID": 26051802,
                "INT_TaskID": 4478,
                "STR_Desc": "累计登陆3天",
                "STR_Loot": "{item,16003,1}",
            },
        ],
    )

    abnormal_results = await _execute_event_task_compare(_build_execute_payload(workbook_path))
    error_types = {result["error_type"] for result in abnormal_results}

    assert "loot_mismatch" in error_types
    assert "desc_mismatch" in error_types
    assert "left_missing_task" in error_types
    assert any(result.get("task_group_id") == "26051802" for result in abnormal_results)
