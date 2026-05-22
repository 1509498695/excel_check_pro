"""SVN 数据同步与能力探测。"""

from __future__ import annotations

import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlsplit, urlunsplit

from backend.app.api.schemas import DataSource
from backend.app.loaders.svn_credentials import SvnCredential
from backend.config import settings

try:
    import psutil
except ImportError:  # pragma: no cover - 依赖安装缺失时由调用路径给出中文提示
    psutil = None  # type: ignore[assignment]


# SVN 命令统一注入的「非交互 + 自签证书放行」参数，避免在 uvicorn 子进程里挂死。
_SVN_NONINTERACTIVE_FLAGS: tuple[str, ...] = (
    "--non-interactive",
    "--trust-server-cert-failures",
    "unknown-ca,cn-mismatch,not-yet-valid,expired,other",
)

_PROCESS_CLOSE_TIMEOUT_SECONDS = 5
_LOCAL_WORKING_COPY_LOCK_PATTERNS: tuple[str, ...] = (
    "working copy locked",
    "working copy is locked",
    "run 'svn cleanup'",
    "run \"svn cleanup\"",
    "cleanup required",
    "sqlite",
    "database is locked",
    "e155004",
    "e155007",
)
_FILE_BUSY_PATTERNS: tuple[str, ...] = (
    "sharing violation",
    "being used by another process",
    "process cannot access the file",
    "access is denied",
    "permission denied",
    "e720032",
    "e720005",
)
_SVN_FILE_LOCK_PATTERNS: tuple[str, ...] = (
    "locked by user",
    "already locked",
    "no lock token",
    "lock token",
    "e195022",
    "e160035",
)


@dataclass(frozen=True)
class ClosedFileProcess:
    """一次目标文件占用进程关闭结果。"""

    pid: int
    name: str
    action: str


class SvnRemoteError(RuntimeError):
    """带分类信息的 SVN 远端错误。"""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


class FileOccupancyError(RuntimeError):
    """关闭占用目标文件的进程失败。"""


def resolve_svn_executable() -> str | None:
    """解析当前环境中可用的 SVN 可执行文件。"""
    configured = _normalize_executable_token(settings.svn_executable)
    resolved = _resolve_configured_executable(configured)
    if resolved is not None:
        return resolved

    if not _is_windows_environment():
        return None

    for candidate in _iter_windows_svn_executables():
        if candidate.is_file():
            return str(candidate.resolve(strict=False))

    return None


def update_svn_working_copy(
    working_copy: Path,
    *,
    update_target: Path | None = None,
    target_file: Path | None = None,
    close_target_file: bool = False,
    cleanup_on_lock: bool = True,
) -> dict[str, Any]:
    """对指定目录执行一次 SVN update，并按需恢复常见本地异常。

    ``update_target`` 用于只更新工作副本内的某个相对路径，未传时更新整目录。
    ``target_file`` 仅由飞书下载链路传入：只关闭持有该目标文件句柄的进程，
    不扫描或关闭整个工作副本目录，避免误伤。
    """
    executable = resolve_svn_executable()
    if executable is None:
        raise NotImplementedError(
            "当前环境未检测到 svn 命令，请先安装 SVN CLI，或在后端配置中指定 svn 可执行文件路径。"
        )

    if not working_copy.exists():
        raise FileNotFoundError(f"SVN 工作目录不存在：'{working_copy}'。")
    if not working_copy.is_dir():
        raise ValueError(f"SVN 更新目标不是目录：'{working_copy}'。")

    resolved_update_target = _normalize_update_target(working_copy, update_target)
    resolved_target = _normalize_target_file(target_file)
    closed_processes: list[ClosedFileProcess] = []
    recovery_steps: list[str] = []
    completed = _run_svn_working_copy_command(
        executable,
        working_copy,
        "update",
        target_path=resolved_update_target,
    )
    combined_output = _combined_completed_output(completed)

    if completed.returncode != 0:
        combined_output = _recover_and_retry_update(
            executable=executable,
            working_copy=working_copy,
            first_error=combined_output,
            update_target=resolved_update_target,
            target_file=resolved_target,
            close_target_file=close_target_file,
            cleanup_on_lock=cleanup_on_lock,
            closed_processes=closed_processes,
            recovery_steps=recovery_steps,
        )

    return {
        "output": combined_output,
        "used_executable": executable,
        "closed_processes": [
            {"pid": item.pid, "name": item.name, "action": item.action}
            for item in closed_processes
        ],
        "recovery_steps": recovery_steps,
    }


