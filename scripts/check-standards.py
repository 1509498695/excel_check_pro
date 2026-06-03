"""跨平台安装、测试和构建检查入口。"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
VENV_DIR = PROJECT_ROOT / ".venv"


@dataclass(frozen=True)
class Step:
    """一键检查中的单个命令步骤。"""

    label: str
    command: list[str]
    cwd: Path = PROJECT_ROOT


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _display_command(command: list[str]) -> str:
    return " ".join(command)


def _resolve_command(command: list[str]) -> list[str]:
    if os.name != "nt" or command[0].lower() != "npm":
        return command
    npm_path = shutil.which("npm.cmd") or shutil.which("npm")
    if npm_path is None:
        return command
    return [npm_path, *command[1:]]


def _run_step(step: Step, *, dry_run: bool) -> None:
    print(f"\n==> {step.label}", flush=True)
    print(f"$ {_display_command(step.command)}", flush=True)
    if dry_run:
        return
    subprocess.run(_resolve_command(step.command), cwd=step.cwd, check=True)


def ensure_venv(*, dry_run: bool) -> None:
    """确保后端检查使用项目内虚拟环境。"""
    python_path = _venv_python()
    print("\n==> Ensure backend virtual environment", flush=True)
    if python_path.exists():
        print(f"Using existing virtual environment: {VENV_DIR}", flush=True)
        return
    print(f"$ {sys.executable} -m venv {VENV_DIR}", flush=True)
    if dry_run:
        return
    venv.EnvBuilder(with_pip=True).create(VENV_DIR)


def build_steps() -> list[Step]:
    python_path = str(_venv_python())
    return [
        Step(
            "Install backend dependencies",
            [
                python_path,
                "-m",
                "pip",
                "install",
                "-r",
                str(PROJECT_ROOT / "backend" / "requirements.txt"),
            ],
        ),
        Step("Run ruff check", [python_path, "-m", "ruff", "check", "backend"]),
        Step("Run backend tests", [python_path, "-m", "pytest", "backend/tests", "-q"]),
        Step("Install frontend dependencies", ["npm", "ci"], cwd=FRONTEND_ROOT),
        Step("Run frontend lint", ["npm", "run", "lint"], cwd=FRONTEND_ROOT),
        Step("Run frontend unit tests", ["npm", "run", "test:unit"], cwd=FRONTEND_ROOT),
        Step("Build frontend", ["npm", "run", "build"], cwd=FRONTEND_ROOT),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install dependencies, run tests, and build Excel Check.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands without creating environments or running checks.",
    )
    args = parser.parse_args(argv)

    try:
        ensure_venv(dry_run=args.dry_run)
        for step in build_steps():
            _run_step(step, dry_run=args.dry_run)
    except FileNotFoundError as exc:
        print(f"\nCheck failed because a required executable was not found: {exc.filename}")
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"\nCheck failed with exit code {exc.returncode}: {_display_command(exc.cmd)}")
        return exc.returncode or 1

    print("\nAll standard checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
