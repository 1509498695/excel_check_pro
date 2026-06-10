"""礼包规划表预解析测试。"""

from __future__ import annotations

import pytest

from backend.app.ai.credentials import PROJECT_AI_UNAVAILABLE_MESSAGE
from backend.app.database import async_session_factory
from backend.app.integrations.feishu_client import FeishuSheetTable
from backend.app.services.package_items_ai_parse_cache import (
    PackageItemsAiParseCacheKey,
    build_sheet_matrix_hash,
    clear_package_items_ai_parse_cache,
    set_package_items_ai_parse_cache_payload,
)
from backend.app.services.package_items_ai_parser import PackageAiParseSuggestion
from backend.app.services.package_items_parser import (
    PackageItemsAiParseCacheContext,
    build_package_items_map,
    extract_package_items_by_ai_suggestion,
    parse_package_items_sheet_async,
    parse_package_items_sheet,
)
from backend.tests.conftest import seed_fixed_rules_config


def test_parse_package_items_header_at_row_18() -> None:
    rows = [["说明"]] * 17 + [
        ["礼包id", "道具ID", "个数"],
        [26042411, 16001, 3],
        [26042412, 16002, 5],
    ]

    result = parse_package_items_sheet(rows)

    assert result.parse_status == "success"
    assert result.parse_mode == "rule"
    assert result.confidence >= 0.8
    assert result.header_rows == [18]
    assert result.detail_ranges[0].model_dump() == {
        "header_row": 18,
        "start_row": 19,
        "end_row": 20,
    }
    assert result.package_ids == ["26042411", "26042412"]
    assert result.package_count == 2
    assert result.detail_row_count == 2
    assert result.field_mapping.model_dump() == {
        "package_id": "礼包id",
        "item_id": "道具ID",
        "count": "个数",
    }
    assert [row.row_index for row in result.detail_rows] == [19, 20]
    assert [row.row_index for row in result.rows] == [19, 20]
    assert result.rows[0].count == 3
    assert result.rows[0].raw_row == [26042411, 16001, 3]


def test_parse_package_items_multiple_header_regions() -> None:
    result = parse_package_items_sheet(
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "16001", "3"],
            ["备注", "", ""],
            ["package_id", "item_id", "count"],
            ["26042412", "16002", "5"],
            ["26042411", "16003", "1"],
        ]
    )

    assert result.parse_status == "success"
    assert result.header_rows == [1, 4]
    assert [item.model_dump() for item in result.detail_ranges] == [
        {"header_row": 1, "start_row": 2, "end_row": 2},
        {"header_row": 4, "start_row": 5, "end_row": 6},
    ]
    assert result.package_ids == ["26042411", "26042412"]
    assert result.package_count == 2
    assert result.detail_row_count == 3
    assert [row.row_index for row in result.detail_rows] == [2, 5, 6]


def test_parse_package_items_rows_can_be_grouped_as_item_map() -> None:
    result = parse_package_items_sheet(
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "39", "8"],
            ["26042411", "48", "25"],
            ["package_id", "item_id", "count"],
            ["26042412", "47", "145"],
        ]
    )

    assert result.parse_status == "success"
    assert build_package_items_map(result.rows) == {
        "26042411": {"39": 8, "48": 25},
        "26042412": {"47": 145},
    }


def test_parse_package_items_warns_duplicate_item_id_without_dropping_rows() -> None:
    result = parse_package_items_sheet(
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "16001", "3"],
            ["26042411", "16001", "4"],
            ["26042412", "16001", "5"],
        ]
    )

    assert result.parse_status == "success"
    assert result.detail_row_count == 3
    assert (
        "识别到重复道具 ID：礼包 26042411 的道具 16001 在第 2 行和第 3 行重复。"
        in result.warnings
    )


def test_parse_package_items_skips_empty_note_and_missing_key_rows() -> None:
    result = parse_package_items_sheet(
        [
            ["礼包ID", "道具id", "数量"],
            ["", "", ""],
            ["说明：以下为测试礼包", "", ""],
            ["26042411", "", "3"],
            ["", "16002", "5"],
            ["26042412", "16003", ""],
            ["26042413", "16004", "7"],
        ]
    )

    assert result.parse_status == "success"
    assert result.detail_row_count == 1
    assert result.detail_rows[0].row_index == 7
    assert result.detail_rows[0].count == "7"
    assert result.rows[0].count == 7
    assert "跳过第 3 行" in result.warnings[0]
    assert "跳过第 4 行" in result.warnings[1]
    assert "跳过第 5 行" in result.warnings[2]
    assert "跳过第 6 行" in result.warnings[3]


