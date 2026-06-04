from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path
from types import ModuleType


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def _load_script_module(module_name: str) -> ModuleType:
    module_path = SCRIPTS_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


check_release_package = _load_script_module("check_release_package")
release_package = _load_script_module("release_package")


def _write_text(path: Path, value: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _zip_names(zip_path: Path) -> set[str]:
    with zipfile.ZipFile(zip_path) as archive:
        return set(archive.namelist())


def _make_project(root: Path) -> Path:
    _write_text(root / "README.md", "# Test\n")
    _write_text(root / "package-lock.json", "{}\n")
    _write_text(root / "backend" / "requirements.in", "fastapi\n")
    _write_text(root / "backend" / "requirements.txt", "fastapi\n")
    _write_text(root / "backend" / "app" / "loaders" / "svn_credentials.py", "VALUE = 1\n")
    _write_text(root / "backend" / "app" / "ai" / "credentials.py", "VALUE = 1\n")
    _write_text(
        root / "frontend" / "src" / "components" / "workbench" / "SvnCredentialDialog.vue",
        "<template />\n",
    )
    _write_text(root / "frontend" / "package-lock.json", "{}\n")
    _write_text(root / "backend" / "tests" / "data" / "sample.txt", "fixture\n")

    _write_text(root / ".git" / "config", "secret\n")
    _write_text(root / "node_modules" / "pkg" / "index.js", "ignored\n")
    _write_text(root / "frontend" / "node_modules" / "pkg" / "index.js", "ignored\n")
    _write_text(root / "frontend" / "dist" / "app.js", "ignored\n")
    _write_text(root / "backend" / ".runtime" / "excel_check.db", "ignored\n")
    _write_text(root / "backend" / ".runtime" / "svn-cache" / "remote" / "file.xlsx", "ignored\n")
    _write_text(root / "backend" / ".runtime" / ".svn-key", "ignored\n")
    _write_text(root / "backend" / ".runtime" / "svn-credentials.json", "ignored\n")
    _write_text(root / ".runtime_uploads" / "upload.xlsx", "ignored\n")
    _write_text(root / "backend" / ".runtime_uploads" / "local_excel" / "upload.xlsx", "ignored\n")
    _write_text(root / ".e2e-runtime" / "backend" / "excel_check_e2e.db", "ignored\n")
    _write_text(root / ".e2e-runtime" / "uploads" / "fixture.xlsx", "ignored\n")
    _write_text(root / "backend" / "app" / "__pycache__" / "module.pyc", "ignored\n")
    _write_text(root / ".svn" / "entries", "ignored\n")
    _write_text(root / "cache" / "svn-cache" / "file.xlsx", "ignored\n")
    _write_text(root / ".env.local", "ignored\n")
    _write_text(root / "local-deploy-jwt-secret.txt", "ignored\n")
    _write_text(root / "private.key", "ignored\n")
    _write_text(root / "debug.log", "ignored\n")
    _write_text(root / "local.sqlite", "ignored\n")
    return root


def test_release_package_keeps_source_and_excludes_runtime_data(tmp_path: Path) -> None:
    project_root = _make_project(tmp_path / "project")

    zip_path = release_package.create_release_package(
        project_root,
        tmp_path / "release",
        zip_name="clean-source.zip",
    )

    names = _zip_names(zip_path)
    assert "README.md" in names
    assert "package-lock.json" in names
    assert "frontend/package-lock.json" in names
    assert "backend/requirements.in" in names
    assert "backend/requirements.txt" in names
    assert "backend/tests/data/sample.txt" in names
    assert "backend/app/loaders/svn_credentials.py" in names
    assert "backend/app/ai/credentials.py" in names
    assert "frontend/src/components/workbench/SvnCredentialDialog.vue" in names

    forbidden_fragments = (
        ".git/",
        "node_modules/",
        "frontend/dist/",
        "backend/.runtime/",
        ".e2e-runtime/",
        ".runtime_uploads/",
        "backend/.runtime_uploads/",
        "__pycache__/",
        ".svn/",
        "svn-cache/",
    )
    for fragment in forbidden_fragments:
        assert not any(fragment in name for name in names)

    forbidden_files = {
        ".env.local",
        "debug.log",
        "local-deploy-jwt-secret.txt",
        "local.sqlite",
        "private.key",
    }
    assert names.isdisjoint(forbidden_files)
    assert check_release_package.scan_zip(zip_path) == []


def test_directory_checker_fails_for_unsafe_content_but_allows_source_credentials(
    tmp_path: Path,
) -> None:
    package_dir = _make_project(tmp_path / "bad-package")

    violations = check_release_package.scan_directory(package_dir)
    violation_paths = {violation.path for violation in violations}

    assert ".git" in violation_paths
    assert "node_modules" in violation_paths
    assert "frontend/dist" in violation_paths
    assert "backend/.runtime" in violation_paths
    assert ".e2e-runtime" in violation_paths
    assert ".runtime_uploads" in violation_paths
    assert "backend/.runtime_uploads" in violation_paths
    assert "backend/app/__pycache__" in violation_paths
    assert ".svn" in violation_paths
    assert "cache/svn-cache" in violation_paths
    assert ".env.local" in violation_paths
    assert "local-deploy-jwt-secret.txt" in violation_paths
    assert "private.key" in violation_paths
    assert "debug.log" in violation_paths
    assert "local.sqlite" in violation_paths

    assert "backend/app/loaders/svn_credentials.py" not in violation_paths
    assert "backend/app/ai/credentials.py" not in violation_paths
    assert "frontend/src/components/workbench/SvnCredentialDialog.vue" not in violation_paths
    assert check_release_package.main([str(package_dir)]) == 1


def test_zip_checker_fails_for_sensitive_paths_and_zip_slip(tmp_path: Path) -> None:
    zip_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("README.md", "ok\n")
        archive.writestr("backend/app/loaders/svn_credentials.py", "VALUE = 1\n")
        archive.writestr("backend/.runtime/excel_check.db", "bad\n")
        archive.writestr("frontend/dist/app.js", "bad\n")
        archive.writestr("token.key", "bad\n")
        archive.writestr("local-secret.txt", "bad\n")
        archive.writestr("/absolute/evil.txt", "bad\n")
        archive.writestr("C:/absolute/evil.txt", "bad\n")
        archive.writestr("safe/../evil.txt", "bad\n")

    violations = check_release_package.scan_zip(zip_path)
    violation_paths = {violation.path for violation in violations}

    assert "backend/.runtime/excel_check.db" in violation_paths
    assert "frontend/dist/app.js" in violation_paths
    assert "token.key" in violation_paths
    assert "local-secret.txt" in violation_paths
    assert "/absolute/evil.txt" in violation_paths
    assert "C:/absolute/evil.txt" in violation_paths
    assert "safe/../evil.txt" in violation_paths
    assert "backend/app/loaders/svn_credentials.py" not in violation_paths
    assert check_release_package.main([str(zip_path)]) == 1


def test_zip_checker_passes_clean_source_zip(tmp_path: Path) -> None:
    zip_path = tmp_path / "clean.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("README.md", "ok\n")
        archive.writestr("backend/app/ai/credentials.py", "VALUE = 1\n")
        archive.writestr("frontend/src/components/workbench/SvnCredentialDialog.vue", "<template />\n")

    assert check_release_package.scan_zip(zip_path) == []
    assert check_release_package.main([str(zip_path)]) == 0
