"""Requirement Atom driven blueprint generation tests."""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest

from backend.app.database import async_session_factory
from backend.app.models import (
    ProjectAiCredentialRecord,
    SourceEvidenceRunRecord,
    TestCaseGenerationRunRecord as GenerationRunRecord,
    TestCaseRequirementAtomRecord as RequirementAtomRecord,
)
from backend.app.security.crypto import encrypt_secret
from backend.app.test_cases.full_generation_blueprint import (
    generate_test_case_blueprint_for_run,
)


async def _seed_project_ai(project_id: int, *, api_key: str = "sk-blueprint-secret") -> None:
    async with async_session_factory() as session:
        session.add(
            ProjectAiCredentialRecord(
                project_id=project_id,
                provider_preset="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
                encrypted_api_key=encrypt_secret(api_key),
                extra_headers_json='{"X-Test":"blueprint"}',
                enabled=True,
            )
        )
        await session.commit()


async def _seed_run_with_atoms(
    project_id: int,
    atoms: list[dict[str, Any]],
    *,
    status: str = "merging_atoms",
) -> int:
    async with async_session_factory() as session:
        source_run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type="local_file",
            source_url="https://demo.invalid/blueprint.xlsx",
            source_token="source-token",
            source_identifier="blueprint-source",
            source_title="blueprint.xlsx",
            status="ready",
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
        )
        session.add(source_run)
        await session.flush()
        run = GenerationRunRecord(
            project_id=project_id,
            source_evidence_run_id=source_run.id,
            status=status,
            planning_sheet_name="需求A",
            reference_ids_json="[999]",
            strict_mode=False,
            atom_count=len(
                [
                    atom
                    for atom in atoms
                    if atom.get("coverage_status", "unmapped") != "unfounded_candidate"
                ]
            ),
            warning_count=1,
            warnings_json=json.dumps(
                [{"source": "requirement_atoms", "level": "warning", "message": "已有 atom warning"}],
                ensure_ascii=False,
            ),
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


@pytest.mark.anyio
async def test_official_atoms_generate_blueprint_and_persist_safe_trace_payload(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    run_id = await _seed_run_with_atoms(
        test_project_id,
        [
            {
                "atom_id": "ATOM-0001",
                "atom_type": "entry",
                "requirement_text": "活动入口按配置开放",
                "source_row_start": 2,
                "source_row_end": 2,
                "cell_excerpt": "活动入口 | 按配置开放入口",
                "visual_evidence_refs": ["sheet_img_2"],
            }
        ],
    )
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompts.append(kwargs["user_prompt"])
        assert kwargs["api_key"] == "sk-blueprint-secret"
        assert kwargs["extra_headers"] == {"X-Test": "blueprint"}
        assert "ATOM-0001" in kwargs["user_prompt"]
        assert "活动入口按配置开放" in kwargs["user_prompt"]
        assert "QA Case Method" in kwargs["user_prompt"]
        assert "Full source summary" in kwargs["user_prompt"]
        assert "已有 context warning" in kwargs["user_prompt"]
        assert "RAW_SHEET_FULL_TEXT" not in kwargs["user_prompt"]
        assert "reference_id=999" not in kwargs["user_prompt"]
        return {
            "modules": [{"name": "活动入口", "atom_ids": ["ATOM-0001"]}],
            "flows": [{"name": "打开活动面板", "atom_ids": ["ATOM-0001"]}],
            "requirement_traces": [
                {"atom_id": "ATOM-0001", "blueprint_node": "活动入口"}
            ],
            "coverage_dimensions": [{"name": "生命周期", "atom_ids": ["ATOM-0001"]}],
            "risks": [],
            "unmapped_requirements": [],
            "unsupported_or_unfounded_test_points": [],
            "open_questions": [],
            "warnings": ["蓝图需人工复核"],
        }, {"latency_ms": 12, "raw_response": "raw prompt sk-blueprint-secret D:/secret.txt"}

    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_blueprint.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        blueprint = await generate_test_case_blueprint_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
            source_summary="Full source summary without raw sheet text",
            context_warnings=["已有 context warning"],
        )
        await session.commit()

    run = await _load_run(run_id)
    payload = json.loads(run.stage_payload_json)
    trace = payload["blueprint"]["requirement_traces"][0]
    assert len(prompts) == 1
    assert run.status == "blueprinting"
    assert run.warning_count >= 2
    assert blueprint.requirement_traces[0]["atom_ids"] == ["ATOM-0001"]
    assert trace["atom_id"] == "ATOM-0001"
    assert trace["atom_ids"] == ["ATOM-0001"]
    assert "ATOM-0001" in trace["source_fragment"]
    assert "活动入口按配置开放" in trace["source_fragment"]
    persisted_text = json.dumps(payload, ensure_ascii=False) + run.warnings_json + run.error_summary
    for forbidden in ("raw_response", "prompt", "sk-blueprint-secret", "D:/secret"):
        assert forbidden not in persisted_text


@pytest.mark.anyio
async def test_empty_official_atom_set_fails_without_calling_provider(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    run_id = await _seed_run_with_atoms(
        test_project_id,
        [
            {
                "atom_id": "CAND-0001",
                "requirement_text": "玩家达到 10 级才能进入活动",
                "coverage_status": "unfounded_candidate",
            }
        ],
    )

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        raise AssertionError("provider must not be called without official atoms")

    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_blueprint.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        await generate_test_case_blueprint_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
            source_summary="Full source summary",
        )
        await session.commit()

    run = await _load_run(run_id)
    assert run.status == "failed"
    assert "没有可生成需求" in run.error_summary
    assert "blueprint" not in json.loads(run.stage_payload_json)


@pytest.mark.anyio
async def test_untraced_provider_nodes_move_to_unsupported_warnings(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    run_id = await _seed_run_with_atoms(
        test_project_id,
        [
            {
                "atom_id": "ATOM-0001",
                "requirement_text": "奖励每日领取一次",
                "source_row_start": 5,
                "source_row_end": 5,
            }
        ],
    )

    async def fake_call_provider_json(**_: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        return {
            "modules": [{"name": "无依据社交模块"}],
            "flows": [{"name": "无依据好友拜访"}],
            "requirement_traces": [],
            "coverage_dimensions": [],
            "risks": [{"name": "无依据性能风险"}],
            "unmapped_requirements": [],
            "unsupported_or_unfounded_test_points": [],
            "open_questions": [],
            "warnings": [],
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_blueprint.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        blueprint = await generate_test_case_blueprint_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    unsupported = json.dumps(
        blueprint.unsupported_or_unfounded_test_points,
        ensure_ascii=False,
    )
    warnings = json.dumps([warning.model_dump() for warning in blueprint.warnings], ensure_ascii=False)
    assert blueprint.modules == []
    assert blueprint.flows == []
    assert "无依据社交模块" in unsupported
    assert "无依据好友拜访" in unsupported
    assert "无依据性能风险" in unsupported
    assert "Requirement Atom trace" in warnings


@pytest.mark.anyio
async def test_unadopted_visual_refs_are_removed_from_blueprint_payload(
    test_db,
    test_project_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_project_ai(test_project_id)
    run_id = await _seed_run_with_atoms(
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
    prompts: list[str] = []

    async def fake_call_provider_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        prompts.append(kwargs["user_prompt"])
        assert "sheet_img_2" in kwargs["user_prompt"]
        assert "unadopted_img" not in kwargs["user_prompt"]
        return {
            "modules": [{"name": "活动入口 unadopted_img", "atom_ids": ["ATOM-0001"]}],
            "flows": [],
            "requirement_traces": [
                {
                    "atom_id": "ATOM-0001",
                    "blueprint_node": "活动入口 unadopted_img",
                    "source_fragment": "截图显示活动入口按钮 unadopted_img",
                }
            ],
            "coverage_dimensions": [],
            "risks": ["unadopted_img"],
            "unmapped_requirements": [],
            "unsupported_or_unfounded_test_points": [],
            "open_questions": [],
            "warnings": ["provider 引用了 unadopted_img"],
        }, {}

    monkeypatch.setattr(
        "backend.app.test_cases.full_generation_blueprint.call_provider_json",
        fake_call_provider_json,
    )

    async with async_session_factory() as session:
        await generate_test_case_blueprint_for_run(
            session,
            project_id=test_project_id,
            run_id=run_id,
        )
        await session.commit()

    run = await _load_run(run_id)
    persisted_text = run.stage_payload_json + run.warnings_json + run.error_summary
    assert len(prompts) == 1
    assert "sheet_img_2" in persisted_text
    assert "unadopted_img" not in persisted_text
