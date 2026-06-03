"""Create a clean source release zip for Excel Check."""

from __future__ import annotations

import argparse
import os
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_release_package import (  # noqa: E402
    Violation,
    check_member_path,
    format_violations,
    scan_zip,
)


@dataclass(frozen=True)
class PackageFile:
    """One source file selected for the release zip."""

    path: Path
    archive_name: str


@dataclass(frozen=True)
class PackagePlan:
    """Files to ship and local entries skipped by release rules."""

    files: list[PackageFile]
    skipped: list[Violation]


def default_project_root() -> Path:
    return SCRIPT_DIR.parent


def default_output_dir(project_root: Path) -> Path:
    return project_root.resolve().parent / "release-packages"


def default_zip_name() -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"excel_check_pro-source-{timestamp}.zip"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _resolve_zip_name(zip_name: str | None) -> str:
    candidate = zip_name or default_zip_name()
    return candidate if candidate.lower().endswith(".zip") else f"{candidate}.zip"


def collect_package_files(
    project_root: Path,
    *,
    output_dir: Path | None = None,
) -> PackagePlan:
    """Collect source files while pruning runtime, cache, dependency and secret paths."""

    root = project_root.resolve()
    if not root.is_dir():
        raise ValueError(f"Project root must be a directory: {root}")

    resolved_output_dir = output_dir.resolve() if output_dir else None
    output_dir_is_inside_project = bool(
        resolved_output_dir and _is_relative_to(resolved_output_dir, root)
    )
    files: list[PackageFile] = []
    skipped: list[Violation] = []

    for current_dir, dir_names, file_names in os.walk(root):
        current = Path(current_dir)
        dir_names.sort()
        file_names.sort()

        kept_dirs: list[str] = []
        for dir_name in dir_names:
            dir_path = current / dir_name
            relative_path = dir_path.relative_to(root).as_posix()
            resolved_dir_path = dir_path.resolve()

            if output_dir_is_inside_project and _is_relative_to(
                resolved_dir_path, resolved_output_dir
            ):
                skipped.append(Violation(relative_path, "release output directory"))
                continue

            violation = check_member_path(relative_path, is_dir=True)
            if violation:
                skipped.append(violation)
                continue

            kept_dirs.append(dir_name)
        dir_names[:] = kept_dirs

        for file_name in file_names:
            file_path = current / file_name
            if not file_path.is_file():
                continue

            relative_path = file_path.relative_to(root).as_posix()
            if output_dir_is_inside_project and _is_relative_to(
                file_path.resolve(), resolved_output_dir
            ):
                skipped.append(Violation(relative_path, "release output file"))
                continue

            violation = check_member_path(relative_path, is_dir=False)
            if violation:
                skipped.append(violation)
                continue

            files.append(PackageFile(path=file_path, archive_name=relative_path))

    return PackagePlan(files=files, skipped=skipped)


def create_release_package(
    project_root: Path,
    output_dir: Path,
    *,
    zip_name: str | None = None,
) -> Path:
    """Create a clean source zip and validate it before returning."""

    root = project_root.resolve()
    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    zip_path = output / _resolve_zip_name(zip_name)

    package_plan = collect_package_files(root, output_dir=output)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for package_file in package_plan.files:
            archive.write(package_file.path, package_file.archive_name)

    violations = scan_zip(zip_path)
    if violations:
        zip_path.unlink(missing_ok=True)
        raise RuntimeError(
            "Generated release package failed validation:\n"
            + format_violations(violations)
        )

    return zip_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a clean source release zip.")
    parser.add_argument(
        "--project-root",
        default=str(default_project_root()),
        help="Project root to package. Defaults to the repository root.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for the generated zip. Defaults to ../release-packages.",
    )
    parser.add_argument(
        "--zip-name",
        default=None,
        help="Optional zip file name. .zip is appended when omitted.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the package summary without writing a zip.",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else default_output_dir(project_root)
    )

    try:
        if args.dry_run:
            package_plan = collect_package_files(project_root, output_dir=output_dir)
            print(f"Project root: {project_root}")
            print(f"Output dir:   {output_dir}")
            print(f"Files:        {len(package_plan.files)}")
            print(f"Skipped:      {len(package_plan.skipped)}")
            for violation in package_plan.skipped[:50]:
                print(f"SKIP {violation.path}: {violation.reason}")
            if len(package_plan.skipped) > 50:
                print(f"... {len(package_plan.skipped) - 50} more skipped entries")
            return 0

        zip_path = create_release_package(
            project_root,
            output_dir,
            zip_name=args.zip_name,
        )
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        print(f"Release package creation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Release package created: {zip_path}")
    print("Release package check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
