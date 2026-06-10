"""配置表查询路径校验与解析。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from backend.app.api.schemas import DataSource
from backend.app.loaders.svn_cache import is_remote_svn_locator, prepare_remote_svn_source


@dataclass(frozen=True)
class NormalizedVersionFolder:
    """已校验的版本目录。"""

    relative: str
    display: str


@dataclass(frozen=True)
class ResolvedConfigFile:
    """已解析到本地的配置文件路径。"""

    version_folder: NormalizedVersionFolder
    path: Path
    missing_message: str | None = None


class ConfigLookupPathError(ValueError):
    """路径校验或文件解析错误。"""


_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def normalize_versioned_config_folder(raw_folder: str) -> NormalizedVersionFolder:
    """校验版本目录，并规范为 query_root 下的相对路径。"""

    raw = (raw_folder or "").strip()
    if not raw:
        raise ConfigLookupPathError("版本配置目录不合法：不能为空")
    if _SCHEME_RE.match(raw):
        raise ConfigLookupPathError(f"版本配置目录不合法：{raw_folder}")
    if _DRIVE_RE.match(raw):
        raise ConfigLookupPathError(f"版本配置目录不合法：{raw_folder}")
    if "\\" in raw:
        raise ConfigLookupPathError(f"版本配置目录不合法：{raw_folder}")

    stripped = raw.lstrip("/")
    path = PurePosixPath(stripped)
    parts = [part for part in path.parts if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ConfigLookupPathError(f"版本配置目录不合法：{raw_folder}")

    relative = "/".join(parts)
    return NormalizedVersionFolder(relative=relative, display=f"/{relative}")


def resolve_config_file(
    *,
    query_root_url: str,
    version_folder: NormalizedVersionFolder,
    file_name: str,
    query_root_alias: str,
) -> ResolvedConfigFile:
    """解析主配置或引用配置文件，远端 SVN 会强制刷新到本地缓存。"""

    if not file_name:
        raise ConfigLookupPathError("配置文件名不能为空")
    if _SCHEME_RE.match(file_name) or _DRIVE_RE.match(file_name) or "\\" in file_name:
        raise ConfigLookupPathError(f"配置文件路径不合法：{file_name}")
    if Path(file_name).is_absolute() or ".." in PurePosixPath(file_name).parts:
        raise ConfigLookupPathError(f"配置文件路径不合法：{file_name}")

    query_root = (query_root_url or "").strip()
    if is_remote_svn_locator(query_root):
        return _resolve_remote_config_file(
            query_root_url=query_root,
            version_folder=version_folder,
            file_name=file_name,
        )
    return _resolve_local_config_file(
        query_root_url=query_root,
        version_folder=version_folder,
        file_name=file_name,
        query_root_alias=query_root_alias,
    )


def _resolve_local_config_file(
    *,
    query_root_url: str,
    version_folder: NormalizedVersionFolder,
    file_name: str,
    query_root_alias: str,
) -> ResolvedConfigFile:
    root = Path(query_root_url).expanduser().resolve(strict=False)
    version_dir = (root / Path(version_folder.relative)).resolve(strict=False)
    try:
        version_dir.relative_to(root)
    except ValueError as exc:
        raise ConfigLookupPathError(f"版本配置目录不合法：{version_folder.display}") from exc

    if not version_dir.exists() or not version_dir.is_dir():
        return ResolvedConfigFile(
            version_folder=version_folder,
            path=version_dir / file_name,
            missing_message=(
                f"未找到版本配置目录：{version_folder.display}，"
                f"请确认目录是否存在于数据根 {query_root_alias} 下"
            ),
        )

    config_path = (version_dir / Path(file_name)).resolve(strict=False)
    try:
        config_path.relative_to(root)
    except ValueError as exc:
        raise ConfigLookupPathError(f"配置文件路径不合法：{file_name}") from exc
    if not config_path.exists() or not config_path.is_file():
        return ResolvedConfigFile(
            version_folder=version_folder,
            path=config_path,
            missing_message=(
                f"未找到配置文件：{file_name}，"
                f"请确认 {version_folder.display} 下是否存在该文件"
            ),
        )
    return ResolvedConfigFile(version_folder=version_folder, path=config_path)


def _resolve_remote_config_file(
    *,
    query_root_url: str,
    version_folder: NormalizedVersionFolder,
    file_name: str,
) -> ResolvedConfigFile:
    url = query_root_url.rstrip("/")
    remote_url = "/".join(
        [url, *[quote(part) for part in version_folder.relative.split("/")], quote(file_name)]
    )
    local_path = prepare_remote_svn_source(
        DataSource(id="config_lookup", type="svn", pathOrUrl=remote_url),
        force_refresh=True,
    )
    return ResolvedConfigFile(version_folder=version_folder, path=local_path)
