"""进程内礼包规划表 AI 结构解析缓存。"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from backend.app.api.fixed_rules_schemas import PackageItemsPreviewResult
from backend.app.services.package_items_ai_parser import PackageAiParseSuggestion
from backend.config import settings


@dataclass(frozen=True)
class PackageItemsAiParseCacheKey:
    """唯一标识一次飞书礼包规划表 AI 结构解析。"""

    feishu_source_id: str
    sheet_id: str
    sheet_revision_or_hash: str
    parse_strategy: str
    ai_parse_mode: str
    prompt_version: str

    def to_storage_key(self) -> str:
        payload = {
            "feishu_source_id": self.feishu_source_id,
            "sheet_id": self.sheet_id,
            "sheet_revision_or_hash": self.sheet_revision_or_hash,
            "parse_strategy": self.parse_strategy,
            "ai_parse_mode": self.ai_parse_mode,
            "prompt_version": self.prompt_version,
        }
        raw_key = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PackageItemsAiParseCacheEntry:
    """缓存中的 AI 建议和确定性解析结果。"""

    suggestion: PackageAiParseSuggestion
    parse_result: PackageItemsPreviewResult


@dataclass
class _StoredPackageItemsAiParseEntry:
    expires_at: float
    suggestion_payload: dict[str, Any]
    parse_result_payload: dict[str, Any]


_CACHE_LOCK = threading.RLock()
_CACHE: dict[str, _StoredPackageItemsAiParseEntry] = {}


def build_sheet_matrix_hash(sheet_matrix: list[list[Any]]) -> str:
    """对读取到的 Sheet 显示值生成稳定 hash。"""
    payload = json.dumps(
        sheet_matrix,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_package_items_ai_parse_cache(
    key: PackageItemsAiParseCacheKey,
) -> PackageItemsAiParseCacheEntry | None:
    """读取缓存；过期或 payload 校验失败时自动删除并返回未命中。"""
    ttl_seconds = settings.package_items_ai_parse_cache_ttl_seconds
    if ttl_seconds <= 0:
        return None

    storage_key = key.to_storage_key()
    with _CACHE_LOCK:
        stored = _CACHE.get(storage_key)
        if stored is None:
            return None
        if stored.expires_at <= time.monotonic():
            _CACHE.pop(storage_key, None)
            return None
        try:
            suggestion = PackageAiParseSuggestion.model_validate(stored.suggestion_payload)
            parse_result = PackageItemsPreviewResult.model_validate(
                stored.parse_result_payload
            )
        except ValidationError:
            _CACHE.pop(storage_key, None)
            return None

    parse_result.cache_hit = True
    return PackageItemsAiParseCacheEntry(
        suggestion=suggestion,
        parse_result=parse_result,
    )


def set_package_items_ai_parse_cache(
    key: PackageItemsAiParseCacheKey,
    *,
    suggestion: PackageAiParseSuggestion,
    parse_result: PackageItemsPreviewResult,
) -> None:
    """写入成功 AI 结构解析结果。"""
    ttl_seconds = settings.package_items_ai_parse_cache_ttl_seconds
    if ttl_seconds <= 0:
        return

    stored_result = parse_result.model_copy(update={"cache_hit": False})
    with _CACHE_LOCK:
        _CACHE[key.to_storage_key()] = _StoredPackageItemsAiParseEntry(
            expires_at=time.monotonic() + ttl_seconds,
            suggestion_payload=suggestion.model_dump(mode="json"),
            parse_result_payload=stored_result.model_dump(mode="json"),
        )


def set_package_items_ai_parse_cache_payload(
    key: PackageItemsAiParseCacheKey,
    *,
    suggestion_payload: dict[str, Any],
    parse_result_payload: dict[str, Any],
) -> None:
    """测试辅助：写入未经校验的缓存 payload。"""
    ttl_seconds = settings.package_items_ai_parse_cache_ttl_seconds
    if ttl_seconds <= 0:
        return
    with _CACHE_LOCK:
        _CACHE[key.to_storage_key()] = _StoredPackageItemsAiParseEntry(
            expires_at=time.monotonic() + ttl_seconds,
            suggestion_payload=suggestion_payload,
            parse_result_payload=parse_result_payload,
        )


def clear_package_items_ai_parse_cache() -> None:
    """清空进程内缓存，供测试隔离使用。"""
    with _CACHE_LOCK:
        _CACHE.clear()
