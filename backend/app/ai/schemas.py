"""Shared AI provider type definitions."""

from __future__ import annotations

from typing import Literal


AiProviderPreset = Literal[
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "qwen",
    "kimi",
    "zhipu",
    "openrouter",
    "xiaomi_mimo",
    "xiaomi_mimo_token_plan",
    "siliconflow",
    "custom_openai_compatible",
    "custom_openai",
]
AiProviderProtocol = Literal["openai_compatible", "anthropic", "gemini"]
