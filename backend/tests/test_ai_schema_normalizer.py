"""AI schema normalizer 单元测试。"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from backend.app.ai.schema_normalizer import (
    normalize_raw_rule_intent,
    normalize_raw_variable_intent,
    summarize_validation_error,
)


def test_normalize_raw_rule_intent_removes_wrappers_and_normalizes_missing() -> None:
    payload = normalize_raw_rule_intent(
        {
            "verdict": "needs_input",
            "params": {"ignored": True},
            "target": {"variable_tag": "[src-sheet-ID]", "pathOrUrl": "demo.xlsx"},
            "missing": {
                "kind": "bad-kind",
                "message": "缺少数据源路径",
                "suggested_action": "bad-action",
                "prefill": {"pathOrUrl": "demo.xlsx"},
            },
        }
    )

    assert "params" not in payload
    assert payload["target"] == {"tag": "[src-sheet-ID]", "path_or_url": "demo.xlsx"}
    assert payload["missing"] == [
        {
            "kind": "source",
            "message": "缺少数据源路径",
            "suggested_action": "open_source_dialog",
            "prefill": {"pathOrUrl": "demo.xlsx"},
        }
    ]


def test_normalize_raw_variable_intent_accepts_string_and_filters_placeholder_columns() -> None:
    assert normalize_raw_variable_intent("[src-sheet-ID]") == {"tag": "[src-sheet-ID]"}
    assert normalize_raw_variable_intent(
        {
            "variable": {"source_url": "demo.xlsx"},
            "kind": "composite",
            "key_column": "业务 Key",
            "columns": [" ID ", "key", "", "Name"],
        }
    ) == {
        "path_or_url": "demo.xlsx",
        "variable_kind": "composite",
        "key_column": None,
        "columns": ["ID", "Name"],
    }


def test_summarize_validation_error_returns_first_error_location() -> None:
    class DemoModel(BaseModel):
        count: int

    with pytest.raises(ValidationError) as exc_info:
        DemoModel.model_validate({"count": "bad"})

    assert summarize_validation_error(exc_info.value).startswith("count:")
