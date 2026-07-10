"""Source Evidence generation legacy endpoint contract tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


def _planning_snapshot_payload() -> dict[str, object]:
    return {
        "source_summary": "local_file：需求.xlsx",
        "sheet_name": "需求A",
        "columns": ["来源类型", "位置", "标题/页签", "内容", "证据状态"],
        "rows": [
            {
                "row_index": 1,
                "cells": [
                    {
                        "row_index": 1,
                        "column_index": 1,
                        "column_name": "来源类型",
                        "value": "local_file:xlsx",
                    },
                    {
                        "row_index": 1,
                        "column_index": 2,
                        "column_name": "位置",
                        "value": "需求A!A1",
                    },
                    {
                        "row_index": 1,
                        "column_index": 3,
                        "column_name": "标题/页签",
                        "value": "需求A",
                    },
                    {
                        "row_index": 1,
                        "column_index": 4,
                        "column_name": "内容",
                        "value": "活动入口按配置展示。",
                    },
                    {
                        "row_index": 1,
                        "column_index": 5,
                        "column_name": "证据状态",
                        "value": "table",
                    },
                ],
            }
        ],
        "non_empty_cell_count": 5,
        "truncated": False,
        "warnings": [],
    }


@pytest.mark.anyio
async def test_legacy_sync_generate_returns_410(
    auth_client: AsyncClient,
) -> None:
    """Source Evidence generation assertions now belong to V3 context/service tests."""
    response = await auth_client.post(
        "/api/v1/test-cases/generate",
        json={
            "planning_snapshot": _planning_snapshot_payload(),
            "source_evidence_run_id": 1,
            "adopted_visual_evidence_ids": [],
            "reference_ids": [],
            "primary_reference_id": None,
        },
    )

    assert response.status_code == 410
    assert response.json()["detail"] == "同步用例生成入口已停用，请使用 V3 Generation Run。"