def test_parse_package_items_reports_invalid_item_id_and_count() -> None:
    result = parse_package_items_sheet(
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "abc", "3"],
            ["26042411", "16001", "三个"],
        ]
    )

    assert result.parse_status == "failed"
    assert result.rows == []
    assert result.detail_rows == []
    assert "跳过第 2 行：道具 ID 无法转换为整数。" in result.warnings
    assert "跳过第 3 行：数量无法转换为整数。" in result.warnings
    assert "未识别到有效明细行" in result.errors


def test_parse_package_items_formula_text_still_fails_without_rendered_values() -> None:
    result = parse_package_items_sheet(
        [
            ["礼包id", "道具ID", "道具名", "个数"],
            ["26042411", "VLOOKUP(C2,'item'!B:H,2,FALSE)", "预备兵道具-1000", "3"],
        ]
    )

    assert result.parse_status == "failed"
    assert result.detail_row_count == 0
    assert "跳过第 2 行：道具 ID 无法转换为整数。" in result.warnings
    assert "未识别到有效明细行" in result.errors


def test_parse_package_items_accepts_formatted_formula_values() -> None:
    result = parse_package_items_sheet(
        [
            ["礼包id", "道具ID", "道具名", "个数"],
            [26042411, 16001, "预备兵道具-1000", 3],
            [26042411, "62", "训练加速分钟=60", "10"],
        ]
    )

    assert result.parse_status == "success"
    assert result.package_ids == ["26042411"]
    assert [item.model_dump() for item in result.detail_ranges] == [
        {"header_row": 1, "start_row": 2, "end_row": 3}
    ]
    assert result.detail_row_count == 2
    assert [row.item_id for row in result.rows] == ["16001", "62"]
    assert [row.count for row in result.rows] == [3, 10]


def test_parse_package_items_recognizes_field_aliases_with_lower_confidence() -> None:
    alias_result = parse_package_items_sheet(
        [
            ["packageId", "itemId", "num"],
            ["26042411", "16001", "3"],
        ]
    )
    standard_result = parse_package_items_sheet(
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "16001", "3"],
        ]
    )

    assert alias_result.parse_status == "success"
    assert alias_result.field_mapping.model_dump() == {
        "package_id": "packageId",
        "item_id": "itemId",
        "count": "num",
    }
    assert alias_result.detail_rows[0].package_id == "26042411"
    assert alias_result.detail_rows[0].item_id == "16001"
    assert alias_result.detail_rows[0].count == "3"
    assert alias_result.confidence < standard_result.confidence
    assert alias_result.confidence == 0.8


def test_parse_package_items_without_header_fails() -> None:
    result = parse_package_items_sheet(
        [
            ["礼包", "道具", "数值"],
            ["26042411", "16001", "3"],
        ]
    )

    assert result.parse_status == "failed"
    assert result.header_rows == []
    assert result.package_count == 0
    assert result.detail_row_count == 0
    assert result.package_ids == []
    assert result.detail_rows == []
    assert result.rows == []
    assert result.errors == ["未识别到表头"]


def test_parse_package_items_missing_count_field_fails() -> None:
    result = parse_package_items_sheet(
        [
            ["礼包id", "道具ID", "备注"],
            ["26042411", "16001", "x"],
        ]
    )

    assert result.parse_status == "failed"
    assert result.header_rows == [1]
    assert "缺少数量字段" in result.errors
    assert result.field_mapping.count == ""


def test_parse_package_items_header_without_valid_detail_rows_fails() -> None:
    result = parse_package_items_sheet(
        [
            ["礼包id", "道具ID", "个数"],
            ["", "", ""],
            ["26042411", "", "3"],
            ["26042412", "16002", ""],
        ]
    )

    assert result.parse_status == "failed"
    assert result.header_rows == [1]
    assert result.detail_row_count == 0
    assert result.rows == []
    assert "未识别到有效明细行" in result.errors


@pytest.mark.anyio
async def test_parse_package_items_auto_high_confidence_rule_does_not_call_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("高置信规则解析不应调用 AI")

    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_sheet_with_ai",
        _fail_if_called,
    )

    result = await parse_package_items_sheet_async(
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "16001", "3"],
        ],
        sheet_name="礼包规划",
        parse_strategy="auto",
        ai_parse_mode="enabled",
    )

    assert result.parse_status == "success"
    assert result.parse_mode == "rule"
    assert result.ai_used is False
    assert result.confidence >= 0.8


@pytest.mark.anyio
async def test_parse_package_items_auto_rule_failure_calls_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _fake_ai(*_args, **_kwargs):
        nonlocal called
        called = True
        return _ai_suggestion(
            detail_ranges=[{"header_row": 1, "start_row": 2, "end_row": 2}],
            field_mapping={
                "package_id": "礼包",
                "item_id": "道具",
                "count": "数量",
            },
        )

    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_sheet_with_ai",
        _fake_ai,
    )

    result = await parse_package_items_sheet_async(
        [["礼包", "道具", "数量"], ["26042411", "16001", "3"]],
        sheet_name="礼包规划",
        parse_strategy="auto",
        ai_parse_mode="auto",
    )

    assert called is True
    assert result.parse_status == "success"
    assert result.parse_mode == "ai"
    assert result.ai_used is True
    assert result.package_ids == ["26042411"]
    assert result.rows[0].package_id == "26042411"


