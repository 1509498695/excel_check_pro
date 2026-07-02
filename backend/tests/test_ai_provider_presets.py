"""AI provider preset defaults."""

from __future__ import annotations

from typing import Any

import pytest

from backend.app.ai import providers
from backend.app.ai.providers import resolve_provider_defaults


def test_qwen_and_zhipu_provider_defaults_match_current_api_docs() -> None:
    """Shared defaults should stay aligned with the admin frontend presets."""
    assert resolve_provider_defaults("qwen", None, None) == (
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen3.6-plus",
    )
    assert resolve_provider_defaults("zhipu", None, None) == (
        "https://open.bigmodel.cn/api/paas/v4",
        "glm-5.2",
    )


@pytest.mark.anyio
async def test_vision_connection_probe_image_meets_common_model_size_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vision connection probes must not use a 1x1 image rejected by Qwen-like models."""

    async def fake_call_provider_vision_json(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        image_bytes = kwargs["image_bytes"]
        assert isinstance(image_bytes, bytes)
        assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        width = int.from_bytes(image_bytes[16:20], "big")
        height = int.from_bytes(image_bytes[20:24], "big")
        assert width > 10
        assert height > 10
        return (
            {
                "summary": "ok",
                "visible_text": "",
                "confidence": 1,
                "limitations": [],
            },
            {"latency_ms": 7},
        )

    monkeypatch.setattr(
        providers,
        "call_provider_vision_json",
        fake_call_provider_vision_json,
    )

    assert await providers.test_provider_vision_connection(
        provider_preset="qwen",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen3.7-plus",
        api_key="sk-test",
    ) == 7
