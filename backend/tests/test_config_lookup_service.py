"""配置表查询核心服务测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config_lookup.schemas import (
    ConfigLookupAiScore,
    ConfigLookupCandidate,
    ConfigLookupRequest,
)
from backend.app.config_lookup.ai_matcher import ProjectAiMatcher
from backend.app.config_lookup.service import lookup_config_table
from backend.app.database import async_session_factory
from backend.app.models import (
    ProjectAiCredentialRecord,
    ProjectQueryRootRecord,
    RuleConfigRecord,
    RuleConfigVersionRecord,
)
from backend.app.security.crypto import encrypt_secret


@pytest.mark.anyio
async def test_project_ai_matcher_prompt_mentions_json_for_json_object_provider(
    test_db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DeepSeek 等兼容接口使用 json_object 时要求 prompt 明确出现 JSON。"""
    captured: dict[str, Any] = {}

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        captured.update(kwargs)
        return {"matches": [{"key": "candidate-1", "score": 0.91}]}, {}

    monkeypatch.setattr(
        "backend.app.config_lookup.ai_matcher.call_provider_json",
        fake_call_provider_json,
    )
    async with async_session_factory() as session:
        session.add(
            ProjectAiCredentialRecord(
                project_id=1,
                provider_preset="deepseek",
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
                encrypted_api_key=encrypt_secret("sk-test"),
                enabled=True,
            )
        )
        await session.commit()

        scores = await ProjectAiMatcher(session, project_id=1).rank(
            lookup_input="月卡",
            candidates=[
                ConfigLookupCandidate(
                    key="candidate-1",
                    page="Template",
                    id_value="1001",
                    name_value="月卡",
                )
            ],
        )

    assert scores[0].candidate_key == "candidate-1"
    assert "json" in captured["system_prompt"].lower()


def _parsed_config(*, file_name: str = "IAPConfig.xlsx") -> dict[str, Any]:
    return {
        "rule_family": "config_lookup",
        "query_type": "礼包",
        "query_root": "game_datas",
        "file": file_name,
        "pages": [
            {
                "name": "AbsolutePack",
                "id_match_field": "INT_PackageId",
                "text_match_fields": [{"label": "礼包名称", "field": "DESC"}],
                "candidate_label_field": "DESC",
                "output_fields": [
                    {"label": "礼包ID", "field": "INT_PackageId"},
                    {"label": "礼包名称", "field": "DESC"},
                    {"label": "国际服开启", "field": "STR_ServerCond_US"},
                    {
                        "label": "绿色服开关",
                        "field": "STR_ABSwitch",
                        "value_map": {"0": "绿色服关闭", "1": "绿色服开启"},
                    },
                    {
                        "label": "价格",
                        "field": "INT_PriceId",
                        "reference": {
                            "page": "Price",
                            "join": "AbsolutePack.INT_PriceId=Price.INT_PriceId",
                            "display_expression": "Price.INT_Point/100",
                        },
                    },
                ],
            },
            {
                "name": "Template",
                "id_match_field": "INT_PackageId",
                "text_match_fields": [{"label": "礼包名称", "field": "DESC"}],
                "candidate_label_field": "DESC",
                "output_fields": [
                    {"label": "礼包ID", "field": "INT_PackageId"},
                    {"label": "模板名称", "field": "DESC"},
                    {
                        "label": "价格",
                        "field": "INT_PriceId",
                        "reference": {
                            "page": "Price",
                            "join": "Template.INT_PriceId=Price.INT_PriceId",
                            "display_expression": "Price.INT_Point/100",
                        },
                    },
                ],
            },
        ],
    }


class FakeAiMatcher:
    """按候选名称返回测试指定分数，并记录是否被调用。"""

    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores
        self.calls: list[tuple[str, list[str]]] = []

    async def rank(
        self,
        *,
        lookup_input: str,
        candidates: list[ConfigLookupCandidate],
    ) -> list[ConfigLookupAiScore]:
        self.calls.append((lookup_input, [candidate.name_value for candidate in candidates]))
        return [
            ConfigLookupAiScore(candidate_key=candidate.key, score=self.scores[candidate.name_value])
            for candidate in candidates
            if candidate.name_value in self.scores
        ]