@pytest.mark.anyio
async def test_parse_package_items_auto_low_confidence_rule_calls_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.api.fixed_rules_schemas import PackageItemsPreviewResult, PackagePlanItemRow

    async def _fake_ai(*_args, **_kwargs):
        return _ai_suggestion(detail_ranges=[{"header_row": 1, "start_row": 2, "end_row": 2}])

    def _low_confidence_rule(*_args, **_kwargs):
        return PackageItemsPreviewResult(
            parse_status="success",
            parse_mode="rule",
            confidence=0.7,
            header_rows=[1],
            package_ids=["26042411"],
            package_count=1,
            detail_row_count=1,
            rows=[
                PackagePlanItemRow(
                    package_id="26042411",
                    item_id="16001",
                    count=3,
                    row_index=2,
                    raw_row=["26042411", "16001", "3"],
                )
            ],
        )

    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_items_sheet",
        _low_confidence_rule,
    )
    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_sheet_with_ai",
        _fake_ai,
    )

    result = await parse_package_items_sheet_async(
        [["礼包id", "道具ID", "个数"], ["26042411", "16001", "3"]],
        sheet_name="礼包规划",
        parse_strategy="auto",
        ai_parse_mode="enabled",
    )

    assert result.parse_status == "success"
    assert result.parse_mode == "ai"
    assert result.ai_used is True
    assert result.confidence == 0.88


@pytest.mark.anyio
async def test_parse_package_items_auto_unconfigured_project_ai_falls_back_to_rule(
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.api.fixed_rules_schemas import PackageItemsPreviewResult, PackagePlanItemRow

    def _low_confidence_rule(*_args, **_kwargs):
        return PackageItemsPreviewResult(
            parse_status="success",
            parse_mode="rule",
            confidence=0.7,
            header_rows=[1],
            package_ids=["26042411"],
            package_count=1,
            detail_row_count=1,
            rows=[
                PackagePlanItemRow(
                    package_id="26042411",
                    item_id="16001",
                    count=3,
                    row_index=2,
                    raw_row=["26042411", "16001", "3"],
                )
            ],
        )

    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_items_sheet",
        _low_confidence_rule,
    )

    async with async_session_factory() as session:
        result = await parse_package_items_sheet_async(
            [
                ["礼包id", "道具ID", "个数"],
                ["26042411", "16001", "3"],
            ],
            sheet_name="礼包规划",
            parse_strategy="auto",
            ai_parse_mode="enabled",
            db=session,
            project_id=test_project_id,
        )

    assert result.parse_status == "success"
    assert result.parse_mode == "rule"
    assert result.ai_used is False
    assert result.package_ids == ["26042411"]
    assert PROJECT_AI_UNAVAILABLE_MESSAGE in result.warnings


@pytest.mark.anyio
async def test_parse_package_items_explicit_ai_unconfigured_project_ai_returns_error(
    test_project_id: int,
) -> None:
    async with async_session_factory() as session:
        result = await parse_package_items_sheet_async(
            [
                ["礼包", "道具", "数量"],
                ["26042411", "16001", "3"],
            ],
            sheet_name="礼包规划",
            parse_strategy="ai",
            ai_parse_mode="enabled",
            db=session,
            project_id=test_project_id,
        )

    assert result.parse_status == "failed"
    assert result.parse_mode == "ai"
    assert result.ai_used is False
    assert result.errors == [PROJECT_AI_UNAVAILABLE_MESSAGE]


@pytest.mark.anyio
async def test_parse_package_items_auto_rule_failure_ai_disabled_does_not_call_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("AI disabled 时不应调用 AI")

    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_sheet_with_ai",
        _fail_if_called,
    )

    result = await parse_package_items_sheet_async(
        [["礼包", "道具", "数值"], ["26042411", "16001", "3"]],
        sheet_name="礼包规划",
        parse_strategy="auto",
        ai_parse_mode="disabled",
    )

    assert result.parse_status == "failed"
    assert result.parse_mode == "rule"
    assert result.ai_used is False
    assert result.errors == ["未识别到表头"]
    assert result.warnings == ["AI 辅助解析已关闭。"]


