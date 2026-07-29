"""Validate the behavioral signal produced by the PR #86 demo."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in {"before", "after"}:
        raise SystemExit("usage: assert_report.py {before|after} REPORT.json")

    mode = sys.argv[1]
    payload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    summary = payload["summary"]
    underfill = float(summary["scheduler_underfill_seconds"])
    utilization = float(summary["concurrency_utilization"])
    peak = int(summary["peak_active_tests"])

    print(
        f"{mode}: peak={peak}, utilization={utilization:.1%}, "
        f"underfill={underfill:.3f}s"
    )
    if peak != 4:
        raise SystemExit(f"expected peak concurrency 4, got {peak}")
    if mode == "before" and underfill < 0.05:
        raise SystemExit("pre-fix scheduler did not produce the expected underfill")
    if mode == "after" and underfill >= 0.05:
        raise SystemExit("fixed scheduler still produced material underfill")


if __name__ == "__main__":
    main()
