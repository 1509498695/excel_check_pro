"""个人校验礼包规划表预览接口测试。"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from backend.app.integrations.feishu_client import FeishuSheetTable


_PREVIEW_URL = "/api/v1/workbench/package-items/preview"


async def _seed_workbench_feishu_source(auth_client: AsyncClient) -> None:
    response = await auth_client.put(
        "/api/v1/workbench/config",
        json={
            "sources": [
                {
                    "id": "feishu-plan",
                    "type": "feishu",
                    "pathOrUrl": "https://demo.feishu.cn/sheets/shtcnabc123",
                }
            ],
            "variables": [],
            "ruleGroups": [],
            "orchestrationRules": [],
        },
    )
    assert response.status_code == 200, response.text


def _sheet_table(raw_values: list[list[Any]]) -> FeishuSheetTable:
    return FeishuSheetTable(
        spreadsheet_token="shtcnabc123",
        sheet_id="gid_plan",
        sheet_title="礼包规划",
        range="gid_plan!A1:C20",
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
        assert kwargs["sheet_id"] == "gid_plan"
        assert kwargs["value_render_option"] == "FormattedValue"
        return _sheet_table(raw_values)

    monkeypatch.setattr(feishu_client, "read_sheet_values", _read_values)


async def _post_preview(
    auth_client: AsyncClient,
    *,
    validation_scope: str = "all",
    package_id_filter: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "feishu_source_id": "feishu-plan",
        "feishu_sheet_id": "gid_plan",
        "parse_strategy": "manual",
        "ai_parse_mode": "off",
        "validation_scope": validation_scope,
    }
    if package_id_filter is not None:
        payload["package_id_filter"] = package_id_filter

    response = await auth_client.post(_PREVIEW_URL, json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.anyio
async def test_workbench_package_items_preview_returns_all_packages(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_workbench_feishu_source(auth_client)
    _patch_sheet_values(
        monkeypatch,
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "16001", "3"],
            ["26042411", "16002", "5"],
            ["26042412", "16003", "7"],
        ],
    )

    data = await _post_preview(auth_client)

    assert data["success"] is True
    assert data["message"] == "解析成功。"
    assert data["package_ids"] == ["26042411", "26042412"]
    assert data["detail_row_count"] == 3
    assert data["field_mapping"] == {
        "package_id_column": "礼包id",
        "item_id_column": "道具ID",
        "count_column": "个数",
        "header_row_index": 1,
        "detail_start_row_index": 2,
        "detail_end_row_index": 4,
    }
    assert data["preview_rows"] == [
        {"row_index": 2, "package_id": "26042411", "item_id": "16001", "count": "3"},
        {"row_index": 3, "package_id": "26042411", "item_id": "16002", "count": "5"},
        {"row_index": 4, "package_id": "26042412", "item_id": "16003", "count": "7"},
    ]
    assert data["parse_strategy_used"] == "manual"
    assert data["ai_used"] is False
    assert data["raw_sheet_name"] == "礼包规划"


@pytest.mark.anyio
async def test_workbench_package_items_preview_filters_specified_package(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_workbench_feishu_source(auth_client)
    _patch_sheet_values(
        monkeypatch,
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "16001", "3"],
            ["26042412", "16003", "7"],
        ],
    )

    data = await _post_preview(
        auth_client,
        validation_scope="specified",
        package_id_filter="26042412",
    )

    assert data["success"] is True
    assert data["package_ids"] == ["26042412"]
    assert data["detail_row_count"] == 1
    assert data["preview_rows"] == [
        {"row_index": 3, "package_id": "26042412", "item_id": "16003", "count": "7"}
    ]


@pytest.mark.anyio
async def test_workbench_package_items_preview_hides_skipped_row_warnings(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_workbench_feishu_source(auth_client)
    _patch_sheet_values(
        monkeypatch,
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "16001", "3"],
            ["说明：以下为测试礼包", "", ""],
            ["26042411", "", "4"],
            ["26042411", "16001", "5"],
        ],
    )

    data = await _post_preview(auth_client)

    assert data["success"] is True
    assert data["detail_row_count"] == 2
    assert data["preview_rows"] == [
        {"row_index": 2, "package_id": "26042411", "item_id": "16001", "count": "3"},
        {"row_index": 5, "package_id": "26042411", "item_id": "16001", "count": "5"},
    ]
    assert not any(warning.startswith("跳过第") for warning in data["warnings"])
    assert data["warnings"] == [
        "识别到重复道具 ID：礼包 26042411 的道具 16001 在第 2 行和第 5 行重复。"
    ]


@pytest.mark.anyio
async def test_workbench_package_items_preview_returns_more_than_twenty_rows(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_workbench_feishu_source(auth_client)
    detail_rows = [
        ["26042411", str(16000 + index), str(index)]
        for index in range(1, 26)
    ]
    _patch_sheet_values(monkeypatch, [["礼包id", "道具ID", "个数"], *detail_rows])

    data = await _post_preview(auth_client)

    assert data["success"] is True
    assert data["detail_row_count"] == 25
    assert len(data["preview_rows"]) == data["detail_row_count"]
    assert data["preview_rows"][0] == {
        "row_index": 2,
        "package_id": "26042411",
        "item_id": "16001",
        "count": "1",
    }
    assert data["preview_rows"][-1] == {
        "row_index": 26,
        "package_id": "26042411",
        "item_id": "16025",
        "count": "25",
    }


@pytest.mark.anyio
async def test_workbench_package_items_preview_reports_field_detection_failure(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_workbench_feishu_source(auth_client)
    _patch_sheet_values(monkeypatch, [["说明"], ["没有表头"]])

    data = await _post_preview(auth_client)

    assert data["success"] is False
    assert data["message"] == "未识别到表头"
    assert data["errors"] == ["未识别到表头"]
    assert data["field_mapping"] is None


@pytest.mark.anyio
async def test_workbench_package_items_preview_reports_missing_package_id(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_workbench_feishu_source(auth_client)
    _patch_sheet_values(
        monkeypatch,
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "16001", "3"],
        ],
    )

    data = await _post_preview(
        auth_client,
        validation_scope="specified",
        package_id_filter="26049999",
    )

    assert data["success"] is False
    assert data["package_ids"] == []
    assert data["detail_row_count"] == 0
    assert data["preview_rows"] == []
    assert data["errors"] == ["未找到指定礼包 ID：26049999"]


@pytest.mark.anyio
async def test_workbench_package_items_preview_reports_empty_sheet(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_workbench_feishu_source(auth_client)
    _patch_sheet_values(monkeypatch, [])

    data = await _post_preview(auth_client)

    assert data["success"] is False
    assert data["errors"] == ["Sheet 为空"]
    assert data["detail_row_count"] == 0


@pytest.mark.anyio
async def test_workbench_package_items_preview_maps_feishu_read_failure(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.integrations import feishu_client
    from backend.app.integrations.feishu_client import (
        FEISHU_DOCUMENT_PERMISSION_DENIED,
        FeishuClientError,
    )

    await _seed_workbench_feishu_source(auth_client)

    async def _read_values(*_args, **_kwargs):
        raise FeishuClientError(FEISHU_DOCUMENT_PERMISSION_DENIED, "飞书未授权")

    monkeypatch.setattr(feishu_client, "read_sheet_values", _read_values)

    data = await _post_preview(auth_client)

    assert data["success"] is False
    assert data["message"] == "飞书未授权"
    assert data["errors"] == ["飞书未授权"]