@pytest.mark.anyio
async def test_parse_package_items_rule_strategy_never_calls_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("rule 策略不应调用 AI")

    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_sheet_with_ai",
        _fail_if_called,
    )

    result = await parse_package_items_sheet_async(
        [["礼包", "道具", "数量"], ["26042411", "16001", "3"]],
        sheet_name="礼包规划",
        parse_strategy="rule",
        ai_parse_mode="enabled",
    )

    assert result.parse_status == "failed"
    assert result.parse_mode == "rule"
    assert result.ai_used is False
    assert result.errors == ["缺少礼包 ID 字段", "缺少道具 ID 字段"]


@pytest.mark.anyio
async def test_parse_package_items_ai_disabled_fails_without_rule_parse() -> None:
    result = await parse_package_items_sheet_async(
        [["礼包id", "道具ID", "个数"], ["26042411", "16001", "3"]],
        sheet_name="礼包规划",
        parse_strategy="ai",
        ai_parse_mode="disabled",
    )

    assert result.parse_status == "failed"
    assert result.parse_mode == "ai"
    assert result.ai_used is False
    assert result.errors == ["AI 辅助解析已关闭。"]


@pytest.mark.anyio
async def test_parse_package_items_ai_enabled_calls_ai_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_ai(*_args, **_kwargs):
        return _ai_suggestion(
            detail_ranges=[{"header_row": 1, "start_row": 2, "end_row": 2}],
            confidence=0.91,
        )

    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_sheet_with_ai",
        _fake_ai,
    )

    result = await parse_package_items_sheet_async(
        [["礼包id", "道具ID", "个数"], ["26042411", "16001", "3"]],
        sheet_name="礼包规划",
        parse_strategy="ai",
        ai_parse_mode="enabled",
    )

    assert result.parse_status == "success"
    assert result.parse_mode == "ai"
    assert result.ai_used is True
    assert result.confidence == 0.91
    assert result.detail_rows[0].count == "3"


@pytest.mark.anyio
async def test_parse_package_items_invalid_ai_result_returns_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.services.package_items_ai_parser import PackageAiParseError

    async def _fake_ai(*_args, **_kwargs):
        raise PackageAiParseError("AI 返回结构不合法")

    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_sheet_with_ai",
        _fake_ai,
    )

    result = await parse_package_items_sheet_async(
        [["礼包", "道具", "数值"], ["26042411", "16001", "3"]],
        sheet_name="礼包规划",
        parse_strategy="auto",
        ai_parse_mode="enabled",
    )

    assert result.parse_status == "failed"
    assert result.parse_mode == "ai"
    assert result.ai_used is True
    assert result.errors == ["未识别到表头", "AI 辅助解析失败：AI 返回结构不合法"]


@pytest.mark.anyio
async def test_parse_package_items_ai_failure_falls_back_to_rule_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.api.fixed_rules_schemas import PackageItemsPreviewResult, PackagePlanItemRow
    from backend.app.services.package_items_ai_parser import PackageAiParseError

    def _low_confidence_rule(*_args, **_kwargs):
        return PackageItemsPreviewResult(
            parse_status="success",
            parse_mode="rule",
            confidence=0.7,
            header_rows=[1],
            package_ids=["26042411"],
            package_count=1,
            detail_row_count=1,
            rows=[
                PackagePlanItemRow(
                    package_id="26042411",
                    item_id="16001",
                    count=3,
                    row_index=2,
                    raw_row=["26042411", "16001", "3"],
                )
            ],
        )

    async def _fake_ai(*_args, **_kwargs):
        raise PackageAiParseError("上游超时")

    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_items_sheet",
        _low_confidence_rule,
    )
    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_sheet_with_ai",
        _fake_ai,
    )

    result = await parse_package_items_sheet_async(
        [["礼包id", "道具ID", "个数"], ["26042411", "16001", "3"]],
        sheet_name="礼包规划",
        parse_strategy="auto",
        ai_parse_mode="enabled",
    )

    assert result.parse_status == "success"
    assert result.parse_mode == "rule"
    assert result.ai_used is True
    assert result.rows[0].package_id == "26042411"
    assert "已回退为规则解析结果" in result.warnings[0]


@pytest.mark.anyio
async def test_parse_package_items_ai_cache_hits_for_same_sheet_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_package_items_ai_parse_cache()
    call_count = 0
    sheet = [["礼包", "道具", "数量"], ["26042411", "16001", "3"]]

    async def _fake_ai(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        return _ai_suggestion(
            detail_ranges=[{"header_row": 1, "start_row": 2, "end_row": 2}],
            field_mapping={
                "package_id": "礼包",
                "item_id": "道具",
                "count": "数量",
            },
        )

    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_sheet_with_ai",
        _fake_ai,
    )
    cache_context = _cache_context(sheet)

    first_result = await parse_package_items_sheet_async(
        sheet,
        sheet_name="礼包规划",
        parse_strategy="auto",
        ai_parse_mode="auto",
        ai_cache_context=cache_context,
    )
    second_result = await parse_package_items_sheet_async(
        sheet,
        sheet_name="礼包规划",
        parse_strategy="auto",
        ai_parse_mode="auto",
        ai_cache_context=cache_context,
    )

    assert call_count == 1
    assert first_result.cache_hit is False
    assert second_result.cache_hit is True
    assert second_result.rows[0].package_id == "26042411"
    clear_package_items_ai_parse_cache()


