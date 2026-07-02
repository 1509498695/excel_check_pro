"""Clean runtime uploads, SVN cache, execution results and logs."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.runtime_cleanup import cleanup_runtime  # noqa: E402


def _print_human_report(report: dict) -> None:
    mode = "DRY-RUN" if report["dry_run"] else "EXECUTE"
    print(f"Runtime cleanup mode: {mode}")
    print(f"Candidates: {len(report['candidates'])}")
    print(f"Deleted:    {len(report['deleted'])}")
    print(f"Skipped:    {len(report['skipped'])}")
    execution_runs = report["execution_runs"]
    print(
        "Execution runs: "
        f"{len(execution_runs['run_ids'])} runs, "
        f"{execution_runs['item_count']} items"
    )
    source_evidence_runs = report["source_evidence_runs"]
    print(
        "Source evidence runs: "
        f"{len(source_evidence_runs['run_ids'])} runs, "
        f"{source_evidence_runs['resource_count']} resources, "
        f"{source_evidence_runs['observation_count']} observations, "
        f"{source_evidence_runs['cleaned_count']} cleaned"
    )

    for candidate in report["candidates"]:
        prefix = "WOULD DELETE" if report["dry_run"] else "CANDIDATE"
        print(
            f"{prefix} [{candidate['category']}] {candidate['path']} "
            f"({candidate['size_bytes']} bytes) - {candidate['reason']}"
        )
    for skipped in report["skipped"]:
        print(f"SKIP [{skipped['category']}] {skipped['path']} - {skipped['reason']}")


async def _main_async(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clean Excel Check runtime files and old execution results.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List cleanup targets without deleting files or database rows.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the cleanup report as JSON.",
    )
    args = parser.parse_args(argv)

    report = await cleanup_runtime(dry_run=args.dry_run)
    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human_report(payload)
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
