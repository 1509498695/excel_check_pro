"""Full Planning Sheet Context builder tests."""

from __future__ import annotations

import datetime
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from backend.app.database import async_session_factory
from backend.app.models import (
    SourceEvidenceResourceRecord,
    SourceEvidenceRunRecord,
    SourceEvidenceVisualObservationRecord,
)
from backend.app.test_cases import source_evidence_storage
from backend.app.test_cases.full_generation_context import (
    build_full_planning_sheet_context,
)


@pytest.fixture(autouse=True)
def _source_evidence_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        source_evidence_storage,
        "settings",
        SimpleNamespace(source_evidence_dir=tmp_path / "source-evidence"),
    )


async def _seed_source_evidence_run(
    project_id: int,
    *,
    parsed_source: dict[str, Any],
    source_type: str = "local_file",
    source_title: str = "full-context.xlsx",
    resources: list[dict[str, Any]] | None = None,
    manifest: dict[str, Any] | None = None,
) -> int:
    async with async_session_factory() as session:
        run = SourceEvidenceRunRecord(
            project_id=project_id,
            source_type=source_type,
            source_url="https://demo.invalid/source",
            source_token="source-token-must-not-leak",
            source_identifier="sha256:full-context",
            source_title=source_title,
            status="ready",
            expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1),
            raw_manifest_json=json.dumps(
                manifest
                or {
                    "warnings": [],
                    "local_path": "D:/secret/source-evidence/raw/source.xlsx",
                    "provider_response": "provider raw must not leak",
                },
                ensure_ascii=False,
            ),
        )
        session.add(run)
        await session.flush()
        source_evidence_storage.ensure_source_evidence_subdirs(
            project_id=project_id,
            run_id=run.id,
        )
        for resource in resources or []:
            session.add(
                SourceEvidenceResourceRecord(
                    run_id=run.id,
                    project_id=project_id,
                    ref=resource["ref"],
                    resource_type=resource.get("type", "image"),
                    position=resource.get("position", ""),
                    filename=resource.get("filename", ""),
                    file_token=resource.get("file_token", "file-token-must-not-leak"),
                    status=resource.get("status", "unobserved"),
                    download_status=resource.get("download_status", "downloaded"),
                    local_path=resource.get("local_path", "D:/secret/source-evidence/ui.png"),
                    mime_type=resource.get("mime_type", "image/png"),
                    metadata_json=json.dumps(
                        resource.get(
                            "metadata",
                            {"provider_response": "provider raw must not leak"},
                        ),
                        ensure_ascii=False,
                    ),
                )
            )
        source_evidence_storage.write_source_evidence_json(
            project_id,
            run.id,
            "raw/parsed_source.json",
            parsed_source,
        )
        await session.commit()
        return run.id


async def _seed_visual_observation(
    project_id: int,
    run_id: int,
    *,
    ref: str,
    summary: str,
    status: str = "adopted",
) -> int:
    async with async_session_factory() as session:
        resource = (
            await session.execute(
                select(SourceEvidenceResourceRecord).where(
                    SourceEvidenceResourceRecord.project_id == project_id,
                    SourceEvidenceResourceRecord.run_id == run_id,
                    SourceEvidenceResourceRecord.ref == ref,
                )
            )
        ).scalar_one()
        observation = SourceEvidenceVisualObservationRecord(
            run_id=run_id,
            project_id=project_id,
            resource_id=resource.id,
            ref=resource.ref,
            position=resource.position,
            filename=resource.filename,
            status=status,
            adopted_at=(
                datetime.datetime.now(datetime.UTC) if status == "adopted" else None
            ),
        )
        session.add(observation)
        await session.flush()
        observation_path = f"visual_evidence/observations/{observation.id}.json"
        source_evidence_storage.write_source_evidence_json(
            project_id,
            run_id,
            observation_path,
            {
                "id": observation.id,
                "run_id": run_id,
                "resource_id": resource.id,
                "ref": resource.ref,
                "position": resource.position,
                "summary": summary,
                "visible_text": summary,
                "confidence": 0.9,
                "limitations": ["仅确认截图可见内容。"],
                "source": {"provider": "openai", "model": "gpt-4o-mini"},
                "status": status,
            },
        )
        observation.observation_path = observation_path
        resource.status = status
        await session.commit()
        return observation.id


