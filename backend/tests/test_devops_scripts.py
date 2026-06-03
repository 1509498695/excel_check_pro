"""可复现安装、测试和构建脚本契约测试。"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS_IN = PROJECT_ROOT / "backend" / "requirements.in"
REQUIREMENTS_TXT = PROJECT_ROOT / "backend" / "requirements.txt"
CHECK_SCRIPT = PROJECT_ROOT / "scripts" / "check-standards.py"


DIRECT_REQUIREMENTS = {
    "fastapi",
    "uvicorn",
    "pydantic",
    "pandas",
    "openpyxl",
    "xlrd",
    "requests",
    "pytest",
    "httpx",
    "sqlalchemy>=2.0",
    "aiosqlite",
    "alembic",
    "python-jose[cryptography]",
    "bcrypt",
    "python-multipart",
    "ruff",
    "lark-oapi",
    "psutil",
}


def _requirement_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_requirements_in_keeps_direct_dependency_list() -> None:
    """后端直接依赖应维护在 requirements.in。"""
    assert REQUIREMENTS_IN.exists()
    assert set(_requirement_lines(REQUIREMENTS_IN)) == DIRECT_REQUIREMENTS


def test_requirements_txt_is_fully_pinned() -> None:
    """requirements.txt 应由 pip-compile 生成并锁定传递依赖版本。"""
    assert REQUIREMENTS_TXT.exists()
    requirement_pattern = re.compile(
        r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[^\s;#]+(?:\s*;.+)?$"
    )

    for raw_line in REQUIREMENTS_TXT.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or raw_line.startswith("    "):
            continue
        assert requirement_pattern.match(line), f"Dependency is not pinned: {line}"


def test_check_standards_dry_run_lists_reproducible_steps() -> None:
    """dry-run 应展示安装、测试和构建的完整命令顺序。"""
    result = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT), "--dry-run"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    output = result.stdout
    expected_snippets = [
        "-m pip install -r",
        "ruff check backend",
        "pytest backend/tests -q",
        "npm ci",
        "npm run lint",
        "npm run test:unit",
        "npm run build",
    ]
    for snippet in expected_snippets:
        assert snippet in output