@pytest.mark.anyio
async def test_parse_package_items_ai_cache_misses_after_sheet_content_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_package_items_ai_parse_cache()
    call_count = 0

    async def _fake_ai(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        return _ai_suggestion(
            detail_ranges=[{"header_row": 1, "start_row": 2, "end_row": 2}],
            field_mapping={
                "package_id": "礼包",
                "item_id": "道具",
                "count": "数量",
            },
        )

    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_sheet_with_ai",
        _fake_ai,
    )
    first_sheet = [["礼包", "道具", "数量"], ["26042411", "16001", "3"]]
    second_sheet = [["礼包", "道具", "数量"], ["26042411", "16001", "4"]]

    first_result = await parse_package_items_sheet_async(
        first_sheet,
        sheet_name="礼包规划",
        parse_strategy="auto",
        ai_parse_mode="auto",
        ai_cache_context=_cache_context(first_sheet),
    )
    second_result = await parse_package_items_sheet_async(
        second_sheet,
        sheet_name="礼包规划",
        parse_strategy="auto",
        ai_parse_mode="auto",
        ai_cache_context=_cache_context(second_sheet),
    )

    assert call_count == 2
    assert first_result.cache_hit is False
    assert second_result.cache_hit is False
    assert second_result.rows[0].count == 4
    clear_package_items_ai_parse_cache()


@pytest.mark.anyio
async def test_parse_package_items_ai_cache_misses_after_prompt_version_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_package_items_ai_parse_cache()
    call_count = 0
    sheet = [["礼包", "道具", "数量"], ["26042411", "16001", "3"]]

    async def _fake_ai(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        return _ai_suggestion(
            detail_ranges=[{"header_row": 1, "start_row": 2, "end_row": 2}],
            field_mapping={
                "package_id": "礼包",
                "item_id": "道具",
                "count": "数量",
            },
        )

    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_sheet_with_ai",
        _fake_ai,
    )
    cache_context = _cache_context(sheet)

    await parse_package_items_sheet_async(
        sheet,
        sheet_name="礼包规划",
        parse_strategy="auto",
        ai_parse_mode="auto",
        ai_cache_context=cache_context,
    )
    monkeypatch.setattr(
        "backend.app.services.package_items_parser.PROMPT_VERSION",
        "package-items-ai-parser-next",
    )
    result = await parse_package_items_sheet_async(
        sheet,
        sheet_name="礼包规划",
        parse_strategy="auto",
        ai_parse_mode="auto",
        ai_cache_context=cache_context,
    )

    assert call_count == 2
    assert result.cache_hit is False
    clear_package_items_ai_parse_cache()


@pytest.mark.anyio
async def test_parse_package_items_ai_cache_invalid_entry_is_recomputed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.services import package_items_parser

    clear_package_items_ai_parse_cache()
    call_count = 0
    sheet = [["礼包", "道具", "数量"], ["26042411", "16001", "3"]]
    cache_context = _cache_context(sheet)
    cache_key = PackageItemsAiParseCacheKey(
        feishu_source_id=cache_context.feishu_source_id,
        sheet_id=cache_context.sheet_id,
        sheet_revision_or_hash=cache_context.sheet_revision_or_hash,
        parse_strategy="auto",
        ai_parse_mode="auto",
        prompt_version=package_items_parser.PROMPT_VERSION,
    )
    set_package_items_ai_parse_cache_payload(
        cache_key,
        suggestion_payload=_ai_suggestion().model_dump(mode="json"),
        parse_result_payload={"parse_status": "success", "parse_mode": "invalid"},
    )

    async def _fake_ai(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        return _ai_suggestion(
            detail_ranges=[{"header_row": 1, "start_row": 2, "end_row": 2}],
            field_mapping={
                "package_id": "礼包",
                "item_id": "道具",
                "count": "数量",
            },
        )

    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_sheet_with_ai",
        _fake_ai,
    )

    result = await parse_package_items_sheet_async(
        sheet,
        sheet_name="礼包规划",
        parse_strategy="auto",
        ai_parse_mode="auto",
        ai_cache_context=cache_context,
    )

    assert call_count == 1
    assert result.cache_hit is False
    assert result.parse_status == "success"
    clear_package_items_ai_parse_cache()


