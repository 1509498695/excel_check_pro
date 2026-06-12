"""飞书机器人配置文件下载指令与安全路径解析。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.parse import urlparse

from backend.app.loaders.svn_manager import update_svn_working_copy


DOWNLOAD_COMMAND = "下载"
QUERY_COMMAND = "查询"
DEFAULT_DOWNLOAD_SUFFIXES = [".xls", ".xlsx", ".csv", ".json", ".xml", ".txt"]
_MENTION_PATTERN = r"(?:@_user_[A-Za-z0-9_]+|@[^\s]+)"
_LEADING_MENTIONS_PATTERN = rf"{_MENTION_PATTERN}(?:\s+{_MENTION_PATTERN})*"
_DOWNLOAD_COMMAND_PATTERN = re.compile(
    rf"^\s*{_LEADING_MENTIONS_PATTERN}\s+下载(?:\s+(?P<path>.+))?\s*$"
)
_QUERY_COMMAND_PATTERN = re.compile(
    rf"^\s*{_LEADING_MENTIONS_PATTERN}\s+查询(?:\s+(?P<args>.*))?\s*$"
)
_REMOTE_SVN_SCHEMES = {"http", "https", "svn"}
SVN_WORKING_COPY_REQUIRED_MESSAGE = (
    "SVN 下载根目录必须配置为本机 SVN 工作副本目录（目录下或父级需存在 .svn）"
)


@dataclass(frozen=True)
class DownloadResolution:
    """一次下载请求解析后的本机文件信息。"""

    path: Path
    root: Path
    source_kind: Literal["local", "svn"]
    display_name: str
    size_bytes: int
    svn_update_output: str = ""


@dataclass(frozen=True)
class QueryRequest:
    """一次目录查询命令解析后的相对目录与名称前缀。"""

    directory: str = "."
    prefix: str = ""


@dataclass(frozen=True)
class QueryListingGroup:
    """一个配置根目录下的查询结果。"""

    title: str
    directory: Path
    entries: list[str]
    source_kind: Literal["local", "svn"]
    error: str = ""


def extract_download_path(text: str) -> str | None:
    """从群 @ 文本中提取下载路径。

    返回值语义：
    - ``None``：不是下载命令。
    - ``""``：是下载命令，但缺少路径。
    - 非空字符串：用户输入的路径，已去掉一层成对引号。
    """
    if not isinstance(text, str):
        return None
    match = _DOWNLOAD_COMMAND_PATTERN.match(text)
    if match is None:
        return None
    raw_path = (match.group("path") or "").strip()
    return _strip_wrapping_quotes(raw_path)


def extract_query_request(text: str) -> QueryRequest | None:
    """从群 @ 文本中提取目录查询请求。"""
    if not isinstance(text, str):
        return None
    match = _QUERY_COMMAND_PATTERN.match(text)
    if match is None:
        return None
    args = (match.group("args") or "").strip()
    if not args:
        return QueryRequest()
    tokens = _split_command_args(args)
    if len(tokens) == 1:
        return QueryRequest(directory=tokens[0] or ".")
    return QueryRequest(directory=tokens[0] or ".", prefix=" ".join(tokens[1:]).strip())


def parse_json_string_list(
    raw: str | None,
    *,
    default: list[str] | None = None,
) -> list[str]:
    """解析配置表中 JSON 数组字符串；旧库异常值按默认值兜底。"""
    fallback = list(default or [])
    if not raw:
        return fallback
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return fallback
    if not isinstance(payload, list):
        return fallback
    return [str(item).strip() for item in payload if str(item).strip()]


def resolve_query_listing(
    request: QueryRequest,
    *,
    local_roots: list[str],
    svn_roots: list[str],
    allowed_suffixes: list[str] | None,
    update_working_copy: Callable[..., dict[str, Any]] = update_svn_working_copy,
) -> list[QueryListingGroup]:
    """查询配置根目录拼接相对目录后的下一级文件和目录。"""
    relative_dir = _normalize_query_directory(request.directory)
    prefix = (request.prefix or "").strip()
    prefix_key = prefix.lower()
    suffixes = _normalize_suffixes(allowed_suffixes)
    svn_root_paths = _normalize_roots(svn_roots)
    local_root_paths = _normalize_roots(local_roots)
    if not svn_root_paths and not local_root_paths:
        raise ValueError("后台尚未配置可下载根目录，请先配置本地或 SVN 下载根目录。")

    groups: list[QueryListingGroup] = []
    for index, root in enumerate(svn_root_paths, start=1):
        title = f"SVN#{index} {root.name or '根目录'}"
        target = (root / relative_dir).resolve(strict=False)
        if not _is_relative_to(target, root):
            raise ValueError("查询目录不在后台配置的下载根目录范围内。")
        try:
            _update_svn_query_directory(
                update_working_copy,
                target_dir=target,
            )
            entries = _list_query_entries(
                target,
                relative_dir=relative_dir,
                suffixes=suffixes,
                prefix_key=prefix_key,
            )
            groups.append(
                QueryListingGroup(
                    title=title,
                    directory=target,
                    entries=entries,
                    source_kind="svn",
                )
            )
        except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
            groups.append(
                QueryListingGroup(
                    title=title,
                    directory=target,
                    entries=[],
                    source_kind="svn",
                    error=_format_query_group_error(exc, root=root, target=target),
                )
            )

    for index, root in enumerate(local_root_paths, start=1):
        title = f"本地#{index} {root.name or '根目录'}"
        target = (root / relative_dir).resolve(strict=False)
        if not _is_relative_to(target, root):
            raise ValueError("查询目录不在后台配置的下载根目录范围内。")
        try:
            entries = _list_query_entries(
                target,
                relative_dir=relative_dir,
                suffixes=suffixes,
                prefix_key=prefix_key,
            )
            groups.append(
                QueryListingGroup(
                    title=title,
                    directory=target,
                    entries=entries,
                    source_kind="local",
                )
            )
        except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
            groups.append(
                QueryListingGroup(
                    title=title,
                    directory=target,
                    entries=[],
                    source_kind="local",
                    error=_format_query_group_error(exc, root=root, target=target),
                )
            )

    return groups


def resolve_download_file(
    requested_path: str,
    *,
    local_roots: list[str],
    svn_roots: list[str],
    allowed_suffixes: list[str] | None,
    max_file_bytes: int,
    update_working_copy: Callable[..., dict[str, Any]] = update_svn_working_copy,
) -> DownloadResolution:
    """在配置根目录内解析用户请求路径，必要时先更新 SVN 工作副本。"""
    raw = (requested_path or "").strip()
    if not raw:
        raise ValueError("请按格式发送：@机器人 下载 <文件路径>")
    if _looks_like_remote_svn_url(raw):
        raise ValueError("第一版暂不支持远端 SVN URL，请使用后台配置的本机 SVN 工作副本路径。")

    svn_root_paths = _normalize_roots(svn_roots)
    local_root_paths = _normalize_roots(local_roots)
    if not svn_root_paths and not local_root_paths:
        raise ValueError("后台尚未配置可下载根目录，请先配置本地或 SVN 下载根目录。")

    suffixes = _normalize_suffixes(allowed_suffixes)
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return _resolve_absolute_candidate(
            candidate,
            svn_roots=svn_root_paths,
            local_roots=local_root_paths,
            suffixes=suffixes,
            max_file_bytes=max_file_bytes,
            update_working_copy=update_working_copy,
        )

    _reject_relative_escape(candidate)
    return _resolve_relative_candidate(
        candidate,
        svn_roots=svn_root_paths,
        local_roots=local_root_paths,
        suffixes=suffixes,
        max_file_bytes=max_file_bytes,
        update_working_copy=update_working_copy,
    )


def _resolve_absolute_candidate(
    candidate: Path,
    *,
    svn_roots: list[Path],
    local_roots: list[Path],
    suffixes: set[str],
    max_file_bytes: int,
    update_working_copy: Callable[..., dict[str, Any]],
) -> DownloadResolution:
    resolved = candidate.resolve(strict=False)
    svn_root = _find_containing_root(resolved, svn_roots)
    if svn_root is not None:
        update_result = _update_svn_file(
            update_working_copy,
            target_file=resolved,
        )
        resolved = resolved.resolve(strict=False)
        return _finalize_file(
            path=resolved,
            root=svn_root,
            source_kind="svn",
            suffixes=suffixes,
            max_file_bytes=max_file_bytes,
            svn_update_output=str(update_result.get("output") or ""),
        )

    local_root = _find_containing_root(resolved, local_roots)
    if local_root is not None:
        return _finalize_file(
            path=resolved,
            root=local_root,
            source_kind="local",
            suffixes=suffixes,
            max_file_bytes=max_file_bytes,
        )

    raise ValueError("请求路径不在后台配置的下载根目录范围内。")


def _resolve_relative_candidate(
    relative_path: Path,
    *,
    svn_roots: list[Path],
    local_roots: list[Path],
    suffixes: set[str],
    max_file_bytes: int,
    update_working_copy: Callable[..., dict[str, Any]],
) -> DownloadResolution:
    svn_matches = _existing_matches(relative_path, svn_roots)
    if not svn_matches and svn_roots:
        updated_outputs: dict[Path, str] = {}
        for root in svn_roots:
            update_result = _update_svn_file(
                update_working_copy,
                target_file=(root / relative_path).resolve(strict=False),
            )
            updated_outputs[root] = str(update_result.get("output") or "")
        svn_matches = _existing_matches(relative_path, svn_roots)
        if svn_matches:
            return _finalize_unique_match(
                svn_matches,
                source_kind="svn",
                suffixes=suffixes,
                max_file_bytes=max_file_bytes,
                svn_update_outputs=updated_outputs,
            )

    if svn_matches:
        matched_paths_by_root = {root: path for path, root in svn_matches}
        updated_outputs = {
            root: str(
                _update_svn_file(
                    update_working_copy,
                    target_file=matched_paths_by_root[root],
                ).get("output")
                or ""
            )
            for root in matched_paths_by_root
        }
        return _finalize_unique_match(
            _existing_matches(relative_path, list(matched_paths_by_root)),
            source_kind="svn",
            suffixes=suffixes,
            max_file_bytes=max_file_bytes,
            svn_update_outputs=updated_outputs,
        )

    local_matches = _existing_matches(relative_path, local_roots)
    if local_matches:
        return _finalize_unique_match(
            local_matches,
            source_kind="local",
            suffixes=suffixes,
            max_file_bytes=max_file_bytes,
        )

    raise FileNotFoundError(f"未找到文件：{relative_path}")


def _finalize_unique_match(
    matches: list[tuple[Path, Path]],
    *,
    source_kind: Literal["local", "svn"],
    suffixes: set[str],
    max_file_bytes: int,
    svn_update_outputs: dict[Path, str] | None = None,
) -> DownloadResolution:
    if len(matches) > 1:
        choices = "；".join(str(path) for path, _ in matches[:5])
        raise ValueError(f"匹配到多个文件，请发送完整路径：{choices}")
    if not matches:
        raise FileNotFoundError("未找到文件。")
    path, root = matches[0]
    return _finalize_file(
        path=path,
        root=root,
        source_kind=source_kind,
        suffixes=suffixes,
        max_file_bytes=max_file_bytes,
        svn_update_output=(svn_update_outputs or {}).get(root, ""),
    )


def _update_svn_file(
    update_working_copy: Callable[..., dict[str, Any]],
    *,
    target_file: Path,
) -> dict[str, Any]:
    working_copy = _find_svn_working_copy_root(target_file.parent)
    return update_working_copy(
        working_copy,
        update_target=target_file,
        target_file=target_file,
        close_target_file=True,
        cleanup_on_lock=True,
    )


def _update_svn_query_directory(
    update_working_copy: Callable[..., dict[str, Any]],
    *,
    target_dir: Path,
) -> dict[str, Any]:
    working_copy = _find_svn_working_copy_root(target_dir)
    update_target = None if _same_path(working_copy, target_dir) else target_dir
    return update_working_copy(working_copy, update_target=update_target)


def _find_svn_working_copy_root(start: Path) -> Path:
    start_dir = _nearest_existing_directory(start)
    if start_dir is None:
        raise ValueError(SVN_WORKING_COPY_REQUIRED_MESSAGE)

    current = start_dir.resolve(strict=False)
    while True:
        if (current / ".svn").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise ValueError(SVN_WORKING_COPY_REQUIRED_MESSAGE)


def _nearest_existing_directory(path: Path) -> Path | None:
    current = path.expanduser().resolve(strict=False)
    while True:
        if current.exists():
            return current if current.is_dir() else current.parent
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _finalize_file(
    *,
    path: Path,
    root: Path,
    source_kind: Literal["local", "svn"],
    suffixes: set[str],
    max_file_bytes: int,
    svn_update_output: str = "",
) -> DownloadResolution:
    resolved = path.resolve(strict=False)
    if not _is_relative_to(resolved, root):
        raise ValueError("请求路径不在后台配置的下载根目录范围内。")
    if not resolved.exists():
        raise FileNotFoundError(f"未找到文件：{resolved}")
    if not resolved.is_file():
        raise ValueError(f"请求路径不是文件：{resolved}")
    suffix = resolved.suffix.lower()
    if suffix not in suffixes:
        allowed = "、".join(sorted(suffixes))
        raise ValueError(f"不允许下载 {suffix or '无后缀'} 文件，仅允许：{allowed}")
    size = resolved.stat().st_size
    if size > max_file_bytes:
        limit_mb = max_file_bytes / 1024 / 1024
        raise ValueError(f"文件超过大小限制（{limit_mb:.0f}MB），请缩小后再发送。")
    return DownloadResolution(
        path=resolved,
        root=root,
        source_kind=source_kind,
        display_name=resolved.name,
        size_bytes=size,
        svn_update_output=svn_update_output,
    )


def _existing_matches(relative_path: Path, roots: list[Path]) -> list[tuple[Path, Path]]:
    matches: list[tuple[Path, Path]] = []
    for root in roots:
        candidate = (root / relative_path).resolve(strict=False)
        if not _is_relative_to(candidate, root):
            continue
        if candidate.is_file():
            matches.append((candidate, root))
    return matches


def _normalize_query_directory(raw_directory: str) -> Path:
    raw = (raw_directory or ".").strip()
    if raw in {"", "."}:
        return Path(".")
    if _looks_like_remote_svn_url(raw):
        raise ValueError("第一版暂不支持远端 SVN URL，请使用后台配置的本机 SVN 工作副本路径。")
    candidate = Path(raw).expanduser()
    _reject_relative_escape(candidate)
    return candidate


def _list_query_entries(
    directory: Path,
    *,
    relative_dir: Path,
    suffixes: set[str],
    prefix_key: str,
) -> list[str]:
    if not directory.exists():
        raise FileNotFoundError(f"目录不存在：{directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"查询目标不是目录：{directory}")

    dirs: list[str] = []
    files: list[str] = []
    prefix_parts = () if str(relative_dir) in {"", "."} else relative_dir.parts
    for child in directory.iterdir():
        name = child.name
        if prefix_key and not name.lower().startswith(prefix_key):
            continue
        display_name = _format_query_entry_path(prefix_parts, name)
        if child.is_dir():
            dirs.append(f"{display_name}/")
            continue
        if child.is_file() and child.suffix.lower() in suffixes:
            files.append(display_name)
    dirs.sort(key=str.lower)
    files.sort(key=str.lower)
    return dirs + files


def _format_query_entry_path(prefix_parts: tuple[str, ...], name: str) -> str:
    parts = [part for part in (*prefix_parts, name) if part and part != "."]
    return "\\".join(parts) if parts else name


def _format_query_group_error(exc: BaseException, *, root: Path, target: Path) -> str:
    if isinstance(exc, FileNotFoundError):
        return "目录不存在"
    if isinstance(exc, NotADirectoryError):
        return "查询目标不是目录"
    message = str(exc) or exc.__class__.__name__
    for path in (target, root):
        path_text = str(path)
        if path_text:
            message = message.replace(path_text, "<配置目录>")
    return message


def _normalize_roots(raw_roots: list[str]) -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()
    for raw in raw_roots:
        if not raw or not str(raw).strip():
            continue
        path = Path(str(raw).strip()).expanduser()
        if not path.is_absolute():
            continue
        resolved = path.resolve(strict=False)
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        roots.append(resolved)
    roots.sort(key=lambda item: len(str(item)), reverse=True)
    return roots


def _normalize_suffixes(raw_suffixes: list[str] | None) -> set[str]:
    suffixes: set[str] = set()
    for raw in raw_suffixes or DEFAULT_DOWNLOAD_SUFFIXES:
        suffix = str(raw).strip().lower()
        if not suffix:
            continue
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        if suffix != "." and "\\" not in suffix and "/" not in suffix:
            suffixes.add(suffix)
    return suffixes or set(DEFAULT_DOWNLOAD_SUFFIXES)


def _find_containing_root(path: Path, roots: list[Path]) -> Path | None:
    for root in roots:
        if _is_relative_to(path, root):
            return root
    return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _same_path(left: Path, right: Path) -> bool:
    return str(left.expanduser().resolve(strict=False)).lower() == str(
        right.expanduser().resolve(strict=False)
    ).lower()


def _reject_relative_escape(path: Path) -> None:
    if path.is_absolute() or path.anchor:
        raise ValueError("相对下载路径不能包含盘符或根路径。")
    if any(part == ".." for part in path.parts):
        raise ValueError("下载路径不能包含 ..。")


def _looks_like_remote_svn_url(raw: str) -> bool:
    parsed = urlparse(raw)
    return parsed.scheme.lower() in _REMOTE_SVN_SCHEMES and bool(parsed.netloc)


def _strip_wrapping_quotes(raw: str) -> str:
    if len(raw) < 2:
        return raw
    quote_pairs = {('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’")}
    first = raw[0]
    last = raw[-1]
    if (first, last) in quote_pairs:
        return raw[1:-1].strip()
    return raw


def _split_command_args(raw: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    quote_end = ""
    quote_pairs = {'"': '"', "'": "'", "“": "”", "‘": "’"}
    for char in raw:
        if quote_end:
            if char == quote_end:
                quote_end = ""
            else:
                current.append(char)
            continue
        if char in quote_pairs:
            quote_end = quote_pairs[char]
            continue
        if char.isspace():
            if current:
                tokens.append("".join(current))
                current = []
            continue
        current.append(char)
    if quote_end:
        raise ValueError("查询参数引号不完整。")
    if current:
        tokens.append("".join(current))
    return tokens


__all__ = [
    "DEFAULT_DOWNLOAD_SUFFIXES",
    "DOWNLOAD_COMMAND",
    "DownloadResolution",
    "QUERY_COMMAND",
    "QueryListingGroup",
    "QueryRequest",
    "extract_download_path",
    "extract_query_request",
    "parse_json_string_list",
    "resolve_query_listing",
    "resolve_download_file",
]
