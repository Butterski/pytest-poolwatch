"""Conservative discovery of configured pytest concurrency."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest

from pytest_poolwatch.models import TargetSpec, TestInterval
from pytest_poolwatch.settings import Settings


def discover_target(
    config: pytest.Config,
    settings: Settings,
    intervals: Iterable[TestInterval],
    peak_active: int,
) -> TargetSpec:
    """Find a reliable capacity, falling back to the observed peak."""

    effective_peak = max(peak_active, 1)
    if settings.target is not None:
        return TargetSpec(
            configured=settings.target,
            effective=settings.target,
            source=settings.target_source or "explicit",
            confidence="explicit",
        )

    plugin_names = {name for name, _plugin in config.pluginmanager.list_name_plugin()}
    cooperative = _has_plugin(
        config, plugin_names, "asyncio-cooperative", "pytest_asyncio_cooperative"
    )
    xdist = _has_plugin(config, plugin_names, "xdist", "dsession")

    cooperative_limit = _cooperative_limit(config) if cooperative else None
    xdist_workers = _xdist_workers(config, intervals) if xdist else None
    if cooperative_limit is not None and xdist_workers is not None:
        limit = cooperative_limit * xdist_workers
        return TargetSpec(
            configured=limit,
            effective=limit,
            source="pytest-asyncio-cooperative × pytest-xdist",
            confidence="detected",
        )
    if cooperative_limit is not None:
        return TargetSpec(
            configured=cooperative_limit,
            effective=cooperative_limit,
            source="pytest-asyncio-cooperative",
            confidence="detected",
        )
    if xdist_workers is not None:
        return TargetSpec(
            configured=xdist_workers,
            effective=xdist_workers,
            source="pytest-xdist",
            confidence="detected",
        )

    if _has_plugin(config, plugin_names, "asyncio-concurrent"):
        return TargetSpec(
            configured=None,
            effective=effective_peak,
            source="observed peak (dynamic asyncio groups)",
            confidence="fallback",
        )

    # pytest and pytest-asyncio execute test protocols serially unless another
    # scheduler takes over. Unknown schedulers should pass --poolwatch-target.
    return TargetSpec(
        configured=1,
        effective=1,
        source="pytest serial execution",
        confidence="detected",
    )


def _has_plugin(
    config: pytest.Config, plugin_names: set[str], *candidates: str
) -> bool:
    for candidate in candidates:
        if candidate in plugin_names or config.pluginmanager.hasplugin(candidate):
            return True
    return any(
        any(candidate in name for candidate in candidates) for name in plugin_names
    )


def _cooperative_limit(config: pytest.Config) -> int | None:
    raw = _get_option(config, "max_asyncio_tasks")
    if raw in (None, ""):
        raw = _get_ini(config, "max_asyncio_tasks")
    return _positive_int(raw)


def _xdist_workers(
    config: pytest.Config, intervals: Iterable[TestInterval]
) -> int | None:
    raw = _get_option(config, "numprocesses")
    parsed = _positive_int(raw)
    if parsed is not None:
        return parsed
    workers = {item.worker for item in intervals if item.worker != "main"}
    return len(workers) or None


def _get_option(config: pytest.Config, name: str) -> Any:
    try:
        return config.getoption(name, default=None)
    except (AttributeError, ValueError):
        return None


def _get_ini(config: pytest.Config, name: str) -> Any:
    try:
        return config.getini(name)
    except ValueError:
        return None


def _positive_int(raw: Any) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None
