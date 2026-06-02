"""礼包明细与 STR_Items 比对规则测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.ai.materializers.registry import materialize_rule_definition
from backend.app.ai.rule_type_inference import infer_hint_rule_type
from backend.app.ai.schemas import RuleIntent, VariableIntent
from backend.app.ai.workflow_hints import AiRuleWorkflowHints
from backend.app.api.fixed_rules_schemas import FixedRuleDefinition, FixedRulesConfig
from backend.app.api.schemas import DataSource, VariableTag
from backend.app.fixed_rules.config_normalizer import validate_and_normalize_fixed_rules_config
from backend.app.fixed_rules.task_tree_builder import build_fixed_rules_task_tree
from backend.app.rules.handlers.fixed.package_items import parse_str_items
from backend.run import app


def _create_package_compare_workbook(
    target_path: Path,
    *,
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
) -> Path:
    with pd.ExcelWriter(target_path, engine="openpyxl") as writer:
        pd.DataFrame(left_rows).to_excel(writer, sheet_name="package_detail", index=False)
        pd.DataFrame(right_rows).to_excel(writer, sheet_name="package_config", index=False)
    return target_path


def _build_payload(workbook_path: Path, *, package_id_filter: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {
        "left_tag": "[package-detail]",
        "right_tag": "[package-config]",
        "rule_name": "礼包明细对比STR_Items",
        "left_package_field": "礼包id",
        "right_package_field": "INT_PackageId",
        "left_item_field": "道具ID",
        "left_count_field": "个数",
        "right_items_field": "STR_Items",
    }
    if package_id_filter is not None:
        params["package_id_filter"] = package_id_filter

    return {
        "sources": [
            {
                "id": "src_package",
                "type": "local_excel",
                "path": str(workbook_path),
            }
        ],
        "variables": [
            {
                "tag": "[package-detail]",
                "source_id": "src_package",
                "sheet": "package_detail",
                "variable_kind": "composite",
                "columns": ["礼包id", "道具ID", "个数"],
                "key_column": "礼包id",
                "append_index_to_key": True,
            },
            {
                "tag": "[package-config]",
                "source_id": "src_package",
                "sheet": "package_config",
                "variable_kind": "composite",
                "columns": ["INT_PackageId", "STR_Items"],
                "key_column": "INT_PackageId",
            },
        ],
        "rules": [
            {
                "rule_type": "package_items_compare",
                "params": params,
            }
        ],
    }


async def _execute_package_compare(payload: dict[str, Any]) -> list[dict[str, Any]]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/api/v1/engine/execute", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200
    return body["data"]["abnormal_results"]


def _find_error(
    results: list[dict[str, Any]],
    error_type: str,
    *,
    package_id: str | None = None,
    item_id: str | None = None,
) -> dict[str, Any]:
    for result in results:
        if result.get("error_type") != error_type:
            continue
        if package_id is not None and result.get("package_id") != package_id:
            continue
        if item_id is not None and result.get("item_id") != item_id:
            continue
        return result
    raise AssertionError(f"未找到结构化错误：{error_type} package={package_id} item={item_id}")


def test_parse_str_items_extracts_item_triples_and_ignores_non_item() -> None:
    items, errors = parse_str_items(
        "[{asgift,2,1},{item,16001,3},{item,62,10},{item,58,50}]"
    )

    assert errors == []
    assert {item_id: item.count for item_id, item in items.items()} == {
        "16001": 3,
        "62": 10,
        "58": 50,
    }


def test_parse_str_items_accepts_empty_array_as_no_items() -> None:
    for raw_value in ("[]", "[ ]"):
        items, errors = parse_str_items(raw_value)

        assert items == {}
        assert errors == []


def test_parse_str_items_reports_malformed_and_duplicate_item() -> None:
    items, errors = parse_str_items("[{item,16001,3},{item,16001,4},{item,62}]")

    assert {item_id: item.count for item_id, item in items.items()} == {"16001": 3}
    assert "STR_Items 道具重复：16001" in errors
    assert "STR_Items 片段格式错误：{item,62}" in errors


def test_parse_str_items_reports_invalid_item_id_and_count() -> None:
    items, errors = parse_str_items("[{item,,3},{item,16002,abc},{item,16003,7}]")

    assert {item_id: item.count for item_id, item in items.items()} == {"16003": 7}
    assert any("道具 ID 为空" in error for error in errors)
    assert any("道具数量 必须是整数" in error for error in errors)


def test_parse_str_items_keeps_other_non_empty_text_as_format_error() -> None:
    items, errors = parse_str_items("[invalid]")

    assert items == {}
    assert errors == ["STR_Items 格式错误：[invalid]"]


@pytest.mark.anyio
async def test_execute_engine_package_items_compare_passes_sample_package(
    tmp_path: Path,
) -> None:
    workbook_path = _create_package_compare_workbook(
        tmp_path / "package_compare_pass.xlsx",
        left_rows=[
            {"礼包id": 26042411, "道具ID": 16001, "个数": 3},
            {"礼包id": 26042411, "道具ID": 62, "个数": 10},
            {"礼包id": 26042411, "道具ID": 58, "个数": 50},
            {"礼包id": 26042411, "道具ID": 3, "个数": 11},
            {"礼包id": 26042411, "道具ID": 9, "个数": 11},
            {"礼包id": 26042411, "道具ID": 15, "个数": 11},
            {"礼包id": 26042411, "道具ID": 21, "个数": 35},
            {"礼包id": 26042411, "道具ID": 304, "个数": 5},
            {"礼包id": 26042411, "道具ID": 300, "个数": 5},
        ],
        right_rows=[
            {
                "INT_PackageId": 26042411,
                "STR_Items": (
                    "[{asgift,2,1},{item,16001,3},{item,62,10},{item,58,50},"
                    "{item,3,11},{item,9,11},{item,15,11},{item,21,35},"
                    "{item,304,5},{item,300,5}]"
                ),
            }
        ],
    )

    abnormal_results = await _execute_package_compare(
        _build_payload(workbook_path, package_id_filter="26042411")
    )

    assert abnormal_results == []


@pytest.mark.anyio
async def test_execute_engine_package_items_compare_passes_with_different_order(
    tmp_path: Path,
) -> None:
    workbook_path = _create_package_compare_workbook(
        tmp_path / "package_compare_order.xlsx",
        left_rows=[
            {"礼包id": 26042411, "道具ID": 39, "个数": 8},
            {"礼包id": 26042411, "道具ID": 48, "个数": 25},
            {"礼包id": 26042411, "道具ID": 47, "个数": 145},
        ],
        right_rows=[
            {
                "INT_PackageId": 26042411,
                "STR_Items": "[{item,47,145},{item,39,8},{item,48,25}]",
            }
        ],
    )

    abnormal_results = await _execute_package_compare(_build_payload(workbook_path))

    assert abnormal_results == []


@pytest.mark.anyio
async def test_execute_engine_package_items_compare_reports_mismatch_missing_and_extra(
    tmp_path: Path,
) -> None:
    workbook_path = _create_package_compare_workbook(
        tmp_path / "package_compare_diff.xlsx",
        left_rows=[
            {"礼包id": 26042411, "道具ID": 16001, "个数": 3},
            {"礼包id": 26042411, "道具ID": 62, "个数": 10},
        ],
        right_rows=[
            {
                "INT_PackageId": 26042411,
                "STR_Items": "[{asgift,2,1},{item,16001,4},{item,99,1}]",
            }
        ],
    )

    abnormal_results = await _execute_package_compare(_build_payload(workbook_path))
    messages = [item["message"] for item in abnormal_results]

    assert any("数量不一致" in message and "16001" in message for message in messages)
    assert any("STR_Items 缺少道具" in message and "62" in message for message in messages)
    assert any("STR_Items 多出道具" in message and "99" in message for message in messages)
    mismatch = _find_error(
        abnormal_results,
        "count_mismatch",
        package_id="26042411",
        item_id="16001",
    )
    assert mismatch["left_value"] == 3
    assert mismatch["right_value"] == 4
    missing = _find_error(
        abnormal_results,
        "right_missing_item",
        package_id="26042411",
        item_id="62",
    )
    assert missing["left_value"] == 10
    assert missing["right_value"] is None
    extra = _find_error(
        abnormal_results,
        "left_missing_item",
        package_id="26042411",
        item_id="99",
    )
    assert extra["left_value"] is None
    assert extra["right_value"] == 1


@pytest.mark.anyio
async def test_execute_engine_package_items_compare_ignores_non_item_types(
    tmp_path: Path,
) -> None:
    workbook_path = _create_package_compare_workbook(
        tmp_path / "package_compare_non_item.xlsx",
        left_rows=[{"礼包id": 26042411, "道具ID": 16001, "个数": 3}],
        right_rows=[
            {
                "INT_PackageId": 26042411,
                "STR_Items": "[{asgift,2,1},{currency,9,99},{item,16001,3}]",
            }
        ],
    )

    abnormal_results = await _execute_package_compare(_build_payload(workbook_path))

    assert abnormal_results == []


@pytest.mark.anyio
async def test_execute_engine_package_items_compare_empty_array_reports_missing_items(
    tmp_path: Path,
) -> None:
    workbook_path = _create_package_compare_workbook(
        tmp_path / "package_compare_empty_array_missing_items.xlsx",
        left_rows=[
            {"礼包id": 26042411, "道具ID": 16001, "个数": 3},
            {"礼包id": 26042411, "道具ID": 16002, "个数": 5},
        ],
        right_rows=[
            {"INT_PackageId": 26042411, "STR_Items": "[]"},
        ],
    )

    abnormal_results = await _execute_package_compare(_build_payload(workbook_path))

    assert not any(item.get("error_type") == "str_items_format_error" for item in abnormal_results)
    assert _find_error(
        abnormal_results,
        "right_missing_item",
        package_id="26042411",
        item_id="16001",
    )["left_value"] == 3
    assert _find_error(
        abnormal_results,
        "right_missing_item",
        package_id="26042411",
        item_id="16002",
    )["left_value"] == 5


@pytest.mark.anyio
async def test_execute_engine_package_items_compare_empty_array_on_unmatched_right_package(
    tmp_path: Path,
) -> None:
    workbook_path = _create_package_compare_workbook(
        tmp_path / "package_compare_empty_array_missing_left_package.xlsx",
        left_rows=[{"礼包id": 26042411, "道具ID": 16001, "个数": 3}],
        right_rows=[
            {"INT_PackageId": 26042412, "STR_Items": "[]"},
        ],
    )

    abnormal_results = await _execute_package_compare(_build_payload(workbook_path))

    assert not any(item.get("error_type") == "str_items_format_error" for item in abnormal_results)
    assert _find_error(
        abnormal_results,
        "left_missing_package",
        package_id="26042412",
    )


@pytest.mark.anyio
async def test_execute_engine_package_items_compare_respects_specified_package_filter(
    tmp_path: Path,
) -> None:
    workbook_path = _create_package_compare_workbook(
        tmp_path / "package_compare_filter_only.xlsx",
        left_rows=[
            {"礼包id": 26042411, "道具ID": 16001, "个数": 3},
            {"礼包id": 26042412, "道具ID": 16002, "个数": 5},
        ],
        right_rows=[
            {"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"},
            {"INT_PackageId": 26042412, "STR_Items": "[{item,16002,999}]"},
        ],
    )

    abnormal_results = await _execute_package_compare(
        _build_payload(workbook_path, package_id_filter="26042411")
    )

    assert abnormal_results == []


@pytest.mark.anyio
async def test_execute_engine_package_items_compare_checks_all_packages_by_default(
    tmp_path: Path,
) -> None:
    workbook_path = _create_package_compare_workbook(
        tmp_path / "package_compare_all_packages.xlsx",
        left_rows=[
            {"礼包id": 26042411, "道具ID": 16001, "个数": 3},
            {"礼包id": 26042412, "道具ID": 16002, "个数": 5},
        ],
        right_rows=[
            {"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"},
            {"INT_PackageId": 26042412, "STR_Items": "[{item,16002,999}]"},
        ],
    )

    abnormal_results = await _execute_package_compare(_build_payload(workbook_path))

    assert any(
        "数量不一致" in item["message"] and "16002" in item["message"]
        for item in abnormal_results
    )


@pytest.mark.anyio
async def test_execute_engine_package_items_compare_reports_missing_package(
    tmp_path: Path,
) -> None:
    workbook_path = _create_package_compare_workbook(
        tmp_path / "package_compare_missing_package.xlsx",
        left_rows=[{"礼包id": 26042411, "道具ID": 16001, "个数": 3}],
        right_rows=[
            {
                "INT_PackageId": 26042412,
                "STR_Items": "[{item,16001,3}]",
            }
        ],
    )

    abnormal_results = await _execute_package_compare(_build_payload(workbook_path))

    assert len(abnormal_results) == 2
    right_missing = _find_error(
        abnormal_results,
        "right_missing_package",
        package_id="26042411",
    )
    assert "INT_PackageId 缺失" in right_missing["message"]
    assert right_missing["row_index"] == 2
    assert right_missing["left_value"] == "26042411"
    assert right_missing["right_value"] is None
    left_missing = _find_error(
        abnormal_results,
        "left_missing_package",
        package_id="26042412",
    )
    assert "飞书 Sheet 中不存在" in left_missing["message"]
    assert left_missing["left_value"] is None
    assert left_missing["right_value"] == "26042412"


@pytest.mark.anyio
async def test_execute_engine_package_items_compare_reports_str_items_format_errors(
    tmp_path: Path,
) -> None:
    workbook_path = _create_package_compare_workbook(
        tmp_path / "package_compare_malformed.xlsx",
        left_rows=[{"礼包id": 26042411, "道具ID": 16001, "个数": 3}],
        right_rows=[
            {
                "INT_PackageId": 26042411,
                "STR_Items": "[{item,16001,3},{item,16001,4},{item,62}]",
            }
        ],
    )

    abnormal_results = await _execute_package_compare(_build_payload(workbook_path))
    messages = [item["message"] for item in abnormal_results]

    assert any("STR_Items 道具重复：16001" in message for message in messages)
    assert any("STR_Items 片段格式错误：{item,62}" in message for message in messages)
    assert _find_error(
        abnormal_results,
        "right_duplicate_item",
        package_id="26042411",
        item_id="16001",
    )
    assert _find_error(
        abnormal_results,
        "str_items_format_error",
        package_id="26042411",
    )


@pytest.mark.anyio
async def test_execute_engine_package_items_compare_reports_left_duplicate_item(
    tmp_path: Path,
) -> None:
    workbook_path = _create_package_compare_workbook(
        tmp_path / "package_compare_left_duplicate.xlsx",
        left_rows=[
            {"礼包id": 26042411, "道具ID": 16001, "个数": 3},
            {"礼包id": 26042411, "道具ID": 16001, "个数": 4},
        ],
        right_rows=[
            {"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"},
        ],
    )

    abnormal_results = await _execute_package_compare(_build_payload(workbook_path))

    duplicate = _find_error(
        abnormal_results,
        "left_duplicate_item",
        package_id="26042411",
        item_id="16001",
    )
    assert "左侧道具重复配置" in duplicate["message"]
    assert duplicate["left_value"] == 4


@pytest.mark.anyio
async def test_execute_engine_package_items_compare_reports_invalid_ids_and_counts(
    tmp_path: Path,
) -> None:
    workbook_path = _create_package_compare_workbook(
        tmp_path / "package_compare_invalid_values.xlsx",
        left_rows=[
            {"礼包id": 26042411, "道具ID": "", "个数": 3},
            {"礼包id": 26042411, "道具ID": 16001, "个数": "三个"},
        ],
        right_rows=[
            {
                "INT_PackageId": 26042411,
                "STR_Items": "[{item,,3},{item,16002,abc}]",
            },
        ],
    )

    abnormal_results = await _execute_package_compare(_build_payload(workbook_path))

    assert _find_error(abnormal_results, "left_invalid_item_id", package_id="26042411")
    assert _find_error(
        abnormal_results,
        "left_invalid_count",
        package_id="26042411",
        item_id="16001",
    )
    assert _find_error(abnormal_results, "right_invalid_item_id", package_id="26042411")
    assert _find_error(
        abnormal_results,
        "right_invalid_count",
        package_id="26042411",
        item_id="16002",
    )


def test_fixed_rules_config_normalizes_package_items_compare_params(tmp_path: Path) -> None:
    workbook_path = _create_package_compare_workbook(
        tmp_path / "package_compare_fixed_config.xlsx",
        left_rows=[{"礼包id": 26042411, "道具ID": 16001, "个数": 3}],
        right_rows=[{"INT_PackageId": 26042411, "STR_Items": "[{item,16001,3}]"}],
    )
    config = FixedRulesConfig(
        configured=True,
        sources=[
            DataSource(id="src_package", type="local_excel", path=str(workbook_path)),
        ],
        variables=[
            VariableTag(
                tag="[package-detail]",
                source_id="src_package",
                sheet="package_detail",
                variable_kind="composite",
                columns=["礼包id", "道具ID", "个数"],
                key_column="礼包id",
                append_index_to_key=True,
            ),
            VariableTag(
                tag="[package-config]",
                source_id="src_package",
                sheet="package_config",
                variable_kind="composite",
                columns=["INT_PackageId", "STR_Items"],
                key_column="INT_PackageId",
            ),
        ],
        rules=[
            FixedRuleDefinition(
                rule_id="rule_package_compare",
                group_id="ungrouped",
                rule_name="礼包明细对比STR_Items",
                target_variable_tag="[package-detail]",
                reference_variable_tag="[package-config]",
                rule_type="package_items_compare",
                left_package_field="礼包id",
                right_package_field="INT_PackageId",
                left_item_field="道具ID",
                left_count_field="个数",
                right_items_field="STR_Items",
                package_id_filter="26042411",
            )
        ],
    )

    normalized = validate_and_normalize_fixed_rules_config(config)
    task_tree = build_fixed_rules_task_tree(normalized)

    assert task_tree.rules[0].rule_type == "package_items_compare"
    assert task_tree.rules[0].params == {
        "left_tag": "[package-detail]",
        "right_tag": "[package-config]",
        "left_package_field": "礼包id",
        "right_package_field": "INT_PackageId",
        "left_item_field": "道具ID",
        "left_count_field": "个数",
        "right_items_field": "STR_Items",
        "package_id_filter": "26042411",
        "display_field": None,
        "rule_name": "礼包明细对比STR_Items",
    }


def test_ai_rule_type_inference_recognizes_package_items_compare() -> None:
    rule_type = infer_hint_rule_type(
        RuleIntent(verdict="needs_input", rule_type=None),
        AiRuleWorkflowHints(),
        "礼包id 与 INT_PackageId 对齐，比较道具id/个数和 STR_Items 中的 {item,id,count}",
    )

    assert rule_type == "package_items_compare"


def test_ai_materializer_builds_package_items_compare_rule() -> None:
    target_variable = VariableTag(
        tag="[package-detail]",
        source_id="src",
        sheet="package_detail",
        variable_kind="composite",
        columns=["礼包id", "道具ID", "个数"],
        key_column="礼包id",
        append_index_to_key=True,
    )
    reference_variable = VariableTag(
        tag="[package-config]",
        source_id="src",
        sheet="package_config",
        variable_kind="composite",
        columns=["INT_PackageId", "STR_Items"],
        key_column="INT_PackageId",
    )
    intent = RuleIntent(
        verdict="ready",
        rule_type="package_items_compare",
        target=VariableIntent(tag="[package-detail]", variable_kind="composite"),
        reference=VariableIntent(tag="[package-config]", variable_kind="composite"),
        left_package_field="礼包id",
        right_package_field="INT_PackageId",
        left_item_field="道具ID",
        left_count_field="个数",
        right_items_field="STR_Items",
        package_id_filter="26042411",
    )

    rule, missing = materialize_rule_definition(
        intent,
        target_variable=target_variable,
        reference_variable=reference_variable,
        description="礼包道具配置校验",
    )

    assert missing == []
    assert rule is not None
    assert rule.rule_type == "package_items_compare"
    assert rule.target_variable_tag == "[package-detail]"
    assert rule.reference_variable_tag == "[package-config]"
    assert rule.left_package_field == "礼包id"
    assert rule.right_package_field == "INT_PackageId"
    assert rule.left_item_field == "道具ID"
    assert rule.left_count_field == "个数"
    assert rule.right_items_field == "STR_Items"
    assert rule.package_id_filter == "26042411"
