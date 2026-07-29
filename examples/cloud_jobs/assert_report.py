"""Check that PoolWatch captured the complete cloud-job stress run."""

from __future__ import annotations

import argparse
import json
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


def _positive_int(raw_value: str) -> int:
    value = int(raw_value)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check PoolWatch invariants for the cloud-job stress run."
    )
    parser.add_argument("report", type=Path, help="PoolWatch JSON report")
    parser.add_argument(
        "--expected-tests",
        type=_positive_int,
        default=EXPECTED_TESTS,
        help=f"expected collected and observed tests (default: {EXPECTED_TESTS})",
    )
    parser.add_argument(
        "--expected-concurrency",
        type=_positive_int,
        default=EXPECTED_CONCURRENCY,
        help=(
            "expected configured and peak concurrency "
            f"(default: {EXPECTED_CONCURRENCY})"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    expected_tests = args.expected_tests
    expected_concurrency = args.expected_concurrency

    payload = _load_report(args.report)
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

    if collected != expected_tests:
        _fail(f"expected {expected_tests} collected tests, got {collected}")
    if observed != expected_tests or len(tests) != expected_tests:
        _fail(f"expected {expected_tests} observed tests, got {observed}")
    if configured != expected_concurrency:
        _fail(f"expected detected concurrency {expected_concurrency}, got {configured}")
    if peak != expected_concurrency:
        _fail(f"expected peak concurrency {expected_concurrency}, got {peak}")
    if duration <= 0:
        _fail(f"expected a positive observed duration, got {duration:.3f}s")
    if payload["exit_status"] != 0:
        _fail(f"pytest exited with status {payload['exit_status']}")
    if any(test["outcome"] != "passed" for test in tests):
        _fail("at least one cloud-job test did not pass")
    if any(test["incomplete"] for test in tests):
        _fail("at least one cloud-job interval was incomplete")
    if len({test["nodeid"] for test in tests}) != expected_tests:
        _fail("cloud-job node IDs are not unique")


if __name__ == "__main__":
    main()
