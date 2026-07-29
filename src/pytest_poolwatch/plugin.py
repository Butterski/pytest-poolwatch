"""pytest entry point for PoolWatch."""

from __future__ import annotations

import warnings
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pytest_poolwatch.analysis import analyze, peak_concurrency
from pytest_poolwatch.collector import SessionCollector
from pytest_poolwatch.models import PoolWatchReport
from pytest_poolwatch.reporting import terminal_lines, write_html, write_json
from pytest_poolwatch.settings import Settings, add_options, load_settings
from pytest_poolwatch.targets import discover_target


def pytest_addoption(parser: pytest.Parser) -> None:
    add_options(parser)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "poolwatch_ignore: exclude a test from PoolWatch timing and metrics",
    )
    config.addinivalue_line(
        "markers",
        "poolwatch_blocking: document a test expected to perform blocking work",
    )
    settings = load_settings(config)
    if not settings.enabled or hasattr(config, "workerinput"):
        return
    runtime = PoolWatchPlugin(config, settings)
    config.pluginmanager.register(runtime, "poolwatch-runtime")


class PoolWatchPlugin:
    """Per-session runtime; instances avoid state leaking between pytest runs."""

    def __init__(self, config: pytest.Config, settings: Settings) -> None:
        self.config = config
        self.settings = settings
        self.collector = SessionCollector()
        self.report: PoolWatchReport | None = None

    def pytest_sessionstart(self, session: pytest.Session) -> None:
        del session
        self.collector.session_started_at = datetime.now(tz=UTC).timestamp()

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        ignored = {
            item.nodeid
            for item in session.items
            if item.get_closest_marker("poolwatch_ignore") is not None
        }
        self.collector.record_collection(
            (item.nodeid for item in session.items), ignored_nodeids=ignored
        )

    @pytest.hookimpl(optionalhook=True)
    def pytest_xdist_node_collection_finished(self, node: Any, ids: list[str]) -> None:
        del node
        self.collector.record_collection(ids)

    def pytest_runtest_logstart(
        self, nodeid: str, location: tuple[str, int | None, str]
    ) -> None:
        del location
        self.collector.record_logstart(nodeid)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        self.collector.record_report(report)

    def pytest_runtest_logfinish(
        self, nodeid: str, location: tuple[str, int | None, str]
    ) -> None:
        del location
        self.collector.record_logfinish(nodeid)

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(
        self, session: pytest.Session, exitstatus: pytest.ExitCode
    ) -> None:
        del session
        intervals = self.collector.finalize()
        target = discover_target(
            self.config,
            self.settings,
            intervals,
            peak_active=peak_concurrency(intervals),
        )
        self.report = analyze(
            intervals,
            self.collector.collected_nodeids,
            target,
            underfill_threshold=self.settings.underfill_threshold,
            generated_at=datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
            exit_status=int(exitstatus),
        )
        if self.settings.json_path is not None:
            self._write_artifact(write_json, self.settings.json_path)
        if self.settings.html_path is not None:
            self._write_artifact(write_html, self.settings.html_path)

    def pytest_terminal_summary(
        self,
        terminalreporter: Any,
        exitstatus: pytest.ExitCode,
        config: pytest.Config,
    ) -> None:
        del exitstatus, config
        if self.report is None:
            return
        terminalreporter.write_sep("=", "PoolWatch summary")
        for line in terminal_lines(self.report):
            terminalreporter.write_line(line)

    def _write_artifact(
        self, writer: Callable[[PoolWatchReport, Path], None], path: Path
    ) -> None:
        assert self.report is not None
        try:
            writer(self.report, path)
        except OSError as error:
            warnings.warn(
                pytest.PytestWarning(
                    f"PoolWatch could not write {path}: {error.strerror or error}"
                ),
                stacklevel=2,
            )