async def _seed_published_rule(
    session: AsyncSession,
    project_id: int,
    parsed_config: dict[str, Any] | None = None,
) -> None:
    parsed = parsed_config or _parsed_config()
    parsed_json = json.dumps(parsed, ensure_ascii=False)
    query_type = parsed["query_type"]
    record = RuleConfigRecord(
        project_id=project_id,
        rule_family="config_lookup",
        query_type=query_type,
        content_md="",
        parsed_config_json=parsed_json,
        status="published",
        draft_version=1,
        published_version=1,
        optimistic_lock_version=1,
    )
    session.add(record)
    await session.flush()
    session.add(
        RuleConfigVersionRecord(
            rule_config_id=record.id,
            project_id=project_id,
            rule_family="config_lookup",
            query_type=query_type,
            version=1,
            content_md="",
            parsed_config_json=parsed_json,
            status="published",
            action="publish",
            description="published",
        )
    )


async def _seed_query_root(
    session: AsyncSession,
    project_id: int,
    root: Path,
) -> None:
    session.add(
        ProjectQueryRootRecord(
            project_id=project_id,
            alias="game_datas",
            display_name="游戏配置主目录",
            svn_root_url=str(root),
            status="enabled",
        )
    )


async def _seed_project_ai(
    session: AsyncSession,
    project_id: int,
    *,
    enabled: bool = True,
) -> None:
    session.add(
        ProjectAiCredentialRecord(
            project_id=project_id,
            provider_preset="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            encrypted_api_key=encrypt_secret("sk-project-secret"),
            extra_headers_json="{}",
            enabled=enabled,
            auto_match_threshold=0.9,
            candidate_threshold=0.6,
            max_candidates=2,
        )
    )


def _write_lookup_workbooks(version_dir: Path, *, include_price_99: bool = True) -> None:
    version_dir.mkdir(parents=True, exist_ok=True)
    price_rows = [{"INT_PriceId": 30, "INT_Point": 300}]
    if include_price_99:
        price_rows.append({"INT_PriceId": 99, "INT_Point": 990})
    with pd.ExcelWriter(version_dir / "IAPConfig.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(
            [
                {
                    "INT_PackageId": 1001,
                    "DESC": "月卡",
                    "STR_Func": "MoonCard",
                    "INT_PriceId": 30,
                    "STR_ServerCond_US": "US",
                    "STR_ABSwitch": "state:1",
                    "INT_RevealAt": 1781204402,
                },
                {
                    "INT_PackageId": 2002,
                    "DESC": "高级礼包",
                    "STR_Func": "PremiumGift",
                    "INT_PriceId": 99,
                    "STR_ServerCond_US": "US2",
                    "STR_ABSwitch": 0,
                    "INT_RevealAt": 1781251200,
                },
                {
                    "INT_PackageId": 4004,
                    "DESC": "空配置礼包",
                    "STR_Func": "",
                    "INT_PriceId": 30,
                    "STR_ServerCond_US": "",
                    "STR_ABSwitch": "",
                    "INT_RevealAt": 0,
                },
                {
                    "INT_PackageId": 5005,
                    "DESC": "未知开关礼包",
                    "STR_Func": "UnknownSwitch",
                    "INT_PriceId": 30,
                    "STR_ServerCond_US": "US5",
                    "STR_ABSwitch": "unknown:9",
                    "INT_RevealAt": "invalid",
                },
            ]
        ).to_excel(writer, sheet_name="AbsolutePack", index=False)
        pd.DataFrame(
            [
                {
                    "INT_PackageId": 1001,
                    "DESC": "模板月卡",
                    "STR_Func": "TemplateMoonCard",
                    "INT_PriceId": 30,
                },
                {
                    "INT_PackageId": 3003,
                    "DESC": "成长礼包",
                    "STR_Func": "GrowthGift",
                    "INT_PriceId": 88,
                },
            ]
        ).to_excel(writer, sheet_name="Template", index=False)
        pd.DataFrame(price_rows).to_excel(writer, sheet_name="Price", index=False)


