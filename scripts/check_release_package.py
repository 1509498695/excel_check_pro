"""Validate clean source release directories or zip packages."""

from __future__ import annotations

import argparse
import os
import re
import sys
import zipfile
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path


SOURCE_FILE_SUFFIXES = {
    ".cjs",
    ".css",
    ".html",
    ".js",
    ".jsx",
    ".mjs",
    ".py",
    ".pyi",
    ".scss",
    ".ts",
    ".tsx",
    ".vue",
}

FILE_PATTERNS = {
    "*.db": "database file",
    "*.key": "key file",
    "*.log": "log file",
    "*.pyc": "Python bytecode",
    "*.pyo": "Python optimized bytecode",
    "*.sqlite": "SQLite database file",
    "*.sqlite3": "SQLite database file",
}

EXACT_SENSITIVE_FILES = {
    ".svn-key": "SVN credential key",
    "svn-credentials.json": "SVN credentials file",
}

DIR_COMPONENT_REASONS = {
    ".codex": "local Codex data directory",
    ".e2e-runtime": "E2E runtime data directory",
    ".git": "Git metadata directory",
    ".pytest_cache": "pytest cache directory",
    ".ruff_cache": "ruff cache directory",
    ".runtime": "runtime data directory",
    ".runtime_uploads": "runtime upload directory",
    ".svn": "SVN metadata directory",
    ".venv": "local virtual environment",
    "__pycache__": "Python cache directory",
    "node_modules": "Node dependency directory",
    "svn-cache": "SVN cache directory",
    "venv": "local virtual environment",
}

WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class Violation:
    """A release package path that must not be shipped."""

    path: str
    reason: str


def normalize_member_path(member_path: str | os.PathLike[str]) -> str:
    """Return a stable POSIX-style relative path for scanner rules."""

    normalized = str(member_path).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def has_zip_slip(member_path: str) -> str | None:
    """Return a reason when a zip entry can escape the extraction root."""

    raw_path = str(member_path).replace("\\", "/")
    if raw_path.startswith("/") or WINDOWS_DRIVE_RE.match(raw_path):
        return "zip entry uses an absolute path"

    parts = [part for part in raw_path.split("/") if part]
    if ".." in parts:
        return "zip entry contains '..' path segment"
    return None


def _path_parts(member_path: str | os.PathLike[str]) -> list[str]:
    normalized = normalize_member_path(member_path)
    if not normalized:
        return []
    return [part for part in normalized.split("/") if part and part != "."]


def _has_adjacent_parts(parts: list[str], left: str, right: str) -> bool:
    return any(parts[index] == left and parts[index + 1] == right for index in range(len(parts) - 1))


def _is_source_file_name(file_name: str) -> bool:
    return any(file_name.endswith(suffix) for suffix in SOURCE_FILE_SUFFIXES)


def _file_violation_reason(file_name: str) -> str | None:
    lower_name = file_name.lower()

    if lower_name == ".env.example":
        return None
    if lower_name == ".env" or lower_name.startswith(".env."):
        return "local environment file"

    exact_reason = EXACT_SENSITIVE_FILES.get(lower_name)
    if exact_reason:
        return exact_reason

    for pattern, reason in FILE_PATTERNS.items():
        if fnmatch(lower_name, pattern):
            return reason

    if "secret" in lower_name and not _is_source_file_name(lower_name):
        return "local secret file"
    if "credential" in lower_name and not _is_source_file_name(lower_name):
        return "local credential file"
    return None


def check_member_path(member_path: str | os.PathLike[str], *, is_dir: bool = False) -> Violation | None:
    """Check one release-relative path and return the first violation."""

    normalized = normalize_member_path(member_path)
    parts = _path_parts(normalized)
    if not parts:
        return None

    lower_parts = [part.lower() for part in parts]
    for part in lower_parts:
        reason = DIR_COMPONENT_REASONS.get(part)
        if reason:
            return Violation(normalized, reason)

    if _has_adjacent_parts(lower_parts, "frontend", "dist"):
        return Violation(normalized, "frontend build output directory")

    if is_dir:
        return None

    reason = _file_violation_reason(lower_parts[-1])
    if reason:
        return Violation(normalized, reason)
    return None


def scan_directory(target: Path) -> list[Violation]:
    """Scan a directory tree without following blocked directories."""

    root = target.resolve()
    violations: list[Violation] = []

    for current_dir, dir_names, file_names in os.walk(root):
        current = Path(current_dir)
        dir_names.sort()
        file_names.sort()

        kept_dirs: list[str] = []
        for dir_name in dir_names:
            dir_path = current / dir_name
            relative_path = dir_path.relative_to(root).as_posix()
            violation = check_member_path(relative_path, is_dir=True)
            if violation:
                violations.append(violation)
                continue
            kept_dirs.append(dir_name)
        dir_names[:] = kept_dirs

        for file_name in file_names:
            file_path = current / file_name
            relative_path = file_path.relative_to(root).as_posix()
            violation = check_member_path(relative_path, is_dir=False)
            if violation:
                violations.append(violation)

    return violations


def scan_zip(target: Path) -> list[Violation]:
    """Scan zip entries without extracting the package."""

    violations: list[Violation] = []
    with zipfile.ZipFile(target) as archive:
        for info in archive.infolist():
            member_name = info.filename
            zip_slip_reason = has_zip_slip(member_name)
            if zip_slip_reason:
                violations.append(Violation(member_name, zip_slip_reason))
                continue

            violation = check_member_path(member_name, is_dir=info.is_dir())
            if violation:
                violations.append(violation)
    return violations


def scan_target(target: Path) -> list[Violation]:
    """Scan a release directory or zip package."""

    if not target.exists():
        raise FileNotFoundError(f"Target does not exist: {target}")
    if target.is_dir():
        return scan_directory(target)
    if target.is_file() and target.suffix.lower() == ".zip":
        return scan_zip(target)
    raise ValueError(f"Target must be a directory or .zip file: {target}")


def format_violations(violations: list[Violation]) -> str:
    """Format violations for terminal output."""

    return "\n".join(f"- {violation.path}: {violation.reason}" for violation in violations)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan a release directory or zip for runtime data and sensitive files.",
    )
    parser.add_argument("target", help="Release directory or .zip package to scan.")
    args = parser.parse_args(argv)

    target = Path(args.target)
    try:
        violations = scan_target(target)
    except (FileNotFoundError, ValueError, zipfile.BadZipFile) as exc:
        print(f"Release package check failed: {exc}", file=sys.stderr)
        return 2

    if violations:
        print("Release package check failed. Forbidden paths found:", file=sys.stderr)
        print(format_violations(violations), file=sys.stderr)
        return 1

    print(f"Release package check passed: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
