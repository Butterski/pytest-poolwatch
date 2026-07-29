"""Pytest configuration for the scalable cloud-job workload."""

from __future__ import annotations

import argparse

import pytest

from .simulator import build_cases

DEFAULT_CLOUD_JOB_COUNT = 800


def _positive_int(raw_value: str) -> int:
    value = int(raw_value)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def pytest_addoption(parser: pytest.Parser) -> None:
    """Expose the workload size without changing the test module."""

    group = parser.getgroup("cloud job simulation")
    group.addoption(
        "--cloud-job-count",
        dest="cloud_job_count",
        type=_positive_int,
        default=DEFAULT_CLOUD_JOB_COUNT,
        metavar="N",
        help=(
            "number of simulated cloud jobs to collect "
            f"(default: {DEFAULT_CLOUD_JOB_COUNT})"
        ),
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Generate deterministic jobs after pytest has parsed CLI options."""

    if "cloud_job_case" not in metafunc.fixturenames:
        return

    count = metafunc.config.getoption("cloud_job_count")
    cases = build_cases(count)
    metafunc.parametrize(
        "cloud_job_case",
        cases,
        ids=[case.pytest_id for case in cases],
    )
