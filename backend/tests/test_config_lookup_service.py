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
from backend.app.config_lookup.service import lookup_config_table
from backend.app.database import async_session_factory
from backend.app.models import (
    ProjectAiCredentialRecord,
    ProjectQueryRootRecord,
    RuleConfigRecord,
    RuleConfigVersionRecord,
)
from backend.app.security.crypto import encrypt_secret


def _parsed_config(*, file_name: str = "IAPConfig.xlsx") -> dict[str, Any]:
    return {
        "rule_family": "config_lookup",
        "queries": [
            {
                "query_type": "礼包",
                "query_root": "game_datas",
                "file": file_name,
                "pages": [
                    {
                        "name": "AbsolutePack",
                        "id_field": "INT_PackageId",
                        "name_field": "DESC",
                        "output_fields": [
                            {"field": "INT_PackageId", "display_name": None},
                            {"field": "DESC", "display_name": "礼包名称"},
                            {"field": "INT_PriceId", "display_name": None},
                        ],
                    },
                    {
                        "name": "Template",
                        "id_field": "INT_PackageId",
                        "name_field": "DESC",
                        "output_fields": [
                            {"field": "INT_PackageId", "display_name": None},
                            {"field": "DESC", "display_name": "模板名称"},
                            {"field": "INT_PriceId", "display_name": None},
                        ],
                    },
                ],
                "references": [
                    {
                        "name": "price",
                        "file": "Price.xlsx",
                        "page": "Price",
                        "join": "INT_PriceId=INT_PriceId",
                        "output_fields": [
                            {"field": "INT_Point", "display_name": "价格点数"},
                        ],
                    }
                ],
            }
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
    session.add(
        RuleConfigRecord(
            project_id=project_id,
            rule_family="config_lookup",
            content_md="",
            parsed_config_json=parsed_json,
            status="published",
            draft_version=1,
            published_version=1,
            optimistic_lock_version=1,
        )
    )
    session.add(
        RuleConfigVersionRecord(
            project_id=project_id,
            rule_family="config_lookup",
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
    with pd.ExcelWriter(version_dir / "IAPConfig.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(
            [
                {
                    "INT_PackageId": 1001,
                    "DESC": "月卡",
                    "INT_PriceId": 30,
                    "STR_ServerCond_US": "US",
                },
                {
                    "INT_PackageId": 2002,
                    "DESC": "高级礼包",
                    "INT_PriceId": 99,
                    "STR_ServerCond_US": "US2",
                },
            ]
        ).to_excel(writer, sheet_name="AbsolutePack", index=False)
        pd.DataFrame(
            [
                {"INT_PackageId": 1001, "DESC": "模板月卡", "INT_PriceId": 30},
                {"INT_PackageId": 3003, "DESC": "成长礼包", "INT_PriceId": 88},
            ]
        ).to_excel(writer, sheet_name="Template", index=False)
    price_rows = [{"INT_PriceId": 30, "INT_Point": 300}]
    if include_price_99:
        price_rows.append({"INT_PriceId": 99, "INT_Point": 990})
    with pd.ExcelWriter(version_dir / "Price.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(price_rows).to_excel(writer, sheet_name="Price", index=False)


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
        ("INT_PackageId", "2002"),
        ("礼包名称", "高级礼包"),
        ("INT_PriceId", "99"),
        ("价格点数", "990"),
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
    assert ("价格点数", "") in [(field.label, field.value) for field in item.fields]
    assert item.warnings == ["引用 price 未命中：INT_PriceId=99"]


@pytest.mark.anyio
async def test_non_numeric_input_triggers_ai_high_confidence_hit(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    ai_matcher = FakeAiMatcher({"月卡": 0.95, "模板月卡": 0.4})
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, lookup_input="月卡", ai_matcher=ai_matcher)

    assert result.status == "hit"
    assert result.ai.used is True
    assert ai_matcher.calls and ai_matcher.calls[0][0] == "月卡"
    assert [item.name_value for item in result.results] == ["月卡"]


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
async def test_ai_low_confidence_returns_no_detail(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    ai_matcher = FakeAiMatcher({"月卡": 0.5})
    await _prepare_lookup_project(test_project_id, tmp_path)

    result = await _lookup(test_project_id, lookup_input="完全不像", ai_matcher=ai_matcher)

    assert result.status == "not_found"
    assert result.results == []
    assert result.candidates == []
    assert "未找到高置信候选" in result.message


@pytest.mark.anyio
async def test_ai_unavailable_degrades_with_clear_message(
    test_project_id: int,
    tmp_path: Path,
) -> None:
    await _prepare_lookup_project(test_project_id, tmp_path, seed_ai=False)

    result = await _lookup(
        test_project_id,
        lookup_input="月卡",
        ai_matcher=FakeAiMatcher({"月卡": 0.95}),
    )

    assert result.status == "ai_unavailable"
    assert result.results == []
    assert result.message == "AI 名称匹配不可用，请联系项目管理员检查项目级 AI 配置"
