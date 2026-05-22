"""SVN 可执行文件发现与工作副本更新测试。"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.loaders import svn_manager
from backend.config import Settings


def test_resolve_svn_executable_prefers_configured_absolute_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式配置为绝对路径时，应优先直接命中。"""
    executable_path = tmp_path / "svn.exe"
    executable_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        svn_manager,
        "settings",
        Settings(svn_executable=str(executable_path)),
    )
    monkeypatch.setattr(svn_manager.shutil, "which", lambda _: None)

    resolved = svn_manager.resolve_svn_executable()

    assert resolved == str(executable_path.resolve())


def test_resolve_svn_executable_falls_back_to_path_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式配置未命中时，应继续尝试 PATH。"""
    discovered_path = r"C:\tools\svn.exe"
    monkeypatch.setattr(
        svn_manager,
        "settings",
        Settings(svn_executable="svn"),
    )
    monkeypatch.setattr(svn_manager.shutil, "which", lambda _: discovered_path)

    resolved = svn_manager.resolve_svn_executable()

    assert resolved == discovered_path


def test_resolve_svn_executable_uses_windows_auto_detection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当 PATH 未命中时，应能继续走 Windows 自动探测。"""
    executable_path = tmp_path / "svn.exe"
    executable_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        svn_manager,
        "settings",
        Settings(svn_executable="svn"),
    )
    monkeypatch.setattr(svn_manager.shutil, "which", lambda _: None)
    monkeypatch.setattr(svn_manager, "_is_windows_environment", lambda: True)
    monkeypatch.setattr(
        svn_manager,
        "_iter_windows_svn_executables",
        lambda: [executable_path],
    )

    resolved = svn_manager.resolve_svn_executable()

    assert resolved == str(executable_path.resolve())


def test_update_svn_working_copy_returns_output_and_used_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """更新成功时，应返回输出和实际使用的可执行文件。"""
    executable_path = tmp_path / "svn.exe"
    working_copy = tmp_path / "working-copy"
    executable_path.write_text("", encoding="utf-8")
    working_copy.mkdir()
    monkeypatch.setattr(
        svn_manager,
        "resolve_svn_executable",
        lambda: str(executable_path.resolve()),
    )
    monkeypatch.setattr(
        svn_manager.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="At revision 449834.\n",
            stderr="",
        ),
    )

    result = svn_manager.update_svn_working_copy(working_copy)

    assert result["used_executable"] == str(executable_path.resolve())
    assert "449834" in result["output"]
    assert result["closed_processes"] == []
    assert result["recovery_steps"] == []


def test_update_svn_working_copy_success_does_not_scan_processes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    working_copy = tmp_path / "working-copy"
    target_file = working_copy / "a.xlsx"
    working_copy.mkdir()
    target_file.write_bytes(b"x")
    psutil_fake = _fake_psutil([])

    def fail_process_iter(attrs=None):  # noqa: ANN001
        raise AssertionError("process scan should only happen after file-busy errors")

    psutil_fake.process_iter = fail_process_iter
    monkeypatch.setattr(svn_manager, "resolve_svn_executable", lambda: "svn")
    monkeypatch.setattr(svn_manager, "psutil", psutil_fake)
    monkeypatch.setattr(
        svn_manager.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="At revision 10.\n",
            stderr="",
        ),
    )

    result = svn_manager.update_svn_working_copy(
        working_copy,
        target_file=target_file,
        close_target_file=True,
    )

    assert "revision 10" in result["output"]
    assert result["closed_processes"] == []


def test_update_svn_working_copy_cleanup_then_retries_on_local_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    working_copy = tmp_path / "working-copy"
    working_copy.mkdir()
    calls: list[list[str]] = []
    responses = iter(
        [
            subprocess.CompletedProcess(
                args=["svn", "update"],
                returncode=1,
                stdout="",
                stderr="svn: E155004: Working copy locked; run 'svn cleanup'",
            ),
            subprocess.CompletedProcess(
                args=["svn", "cleanup"],
                returncode=0,
                stdout="",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["svn", "update"],
                returncode=0,
                stdout="At revision 9.\n",
                stderr="",
            ),
        ]
    )
    monkeypatch.setattr(svn_manager, "resolve_svn_executable", lambda: "svn")

    def fake_run(args, **kwargs):  # noqa: ANN001
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(svn_manager.subprocess, "run", fake_run)

    result = svn_manager.update_svn_working_copy(working_copy)

    assert calls == [["svn", "update"], ["svn", "cleanup"], ["svn", "update"]]
    assert result["recovery_steps"] == ["cleanup"]
    assert "revision 9" in result["output"]