def _write_many_candidate_workbooks(version_dir: Path) -> None:
    version_dir.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(version_dir / "IAPConfig.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(
            [
                {
                    "INT_PackageId": 6001,
                    "DESC": "候选礼包-1",
                    "INT_PriceId": 30,
                    "STR_ServerCond_US": "US1",
                    "STR_ABSwitch": 1,
                },
                {
                    "INT_PackageId": 6002,
                    "DESC": "候选礼包-2",
                    "INT_PriceId": 30,
                    "STR_ServerCond_US": "US2",
                    "STR_ABSwitch": 1,
                },
                {
                    "INT_PackageId": 6002,
                    "DESC": "候选礼包-2",
                    "INT_PriceId": 30,
                    "STR_ServerCond_US": "US2 duplicate",
                    "STR_ABSwitch": 1,
                },
                {
                    "INT_PackageId": 6003,
                    "DESC": "候选礼包-3",
                    "INT_PriceId": 30,
                    "STR_ServerCond_US": "US3",
                    "STR_ABSwitch": 1,
                },
                {
                    "INT_PackageId": 6004,
                    "DESC": "候选礼包-4",
                    "INT_PriceId": 30,
                    "STR_ServerCond_US": "US4",
                    "STR_ABSwitch": 1,
                },
            ]
        ).to_excel(writer, sheet_name="AbsolutePack", index=False)
        pd.DataFrame(
            [
                {"INT_PackageId": 7001, "DESC": "候选礼包-5", "INT_PriceId": 30},
                {"INT_PackageId": 7002, "DESC": "候选礼包-6", "INT_PriceId": 30},
            ]
        ).to_excel(writer, sheet_name="Template", index=False)
        pd.DataFrame([{"INT_PriceId": 30, "INT_Point": 300}]).to_excel(
            writer,
            sheet_name="Price",
            index=False,
        )


async def _prepare_lookup_project(
    test_project_id: int,
    tmp_path: Path,
    *,
    publish: bool = True,
    include_price_99: bool = True,
    parsed_config: dict[str, Any] | None = None,
    seed_ai: bool = True,
) -> Path:
    root = tmp_path / "game_datas"
    _write_lookup_workbooks(root / "datas_qa88", include_price_99=include_price_99)
    async with async_session_factory() as session:
        await _seed_query_root(session, test_project_id, root)
        if publish:
            await _seed_published_rule(session, test_project_id, parsed_config)
        if seed_ai:
            await _seed_project_ai(session, test_project_id)
        await session.commit()
    return root


async def _lookup(
    test_project_id: int,
    *,
    lookup_input: str = "1001",
    versioned_config_folder: str = "/datas_qa88",
    query_type: str = "礼包",
    ai_matcher: FakeAiMatcher | None = None,
):
    async with async_session_factory() as session:
        return await lookup_config_table(
            session,
            ConfigLookupRequest(
                project_id=test_project_id,
                query_type=query_type,
                versioned_config_folder=versioned_config_folder,
                lookup_input=lookup_input,
            ),
            ai_matcher=ai_matcher,
        )


@pytest.mark.anyio
async def test_unpublished_rule_returns_clear_message(test_project_id: int) -> None:
    result = await _lookup(test_project_id)

    assert result.status == "not_found"
    assert result.message == "当前项目尚未发布配置表查询规则，请先在规则配置页发布"


@pytest.mark.anyio
async def test_unknown_query_type_returns_clear_message(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, query_type="活动")

    assert result.status == "not_found"
    assert result.message == "查询类型不存在：活动"


@pytest.mark.anyio
@pytest.mark.parametrize("bad_folder", ["https://svn/x", "C:/datas_qa88", "../datas_qa88"])
async def test_rejects_illegal_versioned_config_folder(
    test_project_id: int,
    tmp_path: Path,
    bad_folder: str,
) -> None:
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, versioned_config_folder=bad_folder)

    assert result.status == "not_found"
    assert "版本配置目录不合法" in result.message


@pytest.mark.anyio
async def test_missing_version_folder_returns_required_message(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, versioned_config_folder="/datas_missing")

    assert result.status == "not_found"
    assert result.message == "未找到版本配置目录：/datas_missing，请确认目录是否存在于数据根 game_datas 下"


