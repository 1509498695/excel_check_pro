"""AI provider client 单元测试。"""

from __future__ import annotations

from typing import Any

import pytest

from backend.app.ai.provider_client import call_model_json


@pytest.mark.anyio
async def test_call_model_json_uses_injected_caller() -> None:
    calls: list[dict[str, Any]] = []

    async def fake_caller(**kwargs: Any) -> tuple[dict[str, str], dict[str, int]]:
        calls.append(kwargs)
        return {"ok": "yes"}, {"tokens": 1}

    payload, meta = await call_model_json(
        caller=fake_caller,
        provider_preset="custom_openai",
        model="demo",
    )

    assert payload == {"ok": "yes"}
    assert meta == {"tokens": 1}
    assert calls == [{"provider_preset": "custom_openai", "model": "demo"}]
