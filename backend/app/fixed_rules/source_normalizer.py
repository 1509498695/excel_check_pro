"""固定规则数据源归一化。"""

from __future__ import annotations

from pathlib import Path

from backend.app.api.schemas import DataSource
from backend.app.fixed_rules.config_common import _normalize_local_source_path


def _normalize_sources(
    sources: list[DataSource],
    *,
    allow_unsupported_csv: bool = False,
) -> list[DataSource]:
    """?????????????????"""
    normalized_sources: list[DataSource] = []
    seen_source_ids: set[str] = set()

    for source in sources:
        source_id = source.id.strip()
        if not source_id:
            raise ValueError("????????? id?")
        if source_id in seen_source_ids:
            raise ValueError(f"??????? ID ???'{source_id}'?")

        source_type = source.type
        raw_locator = (source.pathOrUrl or source.path or source.url or "").strip()
        token = source.token.strip() if source.token else None

        if source_type == "feishu":
            if not raw_locator:
                raise ValueError(f"??????? '{source_id}' ???????")
            normalized_sources.append(
                DataSource(
                    id=source_id,
                    type=source_type,
                    url=raw_locator,
                    pathOrUrl=raw_locator,
                    token=token or None,
                )
            )
        elif source_type in {"local_excel", "local_csv"}:
            if source_type == "local_csv" and not allow_unsupported_csv:
                raise ValueError(
                    f"CSV 数据源“{source_id}”已不再支持，请删除后改用 Excel 或 SVN Excel。"
                )
            normalized_path = _normalize_local_source_path(source_id, raw_locator, source_type)
            normalized_sources.append(
                DataSource(
                    id=source_id,
                    type=source_type,
                    path=str(normalized_path),
                    pathOrUrl=str(normalized_path),
                    token=token or None,
                )
            )
        elif source_type == "svn":
            if not raw_locator:
                raise ValueError(f"数据源 '{source_id}' 缺少 SVN 路径或 URL。")
            from backend.app.loaders.svn_cache import is_remote_svn_locator

            if is_remote_svn_locator(raw_locator):
                # 远端 URL 保持原样，不能 Path.resolve() 污染。
                normalized_sources.append(
                    DataSource(
                        id=source_id,
                        type=source_type,
                        pathOrUrl=raw_locator,
                        token=token or None,
                    )
                )
            else:
                normalized_path = Path(raw_locator).expanduser().resolve(strict=False)
                normalized_sources.append(
                    DataSource(
                        id=source_id,
                        type=source_type,
                        path=str(normalized_path),
                        pathOrUrl=str(normalized_path),
                        token=token or None,
                    )
                )
        else:  # pragma: no cover - ? pydantic Literal ??
            raise ValueError(f"??????? '{source_id}' ????????? '{source_type}'?")

        seen_source_ids.add(source_id)

    return normalized_sources