def close_processes_using_file(target_file: Path) -> list[ClosedFileProcess]:
    """关闭持有目标文件句柄的进程；仅处理这一个文件。"""
    if psutil is None:
        raise FileOccupancyError("关闭占用文件需要安装 psutil 依赖。")

    target = target_file.resolve(strict=False)
    matched_processes = _find_processes_using_file(target)
    closed: list[ClosedFileProcess] = []
    for process in matched_processes:
        pid = int(process.pid)
        name = _safe_process_name(process)
        try:
            process.terminate()
            try:
                process.wait(timeout=_PROCESS_CLOSE_TIMEOUT_SECONDS)
                closed.append(ClosedFileProcess(pid=pid, name=name, action="terminate"))
                continue
            except psutil.TimeoutExpired:  # type: ignore[union-attr]
                process.kill()
                process.wait(timeout=_PROCESS_CLOSE_TIMEOUT_SECONDS)
                closed.append(ClosedFileProcess(pid=pid, name=name, action="kill"))
        except (
            psutil.AccessDenied,  # type: ignore[union-attr]
            psutil.NoSuchProcess,  # type: ignore[union-attr]
            psutil.TimeoutExpired,  # type: ignore[union-attr]
            OSError,
        ) as exc:
            raise FileOccupancyError(
                f"无法关闭占用文件的进程：{name}(PID {pid})，请手动关闭后重试。"
            ) from exc
    return closed


def _recover_and_retry_update(
    *,
    executable: str,
    working_copy: Path,
    first_error: str,
    update_target: Path | None,
    target_file: Path | None,
    close_target_file: bool,
    cleanup_on_lock: bool,
    closed_processes: list[ClosedFileProcess],
    recovery_steps: list[str],
) -> str:
    lower_output = first_error.lower()
    if "not a working copy" in lower_output:
        raise ValueError(f"目标目录不是 SVN 工作副本：'{working_copy}'。")
    if _is_svn_file_lock_error(lower_output):
        raise ValueError("目标文件存在 SVN 锁，请锁持有人释放后重试。")

    if cleanup_on_lock and _is_local_working_copy_lock_error(lower_output):
        cleanup_result = _run_svn_working_copy_command(
            executable,
            working_copy,
            "cleanup",
        )
        cleanup_output = _combined_completed_output(cleanup_result)
        if cleanup_result.returncode != 0:
            raise ValueError(
                f"SVN cleanup 失败：{cleanup_output or '命令返回非零退出码。'}"
            )
        recovery_steps.append("cleanup")
        retry_result = _run_svn_working_copy_command(
            executable,
            working_copy,
            "update",
            target_path=update_target,
        )
        retry_output = _combined_completed_output(retry_result)
        if retry_result.returncode == 0:
            return retry_output
        if _is_svn_file_lock_error(retry_output.lower()):
            raise ValueError("目标文件存在 SVN 锁，请锁持有人释放后重试。")
        first_error = retry_output
        lower_output = retry_output.lower()

    if close_target_file and target_file is not None and _is_file_busy_error(lower_output):
        closed_processes.extend(close_processes_using_file(target_file))
        recovery_steps.append("close_target_file")
        retry_result = _run_svn_working_copy_command(
            executable,
            working_copy,
            "update",
            target_path=update_target,
        )
        retry_output = _combined_completed_output(retry_result)
        if retry_result.returncode == 0:
            return retry_output
        if _is_svn_file_lock_error(retry_output.lower()):
            raise ValueError("目标文件存在 SVN 锁，请锁持有人释放后重试。")
        first_error = retry_output

    raise ValueError(f"SVN 更新失败：{first_error or '命令返回非零退出码。'}")


