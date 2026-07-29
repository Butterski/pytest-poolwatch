"""Normalize pytest reports into test execution intervals."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, cast

from pytest_poolwatch.models import PhaseInterval, PhaseName, TestInterval

_PHASES = frozenset({"setup", "call", "teardown"})


@dataclass(slots=True)
class _Attempt:
    nodeid: str
    attempt: int
    worker: str
    observed_start: float | None = None
    observed_finish: float | None = None
    phases: dict[PhaseName, PhaseInterval] = field(default_factory=dict)

    @property
    def closed(self) -> bool:
        return self.observed_finish is not None


class SessionCollector:
    """Collect timing data without depending on a scheduler's private API."""

    def __init__(self) -> None:
        self.session_started_at = time.time()
        self.collected_nodeids: dict[str, None] = {}
        self.ignored_nodeids: set[str] = set()
        self._attempts: dict[tuple[str, str], list[_Attempt]] = defaultdict(list)
        self._pending_starts: dict[str, list[float]] = defaultdict(list)

    def record_collection(
        self, nodeids: Iterable[str], ignored_nodeids: Iterable[str] = ()
    ) -> None:
        ignored = set(ignored_nodeids)
        self.ignored_nodeids.update(ignored)
        for nodeid in nodeids:
            if nodeid not in ignored:
                self.collected_nodeids.setdefault(nodeid, None)

    def record_logstart(self, nodeid: str, observed_at: float | None = None) -> None:
        if nodeid not in self.ignored_nodeids:
            self._pending_starts[nodeid].append(observed_at or time.time())

    def record_report(self, report: Any) -> None:
        nodeid = str(report.nodeid)
        keywords = getattr(report, "keywords", {})
        if nodeid in self.ignored_nodeids or "poolwatch_ignore" in keywords:
            self.ignored_nodeids.add(nodeid)
            self.collected_nodeids.pop(nodeid, None)
            return

        raw_phase = str(report.when)
        if raw_phase not in _PHASES:
            return
        phase = cast(PhaseName, raw_phase)
        worker = str(getattr(report, "worker_id", "main"))
        attempt = self._attempt_for_report(worker, nodeid, phase)

        fallback = time.time()
        started_at = _safe_timestamp(getattr(report, "start", None), fallback)
        finished_at = _safe_timestamp(
            getattr(report, "stop", None),
            started_at + max(0.0, float(getattr(report, "duration", 0.0))),
        )
        if finished_at < started_at:
            finished_at = started_at
        attempt.phases[phase] = PhaseInterval(
            name=phase,
            started_at=started_at,
            finished_at=finished_at,
            outcome=str(report.outcome),
        )

    def record_logfinish(self, nodeid: str, observed_at: float | None = None) -> None:
        if nodeid in self.ignored_nodeids:
            return
        candidates = [
            attempt
            for (worker, candidate_nodeid), attempts in self._attempts.items()
            if candidate_nodeid == nodeid
            for attempt in attempts
            if not attempt.closed
        ]
        if candidates:
            candidates[-1].observed_finish = observed_at or time.time()

    def finalize(
        self, session_finished_at: float | None = None
    ) -> tuple[TestInterval, ...]:
        finished_at = session_finished_at or time.time()
        for nodeid, starts in self._pending_starts.items():
            attempts = self._attempts[("main", nodeid)]
            next_attempt = len(attempts) + 1
            for offset, started_at in enumerate(starts):
                attempts.append(
                    _Attempt(
                        nodeid=nodeid,
                        attempt=next_attempt + offset,
                        worker="main",
                        observed_start=started_at,
                    )
                )
        self._pending_starts.clear()

        intervals: list[TestInterval] = []
        for attempts in self._attempts.values():
            for attempt in attempts:
                interval = _finalize_attempt(attempt, finished_at)
                if interval is not None:
                    intervals.append(interval)
        intervals.sort(
            key=lambda item: (
                item.started_at,
                item.finished_at,
                item.nodeid,
                item.attempt,
            )
        )
        return tuple(intervals)

    @property
    def collected_count(self) -> int:
        return len(self.collected_nodeids)

    def _attempt_for_report(
        self, worker: str, nodeid: str, phase: PhaseName
    ) -> _Attempt:
        key = (worker, nodeid)
        attempts = self._attempts[key]
        needs_new_attempt = (
            not attempts
            or attempts[-1].closed
            or (
                phase == "setup"
                and bool(attempts[-1].phases)
                and "teardown" in attempts[-1].phases
            )
        )
        if needs_new_attempt:
            observed_start = None
            if self._pending_starts[nodeid]:
                observed_start = self._pending_starts[nodeid].pop(0)
            attempts.append(
                _Attempt(
                    nodeid=nodeid,
                    attempt=len(attempts) + 1,
                    worker=worker,
                    observed_start=observed_start,
                )
            )
        return attempts[-1]


def _finalize_attempt(
    attempt: _Attempt, session_finished_at: float
) -> TestInterval | None:
    phases = tuple(
        attempt.phases[name]
        for name in ("setup", "call", "teardown")
        if name in attempt.phases
    )
    if phases:
        # Report timestamps are authoritative. Some concurrent plugins emit
        # logstart/logfinish only after the coroutine has already completed.
        started_at = min(phase.started_at for phase in phases)
        finished_at = max(phase.finished_at for phase in phases)
        incomplete = False
    elif attempt.observed_start is not None:
        started_at = attempt.observed_start
        finished_at = attempt.observed_finish or session_finished_at
        incomplete = attempt.observed_finish is None
    else:
        return None

    outcome = _attempt_outcome(phases)
    return TestInterval(
        nodeid=attempt.nodeid,
        attempt=attempt.attempt,
        worker=attempt.worker,
        started_at=started_at,
        finished_at=max(started_at, finished_at),
        outcome=outcome,
        phases=phases,
        incomplete=incomplete,
    )


def _attempt_outcome(phases: tuple[PhaseInterval, ...]) -> str:
    if any(phase.outcome == "failed" for phase in phases):
        return "failed"
    call = next((phase for phase in phases if phase.name == "call"), None)
    if call is not None:
        return call.outcome
    if any(phase.outcome == "skipped" for phase in phases):
        return "skipped"
    if phases:
        return phases[-1].outcome
    return "unknown"


def _safe_timestamp(value: Any, fallback: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return fallback
    return result if result >= 0 else fallback