def test_update_svn_working_copy_local_lock_does_not_scan_processes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    working_copy = tmp_path / "working-copy"
    target_file = working_copy / "a.xlsx"
    working_copy.mkdir()
    target_file.write_bytes(b"x")
    responses = iter(
        [
            subprocess.CompletedProcess(
                args=["svn", "update"],
                returncode=1,
                stdout="",
                stderr="svn: E155004: Working copy locked; run 'svn cleanup'",
            ),
            subprocess.CompletedProcess(
                args=["svn", "cleanup"],
                returncode=0,
                stdout="",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["svn", "update"],
                returncode=0,
                stdout="At revision 12.\n",
                stderr="",
            ),
        ]
    )
    psutil_fake = _fake_psutil([])

    def fail_process_iter(attrs=None):  # noqa: ANN001
        raise AssertionError("cleanup recovery should not scan processes")

    psutil_fake.process_iter = fail_process_iter
    monkeypatch.setattr(svn_manager, "resolve_svn_executable", lambda: "svn")
    monkeypatch.setattr(svn_manager, "psutil", psutil_fake)
    monkeypatch.setattr(svn_manager.subprocess, "run", lambda *args, **kwargs: next(responses))

    result = svn_manager.update_svn_working_copy(
        working_copy,
        target_file=target_file,
        close_target_file=True,
    )

    assert result["recovery_steps"] == ["cleanup"]
    assert "revision 12" in result["output"]


def test_update_svn_working_copy_reports_cleanup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    working_copy = tmp_path / "working-copy"
    working_copy.mkdir()
    responses = iter(
        [
            subprocess.CompletedProcess(
                args=["svn", "update"],
                returncode=1,
                stdout="",
                stderr="svn: E155004: Working copy locked; run 'svn cleanup'",
            ),
            subprocess.CompletedProcess(
                args=["svn", "cleanup"],
                returncode=1,
                stdout="",
                stderr="cleanup failed",
            ),
        ]
    )
    monkeypatch.setattr(svn_manager, "resolve_svn_executable", lambda: "svn")
    monkeypatch.setattr(svn_manager.subprocess, "run", lambda *args, **kwargs: next(responses))

    with pytest.raises(ValueError, match="SVN cleanup 失败"):
        svn_manager.update_svn_working_copy(working_copy)


def test_update_svn_working_copy_file_busy_closes_and_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    working_copy = tmp_path / "working-copy"
    target_file = working_copy / "a.xlsx"
    working_copy.mkdir()
    target_file.write_bytes(b"x")
    process = _FakeProcess(pid=456, name="wps.exe", open_paths=[target_file])
    responses = iter(
        [
            subprocess.CompletedProcess(
                args=["svn", "update"],
                returncode=1,
                stdout="",
                stderr="The process cannot access the file because it is being used by another process.",
            ),
            subprocess.CompletedProcess(
                args=["svn", "update"],
                returncode=0,
                stdout="At revision 11.\n",
                stderr="",
            ),
        ]
    )
    monkeypatch.setattr(svn_manager, "resolve_svn_executable", lambda: "svn")
    monkeypatch.setattr(svn_manager, "psutil", _fake_psutil([process]))
    monkeypatch.setattr(svn_manager.subprocess, "run", lambda *args, **kwargs: next(responses))

    result = svn_manager.update_svn_working_copy(
        working_copy,
        target_file=target_file,
        close_target_file=True,
    )

    assert process.terminated is True
    assert process.killed is False
    assert result["closed_processes"] == [
        {"pid": 456, "name": "wps.exe", "action": "terminate"}
    ]
    assert result["recovery_steps"] == ["close_target_file"]
    assert "revision 11" in result["output"]


