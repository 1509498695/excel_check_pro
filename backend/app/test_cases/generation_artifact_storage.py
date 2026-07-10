"""Safe local storage for deterministic Generation Run artifacts."""

from __future__ import annotations

from pathlib import Path
import shutil

from backend.config import settings


ARTIFACT_FILE_NAMES: dict[str, str] = {
    "workbook": "测试用例.xlsx",
    "blueprint": "用例蓝图.md",
    "stats": "用例统计.json",
    "coverage_audit": "覆盖审计.json",
    "quality_audit": "质量审计.json",
}


class GenerationArtifactStorageError(ValueError):
    """Artifact key or resolved path is not safe."""


def generation_artifact_root() -> Path:
    return (settings.runtime_dir / "test-case-generation-artifacts").resolve(strict=False)


def generation_run_artifact_dir(*, project_id: int, run_id: int) -> Path:
    root = generation_artifact_root()
    target = (root / str(int(project_id)) / str(int(run_id))).resolve(strict=False)
    _ensure_inside(root, target)
    return target


def ensure_generation_run_artifact_dir(*, project_id: int, run_id: int) -> Path:
    target = generation_run_artifact_dir(project_id=project_id, run_id=run_id)
    target.mkdir(parents=True, exist_ok=True)
    return target


def generation_artifact_path(*, project_id: int, run_id: int, key: str) -> Path:
    file_name = ARTIFACT_FILE_NAMES.get(key)
    if file_name is None:
        raise GenerationArtifactStorageError("未知的 Generation Run 产物类型。")
    root = generation_run_artifact_dir(project_id=project_id, run_id=run_id)
    target = (root / file_name).resolve(strict=False)
    _ensure_inside(root, target)
    return target


def write_generation_artifact_bytes(
    *,
    project_id: int,
    run_id: int,
    key: str,
    content: bytes,
) -> Path:
    ensure_generation_run_artifact_dir(project_id=project_id, run_id=run_id)
    target = generation_artifact_path(project_id=project_id, run_id=run_id, key=key)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(target)
    return target


def write_generation_artifact_text(
    *,
    project_id: int,
    run_id: int,
    key: str,
    content: str,
) -> Path:
    return write_generation_artifact_bytes(
        project_id=project_id,
        run_id=run_id,
        key=key,
        content=content.encode("utf-8"),
    )


def clear_generation_run_artifacts(*, project_id: int, run_id: int) -> bool:
    target = generation_run_artifact_dir(project_id=project_id, run_id=run_id)
    if not target.exists():
        return False
    shutil.rmtree(target)
    return True


def _ensure_inside(root: Path, target: Path) -> None:
    root_value = root.resolve(strict=False)
    try:
        target.relative_to(root_value)
    except ValueError as error:
        raise GenerationArtifactStorageError("Generation Run 产物路径越界。") from error
