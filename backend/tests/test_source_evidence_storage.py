"""Source Evidence 文件存储目录解析和路径安全测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.test_cases import source_evidence_storage
from backend.app.test_cases.source_evidence_storage import (
    SourceEvidenceStorageError,
    delete_source_evidence_path,
    ensure_source_evidence_run_dir,
    resolve_source_evidence_path,
    run_source_evidence_dir,
)


@pytest.fixture
def source_evidence_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "runtime" / "source-evidence"
    monkeypatch.setattr(
        source_evidence_storage,
        "settings",
        SimpleNamespace(source_evidence_dir=root),
    )
    return root


def test_run_directory_defaults_under_project_and_run(
    source_evidence_root: Path,
) -> None:
    """run 目录固定落在 source_evidence_dir/<project_id>/<run_id>/ 下。"""
    run_dir = run_source_evidence_dir(project_id=12, run_id=34)

    assert run_dir == source_evidence_root / "12" / "34"
    assert not run_dir.exists()
    assert ensure_source_evidence_run_dir(project_id=12, run_id=34) == run_dir
    assert run_dir.is_dir()


def test_resolve_source_evidence_path_allows_nested_relative_paths(
    source_evidence_root: Path,
) -> None:
    """相对资源路径可放在 run 目录内部。"""
    resolved = resolve_source_evidence_path(12, 34, "images", "a.png")

    assert resolved == source_evidence_root / "12" / "34" / "images" / "a.png"


@pytest.mark.parametrize(
    ("parts",),
    [
        (("../outside.txt",),),
        (("..", "outside.txt"),),
        ((Path("..") / "outside.txt",),),
        ((Path("C:/outside.txt"),),),
    ],
)
def test_resolve_source_evidence_path_rejects_escape_attempts(
    source_evidence_root: Path,
    parts: tuple[object, ...],
) -> None:
    """任何读写路径都不能逃出 source_evidence_dir。"""
    with pytest.raises(SourceEvidenceStorageError):
        resolve_source_evidence_path(12, 34, *parts)


def test_delete_helper_refuses_escape_and_deletes_only_inside_root(
    source_evidence_root: Path,
) -> None:
    """删除 helper 同样走安全解析，只能删除 source_evidence_dir 内部文件。"""
    run_dir = ensure_source_evidence_run_dir(project_id=12, run_id=34)
    file_path = run_dir / "raw.md"
    file_path.write_text("sensitive source text", encoding="utf-8")

    assert file_path.exists()
    assert delete_source_evidence_path(12, 34, "raw.md") is True
    assert not file_path.exists()

    outside = source_evidence_root.parent / "outside.md"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("must stay", encoding="utf-8")
    with pytest.raises(SourceEvidenceStorageError):
        delete_source_evidence_path(12, 34, "..", "outside.md")
    assert outside.read_text(encoding="utf-8") == "must stay"