def _run_svn_working_copy_command(
    executable: str,
    working_copy: Path,
    command: str,
    *,
    target_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    args = [executable, command]
    if target_path is not None:
        args.append(str(target_path))
    return subprocess.run(
        args,
        cwd=str(working_copy),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,
    )


def _combined_completed_output(completed: subprocess.CompletedProcess[str]) -> str:
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    return "\n".join(part for part in (stdout, stderr) if part).strip()


def _normalize_target_file(target_file: Path | None) -> Path | None:
    if target_file is None:
        return None
    return Path(target_file).expanduser().resolve(strict=False)


def _normalize_update_target(
    working_copy: Path,
    update_target: Path | None,
) -> Path | None:
    if update_target is None:
        return None
    root = Path(working_copy).expanduser().resolve(strict=False)
    target = Path(update_target).expanduser()
    resolved = (
        target.resolve(strict=False)
        if target.is_absolute()
        else (root / target).resolve(strict=False)
    )
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"SVN 更新目标不在工作副本内：'{resolved}'。") from exc
    if str(relative) in {"", "."}:
        return None
    return relative


def _find_processes_using_file(target_file: Path) -> list[Any]:
    if psutil is None:
        raise FileOccupancyError("关闭占用文件需要安装 psutil 依赖。")

    result: list[Any] = []
    target_key = _path_key(target_file)
    for process in psutil.process_iter(["pid", "name"]):  # type: ignore[union-attr]
        try:
            for opened_file in process.open_files() or []:
                path = getattr(opened_file, "path", "")
                if path and _path_key(Path(path)) == target_key:
                    result.append(process)
                    break
        except (
            psutil.AccessDenied,  # type: ignore[union-attr]
            psutil.NoSuchProcess,  # type: ignore[union-attr]
            OSError,
        ):
            continue
    return result


def _safe_process_name(process: Any) -> str:
    try:
        return str(process.name() or "unknown")
    except Exception:  # noqa: BLE001
        return "unknown"


def _path_key(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False)).lower()


def _is_local_working_copy_lock_error(lower_output: str) -> bool:
    return any(pattern in lower_output for pattern in _LOCAL_WORKING_COPY_LOCK_PATTERNS)


def _is_file_busy_error(lower_output: str) -> bool:
    return any(pattern in lower_output for pattern in _FILE_BUSY_PATTERNS)


def _is_svn_file_lock_error(lower_output: str) -> bool:
    return any(pattern in lower_output for pattern in _SVN_FILE_LOCK_PATTERNS)


def sync_svn_source(source: DataSource) -> None:
    """按数据源配置执行一次 SVN update。"""
    raw_path = source.path or source.pathOrUrl
    if not raw_path:
        raise ValueError(f"SVN source '{source.id}' 缺少 path 或 pathOrUrl。")

    source_path = Path(raw_path).expanduser()
    working_copy = source_path if source_path.is_dir() else source_path.parent
    update_svn_working_copy(working_copy)


def _normalize_executable_token(raw_value: str) -> str:
    """规整配置中的 SVN 命令或路径。"""
    return raw_value.strip().strip('"').strip("'")


def _resolve_configured_executable(configured: str) -> str | None:
    """先按显式配置和 PATH 解析 SVN 可执行文件。"""
    if not configured:
        return None

    configured_path = Path(configured).expanduser()
    if configured_path.is_file():
        return str(configured_path.resolve(strict=False))

    discovered = shutil.which(configured)
    if discovered:
        return discovered

    return None


def _is_windows_environment() -> bool:
    """返回当前是否处于 Windows 运行环境。"""
    return os.name == "nt"


