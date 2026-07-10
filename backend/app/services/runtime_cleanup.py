"""运行时文件和执行结果清理服务。"""

from __future__ import annotations

import datetime as dt
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import async_session_factory
from backend.app.models import ExecutionResultItemRecord, ExecutionRunRecord
from backend.app.test_cases.generation_runs import (
    GenerationRunCleanupRuns,
    cleanup_expired_generation_runs,
    collect_expired_generation_runs,
)
from backend.app.test_cases.source_evidence_cleanup import (
    SourceEvidenceCleanupRuns,
    cleanup_expired_source_evidence_runs,
    collect_expired_source_evidence_runs,
)
from backend.config import settings


CleanupCategory = Literal["upload", "svn_cache", "log"]
TERMINAL_EXECUTION_STATUSES = ("success", "failed", "cancelled")


@dataclass(frozen=True)
class CleanupFileCandidate:
    """一个可以清理的文件或目录候选项。"""

    category: CleanupCategory
    path: str
    is_dir: bool
    size_bytes: int
    reason: str
    mtime: str


@dataclass(frozen=True)
class CleanupSkippedPath:
    """因安全边界或系统错误跳过的路径。"""

    category: str
    path: str
    reason: str


@dataclass(frozen=True)
class CleanupExecutionRuns:
    """本次会清理或已清理的执行结果记录。"""

    run_ids: list[int] = field(default_factory=list)
    item_count: int = 0


@dataclass(frozen=True)
class RuntimeCleanupReport:
    """runtime 清理报告，脚本可直接序列化输出。"""

    dry_run: bool
    candidates: list[CleanupFileCandidate] = field(default_factory=list)
    deleted: list[CleanupFileCandidate] = field(default_factory=list)
    skipped: list[CleanupSkippedPath] = field(default_factory=list)
    execution_runs: CleanupExecutionRuns = field(default_factory=CleanupExecutionRuns)
    source_evidence_runs: SourceEvidenceCleanupRuns = field(
        default_factory=SourceEvidenceCleanupRuns
    )
    generation_runs: GenerationRunCleanupRuns = field(
        default_factory=GenerationRunCleanupRuns
    )

    def to_dict(self) -> dict:
        """返回 JSON 友好的字典。"""
        return asdict(self)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _naive_utc(value: dt.datetime) -> dt.datetime:
    return value.astimezone(dt.UTC).replace(tzinfo=None)


def _resolve_existing_or_parent(path: Path) -> Path:
    try:
        return path.resolve(strict=True)
    except FileNotFoundError:
        return path.resolve(strict=False)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _normalize_root(path: Path) -> Path:
    return _resolve_existing_or_parent(path.expanduser())


def _runtime_roots() -> tuple[Path, ...]:
    roots = {
        _normalize_root(settings.runtime_dir),
        _normalize_root(settings.runtime_upload_dir),
        _normalize_root(settings.runtime_dir / "uploads"),
        _normalize_root(settings.svn_cache_dir),
    }
    return tuple(sorted(roots, key=lambda item: str(item).lower()))


def _is_safe_runtime_path(path: Path, roots: tuple[Path, ...]) -> bool:
    resolved_path = _resolve_existing_or_parent(path.expanduser())
    return any(
        resolved_path != root and _is_relative_to(resolved_path, root)
        for root in roots
    )


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _tree_size(path: Path) -> int:
    if path.is_file():
        return _file_size(path)
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += _file_size(child)
    return total


def _tree_latest_mtime(path: Path) -> float:
    latest = path.stat().st_mtime
    if path.is_file():
        return latest
    for child in path.rglob("*"):
        try:
            latest = max(latest, child.stat().st_mtime)
        except OSError:
            continue
    return latest


def _cutoff_timestamp(now: dt.datetime, retention_days: int) -> float | None:
    if retention_days <= 0:
        return None
    cutoff = now - dt.timedelta(days=retention_days)
    return cutoff.timestamp()


def _candidate_from_path(
    *,
    category: CleanupCategory,
    path: Path,
    reason: str,
    roots: tuple[Path, ...],
) -> tuple[CleanupFileCandidate | None, CleanupSkippedPath | None]:
    resolved_path = _resolve_existing_or_parent(path)
    if not _is_safe_runtime_path(resolved_path, roots):
        return None, CleanupSkippedPath(
            category=category,
            path=str(path),
            reason="路径不在受控 runtime 根目录内，已跳过",
        )
    try:
        mtime = dt.datetime.fromtimestamp(_tree_latest_mtime(resolved_path), dt.UTC)
    except OSError as exc:
        return None, CleanupSkippedPath(
            category=category,
            path=str(path),
            reason=f"读取路径状态失败：{exc}",
        )
    return (
        CleanupFileCandidate(
            category=category,
            path=str(resolved_path),
            is_dir=resolved_path.is_dir(),
            size_bytes=_tree_size(resolved_path),
            reason=reason,
            mtime=mtime.isoformat(),
        ),
        None,
    )


