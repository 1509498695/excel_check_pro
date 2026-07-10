"""Requirement Atom driven case generation service tests."""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest
from sqlalchemy import select

from backend.app.database import async_session_factory
from backend.app.models import (
    ProjectAiCredentialRecord,
    SourceEvidenceRunRecord,
    TestCaseCoverageAuditRecord as CoverageAuditRecord,
    TestCaseGenerationCaseRecord as GenerationCaseRecord,
    TestCaseGenerationRunRecord as GenerationRunRecord,
    TestCaseReferenceFileRecord as ReferenceFileRecord,
    TestCaseRequirementAtomRecord as RequirementAtomRecord,
)
from backend.app.security.crypto import encrypt_secret
from backend.app.test_cases.constants import CANONICAL_CASE_FIELDS
from backend.app.test_cases.full_generation_cases import generate_test_cases_for_run


async def _seed_project_ai(project_id: int, *, api_key: str = "sk-cases-secret") -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectAiCredentialRecord(
                project_id=project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret(api_key),
                extra_headers_json='{"X-Test":"cases"}',
                enabled=True,
            )
        )
        await session.commit()


def _reference_profile() -> dict[str, Any]:
    return {
        "source_type": "excel",
        "source_name": "reference.xlsx",
        "default_sheet_name": "边界用例",
        "reference_case_count": 7,
        "columns": [
            {"index": 1, "original_name": "优先级", "standard_field": "priority"},
            {"index": 2, "original_name": "功能模块", "standard_field": "module"},
            {"index": 3, "original_name": "操作步骤", "standard_field": "steps"},
            {"index": 4, "original_name": "用例标题", "standard_field": "title"},
        ],
        "sheet_options": [
            {
                "name": "边界用例",
                "reference_case_count": 7,
                "is_default": True,
                "header_row_index": 1,
                "columns": [
                    {"index": 1, "original_name": "优先级", "standard_field": "priority"},
                    {"index": 2, "original_name": "功能模块", "standard_field": "module"},
                    {"index": 3, "original_name": "操作步骤", "standard_field": "steps"},
                    {"index": 4, "original_name": "用例标题", "standard_field": "title"},
                ],
            }
        ],
        "warnings": [],
    }


async def _seed_reference(project_id: int) -> int:
    async with async_session_factory() as session:
        record = ReferenceFileRecord(
            project_id=project_id,
            original_filename="reference.xlsx",
            stored_filename="reference.xlsx",
            suffix=".xlsx",
            size_bytes=100,
            storage_path="D:/references/reference.xlsx",
            profile_json=json.dumps(_reference_profile(), ensure_ascii=False),
        )
        session.add(record)
        await session.commit()
        return record.id


