from __future__ import annotations

from types import SimpleNamespace

from pytest_poolwatch.collector import SessionCollector


def _report(
    nodeid: str,
    when: str,
    start: float,
    stop: float,
    outcome: str = "passed",
    **extra: object,
) -> SimpleNamespace:
    return SimpleNamespace(
        nodeid=nodeid,
        when=when,
        start=start,
        stop=stop,
        duration=stop - start,
        outcome=outcome,
        keywords=extra.pop("keywords", {}),
        **extra,
    )


def test_report_timestamps_override_late_log_hooks() -> None:
    collector = SessionCollector()
    collector.record_collection(["test_file.py::test_job"])
    collector.record_logstart("test_file.py::test_job", observed_at=100)
    collector.record_report(_report("test_file.py::test_job", "setup", 1, 2))
    collector.record_report(_report("test_file.py::test_job", "call", 2, 5))
    collector.record_report(_report("test_file.py::test_job", "teardown", 5, 6))
    collector.record_logfinish("test_file.py::test_job", observed_at=101)

    (interval,) = collector.finalize(session_finished_at=102)

    assert interval.started_at == 1
    assert interval.finished_at == 6
    assert interval.duration == 5
    assert [phase.name for phase in interval.phases] == ["setup", "call", "teardown"]
    assert interval.outcome == "passed"
    assert not interval.incomplete


def test_failure_outweighs_other_phase_outcomes() -> None:
    collector = SessionCollector()
    collector.record_report(_report("test_x", "setup", 0, 1))
    collector.record_report(_report("test_x", "call", 1, 2, outcome="failed"))
    collector.record_report(_report("test_x", "teardown", 2, 3))

    (interval,) = collector.finalize()

    assert interval.outcome == "failed"


def test_log_hooks_are_a_fallback_when_reports_are_missing() -> None:
    collector = SessionCollector()
    collector.record_logstart("test_interrupted", observed_at=10)

    (interval,) = collector.finalize(session_finished_at=12)

    assert interval.started_at == 10
    assert interval.finished_at == 12
    assert interval.incomplete
    assert interval.outcome == "unknown"


def test_ignore_marker_removes_test_from_collection_and_intervals() -> None:
    collector = SessionCollector()
    collector.record_collection(["kept", "ignored"])
    collector.record_report(
        _report("ignored", "call", 0, 1, keywords={"poolwatch_ignore": True})
    )
    collector.record_report(_report("kept", "call", 0, 1))

    intervals = collector.finalize()

    assert collector.collected_count == 1
    assert [interval.nodeid for interval in intervals] == ["kept"]


def test_repeated_nodeid_creates_an_attempt_per_protocol() -> None:
    collector = SessionCollector()
    for attempt in range(2):
        offset = float(attempt * 2)
        collector.record_logstart("test_retry", observed_at=offset)
        collector.record_report(_report("test_retry", "setup", offset, offset + 0.2))
        collector.record_report(
            _report("test_retry", "call", offset + 0.2, offset + 0.8)
        )
        collector.record_report(
            _report("test_retry", "teardown", offset + 0.8, offset + 1)
        )
        collector.record_logfinish("test_retry", observed_at=offset + 1)

    intervals = collector.finalize()

    assert [interval.attempt for interval in intervals] == [1, 2]
