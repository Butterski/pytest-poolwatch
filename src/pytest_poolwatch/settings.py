"""PoolWatch command-line and pytest configuration parsing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


@dataclass(frozen=True, slots=True)
class Settings:
    enabled: bool
    target: int | None
    target_source: str | None
    json_path: Path | None
    html_path: Path | None
    underfill_threshold: float


def add_options(parser: pytest.Parser) -> None:
    group = parser.getgroup("poolwatch", "pytest concurrency profiling")
    group.addoption(
        "--poolwatch",
        action="store_true",
        default=False,
        help="enable PoolWatch concurrency profiling",
    )
    group.addoption(
        "--poolwatch-target",
        action="store",
        type=int,
        default=None,
        metavar="N",
        help="expected number of concurrently active tests",
    )
    group.addoption(
        "--poolwatch-json",
        action="store",
        default=None,
        metavar="PATH",
        help="write a versioned JSON report",
    )
    group.addoption(
        "--poolwatch-html",
        action="store",
        default=None,
        metavar="PATH",
        help="write a self-contained HTML report",
    )
    group.addoption(
        "--poolwatch-underfill-threshold",
        action="store",
        type=float,
        default=None,
        metavar="SECONDS",
        help="ignore shorter scheduler underfill windows (default: 0.1)",
    )

    parser.addini("poolwatch", "enable PoolWatch", type="bool", default=False)
    parser.addini("poolwatch_target", "expected concurrency", default="")
    parser.addini("poolwatch_json", "JSON report path", default="")
    parser.addini("poolwatch_html", "HTML report path", default="")
    parser.addini(
        "poolwatch_underfill_threshold",
        "minimum underfill window in seconds",
        default="0.1",
    )


def load_settings(config: pytest.Config) -> Settings:
    cli_target = config.getoption("poolwatch_target")
    ini_target = _optional_positive_int(
        config.getini("poolwatch_target"), "poolwatch_target"
    )
    if cli_target is not None and cli_target <= 0:
        raise pytest.UsageError("--poolwatch-target must be greater than zero")

    target = cli_target if cli_target is not None else ini_target
    target_source = (
        "command_line"
        if cli_target is not None
        else ("pytest_config" if ini_target is not None else None)
    )

    cli_threshold = config.getoption("poolwatch_underfill_threshold")
    threshold = (
        cli_threshold
        if cli_threshold is not None
        else _non_negative_float(
            config.getini("poolwatch_underfill_threshold"),
            "poolwatch_underfill_threshold",
        )
    )
    if threshold < 0:
        raise pytest.UsageError("--poolwatch-underfill-threshold must not be negative")

    cli_json = config.getoption("poolwatch_json")
    cli_html = config.getoption("poolwatch_html")
    ini_json = config.getini("poolwatch_json")
    ini_html = config.getini("poolwatch_html")
    json_value = cli_json or ini_json or None
    html_value = cli_html or ini_html or None

    enabled = bool(
        config.getoption("poolwatch")
        or config.getini("poolwatch")
        or json_value
        or html_value
    )
    return Settings(
        enabled=enabled,
        target=target,
        target_source=target_source,
        json_path=_resolve_path(config, json_value),
        html_path=_resolve_path(config, html_value),
        underfill_threshold=threshold,
    )


def _resolve_path(config: pytest.Config, raw: Any) -> Path | None:
    if raw is None or str(raw).strip() == "":
        return None
    path = Path(str(raw))
    return path if path.is_absolute() else config.rootpath / path


def _optional_positive_int(raw: Any, name: str) -> int | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise pytest.UsageError(f"{name} must be an integer") from error
    if value <= 0:
        raise pytest.UsageError(f"{name} must be greater than zero")
    return value


def _non_negative_float(raw: Any, name: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise pytest.UsageError(f"{name} must be a number") from error
    if value < 0:
        raise pytest.UsageError(f"{name} must not be negative")
    return value