def test_update_svn_working_copy_reports_close_process_access_denied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    working_copy = tmp_path / "working-copy"
    target_file = working_copy / "a.xlsx"
    working_copy.mkdir()
    target_file.write_bytes(b"x")
    process = _FakeProcess(
        pid=789,
        name="EXCEL.EXE",
        open_paths=[target_file],
        terminate_error=_FakeAccessDenied("denied"),
    )
    psutil_fake = _fake_psutil([process])
    monkeypatch.setattr(svn_manager, "resolve_svn_executable", lambda: "svn")
    monkeypatch.setattr(svn_manager, "psutil", psutil_fake)
    monkeypatch.setattr(
        svn_manager.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="The process cannot access the file because it is being used by another process.",
        ),
    )

    with pytest.raises(svn_manager.FileOccupancyError, match="EXCEL.EXE\\(PID 789\\)"):
        svn_manager.update_svn_working_copy(
            working_copy,
            target_file=target_file,
            close_target_file=True,
        )


def test_update_svn_working_copy_svn_file_lock_does_not_force_unlock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    working_copy = tmp_path / "working-copy"
    working_copy.mkdir()
    calls: list[list[str]] = []
    monkeypatch.setattr(svn_manager, "resolve_svn_executable", lambda: "svn")

    def fake_run(args, **kwargs):  # noqa: ANN001
        calls.append(args)
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr="svn: E195022: Path is already locked by user 'zhangsan'",
        )

    monkeypatch.setattr(svn_manager.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="SVN 锁"):
        svn_manager.update_svn_working_copy(working_copy)

    assert calls == [["svn", "update"]]


def test_update_svn_working_copy_raises_clear_error_when_cli_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """当前环境无法发现 svn CLI 时，应返回明确中文提示。"""
    working_copy = tmp_path / "working-copy"
    working_copy.mkdir()
    monkeypatch.setattr(svn_manager, "resolve_svn_executable", lambda: None)

    with pytest.raises(NotImplementedError, match="svn 命令"):
        svn_manager.update_svn_working_copy(working_copy)


def _stub_svn_run(
    *,
    stdout: str = "",
    stderr: str = "",
    returncode: int = 0,
    raise_timeout: bool = False,
):
    def _runner(args, **kwargs):
        if raise_timeout:
            raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs.get("timeout", 1))
        return subprocess.CompletedProcess(
            args=args,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    return _runner


class _FakeAccessDenied(Exception):
    pass


class _FakeNoSuchProcess(Exception):
    pass


class _FakeTimeoutExpired(Exception):
    pass


class _FakeProcess:
    def __init__(
        self,
        *,
        pid: int,
        name: str,
        open_paths: list[Path],
        terminate_error: Exception | None = None,
    ) -> None:
        self.pid = pid
        self._name = name
        self._open_paths = open_paths
        self._terminate_error = terminate_error
        self.terminated = False
        self.killed = False

    def name(self) -> str:
        return self._name

    def open_files(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(path=str(path)) for path in self._open_paths]

    def terminate(self) -> None:
        if self._terminate_error is not None:
            raise self._terminate_error
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: int) -> None:  # noqa: ARG002
        return None


def _fake_psutil(processes: list[_FakeProcess]) -> SimpleNamespace:
    return SimpleNamespace(
        AccessDenied=_FakeAccessDenied,
        NoSuchProcess=_FakeNoSuchProcess,
        TimeoutExpired=_FakeTimeoutExpired,
        process_iter=lambda attrs=None: processes,  # noqa: ARG005
    )


_SAMPLE_LIST_XML = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<lists>
  <list path=\"https://samosvn/data/project/samo/GameDatas/datas_qa88\">
    <entry kind=\"file\">
      <name>quests.xls</name>
      <size>4521984</size>
      <commit revision=\"11823\">
        <author>liming</author>
        <date>2026-04-18T03:11:09.123456Z</date>
      </commit>
    </entry>
    <entry kind=\"file\">
      <name>items.xlsx</name>
      <size>32100</size>
      <commit revision=\"11900\">
        <author>wangwu</author>
        <date>2026-04-19T05:00:00Z</date>
      </commit>
    </entry>
    <entry kind=\"dir\">
      <name>archive</name>
      <commit revision=\"11500\">
        <author>liu</author>
        <date>2026-04-12T09:00:00Z</date>
      </commit>
    </entry>
  </list>
