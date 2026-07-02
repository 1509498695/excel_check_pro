"""AI 供应商适配层，统一输出 JSON 对象。"""

from __future__ import annotations

import json
import base64
import time
from dataclasses import dataclass
from typing import Any

import httpx

from backend.app.ai.schemas import AiProviderPreset, AiProviderProtocol


@dataclass(frozen=True)
class ProviderPreset:
    """内置供应商预设。"""

    label: str
    protocol: AiProviderProtocol
    base_url: str
    model: str
    supports_strict_schema: bool = False
    supports_json_object: bool = True


PROVIDER_PRESETS: dict[AiProviderPreset, ProviderPreset] = {
    "openai": ProviderPreset(
        "OpenAI",
        "openai_compatible",
        "https://api.openai.com/v1",
        "gpt-5.4-mini",
        supports_strict_schema=True,
    ),
    "anthropic": ProviderPreset(
        "Anthropic Claude",
        "anthropic",
        "https://api.anthropic.com/v1",
        "claude-sonnet-4-5",
        supports_json_object=False,
    ),
    "gemini": ProviderPreset(
        "Google Gemini",
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta",
        "gemini-2.5-flash",
        supports_strict_schema=True,
    ),
    "deepseek": ProviderPreset(
        "DeepSeek",
        "openai_compatible",
        "https://api.deepseek.com",
        "deepseek-v4-flash",
    ),
    "qwen": ProviderPreset(
        "通义千问（百炼）",
        "openai_compatible",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen3.6-plus",
    ),
    "kimi": ProviderPreset(
        "Kimi",
        "openai_compatible",
        "https://api.moonshot.ai/v1",
        "kimi-k2-turbo-preview",
    ),
    "zhipu": ProviderPreset(
        "智谱 GLM",
        "openai_compatible",
        "https://open.bigmodel.cn/api/paas/v4",
        "glm-5.2",
    ),
    "openrouter": ProviderPreset(
        "OpenRouter",
        "openai_compatible",
        "https://openrouter.ai/api/v1",
        "openai/gpt-5-mini",
    ),
    "xiaomi_mimo": ProviderPreset(
        "小米 MiMo",
        "openai_compatible",
        "https://api.xiaomimimo.com/v1",
        "mimo-v2.5-pro",
    ),
    "xiaomi_mimo_token_plan": ProviderPreset(
        "小米 MiMo 会员",
        "openai_compatible",
        "https://token-plan-cn.xiaomimimo.com/v1",
        "mimo-v2.5-pro",
    ),
    "siliconflow": ProviderPreset(
        "SiliconFlow",
        "openai_compatible",
        "https://api.siliconflow.cn/v1",
        "",
    ),
    "custom_openai_compatible": ProviderPreset(
        "自定义 OpenAI Compatible",
        "openai_compatible",
        "",
        "",
    ),
    "custom_openai": ProviderPreset(
        "自定义 OpenAI 兼容",
        "openai_compatible",
        "",
        "",
    ),
}


VISION_CONNECTION_TEST_IMAGE_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAmUlEQVR42s2W"
    "QQqAMAwE5zO+zOf7CBU8WNRCknZAD0ox2dV0myzLuu3adYJzPST08067mI5+"
    "E8zlaKHovZiC/iQY53inEwkqo38T1Dh6KWQTssHU0uJhjCRHAhj5wMgvUi5C"
    "sIDUtjEuAQpSSQmMrNizR+RPBG6J3E12ZeoeNLdVuM3ObdfuwHFHpjv0Xdvi"
    "Gi/XOrrm17bvBw7akibFBoBCAAAAAElFTkSuQmCC"
)


class ProviderConnectionError(RuntimeError):
    """大模型上游调用失败，携带前端可展示的分类。"""

    def __init__(self, category: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.category = category
        self.message = message
        self.status_code = status_code


def get_provider_protocol(provider_preset: AiProviderPreset) -> AiProviderProtocol:
    """返回供应商使用的底层协议。"""
    return PROVIDER_PRESETS[provider_preset].protocol


def resolve_provider_defaults(
    provider_preset: AiProviderPreset,
    base_url: str | None,
    model: str | None,
) -> tuple[str, str]:
    """用预设补齐 base_url 和 model。"""
    preset = PROVIDER_PRESETS[provider_preset]
    return (base_url or preset.base_url).strip(), (model or preset.model).strip()


def mask_api_key(api_key: str) -> str:
    """返回脱敏后的 API Key。"""
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:3]}***{api_key[-4:]}"