def _ai_suggestion(**overrides):
    payload = {
        "header_rows": [1],
        "detail_ranges": [{"header_row": 1, "start_row": 2, "end_row": 3}],
        "field_mapping": {
            "package_id": "礼包id",
            "item_id": "道具ID",
            "count": "个数",
        },
        "confidence": 0.88,
        "warnings": [],
        "reasoning_summary": "识别到礼包明细区域。",
    }
    payload.update(overrides)
    return PackageAiParseSuggestion.model_validate(payload)


def _cache_context(sheet: list[list[object]]) -> PackageItemsAiParseCacheContext:
    return PackageItemsAiParseCacheContext(
        feishu_source_id="feishu-plan",
        sheet_id="gid_plan",
        sheet_revision_or_hash=build_sheet_matrix_hash(sheet),
    )


def test_extract_package_items_by_ai_suggestion_extracts_rows() -> None:
    result = extract_package_items_by_ai_suggestion(
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "16001", "3"],
            ["26042412", "16002", "5"],
        ],
        _ai_suggestion(),
    )

    assert result.parse_status == "success"
    assert result.parse_mode == "ai"
    assert result.confidence == 0.88
    assert result.header_rows == [1]
    assert [item.model_dump() for item in result.detail_ranges] == [
        {"header_row": 1, "start_row": 2, "end_row": 3}
    ]
    assert result.field_mapping.model_dump() == {
        "package_id": "礼包id",
        "item_id": "道具ID",
        "count": "个数",
    }
    assert result.package_ids == ["26042411", "26042412"]
    assert result.detail_row_count == 2
    assert [(row.row_index, row.package_id, row.item_id, row.count) for row in result.rows] == [
        (2, "26042411", "16001", 3),
        (3, "26042412", "16002", 5),
    ]


def test_extract_package_items_by_ai_suggestion_supports_multiple_ranges() -> None:
    result = extract_package_items_by_ai_suggestion(
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "16001", "3"],
            ["说明"],
            ["package_id", "item_id", "count"],
            ["26042412", "16002", "5"],
            ["26042411", "16003", "1"],
        ],
        _ai_suggestion(
            header_rows=[1, 4],
            detail_ranges=[
                {"header_row": 1, "start_row": 2, "end_row": 2},
                {"header_row": 4, "start_row": 5, "end_row": 6},
            ],
        ),
    )

    assert result.parse_status == "success"
    assert result.package_ids == ["26042411", "26042412"]
    assert [row.row_index for row in result.rows] == [2, 5, 6]
    assert [row.count for row in result.rows] == [3, 5, 1]


def test_extract_package_items_by_ai_suggestion_warns_duplicate_item_id() -> None:
    result = extract_package_items_by_ai_suggestion(
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "16001", "3"],
            ["26042411", "16001", "4"],
        ],
        _ai_suggestion(detail_ranges=[{"header_row": 1, "start_row": 2, "end_row": 3}]),
    )

    assert result.parse_status == "success"
    assert result.detail_row_count == 2
    assert result.warnings == [
        "识别到重复道具 ID：礼包 26042411 的道具 16001 在第 2 行和第 3 行重复。"
    ]


def test_extract_package_items_by_ai_suggestion_uses_alias_fallback() -> None:
    result = extract_package_items_by_ai_suggestion(
        [
            ["packageId", "itemId", "num"],
            ["26042411", "16001", "3"],
        ],
        _ai_suggestion(
            detail_ranges=[{"header_row": 1, "start_row": 2, "end_row": 2}],
            field_mapping={
                "package_id": "礼包",
                "item_id": "道具",
                "count": "数量",
            },
        ),
    )

    assert result.parse_status == "success"
    assert result.field_mapping.model_dump() == {
        "package_id": "packageId",
        "item_id": "itemId",
        "count": "num",
    }
    assert result.rows[0].package_id == "26042411"
    assert result.rows[0].item_id == "16001"
    assert result.rows[0].count == 3


def test_extract_package_items_by_ai_suggestion_unmatched_mapping_fails() -> None:
    result = extract_package_items_by_ai_suggestion(
        [
            ["礼包名称", "道具名称", "数量描述"],
            ["礼包A", "道具A", "3"],
        ],
        _ai_suggestion(
            detail_ranges=[{"header_row": 1, "start_row": 2, "end_row": 2}],
            field_mapping={
                "package_id": "礼包",
                "item_id": "道具",
                "count": "数量",
            },
        ),
    )

    assert result.parse_status == "failed"
    assert result.rows == []
    assert any("字段映射失败" in error for error in result.errors)