def _iter_windows_svn_executables() -> list[Path]:
    """在 Windows 上按常见安装位置枚举可用的 SVN CLI。"""
    candidates: list[Path] = []

    for raw_value in _read_tortoisesvn_registry_values():
        candidates.extend(_expand_windows_install_value(raw_value))

    for env_name in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(env_name, "").strip()
        if not root:
            continue
        candidates.append(Path(root) / "TortoiseSVN" / "bin" / "svn.exe")

    candidates.extend(
        [
            Path(r"C:\Program Files\TortoiseSVN\bin\svn.exe"),
            Path(r"C:\Program Files (x86)\TortoiseSVN\bin\svn.exe"),
        ]
    )

    unique_candidates: list[Path] = []
    seen_keys: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate).strip()
        if not normalized:
            continue
        candidate_path = Path(normalized)
        key = str(candidate_path).lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_candidates.append(candidate_path)

    return unique_candidates


def _read_tortoisesvn_registry_values() -> list[str]:
    """从注册表读取 TortoiseSVN 安装信息。"""
    try:
        import winreg
    except ImportError:
        return []

    values: list[str] = []
    registry_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\TortoiseSVN"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\TortoiseSVN"),
    ]
    value_names = ("Directory", "ProcPath", "CachePath", "TMergePath")

    for hive, subkey in registry_keys:
        try:
            with winreg.OpenKey(hive, subkey) as registry_key:
                for value_name in value_names:
                    try:
                        value, _ = winreg.QueryValueEx(registry_key, value_name)
                    except OSError:
                        continue
                    if isinstance(value, str) and value.strip():
                        values.append(_normalize_executable_token(value))
        except OSError:
            continue

    return values


def _expand_windows_install_value(raw_value: str) -> list[Path]:
    """把注册表中的目录或可执行文件路径展开为 SVN 候选路径。"""
    normalized = _normalize_executable_token(raw_value)
    if not normalized:
        return []

    value_path = Path(normalized)
    lower_name = value_path.name.lower()

    if lower_name == "svn.exe":
        return [value_path]
    if lower_name.endswith(".exe"):
        return [value_path.parent / "svn.exe"]
    return [value_path / "svn.exe", value_path / "bin" / "svn.exe"]


def normalize_dir_url(raw_url: str) -> str:
    """规整远端目录 URL：去首尾空格，强制末尾带 `/`。"""
    if not raw_url or not raw_url.strip():
        raise ValueError("SVN 目录 URL 不能为空。")
    candidate = raw_url.strip()
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("SVN 目录 URL 必须以 http(s):// 开头。")
    if not parsed.hostname:
        raise ValueError("SVN 目录 URL 缺少 host。")
    if not candidate.endswith("/"):
        candidate = candidate + "/"
    return candidate


def split_remote_url(file_or_dir_url: str) -> tuple[str, str]:
    """把单文件 URL 拆成 (dir_url, file_name)；目录 URL 返回 (dir_url, '')."""
    parsed = urlsplit(file_or_dir_url)
    path_segments = parsed.path.split("/")
    if file_or_dir_url.endswith("/") or not path_segments[-1]:
        # 目录 URL（已带斜杠）：file_name = ''
        normalized_path = parsed.path if parsed.path.endswith("/") else parsed.path + "/"
        return urlunsplit((parsed.scheme, parsed.netloc, normalized_path, "", "")), ""

    file_name = path_segments[-1]
    dir_path = "/".join(path_segments[:-1]) + "/"
    return (
        urlunsplit((parsed.scheme, parsed.netloc, dir_path, "", "")),
        file_name,
    )


def enforce_host_allowlist(host: str | None) -> str:
    """命中 settings.svn_url_allowlist 才允许；返回规整后的 host（lower）。"""
    if not host:
        raise ValueError("SVN 目录 URL 缺少 host。")
    normalized = host.strip().lower()
    allowlist = tuple(item.lower() for item in settings.svn_url_allowlist if item)
    if normalized not in allowlist:
        raise ValueError(
            f"SVN 主机 '{normalized}' 不在允许列表中。"
            "如需新增，请在后端 settings.svn_url_allowlist 显式添加。"
        )
    return normalized