def _collect_expired_files(
    *,
    root: Path,
    category: CleanupCategory,
    retention_days: int,
    now: dt.datetime,
    roots: tuple[Path, ...],
    pattern: str = "*",
) -> tuple[list[CleanupFileCandidate], list[CleanupSkippedPath]]:
    cutoff = _cutoff_timestamp(now, retention_days)
    if cutoff is None or not root.exists():
        return [], []

    candidates: list[CleanupFileCandidate] = []
    skipped: list[CleanupSkippedPath] = []
    for path in root.rglob(pattern):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime >= cutoff:
                continue
        except OSError as exc:
            skipped.append(
                CleanupSkippedPath(
                    category=category,
                    path=str(path),
                    reason=f"读取文件状态失败：{exc}",
                )
            )
            continue

        candidate, skipped_path = _candidate_from_path(
            category=category,
            path=path,
            reason=f"超过 {retention_days} 天保留期",
            roots=roots,
        )
        if candidate:
            candidates.append(candidate)
        if skipped_path:
            skipped.append(skipped_path)
    return candidates, skipped


def _collect_expired_svn_cache_dirs(
    *,
    root: Path,
    retention_days: int,
    now: dt.datetime,
    roots: tuple[Path, ...],
) -> tuple[list[CleanupFileCandidate], list[CleanupSkippedPath]]:
    cutoff = _cutoff_timestamp(now, retention_days)
    if cutoff is None or not root.exists():
        return [], []

    candidates: list[CleanupFileCandidate] = []
    skipped: list[CleanupSkippedPath] = []
    for host_dir in sorted(root.iterdir()):
        if not host_dir.is_dir():
            continue
        for cache_dir in sorted(host_dir.iterdir()):
            if not cache_dir.is_dir():
                continue
            try:
                if _tree_latest_mtime(cache_dir) >= cutoff:
                    continue
            except OSError as exc:
                skipped.append(
                    CleanupSkippedPath(
                        category="svn_cache",
                        path=str(cache_dir),
                        reason=f"读取缓存目录状态失败：{exc}",
                    )
                )
                continue

            candidate, skipped_path = _candidate_from_path(
                category="svn_cache",
                path=cache_dir,
                reason=f"SVN 缓存超过 {retention_days} 天保留期",
                roots=roots,
            )
            if candidate:
                candidates.append(candidate)
            if skipped_path:
                skipped.append(skipped_path)
    return candidates, skipped


async def _collect_execution_runs(
    db: AsyncSession,
    *,
    retention_days: int,
    now: dt.datetime,
) -> CleanupExecutionRuns:
    if retention_days <= 0:
        return CleanupExecutionRuns()

    cutoff = _naive_utc(now - dt.timedelta(days=retention_days))
    run_result = await db.execute(
        select(ExecutionRunRecord.id).where(
            ExecutionRunRecord.status.in_(TERMINAL_EXECUTION_STATUSES),
            ExecutionRunRecord.created_at < cutoff,
        )
    )
    run_ids = list(run_result.scalars().all())
    if not run_ids:
        return CleanupExecutionRuns()

    count_result = await db.execute(
        select(func.count(ExecutionResultItemRecord.id)).where(
            ExecutionResultItemRecord.run_id.in_(run_ids)
        )
    )
    return CleanupExecutionRuns(
        run_ids=run_ids,
        item_count=int(count_result.scalar_one() or 0),
    )


