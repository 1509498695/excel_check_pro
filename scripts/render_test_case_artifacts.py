"""Render a canonical test-case workbook from local structured files only."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.test_cases.artifact_renderer import (  # noqa: E402
    DEFAULT_TEMPLATE_PATH,
    build_canonical_test_case_workbook,
)
from backend.app.test_cases.case_contract import canonical_case_fields  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministically render the canonical test-case workbook."
    )
    parser.add_argument("--cases", required=True, help="CSV with canonical or Chinese headers.")
    parser.add_argument("--blueprint", default="", help="Blueprint Markdown or JSON.")
    parser.add_argument("--coverage-audit", default="", help="Coverage audit JSON.")
    parser.add_argument("--quality-audit", default="", help="Quality audit JSON.")
    parser.add_argument("--title", required=True, help="Workbook title.")
    parser.add_argument("--source-summary", default="本地结构化输入", help="Sanitized source summary.")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE_PATH), help="Canonical xlsx template.")
    parser.add_argument("--out", required=True, help="Output xlsx path.")
    parser.add_argument("--stats-out", required=True, help="Output stats JSON path.")
    parser.add_argument("--force", action="store_true", help="Allow overwriting existing outputs.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = Path(args.out)
    stats_output = Path(args.stats_out)
    _guard_output(output, force=args.force)
    _guard_output(stats_output, force=args.force)
    case_payloads = _read_cases(Path(args.cases))
    blueprint = _read_blueprint(Path(args.blueprint)) if args.blueprint else {}
    coverage = _read_json(Path(args.coverage_audit)) if args.coverage_audit else {}
    quality = _read_json(Path(args.quality_audit)) if args.quality_audit else {}
    workbook = build_canonical_test_case_workbook(
        cases=case_payloads,
        title=args.title,
        source_summary=args.source_summary,
        blueprint=blueprint,
        atoms=coverage.get("atoms", []) if isinstance(coverage.get("atoms"), list) else [],
        coverage_audit=coverage,
        quality_audit=quality,
        metadata={
            "title": args.title,
            "run_id": "standalone",
            "status": "rendered",
            "strict_mode": bool(quality.get("blocks_export")),
        },
        template_path=Path(args.template),
    )
    stats = _stats(case_payloads)
    output.parent.mkdir(parents=True, exist_ok=True)
    stats_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(workbook.getvalue())
    stats_output.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps({**stats, "output": str(output)}, ensure_ascii=False, indent=2))


def _read_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        fields = {
            "primary_module": _pick(row, "primary_module", "一级模块"),
            "secondary_module": _pick(row, "secondary_module", "二级模块"),
            "checkpoint": _pick(row, "checkpoint", "检查点"),
            "preconditions": _pick(row, "preconditions", "前置条件"),
            "steps": _pick(row, "steps", "操作步骤"),
            "expected_results": _pick(row, "expected_results", "预期结果"),
            "priority": _pick(row, "priority", "优先级"),
            "remarks": _pick(row, "remarks", "备注"),
        }
        result.append(
            {
                "case_id": _pick(row, "case_id", "用例编号") or f"TC-{index:04d}",
                "fields": fields,
                "atom_refs": [],
            }
        )
    return result


def _stats(cases: list[dict[str, Any]]) -> dict[str, Any]:
    canonical = [
        canonical_case_fields(
            case.get("fields", {}),
            case_id=str(case.get("case_id") or ""),
        )
        for case in cases
    ]
    return {
        "status": "ok",
        "cases": len(canonical),
        "by_priority": dict(Counter(case["priority"] for case in canonical)),
        "by_module": dict(Counter(case["primary_module"] for case in canonical)),
    }


def _read_blueprint(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        return _read_json(path)
    return {"markdown": path.read_text(encoding="utf-8")}


def _read_json(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return loaded


def _pick(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _guard_output(path: Path, *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"output exists; pass --force to overwrite: {path}")


if __name__ == "__main__":
    main()
