"""AI 模型供应商调用边界。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.app.ai.providers import call_provider_json


async def call_model_json(
    *,
    caller: Callable[..., Any] | None = None,
    **kwargs: Any,
) -> tuple[Any, dict[str, Any]]:
    """调用模型并返回 JSON 结果。

    ``caller`` 作为注入点保留给 ``agent_service`` 兼容历史 monkeypatch。
    """

    provider_caller = caller or call_provider_json
    return await provider_caller(**kwargs)