async def call_provider_json(
    *,
    provider_preset: AiProviderPreset,
    base_url: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any],
    extra_headers: dict[str, str] | None = None,
    timeout_seconds: float = 30.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """调用上游模型并解析为 JSON 对象。"""
    if not api_key:
        raise ProviderConnectionError("auth_failed", "请先填写 API Key。")
    if not base_url or not model:
        raise ProviderConnectionError("invalid_config", "请先填写 Base URL 和模型名称。")

    preset = PROVIDER_PRESETS[provider_preset]
    headers = extra_headers or {}
    started_at = time.perf_counter()

    if preset.protocol == "anthropic":
        raw_text, usage = await _call_anthropic(
            base_url=base_url,
            model=model,
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            extra_headers=headers,
            timeout_seconds=timeout_seconds,
        )
    elif preset.protocol == "gemini":
        raw_text, usage = await _call_gemini(
            base_url=base_url,
            model=model,
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=json_schema,
            extra_headers=headers,
            timeout_seconds=timeout_seconds,
        )
    else:
        raw_text, usage = await _call_openai_compatible(
            provider_preset=provider_preset,
            base_url=base_url,
            model=model,
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=json_schema,
            extra_headers=headers,
            timeout_seconds=timeout_seconds,
        )

    parsed = extract_json_object(raw_text)
    meta = {"latency_ms": int((time.perf_counter() - started_at) * 1000), "usage": usage}
    return parsed, meta


async def test_provider_connection(
    *,
    provider_preset: AiProviderPreset,
    base_url: str,
    model: str,
    api_key: str,
    extra_headers: dict[str, str] | None = None,
) -> int:
    """用最小 JSON 请求测试上游模型连通性，返回耗时毫秒。"""
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    }
    _, meta = await call_provider_json(
        provider_preset=provider_preset,
        base_url=base_url,
        model=model,
        api_key=api_key,
        system_prompt="你只返回 JSON，不要输出 Markdown。",
        user_prompt='返回 {"ok": true}',
        json_schema=schema,
        extra_headers=extra_headers,
        timeout_seconds=15.0,
    )
    return int(meta["latency_ms"])


async def call_provider_vision_json(
    *,
    provider_preset: AiProviderPreset,
    base_url: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    image_bytes: bytes,
    image_mime_type: str,
    json_schema: dict[str, Any],
    extra_headers: dict[str, str] | None = None,
    timeout_seconds: float = 60.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """调用 OpenAI-compatible 多模态模型并解析为 JSON 对象。"""
    if not api_key:
        raise ProviderConnectionError("auth_failed", "请先填写 API Key。")
    if not base_url or not model:
        raise ProviderConnectionError("invalid_config", "请先填写 Base URL 和模型名称。")
    if not image_bytes:
        raise ProviderConnectionError("invalid_config", "视觉观察缺少图片内容。")

    preset = PROVIDER_PRESETS[provider_preset]
    if preset.protocol != "openai_compatible":
        raise ProviderConnectionError(
            "unsupported_protocol",
            "当前 Vision provider 暂不支持视觉观察协议。",
        )

    started_at = time.perf_counter()
    raw_text, usage = await _call_openai_compatible_vision(
        provider_preset=provider_preset,
        base_url=base_url,
        model=model,
        api_key=api_key,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
        json_schema=json_schema,
        extra_headers=extra_headers or {},
        timeout_seconds=timeout_seconds,
    )
    parsed = extract_json_object(raw_text)
    meta = {"latency_ms": int((time.perf_counter() - started_at) * 1000), "usage": usage}
    return parsed, meta


async def test_provider_vision_connection(
    *,
    provider_preset: AiProviderPreset,
    base_url: str,
    model: str,
    api_key: str,
    extra_headers: dict[str, str] | None = None,
) -> int:
    """用最小图片 JSON 请求测试 Vision provider 连通性。"""
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "visible_text": {"type": "string"},
            "confidence": {"type": "number"},
            "limitations": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "visible_text", "confidence", "limitations"],
    }
    _, meta = await call_provider_vision_json(
        provider_preset=provider_preset,
        base_url=base_url,
        model=model,
        api_key=api_key,
        system_prompt="你只返回 JSON，不要输出 Markdown。",
        user_prompt="观察这张测试图片，返回最小 JSON。",
        image_bytes=VISION_CONNECTION_TEST_IMAGE_PNG_BYTES,
        image_mime_type="image/png",
        json_schema=schema,
        extra_headers=extra_headers,
        timeout_seconds=20.0,
    )
    return int(meta["latency_ms"])


def extract_json_object(raw_text: str) -> dict[str, Any]:
    """从模型文本中提取第一个 JSON 对象。"""
    text = (raw_text or "").strip()
    if not text:
        raise ProviderConnectionError("invalid_json", "模型未返回内容。")

    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ProviderConnectionError("invalid_json", "模型未返回 JSON。") from None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ProviderConnectionError("invalid_json", "模型返回的 JSON 无法解析。") from exc

    if not isinstance(payload, dict):
        raise ProviderConnectionError("invalid_json", "模型返回 JSON 不是对象。")
    return payload


def _merge_headers(base_headers: dict[str, str], extra_headers: dict[str, str]) -> dict[str, str]:
    merged = {**base_headers}
    for key, value in extra_headers.items():
        if key.strip() and value.strip():
            merged[key.strip()] = value.strip()
    return merged


def _normalize_chat_completions_url(base_url: str) -> str:
    stripped = base_url.rstrip("/")
    if stripped.endswith("/chat/completions"):
        return stripped
    return f"{stripped}/chat/completions"