def _sheet_parsed_source(
    *,
    sheet_name: str = "需求A",
    cells: list[dict[str, Any]],
    other_cells: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "source_type": "local_file",
        "title": "full-context.xlsx",
        "doc_type": "xlsx",
        "token": "sha256:full-context",
        "url": "",
        "markdown": "# Source: full-context.xlsx\n## Sheet: 需求B\n不应泄露的其他 Sheet 文本",
        "source_units": [
            {
                "unit_id": "sheet_a",
                "kind": "sheet",
                "title": sheet_name,
                "cells": cells,
                "metadata": {"sheet_index": 1, "resource_count": 3},
            },
            {
                "unit_id": "sheet_b",
                "kind": "sheet",
                "title": "需求B",
                "cells": other_cells
                or [
                    {
                        "coord": "A1",
                        "row": 1,
                        "col": 1,
                        "text": "需求B标题",
                    },
                    {
                        "coord": "B2",
                        "row": 2,
                        "col": 2,
                        "text": "需求B不应进入 context",
                    },
                ],
                "metadata": {"sheet_index": 2, "resource_count": 1},
            },
        ],
        "resources": [],
        "raw_manifest": {
            "local_path": "D:/secret/source-evidence/raw/source.xlsx",
            "provider_response": "provider raw must not leak",
        },
        "warnings": [],
    }


def _visual_resources() -> list[dict[str, Any]]:
    return [
        {
            "ref": "sheet_a_img",
            "position": "excel:sheet=需求A:image=1:anchor=B2",
            "filename": "a.png",
            "status": "unobserved",
            "metadata": {"sheet": "需求A", "sheet_index": 1},
        },
        {
            "ref": "sheet_a_unadopted",
            "position": "excel:sheet=需求A:image=2:anchor=C2",
            "filename": "a-unadopted.png",
            "status": "observed",
            "metadata": {"sheet": "需求A", "sheet_index": 1},
        },
        {
            "ref": "sheet_b_img",
            "position": "excel:sheet=需求B:image=1:anchor=B2",
            "filename": "b.png",
            "status": "unobserved",
            "metadata": {"sheet": "需求B", "sheet_index": 2},
        },
    ]


def _context_text(context: Any) -> str:
    return json.dumps(asdict(context), ensure_ascii=False, default=str)


@pytest.mark.anyio
async def test_full_context_keeps_more_than_old_800_row_snapshot_limit(
    test_db,
    test_project_id: int,
) -> None:
    cells = [
        {"coord": "A1", "row": 1, "col": 1, "text": "模块"},
        {"coord": "B1", "row": 1, "col": 2, "text": "规则"},
    ]
    for row in range(2, 903):
        cells.extend(
            [
                {"coord": f"A{row}", "row": row, "col": 1, "text": f"模块-{row}"},
                {"coord": f"B{row}", "row": row, "col": 2, "text": f"规则-{row}"},
            ]
        )
    run_id = await _seed_source_evidence_run(
        test_project_id,
        parsed_source=_sheet_parsed_source(cells=cells),
    )

    async with async_session_factory() as session:
        context = await build_full_planning_sheet_context(
            session,
            project_id=test_project_id,
            source_evidence_run_id=run_id,
            planning_sheet_name="需求A",
        )

    assert context.sheet_name == "需求A"
    assert context.columns == ["模块", "规则"]
    assert len(context.all_fact_rows) == 902
    assert context.all_fact_rows[-1].row_index == 902
    assert context.all_fact_rows[-1].cells[1].value == "规则-902"


@pytest.mark.anyio
async def test_full_context_does_not_apply_old_generation_prompt_char_budget(
    test_db,
    test_project_id: int,
) -> None:
    long_text = "超长需求内容" * 7000
    run_id = await _seed_source_evidence_run(
        test_project_id,
        parsed_source=_sheet_parsed_source(
            cells=[
                {"coord": "A1", "row": 1, "col": 1, "text": "模块"},
                {"coord": "B1", "row": 1, "col": 2, "text": "规则"},
                {"coord": "A2", "row": 2, "col": 1, "text": "活动"},
                {"coord": "B2", "row": 2, "col": 2, "text": long_text},
            ]
        ),
    )

    async with async_session_factory() as session:
        context = await build_full_planning_sheet_context(
            session,
            project_id=test_project_id,
            source_evidence_run_id=run_id,
            planning_sheet_name="需求A",
        )

    context_text = _context_text(context)
    assert long_text in context_text
    assert "已限制为前" not in context_text
    assert "已截断" not in context_text
    assert not any("截断" in warning.message for warning in context.warnings)


