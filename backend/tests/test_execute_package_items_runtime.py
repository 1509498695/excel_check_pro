"""个人校验礼包规划运行时接入测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from backend.app.api.fixed_rules_schemas import (
    PackageDetailRange,
    PackageItemsPreviewDetailRow,
    PackageItemsPreviewResult,
    PackagePlanItemRow,
)
from backend.app.fixed_rules import package_items_runtime
from backend.app.integrations.feishu_client import FEISHU_API_ERROR, FeishuClientError


def _create_package_config_workbook(
    target_path: Path,
    sheets: dict[str, list[dict[str, Any]]],
) -> Path:
    with pd.ExcelWriter(target_path, engine="openpyxl") as writer:
        for sheet_name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name, index=False)
    return target_path


def _preview(rows: list[tuple[int, str, str, int]]) -> PackageItemsPreviewResult:
    plan_rows = [
        PackagePlanItemRow(
            row_index=row_index,
            package_id=package_id,
            item_id=item_id,
            count=count,
            raw_row=[package_id, item_id, count],
        )
        for row_index, package_id, item_id, count in rows
    ]
    package_ids: list[str] = []
    for row in plan_rows:
        if row.package_id not in package_ids:
            package_ids.append(row.package_id)

    return PackageItemsPreviewResult(
        parse_status="success",
        parse_mode="rule",
        ai_used=False,
        header_rows=[1],
        detail_ranges=[
            PackageDetailRange(
                header_row=1,
                start_row=rows[0][0] if rows else 2,
                end_row=rows[-1][0] if rows else 2,
            )
        ],
        field_mapping={
            "package_id": "礼包id",
            "item_id": "道具ID",
            "count": "个数",
        },
        package_ids=package_ids,
        package_count=len(package_ids),
        detail_row_count=len(plan_rows),
        rows=plan_rows,
        detail_rows=[
            PackageItemsPreviewDetailRow(
                row_index=row.row_index,
                package_id=row.package_id,
                item_id=row.item_id,
                count=str(row.count),
            )
            for row in plan_rows
        ],
    )


def _build_package_payload(
    workbook_path: Path,
    *,
    rule_id: str = "rule-package",
    right_tag: str = "[package-config]",
    right_sheet: str = "package_config",
    validation_scope: str = "all",
    package_id_filter: str | None = None,
    sheet_id: str = "gid_plan",
) -> dict[str, Any]:
    parse_config: dict[str, Any] = {
        "feishu_source_id": "feishu-plan",
        "feishu_sheet_id": sheet_id,
        "feishu_sheet_name": "礼包规划",
        "parse_strategy": "auto",
        "ai_parse_mode": "auto",
        "validation_scope": validation_scope,
        "package_id_filter": package_id_filter,
    }
    params: dict[str, Any] = {
        "reference_variable_tag": right_tag,
        "right_package_field": "INT_PackageId",
        "right_items_field": "STR_Items",
        "display_field": "礼包id",
        "package_parse_config": parse_config,
    }
    if package_id_filter is not None:
        params["package_id_filter"] = package_id_filter

    return {
        "sources": [
            {
                "id": "feishu-plan",
                "type": "feishu",
                "pathOrUrl": "https://demo.feishu.cn/sheets/shtcnabc123",
            },
            {
                "id": "config-src",
                "type": "local_excel",
                "path": str(workbook_path),
            },
        ],
        "variables": [
            {
                "tag": right_tag,
                "source_id": "config-src",
                "sheet": right_sheet,
                "variable_kind": "composite",
                "columns": ["INT_PackageId", "STR_Items"],
                "key_column": "INT_PackageId",
            }
        ],
        "rules": [
            {
                "rule_id": rule_id,
                "rule_type": "package_items_compare",
                "params": params,
            }
        ],
    }


def _patch_preview(
    monkeypatch: pytest.MonkeyPatch,
    preview: PackageItemsPreviewResult,
) -> None:
    async def _preview_package_items_from_feishu(*_args, **_kwargs):
        return preview

    monkeypatch.setattr(
        package_items_runtime,
        "preview_package_items_from_feishu",
        _preview_package_items_from_feishu,
    )


async def _execute(auth_client, payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = await auth_client.post("/api/v1/engine/execute", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]["abnormal_results"]


@pytest.mark.anyio
async def test_execute_engine_without_package_rule_does_not_prepare_runtime(
    auth_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "normal_rule.xlsx",
        {"items": [{"ID": 1, "Name": "A"}]},
    )

    async def _unexpected_preview(*_args, **_kwargs):
        raise AssertionError("普通规则不应触发礼包规划解析")

    monkeypatch.setattr(
        package_items_runtime,
        "preview_package_items_from_feishu",
        _unexpected_preview,
    )

    payload = {
        "sources": [
            {"id": "src", "type": "local_excel", "path": str(workbook_path)}
        ],
        "variables": [
            {
                "tag": "[name]",
                "source_id": "src",
                "sheet": "items",
                "column": "Name",
            }
        ],
        "rules": [
            {
                "rule_id": "normal-rule",
                "rule_type": "fixed_value_compare",
                "params": {
                    "target_tag": "[name]",
                    "operator": "eq",
                    "expected_value": "A",
                    "rule_name": "名称检查",
                    "location": "items -> Name",
                },
            }
        ],
    }

    assert await _execute(auth_client, payload) == []


@pytest.mark.anyio
async def test_execute_engine_package_runtime_passes_all_packages(
    auth_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "package_all_pass.xlsx",
        {
            "package_config": [
                {
                    "INT_PackageId": 26042411,
                    "STR_Items": "[{item,16002,4},{item,16001,3}]",
                }
            ]
        },
    )
    _patch_preview(
        monkeypatch,
        _preview(
            [
                (2, "26042411", "16001", 3),
                (3, "26042411", "16002", 4),
            ]
        ),
    )

    results = await _execute(auth_client, _build_package_payload(workbook_path))

    assert results == []


@pytest.mark.anyio
async def test_execute_engine_package_runtime_all_scope_uses_feishu_package_ids(
    auth_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "package_all_feishu_scope.xlsx",
        {
            "package_config": [
                {"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"},
                {"INT_PackageId": 26049999, "STR_Items": "[{item,99999,1}]"},
            ]
        },
    )
    _patch_preview(monkeypatch, _preview([(2, "26042411", "16001", 3)]))

    results = await _execute(auth_client, _build_package_payload(workbook_path))

    assert results == []


@pytest.mark.anyio
async def test_execute_engine_package_runtime_all_scope_skips_right_side_noise(
    auth_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "package_all_right_noise.xlsx",
        {
            "package_config": [
                {"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"},
                {
                    "INT_PackageId": 26049999,
                    "STR_Items": "[{asgift,2,1},{item,10113,5}}]",
                },
            ]
        },
    )
    _patch_preview(monkeypatch, _preview([(2, "26042411", "16001", 3)]))

    results = await _execute(auth_client, _build_package_payload(workbook_path))

    assert results == []


@pytest.mark.anyio
async def test_execute_engine_package_runtime_filters_specified_package(
    auth_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "package_specified.xlsx",
        {
            "package_config": [
                {"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"},
                {"INT_PackageId": 26042412, "STR_Items": "[{item,16002,999}]"},
            ]
        },
    )
    _patch_preview(
        monkeypatch,
        _preview(
            [
                (2, "26042411", "16001", 3),
                (3, "26042412", "16002", 5),
            ]
        ),
    )

    payload = _build_package_payload(
        workbook_path,
        validation_scope="specified",
        package_id_filter="26042411",
    )
    results = await _execute(auth_client, payload)

    assert results == []


@pytest.mark.anyio
async def test_execute_engine_package_runtime_supports_multiple_rules(
    auth_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "package_multi_rules.xlsx",
        {
            "config_a": [
                {"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"}
            ],
            "config_b": [
                {"INT_PackageId": 26042412, "STR_Items": "[{item,16002,5}]"}
            ],
        },
    )
    previews = {
        "gid_a": _preview([(2, "26042411", "16001", 3)]),
        "gid_b": _preview([(2, "26042412", "16002", 5)]),
    }
    seen_sheet_ids: list[str] = []

    async def _preview_package_items_from_feishu(*_args, **kwargs):
        sheet_id = kwargs["sheet_id"]
        seen_sheet_ids.append(sheet_id)
        return previews[sheet_id]

    monkeypatch.setattr(
        package_items_runtime,
        "preview_package_items_from_feishu",
        _preview_package_items_from_feishu,
    )

    payload = _build_package_payload(
        workbook_path,
        rule_id="rule-package-a",
        right_tag="[package-config-a]",
        right_sheet="config_a",
        sheet_id="gid_a",
    )
    second = _build_package_payload(
        workbook_path,
        rule_id="rule-package-b",
        right_tag="[package-config-b]",
        right_sheet="config_b",
        sheet_id="gid_b",
    )
    payload["variables"].extend(second["variables"])
    payload["rules"].extend(second["rules"])

    results = await _execute(auth_client, payload)

    assert results == []
    assert seen_sheet_ids == ["gid_a", "gid_b"]


@pytest.mark.anyio
async def test_execute_engine_package_runtime_reports_feishu_read_failure(
    auth_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "package_feishu_failed.xlsx",
        {
            "package_config": [
                {"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"}
            ]
        },
    )

    async def _preview_package_items_from_feishu(*_args, **_kwargs):
        raise FeishuClientError(FEISHU_API_ERROR, "读取飞书 Sheet 失败")

    monkeypatch.setattr(
        package_items_runtime,
        "preview_package_items_from_feishu",
        _preview_package_items_from_feishu,
    )

    results = await _execute(auth_client, _build_package_payload(workbook_path))

    assert len(results) == 1
    assert results[0]["error_type"] == "feishu_read_failed"
    assert "读取飞书 Sheet 失败" in results[0]["message"]


@pytest.mark.anyio
async def test_execute_engine_package_runtime_reports_parse_failure(
    auth_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "package_parse_failed.xlsx",
        {
            "package_config": [
                {"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"}
            ]
        },
    )
    _patch_preview(
        monkeypatch,
        PackageItemsPreviewResult(
            parse_status="failed",
            parse_mode="rule",
            errors=["未识别到表头"],
        ),
    )

    results = await _execute(auth_client, _build_package_payload(workbook_path))

    assert len(results) == 1
    assert results[0]["error_type"] == "package_parse_failed"
    assert "未识别到表头" in results[0]["message"]


@pytest.mark.anyio
async def test_execute_engine_package_runtime_reports_missing_right_package(
    auth_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "package_missing_right.xlsx",
        {
            "package_config": [
                {"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"}
            ]
        },
    )
    _patch_preview(
        monkeypatch,
        _preview(
            [
                (2, "26042411", "16001", 3),
                (3, "26042412", "16002", 5),
            ]
        ),
    )

    results = await _execute(auth_client, _build_package_payload(workbook_path))

    assert len(results) == 1
    assert results[0]["error_type"] == "right_missing_package"
    assert results[0]["package_id"] == "26042412"


@pytest.mark.anyio
async def test_execute_engine_package_runtime_reports_count_mismatch(
    auth_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "package_mismatch.xlsx",
        {
            "package_config": [
                {"INT_PackageId": 26042411, "STR_Items": "[{item,16001,4}]"}
            ]
        },
    )
    _patch_preview(monkeypatch, _preview([(2, "26042411", "16001", 3)]))

    results = await _execute(auth_client, _build_package_payload(workbook_path))

    assert len(results) == 1
    assert results[0]["error_type"] == "count_mismatch"
    assert results[0]["package_id"] == "26042411"
    assert results[0]["item_id"] == "16001"
    assert results[0]["left_value"] == 3
    assert results[0]["right_value"] == 4


@pytest.mark.anyio
async def test_execute_engine_package_runtime_pagination_preserves_structured_fields(
    auth_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "package_paged_structured_fields.xlsx",
        {
            "package_config": [
                {"INT_PackageId": 26042411, "STR_Items": "[]"}
            ]
        },
    )
    _patch_preview(
        monkeypatch,
        _preview(
            [
                (2, "26042411", "16001", 3),
                (3, "26042411", "16002", 5),
            ]
        ),
    )
    payload = _build_package_payload(workbook_path)
    payload["page"] = 1
    payload["size"] = 1

    execute_response = await auth_client.post("/api/v1/engine/execute", json=payload)

    assert execute_response.status_code == 200, execute_response.text
    execute_payload = execute_response.json()
    result_id = execute_payload["meta"]["result_id"]
    first_item = execute_payload["data"]["list"][0]
    assert first_item["error_type"] == "right_missing_item"
    assert first_item["package_id"] == "26042411"
    assert first_item["item_id"] == "16001"
    assert first_item["left_value"] == 3
    assert first_item["right_value"] is None

    page_two_response = await auth_client.get(
        f"/api/v1/engine/results/{result_id}",
        params={"page": 2, "size": 1},
    )

    assert page_two_response.status_code == 200, page_two_response.text
    second_item = page_two_response.json()["data"]["list"][0]
    assert second_item["error_type"] == "right_missing_item"
    assert second_item["package_id"] == "26042411"
    assert second_item["item_id"] == "16002"
    assert second_item["left_value"] == 5
    assert second_item["right_value"] is None
