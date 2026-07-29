"""Sweep-line concurrency analysis."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import replace

from pytest_poolwatch.models import (
    PoolWatchReport,
    PoolWatchSummary,
    TargetSpec,
    TestInterval,
    TimelinePoint,
    UnderfillWindow,
)


def peak_concurrency(intervals: Iterable[TestInterval]) -> int:
    """Return the maximum number of overlapping test intervals."""

    grouped: dict[float, int] = defaultdict(int)
    for interval in intervals:
        grouped[interval.started_at] += 1
        grouped[interval.finished_at] -= 1
    active = 0
    peak = 0
    for timestamp in sorted(grouped):
        active += grouped[timestamp]
        peak = max(peak, active)
    return peak


def analyze(
    intervals: Iterable[TestInterval],
    collected_nodeids: Iterable[str],
    target: TargetSpec,
    *,
    underfill_threshold: float,
    generated_at: str,
    exit_status: int,
) -> PoolWatchReport:
    tests = tuple(sorted(intervals, key=lambda item: (item.started_at, item.nodeid)))
    collected = set(collected_nodeids)
    if not tests:
        effective_target = target.configured or max(target.effective, 1)
        return PoolWatchReport(
            schema_version=1,
            generated_at=generated_at,
            exit_status=exit_status,
            collected_count=len(collected),
            observed_count=0,
            target=replace(target, effective=effective_target),
            summary=PoolWatchSummary(
                duration=0.0,
                peak_active=0,
                average_active=0.0,
                utilization=0.0,
                scheduler_underfill_seconds=0.0,
                idle_slot_seconds=0.0,
                queued_peak=len(collected),
                phase_durations={},
            ),
            timeline=(),
            underfill_windows=(),
            tests=(),
        )

    events: dict[float, list[tuple[str, str]]] = defaultdict(list)
    for test in tests:
        events[test.started_at].append(("start", test.nodeid))
        events[test.finished_at].append(("finish", test.nodeid))

    times = sorted(events)
    origin = times[0]
    total_work = max(len(collected), len({item.nodeid for item in tests}))
    queued = total_work
    active = 0
    started_nodeids: set[str] = set()
    points: list[TimelinePoint] = []
    active_area = 0.0
    idle_slot_seconds = 0.0
    raw_underfill: list[UnderfillWindow] = []
    peak_active = 0
    queued_peak = 0

    for index, at in enumerate(times):
        # Apply completions before starts for deterministic state transitions;
        # every event at this timestamp is applied before measuring a segment.
        for event, _nodeid in events[at]:
            if event == "finish":
                active = max(0, active - 1)
        for event, nodeid in events[at]:
            if event != "start":
                continue
            active += 1
            if nodeid not in started_nodeids:
                started_nodeids.add(nodeid)
                queued = max(0, queued - 1)

        peak_active = max(peak_active, active)
        queued_peak = max(queued_peak, queued)
        points.append(TimelinePoint(offset=at - origin, active=active, queued=queued))
        if index + 1 >= len(times):
            continue

        next_at = times[index + 1]
        duration = max(0.0, next_at - at)
        active_area += active * duration
        idle_slot_seconds += max(0, target.effective - active) * duration
        if (
            target.supports_underfill_detection
            and queued > 0
            and active < target.effective
            and duration > 0
        ):
            _append_underfill(
                raw_underfill,
                started_at=at - origin,
                finished_at=next_at - origin,
                active=active,
                queued=queued,
                target=target.effective,
            )

    total_duration = max(0.0, times[-1] - origin)
    effective_target = target.configured or max(peak_active, 1)
    if effective_target != target.effective:
        target = replace(target, effective=effective_target)
        idle_slot_seconds = sum(
            max(0, effective_target - point.active)
            * _point_duration(points, index, total_duration)
            for index, point in enumerate(points)
        )

    underfill = tuple(
        window
        for window in raw_underfill
        if window.duration + 1e-12 >= underfill_threshold
    )
    average_active = active_area / total_duration if total_duration else 0.0
    utilization = (
        active_area / (effective_target * total_duration)
        if total_duration and effective_target
        else 0.0
    )
    phase_durations: dict[str, float] = defaultdict(float)
    for test in tests:
        for phase in test.phases:
            phase_durations[phase.name] += phase.duration

    return PoolWatchReport(
        schema_version=1,
        generated_at=generated_at,
        exit_status=exit_status,
        collected_count=total_work,
        observed_count=len(tests),
        target=target,
        summary=PoolWatchSummary(
            duration=total_duration,
            peak_active=peak_active,
            average_active=average_active,
            utilization=utilization,
            scheduler_underfill_seconds=sum(item.duration for item in underfill),
            idle_slot_seconds=idle_slot_seconds,
            queued_peak=queued_peak,
            phase_durations=dict(phase_durations),
        ),
        timeline=tuple(points),
        underfill_windows=underfill,
        tests=tests,
    )


def _append_underfill(
    windows: list[UnderfillWindow],
    *,
    started_at: float,
    finished_at: float,
    active: int,
    queued: int,
    target: int,
) -> None:
    idle = max(0, target - active) * (finished_at - started_at)
    if windows and abs(windows[-1].finished_at - started_at) < 1e-12:
        previous = windows[-1]
        windows[-1] = UnderfillWindow(
            started_at=previous.started_at,
            finished_at=finished_at,
            minimum_active=min(previous.minimum_active, active),
            maximum_queued=max(previous.maximum_queued, queued),
            idle_slot_seconds=previous.idle_slot_seconds + idle,
        )
        return
    windows.append(
        UnderfillWindow(
            started_at=started_at,
            finished_at=finished_at,
            minimum_active=active,
            maximum_queued=queued,
            idle_slot_seconds=idle,
        )
    )


def _point_duration(
    points: list[TimelinePoint], index: int, total_duration: float
) -> float:
    if index + 1 < len(points):
        return max(0.0, points[index + 1].offset - points[index].offset)
    return max(0.0, total_duration - points[index].offset)