@pytest.mark.anyio
async def test_missing_config_file_returns_required_message(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    await _prepare_lookup_project(
        test_project_id,
        tmp_path,
        parsed_config=_parsed_config(file_name="Missing.xls"),
    )

    result = await _lookup(test_project_id)

    assert result.status == "not_found"
    assert result.message == "未找到配置文件：Missing.xls，请确认 /datas_qa88 下是否存在该文件"


@pytest.mark.anyio
async def test_single_page_id_hit_returns_ordered_fields_and_display_name(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, lookup_input="2002")

    assert result.status == "hit"
    assert len(result.results) == 1
    item = result.results[0]
    assert item.page == "AbsolutePack"
    assert item.id_value == "2002"
    assert [(field.label, field.value) for field in item.fields] == [
        ("礼包ID", "2002"),
        ("礼包名称", "高级礼包"),
        ("国际服开启", "US2"),
        ("绿色服开关", "绿色服关闭"),
        ("价格", "9.9"),
    ]


@pytest.mark.anyio
async def test_enum_mapping_matches_colon_tail_value(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, lookup_input="1001")

    assert result.status == "hit"
    item = next(row for row in result.results if row.page == "AbsolutePack")
    assert ("绿色服开关", "绿色服开启") in [
        (field.label, field.value) for field in item.fields
    ]


@pytest.mark.anyio
async def test_enum_mapping_empty_value_outputs_unconfigured(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, lookup_input="4004")

    assert result.status == "hit"
    assert ("国际服开启", "未配置") in [
        (field.label, field.value) for field in result.results[0].fields
    ]
    assert ("绿色服开关", "未配置") in [
        (field.label, field.value) for field in result.results[0].fields
    ]


@pytest.mark.anyio
async def test_enum_mapping_unmatched_value_outputs_raw_value(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, lookup_input="5005")

    assert result.status == "hit"
    assert ("绿色服开关", "unknown:9") in [
        (field.label, field.value) for field in result.results[0].fields
    ]


@pytest.mark.anyio
async def test_timestamp_seconds_formatter_outputs_beijing_time(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    parsed_config = _parsed_config()
    parsed_config["pages"][0]["output_fields"].append(
        {
            "label": "公布时间",
            "field": "INT_RevealAt",
            "formatter": {"type": "timestamp_seconds", "timezone": "Asia/Shanghai"},
        }
    )
    await _prepare_lookup_project(test_project_id, tmp_path, parsed_config=parsed_config)

    result = await _lookup(test_project_id, lookup_input="1001")

    assert result.status == "hit"
    item = next(row for row in result.results if row.page == "AbsolutePack")
    assert ("公布时间", "2026/06/12 03:00:02") in [
        (field.label, field.value) for field in item.fields
    ]


@pytest.mark.anyio
async def test_timestamp_seconds_formatter_treats_zero_as_unconfigured(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    parsed_config = _parsed_config()
    parsed_config["pages"][0]["output_fields"].append(
        {
            "label": "公布时间",
            "field": "INT_RevealAt",
            "formatter": {"type": "timestamp_seconds", "timezone": "Asia/Shanghai"},
        }
    )
    await _prepare_lookup_project(test_project_id, tmp_path, parsed_config=parsed_config)

    result = await _lookup(test_project_id, lookup_input="4004")

    assert result.status == "hit"
    assert ("公布时间", "未配置") in [
        (field.label, field.value) for field in result.results[0].fields
    ]


@pytest.mark.anyio
async def test_multi_page_id_hit_returns_all_results_without_merging(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    ai_matcher = FakeAiMatcher({"月卡": 0.99})
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, lookup_input="1001", ai_matcher=ai_matcher)

    assert result.status == "hit"
    assert [item.page for item in result.results] == ["AbsolutePack", "Template"]
    assert [item.name_value for item in result.results] == ["月卡", "模板月卡"]
    assert ai_matcher.calls == []


@pytest.mark.anyio
async def test_reference_join_miss_keeps_main_result_with_warning(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    await _prepare_lookup_project(test_project_id, tmp_path, include_price_99=False)

    result = await _lookup(test_project_id, lookup_input="2002")

    assert result.status == "hit"
    item = result.results[0]
    assert ("价格", "99(引用未找到)") in [(field.label, field.value) for field in item.fields]
    assert item.warnings == ["引用未找到：AbsolutePack.INT_PriceId=99"]


@pytest.mark.anyio
async def test_missing_configured_field_returns_clear_message(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    parsed_config = _parsed_config()
    parsed_config["pages"][0]["output_fields"].append(
        {"label": "不存在字段", "field": "MISSING_FIELD"}
    )
    await _prepare_lookup_project(test_project_id, tmp_path, parsed_config=parsed_config)

    result = await _lookup(test_project_id, lookup_input="1001")

    assert result.status == "not_found"
    assert result.message == "配置字段不存在：MISSING_FIELD"


@pytest.mark.anyio
async def test_non_numeric_input_triggers_ai_high_confidence_hit(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    ai_matcher = FakeAiMatcher({"月卡": 0.95, "模板月卡": 0.4})
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, lookup_input="月卡礼包", ai_matcher=ai_matcher)

    assert result.status == "hit"
    assert result.ai.used is True
    assert ai_matcher.calls and ai_matcher.calls[0][0] == "月卡礼包"
    assert [item.name_value for item in result.results] == ["月卡"]


@pytest.mark.anyio
async def test_exact_name_hit_returns_detail_without_ai(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    ai_matcher = FakeAiMatcher({})
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, lookup_input="高级礼包", ai_matcher=ai_matcher)

    assert result.status == "hit"
    assert result.message == "查询命中"
    assert result.ai.used is False
    assert len(result.results) == 1
    assert result.results[0].id_value == "2002"
    assert result.results[0].name_value == "高级礼包"
    assert ai_matcher.calls == []


@pytest.mark.anyio
async def test_exact_secondary_text_match_field_returns_detail_with_primary_display_name(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    parsed_config = _parsed_config()
    parsed_config["pages"][0]["text_match_fields"].append(
        {"label": "开关字段", "field": "STR_Func"}
    )
    await _prepare_lookup_project(test_project_id, tmp_path, parsed_config=parsed_config)
    ai_matcher = FakeAiMatcher({})

    result = await _lookup(test_project_id, lookup_input="PremiumGift", ai_matcher=ai_matcher)

    assert result.status == "hit"
    assert result.ai.used is False
    assert len(result.results) == 1
    assert result.results[0].id_value == "2002"
    assert result.results[0].name_value == "高级礼包"
    assert ai_matcher.calls == []


@pytest.mark.anyio
async def test_partial_secondary_text_match_field_returns_candidate_with_primary_display_name(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    parsed_config = _parsed_config()
    parsed_config["pages"][0]["text_match_fields"].append(
        {"label": "开关字段", "field": "STR_Func"}
    )
    await _prepare_lookup_project(test_project_id, tmp_path, parsed_config=parsed_config)
    ai_matcher = FakeAiMatcher({})

    result = await _lookup(test_project_id, lookup_input="Premium", ai_matcher=ai_matcher)

    assert result.status == "candidates"
    assert [(candidate.id_value, candidate.name_value) for candidate in result.candidates] == [
        ("2002", "高级礼包"),
    ]
    assert ai_matcher.calls == []


@pytest.mark.anyio
async def test_partial_name_match_returns_deduplicated_id_name_candidates_without_ai(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    ai_matcher = FakeAiMatcher({})
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, lookup_input="未知开关", ai_matcher=ai_matcher)

    assert result.status == "candidates"
    assert result.message == "找到 1 个候选，请使用 ID 精确查询。"
    assert result.results == []
    assert [(candidate.id_value, candidate.name_value) for candidate in result.candidates] == [
        ("5005", "未知开关礼包"),
    ]
    assert ai_matcher.calls == []


@pytest.mark.anyio
async def test_partial_name_candidates_keep_last_max_after_dedupe_in_excel_order(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    root = tmp_path / "game_datas"
    _write_many_candidate_workbooks(root / "datas_qa88")
    async with async_session_factory() as session:
        await _seed_query_root(session, test_project_id, root)
        await _seed_published_rule(session, test_project_id)
        await _seed_project_ai(session, test_project_id)
        await session.commit()

    result = await _lookup(
        test_project_id,
        lookup_input="候选礼包",
        ai_matcher=FakeAiMatcher({}),
    )

    assert result.status == "candidates"
    assert result.message == (
        "找到 6 个候选，仅展示最后 2 个，请补充更具体的名称、价格、月份或直接使用 ID 查询。"
    )
    assert [(candidate.id_value, candidate.name_value) for candidate in result.candidates] == [
        ("7001", "候选礼包-5"),
        ("7002", "候选礼包-6"),
    ]


@pytest.mark.anyio
async def test_numeric_miss_triggers_ai(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    ai_matcher = FakeAiMatcher({"成长礼包": 0.95})
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, lookup_input="9999", ai_matcher=ai_matcher)

    assert result.status == "hit"
    assert result.results[0].name_value == "成长礼包"
    assert ai_matcher.calls and ai_matcher.calls[0][0] == "9999"


@pytest.mark.anyio
async def test_ai_multiple_candidates_returns_candidate_list(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    ai_matcher = FakeAiMatcher({"月卡": 0.92, "模板月卡": 0.88, "高级礼包": 0.7})
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, lookup_input="卡", ai_matcher=ai_matcher)

    assert result.status == "candidates"
    assert result.results == []
    assert [(candidate.name_value, candidate.score) for candidate in result.candidates] == [
        ("月卡", 0.92),
        ("模板月卡", 0.88),
    ]


@pytest.mark.anyio
async def test_ai_low_confidence_returns_deduplicated_suggestions(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    ai_matcher = FakeAiMatcher({"月卡": 0.5, "模板月卡": 0.4})
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, lookup_input="完全不像", ai_matcher=ai_matcher)

    assert result.status == "candidates"
    assert result.results == []
    assert result.message == "找到 2 个候选，请使用 ID 精确查询。"
    assert [(candidate.id_value, candidate.name_value) for candidate in result.candidates] == [
        ("1001", "月卡"),
        ("1001", "模板月卡"),
    ]


@pytest.mark.anyio
async def test_ai_low_confidence_candidates_keep_last_max_after_dedupe_in_excel_order(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    root = tmp_path / "game_datas"
    _write_many_candidate_workbooks(root / "datas_qa88")
    async with async_session_factory() as session:
        await _seed_query_root(session, test_project_id, root)
        await _seed_published_rule(session, test_project_id)
        await _seed_project_ai(session, test_project_id)
        await session.commit()
    ai_matcher = FakeAiMatcher(
        {
            "候选礼包-1": 0.5,
            "候选礼包-2": 0.5,
            "候选礼包-3": 0.5,
            "候选礼包-4": 0.5,
            "候选礼包-5": 0.5,
            "候选礼包-6": 0.5,
        }
    )

    result = await _lookup(
        test_project_id,
        lookup_input="完全不像",
        ai_matcher=ai_matcher,
    )

    assert result.status == "candidates"
    assert result.message == (
        "找到 6 个候选，仅展示最后 2 个，请补充更具体的名称、价格、月份或直接使用 ID 查询。"
    )
    assert [(candidate.id_value, candidate.name_value) for candidate in result.candidates] == [
        ("7001", "候选礼包-5"),
        ("7002", "候选礼包-6"),
    ]


@pytest.mark.anyio
async def test_ai_candidates_are_deduplicated_by_id_and_name(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    ai_matcher = FakeAiMatcher({"月卡": 0.92, "模板月卡": 0.88})
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, lookup_input="卡", ai_matcher=ai_matcher)

    assert result.status == "candidates"
    assert [(candidate.id_value, candidate.name_value) for candidate in result.candidates] == [
        ("1001", "月卡"),
        ("1001", "模板月卡"),
    ]


@pytest.mark.anyio
async def test_ai_unavailable_degrades_with_clear_message(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    await _prepare_lookup_project(test_project_id, tmp_path, seed_ai=False)

    result = await _lookup(
        test_project_id,
        lookup_input="月卡礼包",
        ai_matcher=FakeAiMatcher({"月卡": 0.95}),
    )

    assert result.status == "ai_unavailable"
    assert result.results == []
    assert result.message == "AI 名称匹配不可用，请联系项目管理员检查项目级 AI 配置"