async def collect_runtime_cleanup_candidates(
    db: AsyncSession | None = None,
    *,
    now: dt.datetime | None = None,
) -> RuntimeCleanupReport:
    """收集将被清理的 runtime 资源，不执行删除。"""
    current_time = now or _utc_now()
    roots = _runtime_roots()
    candidates: list[CleanupFileCandidate] = []
    skipped: list[CleanupSkippedPath] = []

    for upload_root in (
        settings.runtime_upload_dir,
        settings.runtime_dir / "uploads",
    ):
        found, ignored = _collect_expired_files(
            root=upload_root,
            category="upload",
            retention_days=settings.upload_retention_days,
            now=current_time,
            roots=roots,
        )
        candidates.extend(found)
        skipped.extend(ignored)

    found_svn, ignored_svn = _collect_expired_svn_cache_dirs(
        root=settings.svn_cache_dir,
        retention_days=settings.svn_cache_retention_days,
        now=current_time,
        roots=roots,
    )
    candidates.extend(found_svn)
    skipped.extend(ignored_svn)

    for log_root in (settings.runtime_dir, settings.runtime_upload_dir):
        found_logs, ignored_logs = _collect_expired_files(
            root=log_root,
            category="log",
            retention_days=settings.log_retention_days,
            now=current_time,
            roots=roots,
            pattern="*.log",
        )
        candidates.extend(found_logs)
        skipped.extend(ignored_logs)

    if db is None:
        async with async_session_factory() as session:
            execution_runs = await _collect_execution_runs(
                session,
                retention_days=settings.execution_result_retention_days,
                now=current_time,
            )
            source_evidence_runs = await collect_expired_source_evidence_runs(
                session,
                now=current_time,
            )
            generation_runs = await collect_expired_generation_runs(
                session,
                now=current_time,
            )
    else:
        execution_runs = await _collect_execution_runs(
            db,
            retention_days=settings.execution_result_retention_days,
            now=current_time,
        )
        source_evidence_runs = await collect_expired_source_evidence_runs(
            db,
            now=current_time,
        )
        generation_runs = await collect_expired_generation_runs(
            db,
            now=current_time,
        )

    return RuntimeCleanupReport(
        dry_run=True,
        candidates=candidates,
        skipped=skipped,
        execution_runs=execution_runs,
        source_evidence_runs=source_evidence_runs,
        generation_runs=generation_runs,
    )


async def _delete_execution_runs(
    db: AsyncSession,
    execution_runs: CleanupExecutionRuns,
) -> None:
    if not execution_runs.run_ids:
        return
    await db.execute(
        delete(ExecutionResultItemRecord).where(
            ExecutionResultItemRecord.run_id.in_(execution_runs.run_ids)
        )
    )
    await db.execute(
        delete(ExecutionRunRecord).where(
            ExecutionRunRecord.id.in_(execution_runs.run_ids)
        )
    )
    await db.commit()


async def _cleanup_source_evidence_runs(
    db: AsyncSession,
    *,
    now: dt.datetime,
) -> SourceEvidenceCleanupRuns:
    cleaned = await cleanup_expired_source_evidence_runs(db, now=now, cleaned_by=None)
    await db.commit()
    return cleaned


async def _cleanup_generation_runs(
    db: AsyncSession,
    *,
    now: dt.datetime,
) -> GenerationRunCleanupRuns:
    cleaned = await cleanup_expired_generation_runs(db, now=now)
    await db.commit()
    return cleaned


def _delete_candidate(candidate: CleanupFileCandidate) -> None:
    path = Path(candidate.path)
    if candidate.is_dir:
        shutil.rmtree(path)
    else:
        path.unlink()


async def cleanup_runtime(
    dry_run: bool = True,
    db: AsyncSession | None = None,
    *,
    now: dt.datetime | None = None,
) -> RuntimeCleanupReport:
    """按保留策略清理 runtime 资源。"""
    report = await collect_runtime_cleanup_candidates(db, now=now)
    if dry_run:
        return report

    deleted: list[CleanupFileCandidate] = []
    skipped = list(report.skipped)
    roots = _runtime_roots()

    for candidate in report.candidates:
        path = Path(candidate.path)
        if not _is_safe_runtime_path(path, roots):
            skipped.append(
                CleanupSkippedPath(
                    category=candidate.category,
                    path=candidate.path,
                    reason="删除前安全校验失败，已跳过",
                )
            )
            continue
        try:
            _delete_candidate(candidate)
        except OSError as exc:
            skipped.append(
                CleanupSkippedPath(
                    category=candidate.category,
                    path=candidate.path,
                    reason=f"删除失败：{exc}",
                )
            )
            continue
        deleted.append(candidate)

    if db is None:
        async with async_session_factory() as session:
            await _delete_execution_runs(session, report.execution_runs)
            source_evidence_runs = await _cleanup_source_evidence_runs(
                session,
                now=now or _utc_now(),
            )
            generation_runs = await _cleanup_generation_runs(
                session,
                now=now or _utc_now(),
            )
    else:
        await _delete_execution_runs(db, report.execution_runs)
        source_evidence_runs = await _cleanup_source_evidence_runs(
            db,
            now=now or _utc_now(),
        )
        generation_runs = await _cleanup_generation_runs(
            db,
            now=now or _utc_now(),
        )

    return RuntimeCleanupReport(
        dry_run=False,
        candidates=report.candidates,
        deleted=deleted,
        skipped=skipped,
        execution_runs=report.execution_runs,
        source_evidence_runs=source_evidence_runs,
        generation_runs=generation_runs,
    )
