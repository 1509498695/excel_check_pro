"""飞书机器人下载命令与安全路径解析测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.integrations.feishu_download import (
    QueryRequest,
    extract_download_path,
    extract_query_request,
    resolve_query_listing,
    resolve_download_file,
)


def test_extract_download_path_supports_plain_and_quoted_paths() -> None:
    assert extract_download_path("@_user_1 下载 configs/a.xlsx") == "configs/a.xlsx"
    assert extract_download_path('@_user_1 下载 "sub dir/a.xlsx"') == "sub dir/a.xlsx"
    assert extract_download_path("@_user_1 下载") == ""
    assert extract_download_path("下载 configs/a.xlsx") is None
    assert extract_download_path("@_user_1 项目校验") is None


def test_extract_query_request_supports_directory_and_prefix() -> None:
    assert extract_query_request("@_user_1 查询") == QueryRequest()
    assert extract_query_request("@_user_1 查询 configs") == QueryRequest(
        directory="configs"
    )
    assert extract_query_request('@_user_1 查询 "sub dir" x') == QueryRequest(
        directory="sub dir",
        prefix="x",
    )
    assert extract_query_request("@_user_1 查询 . Ab") == QueryRequest(
        directory=".",
        prefix="Ab",
    )
    assert extract_query_request("@_user_1 下载 configs/a.xlsx") is None


def test_extract_query_request_rejects_unclosed_quote() -> None:
    with pytest.raises(ValueError, match="引号"):
        extract_query_request('@_user_1 查询 "sub dir')


def test_resolve_query_listing_groups_roots_and_filters_entries(tmp_path: Path) -> None:
    svn_root = tmp_path / "svn"
    local_root = tmp_path / "local"
    svn_root.mkdir()
    local_root.mkdir()
    (svn_root / "Zoo").mkdir()
    (svn_root / "Alpha.xlsx").write_bytes(b"x")
    (svn_root / "blocked.exe").write_bytes(b"x")
    (local_root / "child").mkdir()
    (local_root / "apple.txt").write_bytes(b"x")
    (local_root / "beta.xlsx").write_bytes(b"x")
    (local_root / "beta.exe").write_bytes(b"x")
    (local_root / "child" / "nested.xlsx").write_bytes(b"x")
    calls: list[Path] = []

    def fake_update(root: Path) -> dict[str, str]:
        calls.append(root)
        return {"output": "updated"}

    groups = resolve_query_listing(
        QueryRequest(directory=".", prefix="a"),
        local_roots=[str(local_root)],
        svn_roots=[str(svn_root)],
        allowed_suffixes=[".xlsx", ".txt"],
        update_working_copy=fake_update,
    )

    assert calls == [svn_root.resolve(strict=False)]
    assert [group.title for group in groups] == [
        f"SVN#1 {svn_root.name}",
        f"本地#1 {local_root.name}",
    ]
    assert groups[0].entries == ["Alpha.xlsx"]
    assert groups[1].entries == ["apple.txt"]


def test_resolve_query_listing_lists_directories_before_files(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    root.mkdir()
    (root / "Beta").mkdir()
    (root / "alpha").mkdir()
    (root / "c.txt").write_bytes(b"x")
    (root / "a.xlsx").write_bytes(b"x")
    (root / "skip.exe").write_bytes(b"x")

    groups = resolve_query_listing(
        QueryRequest(),
        local_roots=[str(root)],
        svn_roots=[],
        allowed_suffixes=[".xlsx", ".txt"],
    )

    assert groups[0].entries == ["alpha/", "Beta/", "a.xlsx", "c.txt"]


def test_resolve_query_listing_reports_missing_directory_without_path(
    tmp_path: Path,
) -> None:
    root = tmp_path / "configs"
    root.mkdir()

    groups = resolve_query_listing(
        QueryRequest(directory="missing"),
        local_roots=[str(root)],
        svn_roots=[],
        allowed_suffixes=[".xlsx"],
    )

    assert groups[0].entries == []
    assert groups[0].error == "目录不存在"
    assert str(root) not in groups[0].error


def test_resolve_query_listing_rejects_unsafe_directory(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    root.mkdir()

    with pytest.raises(ValueError, match=r"\.\."):
        resolve_query_listing(
            QueryRequest(directory="../configs"),
            local_roots=[str(root)],
            svn_roots=[],
            allowed_suffixes=[".xlsx"],
        )

    with pytest.raises(ValueError, match="远端 SVN URL"):
        resolve_query_listing(
            QueryRequest(directory="https://svn.example.com/configs"),
            local_roots=[str(root)],
            svn_roots=[],
            allowed_suffixes=[".xlsx"],
        )


def test_resolve_absolute_path_inside_configured_root(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    root.mkdir()
    file_path = root / "a.xlsx"
    file_path.write_bytes(b"xlsx")

    result = resolve_download_file(
        str(file_path),
        local_roots=[str(root)],
        svn_roots=[],
        allowed_suffixes=[".xlsx"],
        max_file_bytes=1024,
    )

    assert result.path == file_path.resolve(strict=False)
    assert result.source_kind == "local"
    assert result.display_name == "a.xlsx"


def test_resolve_rejects_path_outside_configured_root(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    root.mkdir()
    outside = tmp_path / "outside.xlsx"
    outside.write_bytes(b"x")

    with pytest.raises(ValueError, match="下载根目录"):
        resolve_download_file(
            str(outside),
            local_roots=[str(root)],
            svn_roots=[],
            allowed_suffixes=[".xlsx"],
            max_file_bytes=1024,
        )


def test_resolve_rejects_relative_escape(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    root.mkdir()

    with pytest.raises(ValueError, match=r"\.\."):
        resolve_download_file(
            "../a.xlsx",
            local_roots=[str(root)],
            svn_roots=[],
            allowed_suffixes=[".xlsx"],
            max_file_bytes=1024,
        )


def test_resolve_rejects_disallowed_suffix(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    root.mkdir()
    file_path = root / "a.exe"
    file_path.write_bytes(b"x")

    with pytest.raises(ValueError, match="不允许下载"):
        resolve_download_file(
            "a.exe",
            local_roots=[str(root)],
            svn_roots=[],
            allowed_suffixes=[".xlsx"],
            max_file_bytes=1024,
        )


def test_resolve_reports_ambiguous_relative_matches(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "same.xlsx").write_bytes(b"a")
    (root_b / "same.xlsx").write_bytes(b"b")

    with pytest.raises(ValueError, match="匹配到多个文件"):
        resolve_download_file(
            "same.xlsx",
            local_roots=[str(root_a), str(root_b)],
            svn_roots=[],
            allowed_suffixes=[".xlsx"],
            max_file_bytes=1024,
        )


def test_resolve_updates_svn_root_before_returning_file(tmp_path: Path) -> None:
    svn_root = tmp_path / "svn"
    svn_root.mkdir()
    file_path = svn_root / "a.xlsx"
    file_path.write_bytes(b"x")
    calls: list[tuple[Path, Path, bool, bool]] = []

    def fake_update(
        root: Path,
        *,
        target_file: Path,
        close_target_file: bool,
        cleanup_on_lock: bool,
    ) -> dict[str, str]:
        calls.append((root, target_file, close_target_file, cleanup_on_lock))
        return {"output": "updated"}

    result = resolve_download_file(
        "a.xlsx",
        local_roots=[],
        svn_roots=[str(svn_root)],
        allowed_suffixes=[".xlsx"],
        max_file_bytes=1024,
        update_working_copy=fake_update,
    )

    assert calls == [
        (
            svn_root.resolve(strict=False),
            file_path.resolve(strict=False),
            True,
            True,
        )
    ]
    assert result.source_kind == "svn"
    assert result.svn_update_output == "updated"


def test_resolve_updates_svn_relative_path_even_when_file_missing_before_update(
    tmp_path: Path,
) -> None:
    svn_root = tmp_path / "svn"
    svn_root.mkdir()
    file_path = svn_root / "generated.xlsx"
    calls: list[Path] = []

    def fake_update(root: Path, *, target_file: Path, **kwargs) -> dict[str, str]:  # noqa: ANN003
        calls.append(target_file)
        file_path.write_bytes(b"x")
        return {"output": "updated"}

    result = resolve_download_file(
        "generated.xlsx",
        local_roots=[],
        svn_roots=[str(svn_root)],
        allowed_suffixes=[".xlsx"],
        max_file_bytes=1024,
        update_working_copy=fake_update,
    )

    assert calls == [file_path.resolve(strict=False)]
    assert result.path == file_path.resolve(strict=False)
    assert result.source_kind == "svn"


def test_resolve_local_root_does_not_call_svn_update(tmp_path: Path) -> None:
    local_root = tmp_path / "local"
    local_root.mkdir()
    file_path = local_root / "a.xlsx"
    file_path.write_bytes(b"x")

    def fake_update(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("local downloads must not update svn")

    result = resolve_download_file(
        "a.xlsx",
        local_roots=[str(local_root)],
        svn_roots=[],
        allowed_suffixes=[".xlsx"],
        max_file_bytes=1024,
        update_working_copy=fake_update,
    )

    assert result.source_kind == "local"


def test_resolve_rejects_remote_svn_url(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    root.mkdir()

    with pytest.raises(ValueError, match="远端 SVN URL"):
        resolve_download_file(
            "https://svn.example.com/configs/a.xlsx",
            local_roots=[str(root)],
            svn_roots=[],
            allowed_suffixes=[".xlsx"],
            max_file_bytes=1024,
        )


def test_resolve_rejects_too_large_file(tmp_path: Path) -> None:
    root = tmp_path / "configs"
    root.mkdir()
    file_path = root / "a.xlsx"
    file_path.write_bytes(b"12345")

    with pytest.raises(ValueError, match="大小限制"):
        resolve_download_file(
            "a.xlsx",
            local_roots=[str(root)],
            svn_roots=[],
            allowed_suffixes=[".xlsx"],
            max_file_bytes=4,
        )
