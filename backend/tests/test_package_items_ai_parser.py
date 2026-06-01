"""礼包规划表 AI 结构识别服务测试。"""

from __future__ import annotations

import json
from typing import Any

import pytest

from backend.app.services.package_items_ai_parser import (
    PackageAiParseError,
    PackageAiParseSuggestion,
    parse_package_sheet_with_ai,
)


class _FakeAiClient:
    def __init__(self, response: dict[str, Any] | str) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any] | str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "json_schema": json_schema,
            }
        )
        return self.response


def _valid_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "header_rows": [1],
        "detail_ranges": [{"header_row": 1, "start_row": 2, "end_row": 3}],
        "field_mapping": {
            "package_id": "礼包id",
            "item_id": "道具ID",
            "count": "个数",
        },
        "confidence": 0.86,
        "warnings": [],
        "reasoning_summary": "识别到标准礼包明细表头。",
    }
    payload.update(overrides)
    return payload


def _sheet_matrix() -> list[list[Any]]:
    return [
        ["礼包id", "道具ID", "个数"],
        ["26042411", "16001", "3"],
        ["26042412", "16002", "5"],
    ]


@pytest.mark.anyio
async def test_parse_package_sheet_with_ai_valid_json_success() -> None:
    fake_client = _FakeAiClient(_valid_payload(warnings=[123, "  注意辅助表  "]))

    result = await parse_package_sheet_with_ai(
        _sheet_matrix(),
        "礼包规划",
        {"ai_client": fake_client},
    )

    assert isinstance(result, PackageAiParseSuggestion)
    assert result.header_rows == [1]
    assert [item.model_dump() for item in result.detail_ranges] == [
        {"header_row": 1, "start_row": 2, "end_row": 3}
    ]
    assert result.field_mapping == {
        "package_id": "礼包id",
        "item_id": "道具ID",
        "count": "个数",
    }
    assert result.confidence == 0.86
    assert result.warnings == ["123", "注意辅助表"]
    assert fake_client.calls
    call = fake_client.calls[0]
    prompt_text = f"{call['system_prompt']}\n{call['user_prompt']}"
    assert "不做最终校验判断" in prompt_text
    assert "只输出符合 JSON schema 的 JSON 对象" in prompt_text
    assert "原始 1-based 行号" in prompt_text
    assert "confidence < 0.7" in prompt_text
    assert "warnings" in prompt_text
    assert "field_mapping 必须使用表头中的原始字段名" in prompt_text
    json_schema = call["json_schema"]
    assert json_schema["required"] == [
        "header_rows",
        "detail_ranges",
        "field_mapping",
        "confidence",
        "warnings",
        "reasoning_summary",
    ]
    assert set(json_schema["properties"]["field_mapping"]["required"]) == {
        "package_id",
        "item_id",
        "count",
    }


@pytest.mark.anyio
async def test_parse_package_sheet_with_ai_extracts_markdown_json() -> None:
    fake_client = _FakeAiClient(f"```json\n{json.dumps(_valid_payload(), ensure_ascii=False)}\n```")

    result = await parse_package_sheet_with_ai(
        _sheet_matrix(),
        "礼包规划",
        {"ai_client": fake_client},
    )

    assert PackageAiParseSuggestion.model_validate(result.model_dump()).confidence == 0.86
    assert result.detail_ranges[0].start_row == 2


@pytest.mark.anyio
async def test_parse_package_sheet_with_ai_invalid_json_raises_error() -> None:
    fake_client = _FakeAiClient("模型没有返回 JSON")

    with pytest.raises(PackageAiParseError, match="模型未返回 JSON"):
        await parse_package_sheet_with_ai(
            _sheet_matrix(),
            "礼包规划",
            {"ai_client": fake_client},
        )


@pytest.mark.anyio
async def test_parse_package_sheet_with_ai_out_of_bounds_detail_range_fails() -> None:
    fake_client = _FakeAiClient(
        _valid_payload(detail_ranges=[{"header_row": 1, "start_row": 2, "end_row": 99}])
    )

    with pytest.raises(PackageAiParseError, match="范围越界"):
        await parse_package_sheet_with_ai(
            _sheet_matrix(),
            "礼包规划",
            {"ai_client": fake_client},
        )


@pytest.mark.anyio
async def test_parse_package_sheet_with_ai_missing_count_mapping_fails() -> None:
    fake_client = _FakeAiClient(
        _valid_payload(
            field_mapping={
                "package_id": "礼包id",
                "item_id": "道具ID",
            }
        )
    )

    with pytest.raises(PackageAiParseError, match="Field required|缺少字段"):
        await parse_package_sheet_with_ai(
            _sheet_matrix(),
            "礼包规划",
            {"ai_client": fake_client},
        )


