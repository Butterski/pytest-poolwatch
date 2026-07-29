from __future__ import annotations

import json

from pytest_poolwatch.analysis import analyze
from pytest_poolwatch.models import TargetSpec
from pytest_poolwatch.models import TestInterval as Interval
from pytest_poolwatch.reporting import (
    render_html,
    report_to_dict,
    terminal_lines,
    write_html,
    write_json,
)


def _report():
    intervals = [
        Interval(
            nodeid="test_<unsafe>.py::test_thing",
            attempt=1,
            worker="gw0",
            started_at=10,
            finished_at=11,
            outcome="passed",
        ),
        Interval(
            nodeid="test_other.py::test_thing",
            attempt=1,
            worker="gw1",
            started_at=10,
            finished_at=12,
            outcome="passed",
        ),
        Interval(
            nodeid="test_later.py::test_thing",
            attempt=1,
            worker="gw0",
            started_at=12,
            finished_at=13,
            outcome="passed",
        ),
    ]
    return analyze(
        intervals,
        [item.nodeid for item in intervals],
        TargetSpec(2, 2, "test", "explicit"),
        underfill_threshold=0,
        generated_at="2026-07-29T12:00:00Z",
        exit_status=0,
    )


def test_versioned_json_is_serializable_and_atomic(tmp_path) -> None:
    path = tmp_path / "nested" / "report.json"

    write_json(_report(), path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["target"]["configured"] == 2
    assert payload["summary"]["peak_active_tests"] == 2
    assert len(payload["tests"]) == 3
    assert not path.with_name(".report.json.tmp").exists()
    assert report_to_dict(_report()) == payload


def test_html_is_self_contained_and_escapes_nodeids(tmp_path) -> None:
    report = _report()
    path = tmp_path / "report.html"

    write_html(report, path)
    rendered = path.read_text(encoding="utf-8")

    assert rendered == render_html(report)
    assert "<svg" in rendered
    assert "gradient(" not in rendered
    assert "https://" not in rendered
    assert "read-only execution notebook" in rendered
    assert 'content: "Out [0]: summary"' in rendered
    assert "Segoe Print" not in rendered
    assert "Comic Sans" not in rendered
    assert "test_&lt;unsafe&gt;.py" in rendered
    assert "test_<unsafe>.py" not in rendered


def test_terminal_summary_explains_detected_underfill() -> None:
    report = _report()

    lines = terminal_lines(report)

    assert any("Configured concurrency" in line and "2" in line for line in lines)
    assert any("Scheduler underfill detected" in line for line in lines)
    assert any("Likely cause" in line for line in lines)


def test_terminal_summary_requests_target_for_fallback() -> None:
    report = _report()
    fallback = analyze(
        report.tests,
        [item.nodeid for item in report.tests],
        TargetSpec(None, 2, "observed peak", "fallback"),
        underfill_threshold=0,
        generated_at="now",
        exit_status=0,
    )

    lines = terminal_lines(fallback)

    assert any("diagnosis unavailable" in line for line in lines)
    assert any("--poolwatch-target" in line for line in lines)