def test_extract_package_items_by_ai_suggestion_skips_empty_and_note_rows() -> None:
    result = extract_package_items_by_ai_suggestion(
        [
            ["礼包id", "道具ID", "个数"],
            ["", "", ""],
            ["说明：测试礼包", "", ""],
            ["26042411", "16001", "3"],
        ],
        _ai_suggestion(detail_ranges=[{"header_row": 1, "start_row": 2, "end_row": 4}]),
    )

    assert result.parse_status == "success"
    assert [row.row_index for row in result.rows] == [4]
    assert result.warnings == ["跳过第 3 行：缺少礼包 ID 或道具 ID。"]


def test_extract_package_items_by_ai_suggestion_out_of_bounds_range_fails() -> None:
    result = extract_package_items_by_ai_suggestion(
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "16001", "3"],
        ],
        _ai_suggestion(detail_ranges=[{"header_row": 1, "start_row": 2, "end_row": 99}]),
    )

    assert result.parse_status == "failed"
    assert result.rows == []
    assert any("范围越界" in error for error in result.errors)


def test_extract_package_items_by_ai_suggestion_invalid_count_warns_and_fails_if_empty() -> None:
    result = extract_package_items_by_ai_suggestion(
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "16001", "三个"],
        ],
        _ai_suggestion(detail_ranges=[{"header_row": 1, "start_row": 2, "end_row": 2}]),
    )

    assert result.parse_status == "failed"
    assert result.detail_row_count == 0
    assert result.warnings == ["跳过第 2 行：数量无法转换为整数。"]
    assert result.errors == ["未识别到有效明细行"]


def test_extract_package_items_by_ai_suggestion_ignores_fabricated_detail_rows() -> None:
    suggestion = {
        "header_rows": [1],
        "detail_ranges": [{"header_row": 1, "start_row": 2, "end_row": 2}],
        "field_mapping": {
            "package_id": "礼包id",
            "item_id": "道具ID",
            "count": "个数",
        },
        "confidence": 0.91,
        "warnings": [],
        "detail_rows": [
            {
                "row_index": 2,
                "package_id": "fake-package",
                "item_id": "fake-item",
                "count": 999,
            }
        ],
    }

    result = extract_package_items_by_ai_suggestion(
        [
            ["礼包id", "道具ID", "个数"],
            ["26042411", "16001", "3"],
        ],
        suggestion,
    )

    assert result.parse_status == "success"
    assert result.rows[0].package_id == "26042411"
    assert result.rows[0].item_id == "16001"
    assert result.rows[0].count == 3


