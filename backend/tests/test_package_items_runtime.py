"""礼包规划表运行时解析执行测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from backend.app.api.fixed_rules_schemas import (
    FixedRulesConfig,
    PackageDetailRange,
    PackageItemsPreviewDetailRow,
    PackageItemsPreviewResult,
    PackagePlanItemRow,
)
from backend.app.fixed_rules import package_items_runtime
from backend.app.fixed_rules.config_normalizer import validate_and_normalize_fixed_rules_config
from backend.app.fixed_rules.package_items_runtime import (
    RUNTIME_PACKAGE_TAG_PREFIX,
    prepare_package_items_runtime_config,
    prepare_package_items_runtime_task_tree,
)
from backend.app.api.schemas import TaskTree
from backend.app.database import async_session_factory
from backend.app.integrations.feishu_client import FeishuSheetTable
from backend.app.services.package_items_ai_parse_cache import clear_package_items_ai_parse_cache
from backend.app.services.package_items_ai_parser import PackageAiParseSuggestion
from backend.tests.conftest import seed_fixed_rules_config


def _create_package_config_workbook(
    target_path: Path,
    rows: list[dict[str, Any]],
) -> Path:
    with pd.ExcelWriter(target_path, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="package_config", index=False)
    return target_path


def _build_runtime_config(
    workbook_path: Path,
    *,
    package_id_filter: str | None = None,
) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "rule_id": "rule-package-runtime",
        "group_id": "ungrouped",
        "rule_name": "飞书礼包规划校验",
        "rule_type": "package_items_compare",
        "reference_variable_tag": "[package-config]",
        "left_package_field": "packageId",
        "left_item_field": "itemId",
        "left_count_field": "num",
        "right_package_field": "INT_PackageId",
        "right_items_field": "STR_Items",
        "package_parse_config": {
            "feishu_source_id": "feishu-plan",
            "feishu_sheet_id": "gid_plan",
            "feishu_sheet_name": "礼包规划",
            "parse_strategy": "auto",
            "ai_parse_mode": "auto",
        },
    }
    if package_id_filter is not None:
        rule["package_id_filter"] = package_id_filter

    return {
        "version": 6,
        "configured": True,
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
                "tag": "[package-config]",
                "source_id": "config-src",
                "sheet": "package_config",
                "variable_kind": "composite",
                "columns": ["INT_PackageId", "STR_Items"],
                "key_column": "INT_PackageId",
            }
        ],
        "groups": [{"group_id": "ungrouped", "group_name": "未分组", "builtin": True}],
        "rules": [rule],
        "local_path_replacement_presets": [],
        "svn_path_replacement_presets": [],
    }


def _success_preview(*, include_second_package: bool = True) -> PackageItemsPreviewResult:
    detail_rows = [
        PackageItemsPreviewDetailRow(
            row_index=2,
            package_id="26042411",
            item_id="16001",
            count="3",
        )
    ]
    rows = [
        PackagePlanItemRow(
            row_index=2,
            package_id="26042411",
            item_id="16001",
            count=3,
            raw_row=["26042411", "16001", "3"],
        )
    ]
    package_ids = ["26042411"]
    if include_second_package:
        detail_rows.append(
            PackageItemsPreviewDetailRow(
                row_index=3,
                package_id="26042412",
                item_id="16002",
                count="5",
            )
        )
        rows.append(
            PackagePlanItemRow(
                row_index=3,
                package_id="26042412",
                item_id="16002",
                count=5,
                raw_row=["26042412", "16002", "5"],
            )
        )
        package_ids.append("26042412")

    return PackageItemsPreviewResult(
        parse_status="success",
        parse_mode="rule",
        ai_used=False,
        header_rows=[1],
        detail_ranges=[
            PackageDetailRange(
                header_row=1,
                start_row=2,
                end_row=3 if include_second_package else 2,
            )
        ],
        package_count=len(package_ids),
        detail_row_count=len(detail_rows),
        package_ids=package_ids,
        field_mapping={
            "package_id": "packageId",
            "item_id": "itemId",
            "count": "num",
        },
        rows=rows,
        detail_rows=detail_rows,
    )


def _patch_package_preview(
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


@pytest.mark.anyio
async def test_package_parse_config_generates_runtime_variable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_project_id: int,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "runtime_package_config.xlsx",
        [{"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"}],
    )
    _patch_package_preview(monkeypatch, _success_preview(include_second_package=False))

    config = validate_and_normalize_fixed_rules_config(
        FixedRulesConfig.model_validate(_build_runtime_config(workbook_path))
    )
    async with async_session_factory() as db:
        preparation = await prepare_package_items_runtime_config(
            config,
            db=db,
            project_id=test_project_id,
        )

    temp_tag = f"{RUNTIME_PACKAGE_TAG_PREFIX}rule-package-runtime"
    assert temp_tag in preparation.preloaded_variable_frames
    assert any(variable.tag == temp_tag for variable in preparation.config.variables)
    runtime_rule = preparation.config.rules[0]
    assert runtime_rule.target_variable_tag == temp_tag
    assert runtime_rule.package_parse_config is None
    assert runtime_rule.left_package_field == "礼包id"
    assert runtime_rule.left_item_field == "道具ID"
    assert runtime_rule.left_count_field == "个数"
    assert list(preparation.preloaded_variable_frames[temp_tag].columns) == [
        "__key__",
        "礼包id",
        "道具ID",
        "个数",
        "_row_index",
    ]
    assert preparation.preloaded_variable_frames[temp_tag].to_dict("records") == [
        {
            "__key__": "26042411_0",
            "礼包id": "26042411",
            "道具ID": "16001",
            "个数": 3,
            "_row_index": 2,
        }
    ]


@pytest.mark.anyio
async def test_task_tree_runtime_variables_are_stable_and_isolated(
    monkeypatch: pytest.MonkeyPatch,
    test_project_id: int,
) -> None:
    previews = {
        "gid_plan_a": _success_preview(include_second_package=False),
        "gid_plan_b": PackageItemsPreviewResult(
            parse_status="success",
            parse_mode="rule",
            ai_used=False,
            header_rows=[1],
            detail_ranges=[PackageDetailRange(header_row=1, start_row=2, end_row=2)],
            package_ids=["26049999"],
            package_count=1,
            detail_row_count=1,
            field_mapping={"package_id": "packageId", "item_id": "itemId", "count": "num"},
            rows=[
                PackagePlanItemRow(
                    row_index=2,
                    package_id="26049999",
                    item_id="18001",
                    count=9,
                    raw_row=["26049999", "18001", "9"],
                )
            ],
        ),
    }

    async def _preview_package_items_from_feishu(*_args, **kwargs):
        return previews[kwargs["sheet_id"]]

    monkeypatch.setattr(
        package_items_runtime,
        "preview_package_items_from_feishu",
        _preview_package_items_from_feishu,
    )
    task_tree = TaskTree.model_validate(
        {
            "sources": [
                {
                    "id": "feishu-plan",
                    "type": "feishu",
                    "pathOrUrl": "https://demo.feishu.cn/sheets/shtcnabc123",
                },
                {
                    "id": "config-src",
                    "type": "local_excel",
                    "path": "D:/tmp/package.xlsx",
                },
            ],
            "variables": [
                {
                    "tag": "[package-config-a]",
                    "source_id": "config-src",
                    "sheet": "package_config_a",
                    "variable_kind": "composite",
                    "columns": ["INT_PackageId", "STR_Items"],
                    "key_column": "INT_PackageId",
                },
                {
                    "tag": "[package-config-b]",
                    "source_id": "config-src",
                    "sheet": "package_config_b",
                    "variable_kind": "composite",
                    "columns": ["INT_PackageId", "STR_Items"],
                    "key_column": "INT_PackageId",
                },
            ],
            "rules": [
                {
                    "rule_id": "rule-package-a",
                    "rule_type": "package_items_compare",
                    "params": {
                        "reference_variable_tag": "[package-config-a]",
                        "right_package_field": "INT_PackageId",
                        "right_items_field": "STR_Items",
                        "package_parse_config": {
                            "feishu_source_id": "feishu-plan",
                            "feishu_sheet_id": "gid_plan_a",
                            "parse_strategy": "auto",
                            "ai_parse_mode": "auto",
                            "validation_scope": "all",
                        },
                    },
                },
                {
                    "rule_id": "rule-package-b",
                    "rule_type": "package_items_compare",
                    "params": {
                        "reference_variable_tag": "[package-config-b]",
                        "right_package_field": "INT_PackageId",
                        "right_items_field": "STR_Items",
                        "package_parse_config": {
                            "feishu_source_id": "feishu-plan",
                            "feishu_sheet_id": "gid_plan_b",
                            "parse_strategy": "auto",
                            "ai_parse_mode": "auto",
                            "validation_scope": "all",
                        },
                    },
                },
            ],
        }
    )

    async with async_session_factory() as db:
        preparation = await prepare_package_items_runtime_task_tree(
            task_tree,
            db=db,
            project_id=test_project_id,
        )

    assert set(preparation.preloaded_variable_frames) == {
        "__runtime_package_plan__:rule-package-a",
        "__runtime_package_plan__:rule-package-b",
    }
    assert preparation.task_tree.rules[0].params["left_tag"] == "__runtime_package_plan__:rule-package-a"
    assert preparation.task_tree.rules[1].params["left_tag"] == "__runtime_package_plan__:rule-package-b"
    assert preparation.preloaded_variable_frames[
        "__runtime_package_plan__:rule-package-a"
    ].iloc[0]["礼包id"] == "26042411"
    assert preparation.preloaded_variable_frames[
        "__runtime_package_plan__:rule-package-b"
    ].iloc[0]["礼包id"] == "26049999"


@pytest.mark.anyio
async def test_fixed_rules_config_round_trips_package_parse_config(
    auth_client,
    tmp_path: Path,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "runtime_roundtrip.xlsx",
        [{"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"}],
    )
    payload = _build_runtime_config(workbook_path, package_id_filter="26042411")

    save_response = await auth_client.put("/api/v1/fixed-rules/config", json=payload)
    get_response = await auth_client.get("/api/v1/fixed-rules/config")

    assert save_response.status_code == 200, save_response.text
    assert get_response.status_code == 200, get_response.text
    saved_rule = get_response.json()["data"]["rules"][0]
    assert saved_rule["package_parse_config"] == {
        "feishu_source_id": "feishu-plan",
        "feishu_sheet_id": "gid_plan",
        "feishu_sheet_name": "礼包规划",
        "parse_strategy": "auto",
        "ai_parse_mode": "auto",
    }
    assert saved_rule["package_id_filter"] == "26042411"


@pytest.mark.anyio
async def test_execute_runtime_package_rule_filters_selected_package(
    auth_client,
    test_project_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "runtime_filter.xlsx",
        [{"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"}],
    )
    await seed_fixed_rules_config(
        _build_runtime_config(workbook_path, package_id_filter="26042411"),
        test_project_id,
    )
    _patch_package_preview(monkeypatch, _success_preview())

    response = await auth_client.post("/api/v1/fixed-rules/execute", json={})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["data"]["abnormal_results"] == []
    assert payload["meta"]["package_items_parse"] == [
        {
            "rule_id": "rule-package-runtime",
            "parse_mode": "rule",
            "ai_used": False,
            "cache_hit": False,
            "confidence": 0.0,
            "header_rows": [1],
            "package_ids": ["26042411", "26042412"],
            "detail_row_count": 2,
            "warnings": [],
            "errors": [],
        }
    ]


@pytest.mark.anyio
async def test_execute_runtime_package_rule_checks_all_parsed_packages(
    auth_client,
    test_project_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "runtime_all.xlsx",
        [{"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"}],
    )
    await seed_fixed_rules_config(_build_runtime_config(workbook_path), test_project_id)
    _patch_package_preview(monkeypatch, _success_preview())

    response = await auth_client.post("/api/v1/fixed-rules/execute", json={})

    assert response.status_code == 200, response.text
    abnormal_results = response.json()["data"]["abnormal_results"]
    assert len(abnormal_results) == 1
    assert "INT_PackageId 缺失：礼包 26042412" in abnormal_results[0]["message"]
    assert abnormal_results[0]["row_index"] == 3


@pytest.mark.anyio
async def test_execute_runtime_package_rule_skips_right_packages_outside_feishu_sheet(
    auth_client,
    test_project_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "runtime_all_feishu_scope.xlsx",
        [
            {"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"},
            {
                "INT_PackageId": 26049999,
                "STR_Items": "[{asgift,2,1},{item,10113,5}}]",
            },
        ],
    )
    await seed_fixed_rules_config(_build_runtime_config(workbook_path), test_project_id)
    _patch_package_preview(monkeypatch, _success_preview(include_second_package=False))

    response = await auth_client.post("/api/v1/fixed-rules/execute", json={})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["abnormal_results"] == []


@pytest.mark.anyio
async def test_execute_runtime_package_rule_uses_ai_parse_result(
    auth_client,
    test_project_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.integrations import feishu_client
    from backend.app.services import package_items_parser

    clear_package_items_ai_parse_cache()
    workbook_path = _create_package_config_workbook(
        tmp_path / "runtime_ai.xlsx",
        [{"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"}],
    )
    await seed_fixed_rules_config(_build_runtime_config(workbook_path), test_project_id)
    ai_call_count = 0

    async def _read_values(*_args, **kwargs):
        assert kwargs["sheet_id"] == "gid_plan"
        return FeishuSheetTable(
            spreadsheet_token="shtcnabc123",
            sheet_id="gid_plan",
            sheet_title="礼包规划",
            range="gid_plan!A1:C2",
            columns=[],
            rows=[],
            raw_values=[
                ["礼包", "道具", "数量"],
                ["26042411", "16001", "3"],
            ],
        )

    async def _parse_with_ai(*_args, **_kwargs):
        nonlocal ai_call_count
        ai_call_count += 1
        return PackageAiParseSuggestion.model_validate(
            {
                "header_rows": [1],
                "detail_ranges": [{"header_row": 1, "start_row": 2, "end_row": 2}],
                "field_mapping": {
                    "package_id": "礼包",
                    "item_id": "道具",
                    "count": "数量",
                },
                "confidence": 0.9,
                "warnings": [],
                "reasoning_summary": "识别到非标准表头。",
            }
        )

    monkeypatch.setattr(feishu_client, "read_sheet_values", _read_values)
    monkeypatch.setattr(package_items_parser, "parse_package_sheet_with_ai", _parse_with_ai)

    preview_response = await auth_client.post(
        "/api/v1/fixed-rules/package-items/preview",
        json={
            "feishu_source_id": "feishu-plan",
            "sheet_id": "gid_plan",
            "parse_strategy": "auto",
            "ai_parse_mode": "auto",
        },
    )
    assert preview_response.status_code == 200, preview_response.text
    assert preview_response.json()["data"]["cache_hit"] is False

    response = await auth_client.post("/api/v1/fixed-rules/execute", json={})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert ai_call_count == 1
    assert payload["data"]["abnormal_results"] == []
    assert payload["meta"]["package_items_parse"] == [
        {
            "rule_id": "rule-package-runtime",
            "parse_mode": "ai",
            "ai_used": True,
            "cache_hit": True,
            "confidence": 0.9,
            "header_rows": [1],
            "package_ids": ["26042411"],
            "detail_row_count": 1,
            "warnings": [],
            "errors": [],
        }
    ]
    clear_package_items_ai_parse_cache()


@pytest.mark.anyio
async def test_execute_runtime_package_rule_parse_failure_is_not_silent(
    auth_client,
    test_project_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "runtime_failed.xlsx",
        [{"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"}],
    )
    await seed_fixed_rules_config(_build_runtime_config(workbook_path), test_project_id)
    _patch_package_preview(
        monkeypatch,
        PackageItemsPreviewResult(
            parse_status="failed",
            parse_mode="rule",
            warnings=["未识别到包含礼包 ID、道具 ID、个数的表头行。"],
        ),
    )

    response = await auth_client.post("/api/v1/fixed-rules/execute", json={})

    assert response.status_code == 400
    assert "飞书解析失败" in response.json()["detail"]


@pytest.mark.anyio
async def test_execute_runtime_package_rule_empty_details_fail(
    auth_client,
    test_project_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workbook_path = _create_package_config_workbook(
        tmp_path / "runtime_empty.xlsx",
        [{"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"}],
    )
    await seed_fixed_rules_config(_build_runtime_config(workbook_path), test_project_id)
    _patch_package_preview(
        monkeypatch,
        PackageItemsPreviewResult(
            parse_status="success",
            parse_mode="rule",
            header_rows=[1],
            field_mapping={
                "package_id": "packageId",
                "item_id": "itemId",
                "count": "num",
            },
        ),
    )

    response = await auth_client.post("/api/v1/fixed-rules/execute", json={})

    assert response.status_code == 400
    assert "未识别到礼包明细" in response.json()["detail"]