def _translate_svn_stderr(stderr: str) -> tuple[str, str]:
    """把 SVN CLI 的 stderr 归类为 (category, msg)。"""
    text = (stderr or "").strip()
    lower = text.lower()
    if not text:
        return "unknown", "SVN 命令返回空错误信息。"

    if (
        "authorization failed" in lower
        or "authentication failed" in lower
        or "forbidden" in lower
        or "e170001" in lower
        or "e215004" in lower
    ):
        return "auth_failed", "当前账号无权访问测试目录，请检查 SVN 用户权限或重新输入凭据。"
    if (
        "non-existent" in lower
        or "not found" in lower
        or "e160013" in lower
        or "e170000" in lower
    ):
        return "not_found", "SVN 目录或文件不存在，或当前账号无权访问。"
    if (
        "could not connect" in lower
        or "unable to connect" in lower
        or "connection refused" in lower
        or "name or service not known" in lower
        or "e175002" in lower
        or "e670002" in lower
    ):
        return "network", "无法连接到 SVN 服务器，请检查网络与 URL。"
    return "unknown", text


def _build_credential_args(credentials: SvnCredential | None) -> list[str]:
    """凭据存在时显式带上 --username/--password，避免与 SVN 自带 auth cache 串扰。"""
    if credentials is None:
        return []
    return [
        "--username",
        credentials.username,
        "--password",
        credentials.password,
    ]