@pytest.mark.anyio
async def test_preview_package_items_endpoint_returns_parse_summary(
    auth_client,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.integrations import feishu_client

    await seed_fixed_rules_config(
        {
            "version": 6,
            "configured": True,
            "sources": [
                {
                    "id": "feishu-plan",
                    "type": "feishu",
                    "pathOrUrl": "https://demo.feishu.cn/sheets/shtcnabc123",
                }
            ],
            "variables": [],
            "groups": [],
            "rules": [],
            "local_path_replacement_presets": [],
            "svn_path_replacement_presets": [],
        },
        test_project_id,
    )

    async def _read_values(*_args, **kwargs):
        assert kwargs["sheet_id"] == "gid_plan"
        assert kwargs["value_render_option"] == "FormattedValue"
        return FeishuSheetTable(
            spreadsheet_token="shtcnabc123",
            sheet_id="gid_plan",
            sheet_title="礼包规划",
            range="gid_plan!A1:C2",
            columns=[],
            rows=[],
            raw_values=[
                ["礼包id", "道具ID", "个数"],
                ["26042411", "16001", "3"],
            ],
        )

    monkeypatch.setattr(feishu_client, "read_sheet_values", _read_values)

    response = await auth_client.post(
        "/api/v1/fixed-rules/package-items/preview",
        json={
            "feishu_source_id": "feishu-plan",
            "sheet_id": "gid_plan",
            "parse_strategy": "auto",
            "ai_parse_mode": "auto",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["parse_status"] == "success"
    assert data["parse_mode"] == "rule"
    assert data["ai_used"] is False
    assert data["confidence"] >= 0.8
    assert data["package_ids"] == ["26042411"]
    assert data["package_count"] == 1
    assert data["detail_row_count"] == 1
    assert data["detail_ranges"] == [{"header_row": 1, "start_row": 2, "end_row": 2}]
    assert data["detail_rows"] == [
        {
            "row_index": 2,
            "package_id": "26042411",
            "item_id": "16001",
            "count": "3",
        }
    ]
    assert data["rows"] == [
        {
            "row_index": 2,
            "package_id": "26042411",
            "item_id": "16001",
            "count": 3,
            "raw_row": ["26042411", "16001", "3"],
        }
    ]
    assert set(
        [
            "parse_status",
            "parse_mode",
            "confidence",
            "ai_used",
            "cache_hit",
            "package_ids",
            "package_count",
            "detail_row_count",
            "header_rows",
            "detail_ranges",
            "field_mapping",
            "warnings",
            "errors",
        ]
    ).issubset(data.keys())


@pytest.mark.anyio
async def test_preview_package_items_endpoint_returns_ai_parse_summary(
    auth_client,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.integrations import feishu_client

    await seed_fixed_rules_config(
        {
            "version": 6,
            "configured": True,
            "sources": [
                {
                    "id": "feishu-plan",
                    "type": "feishu",
                    "pathOrUrl": "https://demo.feishu.cn/sheets/shtcnabc123",
                }
            ],
            "variables": [],
            "groups": [],
            "rules": [],
        },
        test_project_id,
    )

    async def _read_values(*_args, **_kwargs):
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
        return _ai_suggestion(
            detail_ranges=[{"header_row": 1, "start_row": 2, "end_row": 2}],
            field_mapping={
                "package_id": "礼包",
                "item_id": "道具",
                "count": "数量",
            },
            confidence=0.93,
            warnings=["识别到非标准表头"],
        )

    monkeypatch.setattr(feishu_client, "read_sheet_values", _read_values)
    monkeypatch.setattr(
        "backend.app.services.package_items_parser.parse_package_sheet_with_ai",
        _parse_with_ai,
    )

    response = await auth_client.post(
        "/api/v1/fixed-rules/package-items/preview",
        json={
            "feishu_source_id": "feishu-plan",
            "sheet_id": "gid_plan",
            "parse_strategy": "auto",
            "ai_parse_mode": "enabled",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["parse_status"] == "success"
    assert data["parse_mode"] == "ai"
    assert data["ai_used"] is True
    assert data["confidence"] == 0.93
    assert data["warnings"] == ["识别到非标准表头"]
    assert data["package_ids"] == ["26042411"]


@pytest.mark.anyio
async def test_preview_package_items_endpoint_reports_parse_failure(
    auth_client,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.integrations import feishu_client

    await seed_fixed_rules_config(
        {
            "version": 6,
            "configured": True,
            "sources": [
                {
                    "id": "feishu-plan",
                    "type": "feishu",
                    "pathOrUrl": "https://demo.feishu.cn/sheets/shtcnabc123",
                }
            ],
            "variables": [],
            "groups": [],
            "rules": [],
        },
        test_project_id,
    )

    async def _read_values(*_args, **_kwargs):
        return FeishuSheetTable(
            spreadsheet_token="shtcnabc123",
            sheet_id="gid_plan",
            sheet_title="礼包规划",
            range="gid_plan!A1:C2",
            columns=[],
            rows=[],
            raw_values=[["说明"], ["没有表头"]],
        )

    monkeypatch.setattr(feishu_client, "read_sheet_values", _read_values)

    response = await auth_client.post(
        "/api/v1/fixed-rules/package-items/preview",
        json={
            "feishu_source_id": "feishu-plan",
            "sheet_id": "gid_plan",
            "parse_strategy": "rule",
            "ai_parse_mode": "disabled",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["parse_status"] == "failed"
    assert data["parse_mode"] == "rule"
    assert data["errors"] == ["未识别到表头"]


@pytest.mark.anyio
async def test_preview_package_items_endpoint_maps_feishu_errors(
    auth_client,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.app.integrations import feishu_client
    from backend.app.integrations.feishu_client import (
        FEISHU_DOCUMENT_PERMISSION_DENIED,
        FeishuClientError,
    )

    await seed_fixed_rules_config(
        {
            "version": 6,
            "configured": True,
            "sources": [
                {
                    "id": "feishu-plan",
                    "type": "feishu",
                    "pathOrUrl": "https://demo.feishu.cn/sheets/shtcnabc123",
                }
            ],
            "variables": [],
            "groups": [],
            "rules": [],
        },
        test_project_id,
    )

    async def _read_values(*_args, **_kwargs):
        raise FeishuClientError(FEISHU_DOCUMENT_PERMISSION_DENIED, "飞书未授权")

    monkeypatch.setattr(feishu_client, "read_sheet_values", _read_values)

    response = await auth_client.post(
        "/api/v1/fixed-rules/package-items/preview",
        json={
            "feishu_source_id": "feishu-plan",
            "sheet_id": "gid_plan",
            "parse_strategy": "rule",
            "ai_parse_mode": "disabled",
        },
    )

    assert response.status_code == 400
    assert "飞书未授权" in response.json()["detail"]


@pytest.mark.anyio
async def test_preview_package_items_endpoint_rejects_invalid_payload(auth_client) -> None:
    response = await auth_client.post(
        "/api/v1/fixed-rules/package-items/preview",
        json={
            "feishu_source_id": "feishu-plan",
            "sheet_id": "gid_plan",
            "parse_strategy": "invalid",
            "ai_parse_mode": "auto",
        },
    )

    assert response.status_code == 422