async def _post_json(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise ProviderConnectionError("network", "调用大模型超时，请稍后重试。") from exc
    except httpx.HTTPError as exc:
        raise ProviderConnectionError("network", f"无法连接大模型服务：{exc}") from exc

    if response.status_code in {401, 403}:
        raise ProviderConnectionError("auth_failed", "API Key 无效或无权限。")
    if response.status_code == 404:
        raise ProviderConnectionError("model_not_found", "模型名或接口地址不存在。")
    if response.status_code == 429:
        raise ProviderConnectionError("rate_limited", "大模型服务限流，请稍后重试。", 429)
    if response.status_code >= 500:
        raise ProviderConnectionError("upstream_error", "大模型服务暂不可用。")
    if response.status_code >= 400:
        raise ProviderConnectionError("unknown", _extract_upstream_error(response))
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise ProviderConnectionError("invalid_json", "大模型服务返回了非 JSON 响应。") from exc


def _extract_upstream_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return response.text[:500] or "大模型调用失败。"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("type") or "大模型调用失败。")
        if isinstance(payload.get("message"), str):
            return str(payload["message"])
        if isinstance(payload.get("msg"), str):
            return str(payload["msg"])
    return "大模型调用失败。"


async def _call_openai_compatible(
    *,
    provider_preset: AiProviderPreset,
    base_url: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any],
    extra_headers: dict[str, str],
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    preset = PROVIDER_PRESETS[provider_preset]
    headers = _merge_headers(
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        extra_headers,
    )
    base_payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "stream": False,
    }

    response_format: dict[str, Any]
    if preset.supports_strict_schema:
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "excel_check_rule_draft",
                "strict": True,
                "schema": json_schema,
            },
        }
    else:
        response_format = {"type": "json_object"}

    payload = {**base_payload, "response_format": response_format}
    url = _normalize_chat_completions_url(base_url)
    try:
        data = await _post_json(url, headers=headers, payload=payload, timeout_seconds=timeout_seconds)
    except ProviderConnectionError as exc:
        if exc.category not in {"unknown", "invalid_json"} or not preset.supports_strict_schema:
            raise
        payload = {**base_payload, "response_format": {"type": "json_object"}}
        data = await _post_json(url, headers=headers, payload=payload, timeout_seconds=timeout_seconds)

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderConnectionError("invalid_json", "大模型响应缺少 choices.message.content。") from exc
    return str(content), data.get("usage") if isinstance(data.get("usage"), dict) else {}


async def _call_openai_compatible_vision(
    *,
    provider_preset: AiProviderPreset,
    base_url: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    image_bytes: bytes,
    image_mime_type: str,
    json_schema: dict[str, Any],
    extra_headers: dict[str, str],
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    preset = PROVIDER_PRESETS[provider_preset]
    headers = _merge_headers(
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        extra_headers,
    )
    image_mime = image_mime_type or "image/jpeg"
    image_url = f"data:{image_mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    base_payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "auto"},
                    },
                ],
            },
        ],
        "temperature": 0,
        "stream": False,
        "max_tokens": 1200,
    }
    if preset.supports_strict_schema:
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "source_evidence_visual_observation",
                "strict": True,
                "schema": json_schema,
            },
        }
    else:
        response_format = {"type": "json_object"}

    payload = {**base_payload, "response_format": response_format}
    url = _normalize_chat_completions_url(base_url)
    try:
        data = await _post_json(url, headers=headers, payload=payload, timeout_seconds=timeout_seconds)
    except ProviderConnectionError as exc:
        if exc.category not in {"unknown", "invalid_json"} or not preset.supports_strict_schema:
            raise
        payload = {**base_payload, "response_format": {"type": "json_object"}}
        data = await _post_json(url, headers=headers, payload=payload, timeout_seconds=timeout_seconds)

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderConnectionError("invalid_json", "Vision 模型响应缺少 choices.message.content。") from exc
    return str(content), data.get("usage") if isinstance(data.get("usage"), dict) else {}


async def _call_anthropic(
    *,
    base_url: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    extra_headers: dict[str, str],
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    headers = _merge_headers(
        {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        extra_headers,
    )
    url = f"{base_url.rstrip('/')}/messages"
    payload = {
        "model": model,
        "max_tokens": 4096,
        "temperature": 0,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    data = await _post_json(url, headers=headers, payload=payload, timeout_seconds=timeout_seconds)
    content_items = data.get("content")
    if not isinstance(content_items, list):
        raise ProviderConnectionError("invalid_json", "Claude 响应缺少 content。")
    text_parts = [
        str(item.get("text", ""))
        for item in content_items
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    return "\n".join(text_parts), data.get("usage") if isinstance(data.get("usage"), dict) else {}


async def _call_gemini(
    *,
    base_url: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any],
    extra_headers: dict[str, str],
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    headers = _merge_headers(
        {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        extra_headers,
    )
    url = f"{base_url.rstrip('/')}/models/{model}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseJsonSchema": json_schema,
        },
    }
    data = await _post_json(url, headers=headers, payload=payload, timeout_seconds=timeout_seconds)
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderConnectionError("invalid_json", "Gemini 响应缺少 candidates.content.parts。") from exc
    text = "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
    return text, data.get("usageMetadata") if isinstance(data.get("usageMetadata"), dict) else {}
