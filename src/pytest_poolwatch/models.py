"""Immutable data models shared by collection, analysis, and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PhaseName = Literal["setup", "call", "teardown"]


@dataclass(frozen=True, slots=True)
class PhaseInterval:
    """The observed execution interval for one pytest phase."""

    name: PhaseName
    started_at: float
    finished_at: float
    outcome: str

    @property
    def duration(self) -> float:
        return max(0.0, self.finished_at - self.started_at)


@dataclass(frozen=True, slots=True)
class TestInterval:
    """A single observed attempt of a pytest item."""

    nodeid: str
    attempt: int
    worker: str
    started_at: float
    finished_at: float
    outcome: str
    phases: tuple[PhaseInterval, ...] = ()
    incomplete: bool = False

    @property
    def duration(self) -> float:
        return max(0.0, self.finished_at - self.started_at)


@dataclass(frozen=True, slots=True)
class TargetSpec:
    """Configured or inferred scheduler capacity."""

    configured: int | None
    effective: int
    source: str
    confidence: Literal["explicit", "detected", "fallback"]

    @property
    def supports_underfill_detection(self) -> bool:
        return self.configured is not None


@dataclass(frozen=True, slots=True)
class TimelinePoint:
    """State immediately after all events at ``offset`` were applied."""

    offset: float
    active: int
    queued: int


@dataclass(frozen=True, slots=True)
class UnderfillWindow:
    """A contiguous interval with queued work and unused known capacity."""

    started_at: float
    finished_at: float
    minimum_active: int
    maximum_queued: int
    idle_slot_seconds: float

    @property
    def duration(self) -> float:
        return max(0.0, self.finished_at - self.started_at)


@dataclass(frozen=True, slots=True)
class PoolWatchSummary:
    """Aggregate metrics derived from a timeline."""

    duration: float
    peak_active: int
    average_active: float
    utilization: float
    scheduler_underfill_seconds: float
    idle_slot_seconds: float
    queued_peak: int
    phase_durations: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PoolWatchReport:
    """Complete, renderer-independent report."""

    schema_version: int
    generated_at: str
    exit_status: int
    collected_count: int
    observed_count: int
    target: TargetSpec
    summary: PoolWatchSummary
    timeline: tuple[TimelinePoint, ...]
    underfill_windows: tuple[UnderfillWindow, ...]
    tests: tuple[TestInterval, ...]