@pytest.mark.anyio
async def test_full_context_adds_only_current_sheet_adopted_visual_evidence(
    test_db,
    test_project_id: int,
) -> None:
    run_id = await _seed_source_evidence_run(
        test_project_id,
        parsed_source=_sheet_parsed_source(
            cells=[
                {"coord": "A1", "row": 1, "col": 1, "text": "模块"},
                {"coord": "B1", "row": 1, "col": 2, "text": "规则"},
                {"coord": "A2", "row": 2, "col": 1, "text": "活动入口"},
                {"coord": "B2", "row": 2, "col": 2, "text": "按 A 配置展示"},
            ]
        ),
        resources=_visual_resources(),
    )
    current_id = await _seed_visual_observation(
        test_project_id,
        run_id,
        ref="sheet_a_img",
        summary="需求A截图显示 A 入口按钮。",
        status="adopted",
    )
    await _seed_visual_observation(
        test_project_id,
        run_id,
        ref="sheet_b_img",
        summary="需求B截图显示 B 入口按钮。",
        status="adopted",
    )
    await _seed_visual_observation(
        test_project_id,
        run_id,
        ref="sheet_a_unadopted",
        summary="需求A未采纳观察摘要。",
        status="observed",
    )

    async with async_session_factory() as session:
        context = await build_full_planning_sheet_context(
            session,
            project_id=test_project_id,
            source_evidence_run_id=run_id,
            planning_sheet_name="需求A",
        )

    assert [item.id for item in context.adopted_visual_evidence_summaries] == [current_id]
    context_text = _context_text(context)
    assert "需求A截图显示 A 入口按钮。" in context_text
    assert "需求B截图显示 B 入口按钮。" not in context_text
    assert "需求A未采纳观察摘要。" not in context_text
    warning_text = json.dumps(
        [warning.model_dump(mode="json") for warning in context.warnings],
        ensure_ascii=False,
    )
    assert "其他 Sheet" in warning_text
    assert "未观察或未采纳" in warning_text


@pytest.mark.anyio
async def test_docx_source_uses_source_evidence_sheet_and_omits_resource_markers(
    test_db,
    test_project_id: int,
) -> None:
    run_id = await _seed_source_evidence_run(
        test_project_id,
        source_type="feishu",
        source_title="活动需求文档",
        parsed_source={
            "source_type": "feishu",
            "title": "活动需求文档",
            "doc_type": "docx",
            "token": "doccn-token-must-not-leak",
            "url": "https://demo.feishu.cn/docx/doccn-token-must-not-leak",
            "markdown": (
                "# Source: 活动需求文档\n"
                "正文规则：每日可领取一次。\n"
                "<image ref=\"docx_img_001\" position=\"docx:block:img\" />\n"
                "奖励规则：仅活动期内展示。\n"
            ),
            "source_units": [
                {
                    "unit_id": "docx_doccn",
                    "kind": "docx",
                    "title": "活动需求文档",
                    "metadata": {"block_count": 3},
                }
            ],
            "resources": [],
            "raw_manifest": {"provider_response": "provider raw must not leak"},
            "warnings": [],
        },
        resources=[
            {
                "ref": "docx_img_001",
                "position": "docx:block:img",
                "filename": "ui.png",
                "status": "unobserved",
                "local_path": "D:/secret/source-evidence/ui.png",
            }
        ],
    )

    async with async_session_factory() as session:
        context = await build_full_planning_sheet_context(
            session,
            project_id=test_project_id,
            source_evidence_run_id=run_id,
            planning_sheet_name="Source Evidence",
        )

    context_text = _context_text(context)
    assert context.sheet_name == "Source Evidence"
    assert context.columns == ["Content"]
    assert "正文规则：每日可领取一次。" in context_text
    assert "奖励规则：仅活动期内展示。" in context_text
    assert "<image" not in context_text
    assert "docx_img_001" not in context_text
    assert "未观察或未采纳" in context_text


@pytest.mark.anyio
async def test_full_context_does_not_leak_paths_tokens_or_provider_payloads(
    test_db,
    test_project_id: int,
) -> None:
    run_id = await _seed_source_evidence_run(
        test_project_id,
        parsed_source=_sheet_parsed_source(
            cells=[
                {"coord": "A1", "row": 1, "col": 1, "text": "模块"},
                {"coord": "A2", "row": 2, "col": 1, "text": "活动入口"},
            ]
        ),
        resources=_visual_resources(),
    )
    await _seed_visual_observation(
        test_project_id,
        run_id,
        ref="sheet_a_img",
        summary="安全视觉摘要。",
        status="adopted",
    )

    async with async_session_factory() as session:
        context = await build_full_planning_sheet_context(
            session,
            project_id=test_project_id,
            source_evidence_run_id=run_id,
            planning_sheet_name="需求A",
        )

    context_text = _context_text(context)
    for forbidden in (
        "D:/secret",
        "source-token-must-not-leak",
        "file-token-must-not-leak",
        "provider_response",
        "provider raw must not leak",
        "raw_response",
        "prompt",
        "visual_evidence/observations",
    ):
        assert forbidden not in context_text