</lists>
"""


def test_list_svn_directory_parses_xml_and_sorts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """正向：能正确解析 XML，dir 在前，file 按 name 升序。"""
    monkeypatch.setattr(svn_manager, "resolve_svn_executable", lambda: "svn")
    monkeypatch.setattr(
        svn_manager.subprocess,
        "run",
        _stub_svn_run(stdout=_SAMPLE_LIST_XML),
    )

    result = svn_manager.list_svn_directory(
        "https://samosvn/data/project/samo/GameDatas/datas_qa88",
        credentials=None,
    )

    assert result["dir_url"].endswith("/datas_qa88/")
    entries = result["entries"]
    # dir 在前，file 按 name 升序
    assert [item["kind"] for item in entries] == ["dir", "file", "file"]
    assert entries[0]["name"] == "archive"
    assert entries[1]["name"] == "items.xlsx"
    assert entries[2]["name"] == "quests.xls"
    assert entries[2]["size"] == 4521984
    assert entries[2]["revision"] == 11823


def test_list_svn_directory_rejects_host_outside_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非白名单 host 直接 ValueError，不会触达 subprocess。"""
    import dataclasses

    monkeypatch.setattr(
        svn_manager,
        "settings",
        dataclasses.replace(svn_manager.settings, svn_url_allowlist=("samosvn",)),
    )
    monkeypatch.setattr(svn_manager, "resolve_svn_executable", lambda: "svn")

    with pytest.raises(ValueError, match="不在允许列表中"):
        svn_manager.list_svn_directory(
            "https://evil.example.com/data/",
            credentials=None,
        )


def test_list_svn_directory_translates_authorization_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stderr 含 Authorization failed → SvnRemoteError(auth_failed)。"""
    monkeypatch.setattr(svn_manager, "resolve_svn_executable", lambda: "svn")
    monkeypatch.setattr(
        svn_manager.subprocess,
        "run",
        _stub_svn_run(returncode=1, stderr="svn: E170001: Authorization failed"),
    )

    with pytest.raises(svn_manager.SvnRemoteError) as info:
        svn_manager.list_svn_directory(
            "https://samosvn/data/project/samo/GameDatas/datas_qa88/",
            credentials=None,
        )
    assert info.value.category == "auth_failed"


def test_list_svn_directory_translates_forbidden_to_auth_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stderr 含 forbidden → 归类为鉴权/权限失败，而不是 unknown。"""
    monkeypatch.setattr(svn_manager, "resolve_svn_executable", lambda: "svn")
    monkeypatch.setattr(
        svn_manager.subprocess,
        "run",
        _stub_svn_run(
            returncode=1,
            stderr="svn: E175013: Access to '/data/project/samo' forbidden",
        ),
    )

    with pytest.raises(svn_manager.SvnRemoteError) as info:
        svn_manager.list_svn_directory(
            "https://samosvn/data/project/samo/",
            credentials=None,
        )
    assert info.value.category == "auth_failed"
    assert "无权访问测试目录" in info.value.message


def test_list_svn_directory_translates_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stderr 含 non-existent → SvnRemoteError(not_found)。"""
    monkeypatch.setattr(svn_manager, "resolve_svn_executable", lambda: "svn")
    monkeypatch.setattr(
        svn_manager.subprocess,
        "run",
        _stub_svn_run(returncode=1, stderr="svn: warning: W160013: 'X' path not found"),
    )

    with pytest.raises(svn_manager.SvnRemoteError) as info:
        svn_manager.list_svn_directory(
            "https://samosvn/data/project/samo/GameDatas/datas_qa88/",
            credentials=None,
        )
    assert info.value.category == "not_found"


def test_list_svn_directory_handles_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """subprocess timeout → SvnRemoteError(timeout)。"""
    monkeypatch.setattr(svn_manager, "resolve_svn_executable", lambda: "svn")
    monkeypatch.setattr(
        svn_manager.subprocess,
        "run",
        _stub_svn_run(raise_timeout=True),
    )

    with pytest.raises(svn_manager.SvnRemoteError) as info:
        svn_manager.list_svn_directory(
            "https://samosvn/data/project/samo/GameDatas/datas_qa88/",
            credentials=None,
        )
    assert info.value.category == "timeout"