async def _seed_run_with_blueprint_and_atoms(
    project_id: int,
    atoms: list[dict[str, Any]],
    *,
    blueprint: dict[str, Any] | None = None,
    reference_ids: list[int] | None = None,
    primary_reference_id: int | None = None,
    primary_reference_sheet_name: str | None = None,
) -> int:
    async with async_session_factory() as session:
        source_run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type="local_file",
            source_url="https://demo.invalid/cases.xlsx",
            source_token="source-token",
            source_identifier="cases-source",
            source_title="cases.xlsx",
            status="ready",
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(source_run)
        await session.flush()
        stage_blueprint = blueprint or {
            "modules": [
                {"name": "活动入口", "atom_ids": ["ATOM-0001"]},
                {"name": "奖励领取", "atom_ids": ["ATOM-0002"]},
            ],
            "flows": [],
            "requirement_traces": [],
            "coverage_dimensions": [],
            "risks": [],
            "unmapped_requirements": [],
            "unsupported_or_unfounded_test_points": [],
            "open_questions": [],
            "warnings": [],
        }
        run = GenerationRunRecord(
            project_id=project_id,
            source_evidence_run_id=source_run.id,
            status="blueprinting",
            planning_sheet_name="需求A",
            reference_ids_json=json.dumps(reference_ids or [], ensure_ascii=False),
            primary_reference_id=primary_reference_id,
            primary_reference_sheet_name=primary_reference_sheet_name,
            atom_count=len(
                [
                    atom
                    for atom in atoms
                    if atom.get("coverage_status", "unmapped") != "unfounded_candidate"
                    and atom["atom_id"].startswith("ATOM-")
                ]
            ),
            stage_payload_json=json.dumps({"blueprint": stage_blueprint}, ensure_ascii=False),
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(run)
        await session.flush()
        for index, atom in enumerate(atoms, start=1):
            session.add(
                RequirementAtomRecord(
                    run_id=run.id,
                    project_id=project_id,
                    atom_id=atom["atom_id"],
                    atom_type=atom.get("atom_type", "rule"),
                    requirement_text=atom["requirement_text"],
                    source_sheet_name=atom.get("source_sheet_name", "需求A"),
                    source_row_start=atom.get("source_row_start", index),
                    source_row_end=atom.get("source_row_end", index),
                    source_columns_json=json.dumps(
                        atom.get("source_columns", ["模块", "规则"]),
                        ensure_ascii=False,
                    ),
                    cell_excerpt=atom.get("cell_excerpt", atom["requirement_text"]),
                    visual_evidence_refs_json=json.dumps(
                        atom.get("visual_evidence_refs", []),
                        ensure_ascii=False,
                    ),
                    confidence=atom.get("confidence", 0.9),
                    warnings_json=json.dumps(atom.get("warnings", []), ensure_ascii=False),
                    coverage_status=atom.get("coverage_status", "unmapped"),
                    merge_group_id=atom.get("merge_group_id", atom["atom_id"]),
                )
            )
        await session.commit()
        return run.id


async def _load_run(run_id: int) -> GenerationRunRecord:
    async with async_session_factory() as session:
        run = await session.get(GenerationRunRecord, run_id)
        assert run is not None
        return run


async def _load_cases(run_id: int) -> list[GenerationCaseRecord]:
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(GenerationCaseRecord)
                    .where(GenerationCaseRecord.run_id == run_id)
                    .order_by(GenerationCaseRecord.case_id)
                )
            ).scalars()
        )


async def _load_audit(run_id: int) -> CoverageAuditRecord:
    async with async_session_factory() as session:
        audit = (
            await session.execute(
                select(CoverageAuditRecord).where(CoverageAuditRecord.run_id == run_id)
            )
        ).scalar_one()
        return audit


