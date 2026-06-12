"""规则配置试查接口测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config_lookup.schemas import ConfigLookupAiScore, ConfigLookupCandidate
from backend.app.database import async_session_factory
from backend.app.models import (
    ProjectAiCredentialRecord,
    ProjectQueryRootRecord,
    RuleConfigRecord,
    RuleConfigVersionRecord,
)
from backend.app.security.crypto import encrypt_secret


CONTENT_MD = """
查询类型: 礼包
数据根: game_datas
配置文件: IAPConfig.xlsx

  - 分页名称: AbsolutePack
  - 输出字段
    - ID字段: INT_PackageId
    - 礼包名称:DESC
    - 价格:INT_PriceId
""".strip()


def _parsed_config(
    *,
    file_name: str = "IAPConfig.xlsx",
    query_type: str = "礼包",
) -> dict[str, Any]:
    return {
        "rule_family": "config_lookup",
        "query_type": query_type,
        "query_root": "game_datas",
        "file": file_name,
        "pages": [
            {
                "name": "AbsolutePack",
                "id_field": "INT_PackageId",
                "name_field": "DESC",
                "output_fields": [
                    {"label": "ID字段", "field": "INT_PackageId"},
                    {"label": "礼包名称", "field": "DESC"},
                    {"label": "价格", "field": "INT_PriceId"},
                ],
            }
        ],
    }


class FakeAiMatcher:
    """规则试查接口测试用 AI matcher。"""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.calls: list[str] = []

    async def rank(
        self,
        *,
        lookup_input: str,
        candidates: list[ConfigLookupCandidate],
    ) -> list[ConfigLookupAiScore]:
        self.calls.append(lookup_input)
        return [
            ConfigLookupAiScore(candidate_key=candidate.key, score=0.82)
            for candidate in candidates
            if candidate.name_value in {"月卡", "高级礼包"}
        ]


def _write_workbook(root: Path) -> None:
    version_dir = root / "datas_qa88"
    version_dir.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(version_dir / "IAPConfig.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(
            [
                {"INT_PackageId": 1001, "DESC": "月卡", "INT_PriceId": 30},
                {"INT_PackageId": 2002, "DESC": "高级礼包", "INT_PriceId": 99},
            ]
        ).to_excel(writer, sheet_name="AbsolutePack", index=False)


async def _seed_query_root(project_id: int, root: Path) -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectQueryRootRecord(
                project_id=project_id,
                alias="game_datas",
                display_name="游戏配置主目录",
                svn_root_url=str(root),
                status="enabled",
            )
        )
        await session.commit()


async def _seed_published_rule(
    project_id: int,
    *,
    parsed_config: dict[str, Any] | None = None,
) -> int:
    parsed = parsed_config or _parsed_config()
    parsed_json = json.dumps(parsed, ensure_ascii=False)
    query_type = parsed["query_type"]
    async with async_session_factory() as session:
        record = RuleConfigRecord(
            project_id=project_id,
            rule_family="config_lookup",
            query_type=query_type,
            content_md=CONTENT_MD,
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
                content_md=CONTENT_MD,
                parsed_config_json=parsed_json,
                status="published",
                action="publish",
                description="发布规则",
            )
        )
        await session.commit()
        return record.id


async def _seed_draft_rule(project_id: int, *, query_type: str = "旧礼包") -> int:
    parsed = _parsed_config(query_type=query_type)
    parsed_json = json.dumps(parsed, ensure_ascii=False)
    async with async_session_factory() as session:
        record = RuleConfigRecord(
            project_id=project_id,
            rule_family="config_lookup",
            query_type=query_type,
            content_md=CONTENT_MD.replace("查询类型: 礼包", f"查询类型: {query_type}"),
            parsed_config_json=parsed_json,
            status="draft",
            draft_version=1,
            published_version=None,
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
                content_md=record.content_md,
                parsed_config_json=parsed_json,
                status="draft",
                action="save_draft",
                description="创建草稿",
            )
        )
        await session.commit()
        return record.id


async def _seed_project_ai(project_id: int) -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectAiCredentialRecord(
                project_id=project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret("sk-project-secret"),
                extra_headers_json="{}",
                enabled=True,
                auto_match_threshold=0.9,
                candidate_threshold=0.6,
                max_candidates=5,
            )
        )
        await session.commit()


async def _history_count(session: AsyncSession, rule_id: int) -> int:
    result = await session.execute(
        select(func.count(RuleConfigVersionRecord.id)).where(
            RuleConfigVersionRecord.rule_config_id == rule_id,
        )
    )
    return int(result.scalar_one())


def _trial_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "query_type": "礼包",
        "versioned_config_folder": "/datas_qa88",
        "lookup_input": "1001",
        "use_current_draft": False,
    }
    payload.update(overrides)
    return payload


@pytest.mark.anyio
async def test_trial_with_published_version_returns_hit(
    auth_client: AsyncClient,
    test_project_id: int,
    tmp_path: Path,
) -> None:
    root = tmp_path / "game_datas"
    _write_workbook(root)
    await _seed_query_root(test_project_id, root)
    rule_id = await _seed_published_rule(test_project_id)

    response = await auth_client.post(
        f"/api/v1/rule-configs/config_lookup/{rule_id}/trial",
        json=_trial_payload(),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "hit"
    assert data["results"][0]["id_value"] == "1001"
    assert data["results"][0]["fields"][1] == {
        "field": "DESC",
        "label": "礼包名称",
        "value": "月卡",
    }


@pytest.mark.anyio
async def test_trial_with_current_draft_does_not_create_versions(
    auth_client: AsyncClient,
    test_project_id: int,
    tmp_path: Path,
) -> None:
    root = tmp_path / "game_datas"
    _write_workbook(root)
    await _seed_query_root(test_project_id, root)
    rule_id = await _seed_published_rule(test_project_id)

    async with async_session_factory() as session:
        before_count = await _history_count(session, rule_id)

    response = await auth_client.post(
        f"/api/v1/rule-configs/config_lookup/{rule_id}/trial",
        json=_trial_payload(use_current_draft=True, content_md=CONTENT_MD),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "hit"
    assert data["validation"]["ok"] is True
    async with async_session_factory() as session:
        after_count = await _history_count(session, rule_id)
        current = (
            await session.execute(
                select(RuleConfigRecord).where(RuleConfigRecord.id == rule_id)
            )
        ).scalar_one()
    assert after_count == before_count
    assert current.draft_version == 1
    assert current.published_version == 1


@pytest.mark.anyio
async def test_trial_with_current_draft_uses_parsed_query_type(
    auth_client: AsyncClient,
    test_project_id: int,
    tmp_path: Path,
) -> None:
    root = tmp_path / "game_datas"
    _write_workbook(root)
    await _seed_query_root(test_project_id, root)
    rule_id = await _seed_draft_rule(test_project_id, query_type="旧礼包")

    response = await auth_client.post(
        f"/api/v1/rule-configs/config_lookup/{rule_id}/trial",
        json=_trial_payload(
            query_type="礼包",
            use_current_draft=True,
            content_md=CONTENT_MD,
        ),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "hit"
    assert data["results"][0]["query_type"] == "礼包"
    async with async_session_factory() as session:
        current = (
            await session.execute(
                select(RuleConfigRecord).where(RuleConfigRecord.id == rule_id)
            )
        ).scalar_one()
        history_count = await _history_count(session, rule_id)
    assert current.query_type == "旧礼包"
    assert current.draft_version == 1
    assert current.published_version is None
    assert history_count == 1


@pytest.mark.anyio
async def test_trial_with_invalid_current_draft_returns_validation_errors(
    auth_client: AsyncClient,
    test_project_id: int,
    tmp_path: Path,
) -> None:
    root = tmp_path / "game_datas"
    _write_workbook(root)
    await _seed_query_root(test_project_id, root)
    rule_id = await _seed_published_rule(test_project_id)

    response = await auth_client.post(
        f"/api/v1/rule-configs/config_lookup/{rule_id}/trial",
        json=_trial_payload(use_current_draft=True, content_md=CONTENT_MD.replace("数据根: game_datas\n", "")),
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "RULE_CONFIG_VALIDATION_FAILED"
    assert "缺少必填字段：数据根" in detail["errors"]


@pytest.mark.anyio
async def test_trial_name_query_returns_ai_candidates(
    auth_client: AsyncClient,
    test_project_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "game_datas"
    _write_workbook(root)
    await _seed_query_root(test_project_id, root)
    rule_id = await _seed_published_rule(test_project_id)
    await _seed_project_ai(test_project_id)
    monkeypatch.setattr("backend.app.config_lookup.service.ProjectAiMatcher", FakeAiMatcher)

    response = await auth_client.post(
        f"/api/v1/rule-configs/config_lookup/{rule_id}/trial",
        json=_trial_payload(lookup_input="礼包"),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "candidates"
    assert [item["name_value"] for item in data["candidates"]] == ["月卡", "高级礼包"]


@pytest.mark.anyio
async def test_trial_version_folder_missing_returns_message(
    auth_client: AsyncClient,
    test_project_id: int,
    tmp_path: Path,
) -> None:
    root = tmp_path / "game_datas"
    _write_workbook(root)
    await _seed_query_root(test_project_id, root)
    rule_id = await _seed_published_rule(test_project_id)

    response = await auth_client.post(
        f"/api/v1/rule-configs/config_lookup/{rule_id}/trial",
        json=_trial_payload(versioned_config_folder="/datas_missing"),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "not_found"
    assert data["message"] == "未找到版本配置目录：/datas_missing，请确认目录是否存在于数据根 game_datas 下"


@pytest.mark.anyio
async def test_trial_config_file_missing_returns_message(
    auth_client: AsyncClient,
    test_project_id: int,
    tmp_path: Path,
) -> None:
    root = tmp_path / "game_datas"
    _write_workbook(root)
    await _seed_query_root(test_project_id, root)
    rule_id = await _seed_published_rule(
        test_project_id,
        parsed_config=_parsed_config(file_name="Missing.xlsx"),
    )

    response = await auth_client.post(
        f"/api/v1/rule-configs/config_lookup/{rule_id}/trial",
        json=_trial_payload(),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "not_found"
    assert data["message"] == "未找到配置文件：Missing.xlsx，请确认 /datas_qa88 下是否存在该文件"


@pytest.mark.anyio
async def test_trial_ai_unavailable_returns_degraded_message(
    auth_client: AsyncClient,
    test_project_id: int,
    tmp_path: Path,
) -> None:
    root = tmp_path / "game_datas"
    _write_workbook(root)
    await _seed_query_root(test_project_id, root)
    rule_id = await _seed_published_rule(test_project_id)

    response = await auth_client.post(
        f"/api/v1/rule-configs/config_lookup/{rule_id}/trial",
        json=_trial_payload(lookup_input="月卡礼包"),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "ai_unavailable"
    assert data["message"] == "AI 名称匹配不可用，请联系项目管理员检查项目级 AI 配置"