def _run_svn_subprocess(
    *,
    args: list[str],
    timeout: int,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """统一的 SVN 子进程封装。"""
    executable = resolve_svn_executable()
    if executable is None:
        raise NotImplementedError(
            "当前环境未检测到 svn 命令，请先安装 SVN CLI，"
            "或在后端配置中指定 svn 可执行文件路径。"
        )

    return subprocess.run(
        [executable, *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,
        timeout=timeout,
    )


def list_svn_directory(
    dir_url: str,
    *,
    credentials: SvnCredential | None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """`svn list <dir_url> --xml`，返回结构化目录条目。

    返回 dict 形如::

        {
            "dir_url": "https://samosvn/.../datas_qa88/",
            "entries": [
                {"kind": "file", "name": "...", "size": ..., "revision": ...,
                 "last_author": "...", "last_modified_at": "..."},
                ...
            ],
        }
    """
    normalized_dir_url = normalize_dir_url(dir_url)
    parsed_host = urlparse(normalized_dir_url).hostname
    enforce_host_allowlist(parsed_host)

    effective_timeout = timeout if timeout is not None else settings.svn_list_timeout_seconds

    args: list[str] = [
        "list",
        normalized_dir_url,
        "--xml",
        *_SVN_NONINTERACTIVE_FLAGS,
        *_build_credential_args(credentials),
    ]

    try:
        completed = _run_svn_subprocess(args=args, timeout=effective_timeout)
    except subprocess.TimeoutExpired as error:
        raise SvnRemoteError(
            "timeout",
            f"SVN 列表超时（>{effective_timeout}s），请稍后重试或缩小目录。",
        ) from error

    if completed.returncode != 0:
        category, message = _translate_svn_stderr(completed.stderr or completed.stdout or "")
        raise SvnRemoteError(category, message)

    return {
        "dir_url": normalized_dir_url,
        "entries": _parse_svn_list_xml(completed.stdout or ""),
    }


def _parse_svn_list_xml(xml_text: str) -> list[dict[str, Any]]:
    """解析 `svn list --xml` 输出。"""
    if not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        raise SvnRemoteError(
            "unknown",
            f"解析 SVN 列表 XML 失败：{error}",
        ) from error

    entries: list[dict[str, Any]] = []
    for entry in root.iter("entry"):
        kind = entry.get("kind", "")
        if kind not in {"file", "dir"}:
            continue
        name_element = entry.find("name")
        if name_element is None or not (name_element.text or "").strip():
            continue
        name = name_element.text.strip()

        size_element = entry.find("size")
        try:
            size_value = int(size_element.text) if size_element is not None and size_element.text else None
        except ValueError:
            size_value = None

        commit_element = entry.find("commit")
        revision_value: int | None = None
        author_value = ""
        last_modified_at = ""
        if commit_element is not None:
            try:
                revision_value = int(commit_element.get("revision", "")) if commit_element.get("revision") else None
            except ValueError:
                revision_value = None
            author_node = commit_element.find("author")
            if author_node is not None and author_node.text:
                author_value = author_node.text.strip()
            date_node = commit_element.find("date")
            if date_node is not None and date_node.text:
                last_modified_at = date_node.text.strip()

        entries.append(
            {
                "kind": kind,
                "name": name,
                "size": size_value,
                "revision": revision_value,
                "last_author": author_value,
                "last_modified_at": last_modified_at,
            }
        )

    # dir 优先、按 name 升序，方便前端直接渲染。
    entries.sort(key=lambda item: (0 if item["kind"] == "dir" else 1, item["name"].lower()))
    return entries


def checkout_remote_directory(
    *,
    dir_url: str,
    target_dir: Path,
    credentials: SvnCredential | None,
    depth: str = "files",
    timeout: int | None = None,
) -> dict[str, Any]:
    """`svn checkout --depth=<depth> <dir_url> <target_dir>`。"""
    normalized_dir_url = normalize_dir_url(dir_url)
    enforce_host_allowlist(urlparse(normalized_dir_url).hostname)
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    effective_timeout = (
        timeout if timeout is not None else settings.svn_subprocess_timeout_seconds
    )

    args: list[str] = [
        "checkout",
        f"--depth={depth}",
        normalized_dir_url,
        str(target_dir),
        *_SVN_NONINTERACTIVE_FLAGS,
        *_build_credential_args(credentials),
    ]

    try:
        completed = _run_svn_subprocess(args=args, timeout=effective_timeout)
    except subprocess.TimeoutExpired as error:
        raise SvnRemoteError(
            "timeout",
            f"SVN 拉取超时（>{effective_timeout}s）。",
        ) from error

    if completed.returncode != 0:
        category, message = _translate_svn_stderr(completed.stderr or "")
        raise SvnRemoteError(category, message)

    return {"output": (completed.stdout or "").strip()}


def update_remote_cache_directory(
    *,
    cache_dir: Path,
    credentials: SvnCredential | None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """对已存在的 cache 目录执行 `svn update --depth=files`。"""
    if not cache_dir.is_dir():
        raise FileNotFoundError(f"SVN 缓存目录不存在：'{cache_dir}'。")

    effective_timeout = (
        timeout if timeout is not None else settings.svn_subprocess_timeout_seconds
    )

    args: list[str] = [
        "update",
        "--depth=files",
        *_SVN_NONINTERACTIVE_FLAGS,
        *_build_credential_args(credentials),
    ]

    try:
        completed = _run_svn_subprocess(
            args=args,
            timeout=effective_timeout,
            cwd=cache_dir,
        )
    except subprocess.TimeoutExpired as error:
        raise SvnRemoteError(
            "timeout",
            f"SVN 更新超时（>{effective_timeout}s）。",
        ) from error

    if completed.returncode != 0:
        category, message = _translate_svn_stderr(completed.stderr or "")
        raise SvnRemoteError(category, message)

    return {"output": (completed.stdout or "").strip()}


def get_remote_revision(
    cache_dir: Path,
    *,
    credentials: SvnCredential | None = None,
    timeout: int | None = None,
) -> int | None:
    """`svn info --show-item revision`，读取 cache_dir 当前 working revision。"""
    if not cache_dir.is_dir():
        return None

    effective_timeout = (
        timeout if timeout is not None else settings.svn_list_timeout_seconds
    )

    args: list[str] = [
        "info",
        "--show-item",
        "revision",
        "--no-newline",
        *_SVN_NONINTERACTIVE_FLAGS,
        *_build_credential_args(credentials),
    ]

    try:
        completed = _run_svn_subprocess(
            args=args,
            timeout=effective_timeout,
            cwd=cache_dir,
        )
    except subprocess.TimeoutExpired:
        return None

    if completed.returncode != 0:
        return None

    raw = (completed.stdout or "").strip()
    try:
        return int(raw) if raw else None
    except ValueError:
        return None
