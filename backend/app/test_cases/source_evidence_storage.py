"""Source Evidence 本地存储路径解析和安全删除。"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

from backend.config import settings


class SourceEvidenceStorageError(ValueError):
    """Source Evidence 路径不安全或不合法。"""


def source_evidence_root() -> Path:
    """返回规范化后的 Source Evidence 根目录。"""
    return Path(settings.source_evidence_dir).expanduser().resolve(strict=False)


def run_source_evidence_dir(*, project_id: int, run_id: int) -> Path:
    """返回 source_evidence_dir/<project_id>/<run_id>。"""
    return _resolve_inside_root(str(project_id), str(run_id))


def ensure_source_evidence_run_dir(*, project_id: int, run_id: int) -> Path:
    """创建并返回当前 run 的存储目录。"""
    run_dir = run_source_evidence_dir(project_id=project_id, run_id=run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def ensure_source_evidence_subdirs(*, project_id: int, run_id: int) -> dict[str, Path]:
    """创建 run 需要的固定子目录。"""
    run_dir = ensure_source_evidence_run_dir(project_id=project_id, run_id=run_id)
    subdirs = {
        "run": run_dir,
        "raw": resolve_source_evidence_path(project_id, run_id, "raw"),
        "images": resolve_source_evidence_path(project_id, run_id, "images"),
        "attachments": resolve_source_evidence_path(project_id, run_id, "attachments"),
    }
    for path in subdirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return subdirs


def resolve_source_evidence_path(
    project_id: int,
    run_id: int,
    *relative_parts: object,
) -> Path:
    """解析 run 内部文件路径，拒绝绝对路径和 .. 逃逸。"""
    parts = [str(project_id), str(run_id)]
    parts.extend(_normalize_relative_parts(relative_parts))
    return _resolve_inside_root(*parts)


def delete_source_evidence_path(
    project_id: int,
    run_id: int,
    *relative_parts: object,
) -> bool:
    """安全删除 run 目录内的文件或子目录。"""
    path = resolve_source_evidence_path(project_id, run_id, *relative_parts)
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True


def clear_source_evidence_run_dir(*, project_id: int, run_id: int) -> None:
    """清空单个 run 目录内容，但保留 run 目录本身。"""
    run_dir = ensure_source_evidence_run_dir(project_id=project_id, run_id=run_id)
    run_root = run_dir.resolve(strict=True)
    for child in list(run_dir.iterdir()):
        _delete_run_dir_child(run_root, child)


def write_source_evidence_text(
    project_id: int,
    run_id: int,
    relative_path: object,
    content: str,
) -> Path:
    """安全写入 run 内 Markdown/text 文件。"""
    path = resolve_source_evidence_path(project_id, run_id, relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_source_evidence_bytes(
    project_id: int,
    run_id: int,
    relative_path: object,
    content: bytes,
) -> Path:
    """安全写入 run 内二进制资源文件。"""
    path = resolve_source_evidence_path(project_id, run_id, relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def read_source_evidence_text(
    project_id: int,
    run_id: int,
    relative_path: object,
) -> str:
    """安全读取 run 内文本文件。"""
    path = resolve_source_evidence_path(project_id, run_id, relative_path)
    return path.read_text(encoding="utf-8")


def write_source_evidence_json(
    project_id: int,
    run_id: int,
    relative_path: object,
    payload: Any,
) -> Path:
    """安全写入 run 内 JSON 文件。"""
    return write_source_evidence_text(
        project_id,
        run_id,
        relative_path,
        json.dumps(payload, ensure_ascii=False, indent=2),
    )


def read_source_evidence_json(
    project_id: int,
    run_id: int,
    relative_path: object,
) -> Any:
    """安全读取 run 内 JSON 文件。"""
    return json.loads(read_source_evidence_text(project_id, run_id, relative_path))


def _normalize_relative_parts(relative_parts: tuple[object, ...]) -> list[str]:
    normalized: list[str] = []
    for raw_part in relative_parts:
        part = Path(str(raw_part))
        if part.is_absolute():
            raise SourceEvidenceStorageError("Source Evidence 路径不能使用绝对路径。")
        for segment in part.parts:
            if segment in {"", "."}:
                continue
            if segment == "..":
                raise SourceEvidenceStorageError("Source Evidence 路径不能逃出根目录。")
            normalized.append(segment)
    return normalized


def _resolve_inside_root(*parts: str) -> Path:
    root = source_evidence_root()
    candidate = root.joinpath(*parts).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SourceEvidenceStorageError("Source Evidence 路径必须位于根目录内。") from exc
    return candidate


def _delete_run_dir_child(run_root: Path, child: Path) -> None:
    """删除 run 根目录下的单个直接子项，不跟随 symlink/junction。"""
    try:
        child.parent.resolve(strict=True).relative_to(run_root)
    except ValueError as exc:
        raise SourceEvidenceStorageError("Source Evidence 清理路径必须位于当前 run 目录内。") from exc
    if child.parent.resolve(strict=True) != run_root:
        raise SourceEvidenceStorageError("Source Evidence 清理只允许删除当前 run 的直接子项。")

    if _is_link_or_junction(child):
        _unlink_link_or_junction(child)
        return

    resolved_child = child.resolve(strict=False)
    try:
        resolved_child.relative_to(run_root)
    except ValueError as exc:
        raise SourceEvidenceStorageError("Source Evidence 清理路径不能逃出当前 run 目录。") from exc
    if resolved_child == run_root:
        raise SourceEvidenceStorageError("Source Evidence 清理不能删除 run 目录本身。")

    if child.is_dir():
        shutil.rmtree(child)
    elif child.exists():
        child.unlink()


def _is_link_or_junction(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (callable(is_junction) and bool(is_junction()))


def _unlink_link_or_junction(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
        return
    try:
        path.rmdir()
    except NotADirectoryError:
        path.unlink()