@pytest.mark.anyio
async def test_parse_package_sheet_with_ai_missing_header_rows_fails() -> None:
    payload = _valid_payload()
    payload.pop("header_rows")
    fake_client = _FakeAiClient(payload)

    with pytest.raises(PackageAiParseError, match="Field required|缺少 header_rows"):
        await parse_package_sheet_with_ai(
            _sheet_matrix(),
            "礼包规划",
            {"ai_client": fake_client},
        )


@pytest.mark.anyio
async def test_parse_package_sheet_with_ai_missing_detail_ranges_fails() -> None:
    payload = _valid_payload()
    payload.pop("detail_ranges")
    fake_client = _FakeAiClient(payload)

    with pytest.raises(PackageAiParseError, match="Field required|缺少 detail_ranges"):
        await parse_package_sheet_with_ai(
            _sheet_matrix(),
            "礼包规划",
            {"ai_client": fake_client},
        )


@pytest.mark.anyio
async def test_parse_package_sheet_with_ai_missing_field_mapping_fails() -> None:
    payload = _valid_payload()
    payload.pop("field_mapping")
    fake_client = _FakeAiClient(payload)

    with pytest.raises(PackageAiParseError, match="Field required"):
        await parse_package_sheet_with_ai(
            _sheet_matrix(),
            "礼包规划",
            {"ai_client": fake_client},
        )


@pytest.mark.anyio
async def test_parse_package_sheet_with_ai_start_row_must_follow_header() -> None:
    fake_client = _FakeAiClient(
        _valid_payload(detail_ranges=[{"header_row": 1, "start_row": 1, "end_row": 2}])
    )

    with pytest.raises(PackageAiParseError, match="start_row 必须大于 header_row"):
        await parse_package_sheet_with_ai(
            _sheet_matrix(),
            "礼包规划",
            {"ai_client": fake_client},
        )


@pytest.mark.anyio
async def test_parse_package_sheet_with_ai_confidence_out_of_range_fails() -> None:
    fake_client = _FakeAiClient(_valid_payload(confidence=1.2))

    with pytest.raises(PackageAiParseError, match="less than or equal to 1"):
        await parse_package_sheet_with_ai(
            _sheet_matrix(),
            "礼包规划",
            {"ai_client": fake_client},
        )


@pytest.mark.anyio
async def test_parse_package_sheet_with_ai_empty_field_name_fails() -> None:
    fake_client = _FakeAiClient(
        _valid_payload(
            field_mapping={
                "package_id": "礼包id",
                "item_id": "",
                "count": "个数",
            }
        )
    )

    with pytest.raises(PackageAiParseError, match="field_mapping.item_id 必须是非空字符串"):
        await parse_package_sheet_with_ai(
            _sheet_matrix(),
            "礼包规划",
            {"ai_client": fake_client},
        )


@pytest.mark.anyio
async def test_parse_package_sheet_with_ai_rejects_fabricated_detail_rows() -> None:
    fake_client = _FakeAiClient(
        _valid_payload(
            detail_rows=[
                {
                    "row_index": 2,
                    "package_id": "fake-package",
                    "item_id": "fake-item",
                    "count": 999,
                }
            ]
        )
    )

    with pytest.raises(PackageAiParseError, match="Extra inputs are not permitted"):
        await parse_package_sheet_with_ai(
            _sheet_matrix(),
            "礼包规划",
            {"ai_client": fake_client},
        )


@pytest.mark.anyio
async def test_parse_package_sheet_with_ai_snapshot_clips_and_preserves_row_numbers() -> None:
    fake_client = _FakeAiClient(_valid_payload())
    sheet = [
        ["礼包id", "道具ID", "个数", "额外列"],
        ["", "", "", ""],
        ["26042411", "16001", "3", "x" * 20],
    ]

    await parse_package_sheet_with_ai(
        sheet,
        "礼包规划",
        {"ai_client": fake_client, "max_rows": 3, "max_columns": 3, "cell_max_chars": 5},
    )

    user_prompt = fake_client.calls[0]["user_prompt"]
    assert '"row_index": 1' in user_prompt
    assert '"row_index": 2, "empty": true' in user_prompt
    assert '"row_index": 3' in user_prompt
    assert '"included_columns": 3' in user_prompt
    assert "xxxxx..." not in user_prompt
