from __future__ import annotations

import pytest

from pytest_poolwatch.analysis import analyze, peak_concurrency
from pytest_poolwatch.models import TargetSpec
from pytest_poolwatch.models import TestInterval as Interval


def _interval(nodeid: str, start: float, finish: float) -> Interval:
    return Interval(
        nodeid=nodeid,
        attempt=1,
        worker="main",
        started_at=start,
        finished_at=finish,
        outcome="passed",
    )


def _target(limit: int | None, effective: int | None = None) -> TargetSpec:
    return TargetSpec(
        configured=limit,
        effective=effective or limit or 1,
        source="test",
        confidence="detected" if limit is not None else "fallback",
    )


def _analyze(
    intervals: list[Interval],
    target: TargetSpec,
    *,
    threshold: float = 0.0,
):
    return analyze(
        intervals,
        [item.nodeid for item in intervals],
        target,
        underfill_threshold=threshold,
        generated_at="2026-07-29T12:00:00Z",
        exit_status=0,
    )


def test_work_conserving_timeline_has_no_underfill() -> None:
    intervals = [
        _interval("a", 0, 1),
        _interval("b", 0, 1),
        _interval("c", 0, 1),
        _interval("d", 0, 1),
        _interval("e", 1, 2),
        _interval("f", 1, 2),
    ]

    report = _analyze(intervals, _target(4))

    assert peak_concurrency(intervals) == 4
    assert report.summary.peak_active == 4
    assert report.summary.average_active == pytest.approx(3.0)
    assert report.summary.utilization == pytest.approx(0.75)
    assert report.summary.queued_peak == 2
    assert report.summary.idle_slot_seconds == pytest.approx(2.0)
    assert report.summary.scheduler_underfill_seconds == 0
    assert report.underfill_windows == ()


def test_pr86_shape_is_diagnosed_as_underfill() -> None:
    intervals = [
        _interval("a", 0, 1),
        _interval("b", 0, 1),
        _interval("c", 0, 1),
        _interval("d", 0, 1),
        _interval("e", 1, 2),
        _interval("f", 2, 3),
    ]

    report = _analyze(intervals, _target(4))

    assert report.summary.peak_active == 4
    assert report.summary.average_active == pytest.approx(2.0)
    assert report.summary.utilization == pytest.approx(0.5)
    assert report.summary.scheduler_underfill_seconds == pytest.approx(1.0)
    assert report.summary.idle_slot_seconds == pytest.approx(6.0)
    assert len(report.underfill_windows) == 1
    window = report.underfill_windows[0]
    assert window.started_at == pytest.approx(1.0)
    assert window.finished_at == pytest.approx(2.0)
    assert window.minimum_active == 1
    assert window.maximum_queued == 1
    assert window.idle_slot_seconds == pytest.approx(3.0)


def test_natural_drain_is_not_underfill() -> None:
    intervals = [
        _interval("a", 0, 1),
        _interval("b", 0, 2),
        _interval("c", 0, 3),
    ]

    report = _analyze(intervals, _target(4))

    assert report.summary.idle_slot_seconds > 0
    assert report.summary.scheduler_underfill_seconds == 0


def test_short_underfill_is_filtered_by_threshold() -> None:
    intervals = [
        _interval("a", 0, 1),
        _interval("b", 0, 1),
        _interval("c", 0, 1),
        _interval("d", 0, 1),
        _interval("e", 1.05, 2),
        _interval("f", 1.05, 2),
    ]

    report = _analyze(intervals, _target(4), threshold=0.1)

    assert report.underfill_windows == ()
    assert report.summary.scheduler_underfill_seconds == 0


def test_unknown_target_uses_peak_without_definitive_diagnosis() -> None:
    intervals = [
        _interval("a", 0, 1),
        _interval("b", 0, 1),
        _interval("c", 1, 2),
    ]

    report = _analyze(intervals, _target(None, effective=2))

    assert report.target.configured is None
    assert report.target.effective == 2
    assert report.summary.utilization == pytest.approx(0.75)
    assert report.underfill_windows == ()


def test_empty_run_preserves_collected_count() -> None:
    report = analyze(
        [],
        ["a", "b"],
        _target(1),
        underfill_threshold=0,
        generated_at="now",
        exit_status=5,
    )

    assert report.collected_count == 2
    assert report.observed_count == 0
    assert report.summary.duration == 0
    assert report.exit_status == 5
