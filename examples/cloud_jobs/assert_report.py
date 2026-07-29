"""Check that PoolWatch captured the complete cloud-job stress run."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Never

EXPECTED_TESTS = 800
EXPECTED_CONCURRENCY = 40


def _fail(message: str) -> Never:
    raise SystemExit(message)


def _load_report(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        _fail(f"could not read PoolWatch report {path}: {error}")


def main() -> None:
    if len(sys.argv) != 2:
        _fail("usage: assert_report.py REPORT.json")

    payload = _load_report(Path(sys.argv[1]))
    session = payload["session"]
    target = payload["target"]
    summary = payload["summary"]
    tests = payload["tests"]

    collected = int(session["collected_tests"])
    observed = int(session["observed_test_attempts"])
    duration = float(session["duration_seconds"])
    configured = int(target["configured"])
    peak = int(summary["peak_active_tests"])
    utilization = float(summary["concurrency_utilization"])

    print(
        f"cloud jobs: collected={collected}, observed={observed}, "
        f"target={configured}, peak={peak}, duration={duration:.3f}s, "
        f"utilization={utilization:.1%}"
    )

    if collected != EXPECTED_TESTS:
        _fail(f"expected {EXPECTED_TESTS} collected tests, got {collected}")
    if observed != EXPECTED_TESTS or len(tests) != EXPECTED_TESTS:
        _fail(f"expected {EXPECTED_TESTS} observed tests, got {observed}")
    if configured != EXPECTED_CONCURRENCY:
        _fail(f"expected detected concurrency {EXPECTED_CONCURRENCY}, got {configured}")
    if peak != EXPECTED_CONCURRENCY:
        _fail(f"expected peak concurrency {EXPECTED_CONCURRENCY}, got {peak}")
    if duration <= 0:
        _fail(f"expected a positive observed duration, got {duration:.3f}s")
    if payload["exit_status"] != 0:
        _fail(f"pytest exited with status {payload['exit_status']}")
    if any(test["outcome"] != "passed" for test in tests):
        _fail("at least one cloud-job test did not pass")
    if any(test["incomplete"] for test in tests):
        _fail("at least one cloud-job interval was incomplete")
    if len({test["nodeid"] for test in tests}) != EXPECTED_TESTS:
        _fail("cloud-job node IDs are not unique")


if __name__ == "__main__":
    main()
