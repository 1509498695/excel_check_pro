"""项目级 AI 名称匹配器。"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.providers import ProviderConnectionError, call_provider_json
from backend.app.config_lookup.schemas import (
    ConfigLookupAiMatcher,
    ConfigLookupAiScore,
    ConfigLookupCandidate,
)
from backend.app.models import ProjectAiCredentialRecord
from backend.app.security.crypto import decrypt_secret


AI_UNAVAILABLE_MESSAGE = "AI 名称匹配不可用，请联系项目管理员检查项目级 AI 配置"


class ProjectAiMatcher(ConfigLookupAiMatcher):
    """使用项目级 AI 凭据对主配置候选名称排序。"""

    def __init__(self, db: AsyncSession, *, project_id: int) -> None:
        self._db = db
        self._project_id = project_id

    async def rank(
        self,
        *,
        lookup_input: str,
        candidates: list[ConfigLookupCandidate],
    ) -> list[ConfigLookupAiScore]:
        credential = await self._load_credential()
        if credential is None or not credential.enabled:
            raise AiMatcherUnavailable(AI_UNAVAILABLE_MESSAGE)
        try:
            api_key = decrypt_secret(credential.encrypted_api_key)
        except ValueError as exc:
            raise AiMatcherUnavailable(AI_UNAVAILABLE_MESSAGE) from exc
        if not api_key or not credential.model or not credential.base_url:
            raise AiMatcherUnavailable(AI_UNAVAILABLE_MESSAGE)

        payload = {
            "lookup_input": lookup_input,
            "candidates": [
                {
                    "key": candidate.key,
                    "page": candidate.page,
                    "id": candidate.id_value,
                    "name": candidate.name_value,
                }
                for candidate in candidates
            ],
        }
        try:
            parsed, _meta = await call_provider_json(
                provider_preset=credential.provider_preset,  # type: ignore[arg-type]
                base_url=credential.base_url,
                model=credential.model,
                api_key=api_key,
                system_prompt=(
                    "你只负责给已有配置表名称候选排序打分。"
                    "只能返回 JSON 对象，只能返回候选中的 key，"
                    "不要创造新候选，不要解释。"
                ),
                user_prompt=json.dumps(payload, ensure_ascii=False),
                json_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "matches": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "key": {"type": "string"},
                                    "score": {"type": "number"},
                                },
                                "required": ["key", "score"],
                            },
                        }
                    },
                    "required": ["matches"],
                },
                extra_headers=_parse_extra_headers(credential.extra_headers_json),
                timeout_seconds=20.0,
            )
        except ProviderConnectionError as exc:
            raise AiMatcherUnavailable(AI_UNAVAILABLE_MESSAGE) from exc

        valid_keys = {candidate.key for candidate in candidates}
        scores: list[ConfigLookupAiScore] = []
        matches = parsed.get("matches")
        if not isinstance(matches, list):
            return scores
        for item in matches:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "")
            if key not in valid_keys:
                continue
            try:
                score = float(item.get("score"))
            except (TypeError, ValueError):
                continue
            scores.append(ConfigLookupAiScore(candidate_key=key, score=max(0.0, min(1.0, score))))
        return scores

    async def _load_credential(self) -> ProjectAiCredentialRecord | None:
        result = await self._db.execute(
            select(ProjectAiCredentialRecord).where(
                ProjectAiCredentialRecord.project_id == self._project_id
            )
        )
        return result.scalar_one_or_none()


class AiMatcherUnavailable(RuntimeError):
    """项目级 AI 名称匹配不可用。"""


def _parse_extra_headers(raw_json: str) -> dict[str, str]:
    try:
        parsed = json.loads(raw_json or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in parsed.items():
        if isinstance(key, str) and isinstance(value, str) and key.strip() and value.strip():
            result[key.strip()] = value.strip()
    return result
