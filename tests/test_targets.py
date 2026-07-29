from __future__ import annotations

from typing import Any

from pytest_poolwatch.settings import Settings
from pytest_poolwatch.targets import discover_target


class _PluginManager:
    def __init__(self, names: set[str]) -> None:
        self.names = names

    def list_name_plugin(self) -> list[tuple[str, object]]:
        return [(name, object()) for name in self.names]

    def hasplugin(self, name: str) -> bool:
        return name in self.names


class _Config:
    def __init__(self, plugins: set[str], options: dict[str, object]) -> None:
        self.pluginmanager = _PluginManager(plugins)
        self.options = options

    def getoption(self, name: str, default: object = None) -> object:
        return self.options.get(name, default)

    def getini(self, name: str) -> object:
        return self.options.get(name, "")


def _settings() -> Settings:
    return Settings(
        enabled=True,
        target=None,
        target_source=None,
        json_path=None,
        html_path=None,
        underfill_threshold=0.1,
    )


def test_xdist_capacity_wins_when_cooperative_is_also_installed() -> None:
    config: Any = _Config(
        {"xdist", "asyncio-cooperative"},
        {"numprocesses": 2, "max_asyncio_tasks": 100},
    )

    target = discover_target(
        config,
        _settings(),
        (),
        peak_active=2,
    )

    assert target.configured == 2
    assert target.effective == 2
    assert target.source == "pytest-xdist"


def test_cooperative_capacity_is_detected_when_used_without_xdist() -> None:
    config: Any = _Config(
        {"asyncio-cooperative"},
        {"max_asyncio_tasks": 40},
    )

    target = discover_target(
        config,
        _settings(),
        (),
        peak_active=40,
    )

    assert target.configured == 40
    assert target.effective == 40
    assert target.source == "pytest-asyncio-cooperative"


def test_installed_but_inactive_xdist_does_not_hide_cooperative_capacity() -> None:
    config: Any = _Config(
        {"xdist", "asyncio-cooperative"},
        {"numprocesses": None, "max_asyncio_tasks": 40},
    )

    target = discover_target(
        config,
        _settings(),
        (),
        peak_active=40,
    )

    assert target.configured == 40
    assert target.effective == 40
    assert target.source == "pytest-asyncio-cooperative"
