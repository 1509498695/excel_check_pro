"""Project-level AI provider credential loading helpers."""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.providers import mask_api_key
from backend.app.models import ProjectAiCredentialRecord
from backend.app.security.crypto import decrypt_secret


PROJECT_AI_UNAVAILABLE_MESSAGE = "当前项目尚未配置或启用项目级 AI 凭据，请联系项目管理员在管理后台配置"
_SK_STYLE_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b")
_BEARER_TOKEN_RE = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._\-]{12,}")


class AiProviderNotConfigured(ValueError):
    """项目级 AI 供应商尚未配置或未启用。"""


class AiProviderInvalid(ValueError):
    """项目级 AI 凭据无法解密。"""


async def load_project_credential(
    db: AsyncSession,
    project_id: int,
) -> ProjectAiCredentialRecord:
    """Load the current project's AI credential record."""
    result = await db.execute(
        select(ProjectAiCredentialRecord).where(
            ProjectAiCredentialRecord.project_id == project_id
        )
    )
    credential = result.scalar_one_or_none()
    if credential is None or not credential.encrypted_api_key:
        raise AiProviderNotConfigured(PROJECT_AI_UNAVAILABLE_MESSAGE)
    if not credential.enabled:
        raise AiProviderNotConfigured(PROJECT_AI_UNAVAILABLE_MESSAGE)
    return credential


def decrypt_credential_key(credential: ProjectAiCredentialRecord) -> str:
    """Decrypt a provider API key and normalize the domain error."""
    try:
        api_key = decrypt_secret(credential.encrypted_api_key)
    except ValueError as exc:
        raise AiProviderInvalid(PROJECT_AI_UNAVAILABLE_MESSAGE) from exc
    if not api_key:
        raise AiProviderNotConfigured(PROJECT_AI_UNAVAILABLE_MESSAGE)
    return api_key


def sanitize_ai_error(message: str, api_key: str = "", *, max_length: int = 500) -> str:
    """Return a user-facing AI error string without full API keys."""
    sanitized = message or "AI 调用失败，请检查项目级 AI 配置。"
    if api_key:
        sanitized = sanitized.replace(api_key, mask_api_key(api_key) or "[已脱敏]")
    sanitized = _SK_STYLE_KEY_RE.sub(
        lambda match: mask_api_key(match.group(0)) or "[已脱敏]",
        sanitized,
    )
    sanitized = _BEARER_TOKEN_RE.sub(r"\1[已脱敏]", sanitized)
    return sanitized[:max_length]


def parse_extra_headers(raw_json: str) -> dict[str, str]:
    """Parse persisted provider extra headers."""
    try:
        parsed = json.loads(raw_json or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(value) for key, value in parsed.items()}