@pytest.mark.anyio
async def test_atom_groups_generate_official_cases_and_persist_atom_refs(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    run_id = await _seed_run_with_blueprint_and_atoms(
        test_project_id,
        [
            {
                "atom_id": "ATOM-0001",
                "atom_type": "entry",
                "requirement_text": "活动入口按配置开放",
                "cell_excerpt": "活动入口 | 按配置开放入口",
                "merge_group_id": "entry:open",
            },
            {
                "atom_id": "ATOM-0002",
                "atom_type": "reward",
                "requirement_text": "奖励每日领取一次",
                "cell_excerpt": "奖励 | 每日领取一次",
                "merge_group_id": "reward:daily",
            },
        ],
    )
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompts.append(kwargs["user_prompt"])
        assert kwargs["api_key"] == "sk-cases-secret"
        assert kwargs["extra_headers"] == {"X-Test": "cases"}
        assert "Reference Test Case Library" in kwargs["user_prompt"]
        assert "不能生成新需求" in kwargs["user_prompt"]
        if "ATOM-0001" in kwargs["user_prompt"]:
            return {
                "cases": [
                    {
                        "case_id": "",
                        "module": "活动入口",
                        "feature": "入口开放",
                        "scenario": "配置开启",
                        "title": "活动入口按配置展示",
                        "preconditions": "活动配置已开启",
                        "steps": "进入主界面查看活动入口",
                        "expected_results": "入口展示",
                        "priority": "P1",
                        "case_type": "功能",
                        "source_requirement": "活动入口按配置开放",
                        "atom_ids": ["ATOM-0001"],
                    }
                ],
                "warnings": [],
            }, {"latency_ms": 10, "raw_response": "raw prompt sk-cases-secret D:/secret.txt"}
        return {
            "cases": [
                {
                    "case_id": "MODEL-ID",
                    "module": "奖励领取",
                    "feature": "每日奖励",
                    "scenario": "重复领取",
                    "title": "奖励每日仅可领取一次",
                    "preconditions": "玩家满足领取条件",
                    "steps": "领取后再次点击领取",
                    "expected_results": "重复领取被拦截",
                    "case_type": "边界",
                    "source_requirement": "奖励每日领取一次",
                    "atom_ids": ["ATOM-0002"],
                }
            ],
            "warnings": [],
        }, {"latency_ms": 11}

    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_cases.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        cases = await generate_test_cases_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    run = await _load_run(run_id)
    persisted = await _load_cases(run_id)
    audit = await _load_audit(run_id)
    assert len(prompts) == 2
    assert run.status == "generating_cases"
    assert run.case_count == 2
    assert [case.case_id for case in cases] == ["TC-0001", "MODEL-ID"]
    assert [case.case_id for case in persisted] == ["MODEL-ID", "TC-0001"]
    assert json.loads(persisted[0].atom_refs_json) == ["ATOM-0002"]
    assert json.loads(persisted[1].atom_refs_json) == ["ATOM-0001"]
    assert json.loads(persisted[1].fields_json)["priority"] == "P1"
    assert json.loads(persisted[0].fields_json)["priority"] == "P2"
    assert json.loads(persisted[0].fields_json)["initial_status"] == "未执行"
    assert audit.covered_atoms == 2
    assert audit.uncovered_atoms == 0
    persisted_text = run.stage_payload_json + run.warnings_json
    for forbidden in ("raw_response", "prompt", "sk-cases-secret", "D:/secret"):
        assert forbidden not in persisted_text


@pytest.mark.anyio
async def test_unfounded_case_is_excluded_and_written_to_coverage_audit(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    run_id = await _seed_run_with_blueprint_and_atoms(
        test_project_id,
        [{"atom_id": "ATOM-0001", "requirement_text": "活动入口按配置开放"}],
    )

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        return {
            "cases": [
                {
                    "case_id": "BAD-001",
                    "module": "社交",
                    "title": "无依据好友拜访",
                    "steps": "进入好友列表并拜访好友",
                    "expected_results": "获得好友奖励",
                    "source_requirement": "好友拜访奖励",
                }
            ],
            "warnings": [],
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_cases.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        cases = await generate_test_cases_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    run = await _load_run(run_id)
    audit = await _load_audit(run_id)
    assert cases == []
    assert await _load_cases(run_id) == []
    assert run.case_count == 0
    assert audit.unfounded_case_count == 1
    candidates = json.loads(audit.unfounded_candidates_json)
    assert candidates[0]["case_id"] == "BAD-001"
    assert "无依据好友拜访" in json.dumps(candidates, ensure_ascii=False)


@pytest.mark.anyio
async def test_source_requirement_match_backfills_atom_ids_and_arrays_are_normalized(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    run_id = await _seed_run_with_blueprint_and_atoms(
        test_project_id,
        [
            {
                "atom_id": "ATOM-0001",
                "requirement_text": "奖励每日领取一次",
                "cell_excerpt": "奖励 | 每日领取一次",
            }
        ],
    )

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        return {
            "cases": [
                {
                    "case_id": "TC-DUP",
                    "module": "奖励领取",
                    "title": "奖励每日仅可领取一次",
                    "steps": ["1. 领取奖励", "2. 再次点击领取"],
                    "expected_results": ["首次领取成功", "重复领取被拦截"],
                    "source_requirement": "每日领取一次",
                    "planning_answer": 10,
                },
                {
                    "case_id": "TC-DUP",
                    "module": "奖励领取",
                    "title": "奖励每日仅可领取一次",
                    "steps": ["1. 领取奖励", "2. 再次点击领取"],
                    "expected_results": ["首次领取成功", "重复领取被拦截"],
                    "source_requirement": "每日领取一次",
                },
            ],
            "warnings": [],
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_cases.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        cases = await generate_test_cases_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    persisted = await _load_cases(run_id)
    assert len(cases) == 1
    assert len(persisted) == 1
    assert cases[0].case_id == "TC-DUP"
    assert cases[0].steps == "1. 领取奖励\n2. 再次点击领取"
    assert cases[0].expected_results == "首次领取成功\n重复领取被拦截"
    assert cases[0].planning_answer == "10"
    assert json.loads(persisted[0].atom_refs_json) == ["ATOM-0001"]


@pytest.mark.anyio
async def test_duplicate_case_ids_are_stably_rewritten_when_cases_are_distinct(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    run_id = await _seed_run_with_blueprint_and_atoms(
        test_project_id,
        [
            {
                "atom_id": "ATOM-0001",
                "requirement_text": "活动入口按配置开放",
            }
        ],
    )

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        return {
            "cases": [
                {
                    "case_id": "DUP",
                    "module": "活动入口",
                    "title": "入口开启时展示",
                    "steps": "配置开启后进入主界面",
                    "expected_results": "入口展示",
                    "atom_ids": ["ATOM-0001"],
                },
                {
                    "case_id": "DUP",
                    "module": "活动入口",
                    "title": "入口关闭时隐藏",
                    "steps": "配置关闭后进入主界面",
                    "expected_results": "入口隐藏",
                    "atom_ids": ["ATOM-0001"],
                },
            ],
            "warnings": [],
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_cases.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        cases = await generate_test_cases_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    assert [case.case_id for case in cases] == ["DUP", "TC-0002"]


@pytest.mark.anyio
async def test_reference_profile_guides_style_without_redefining_canonical_fields(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    reference_id = await _seed_reference(test_project_id)
    run_id = await _seed_run_with_blueprint_and_atoms(
        test_project_id,
        [{"atom_id": "ATOM-0001", "requirement_text": "活动入口按配置开放"}],
        reference_ids=[reference_id],
        primary_reference_id=reference_id,
        primary_reference_sheet_name="边界用例",
    )
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompts.append(kwargs["user_prompt"])
        assert "字段顺序" in kwargs["user_prompt"]
        assert "边界用例" in kwargs["user_prompt"]
        assert "参考用例数量：7" in kwargs["user_prompt"]
        assert "D:/references" not in kwargs["user_prompt"]
        return {
            "cases": [
                {
                    "case_id": "REF-NEW",
                    "module": "历史社交模块",
                    "title": "参考案例新增需求不应进入 official",
                    "steps": "按参考案例执行好友拜访",
                    "expected_results": "获得好友奖励",
                    "source_requirement": "参考案例好友拜访",
                }
            ],
            "warnings": [],
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_cases.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        await generate_test_cases_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    run = await _load_run(run_id)
    audit = await _load_audit(run_id)
    assert await _load_cases(run_id) == []
    assert json.loads(run.stage_payload_json)["case_generation"]["export_columns"] == list(
        CANONICAL_CASE_FIELDS
    )
    assert audit.unfounded_case_count == 1


@pytest.mark.anyio
async def test_unadopted_visual_ref_in_case_output_is_removed_from_persistence(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    run_id = await _seed_run_with_blueprint_and_atoms(
        test_project_id,
        [
            {
                "atom_id": "ATOM-0001",
                "atom_type": "visual_fact",
                "requirement_text": "截图显示活动入口按钮",
                "visual_evidence_refs": ["sheet_img_2"],
            },
            {
                "atom_id": "CAND-0001",
                "requirement_text": "未采纳图片声称存在红点",
                "visual_evidence_refs": ["unadopted_img"],
                "coverage_status": "unfounded_candidate",
            },
        ],
    )

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        assert "sheet_img_2" in kwargs["user_prompt"]
        assert "unadopted_img" not in kwargs["user_prompt"]
        return {
            "cases": [
                {
                    "case_id": "VIS-001",
                    "module": "活动入口 unadopted_img",
                    "title": "截图入口展示 unadopted_img",
                    "steps": "查看 sheet_img_2 和 unadopted_img",
                    "expected_results": "入口按钮展示 unadopted_img",
                    "atom_ids": ["ATOM-0001"],
                }
            ],
            "warnings": ["provider 引用了 unadopted_img"],
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_cases.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        await generate_test_cases_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    run = await _load_run(run_id)
    persisted = await _load_cases(run_id)
    audit = await _load_audit(run_id)
    persisted_text = (
        run.stage_payload_json
        + run.warnings_json
        + json.dumps([case.fields_json for case in persisted], ensure_ascii=False)
        + audit.unfounded_candidates_json
        + audit.warnings_json
    )
    assert "sheet_img_2" in persisted_text
    assert "unadopted_img" not in persisted_text
