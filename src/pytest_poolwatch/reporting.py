"""Terminal, JSON, and self-contained HTML renderers."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from pytest_poolwatch.models import PoolWatchReport, TimelinePoint


def report_to_dict(report: PoolWatchReport) -> dict[str, Any]:
    return {
        "schema_version": report.schema_version,
        "generated_at": report.generated_at,
        "exit_status": report.exit_status,
        "session": {
            "collected_tests": report.collected_count,
            "observed_test_attempts": report.observed_count,
            "duration_seconds": _rounded(report.summary.duration),
        },
        "target": {
            "configured": report.target.configured,
            "effective": report.target.effective,
            "source": report.target.source,
            "confidence": report.target.confidence,
        },
        "summary": {
            "peak_active_tests": report.summary.peak_active,
            "average_active_tests": _rounded(report.summary.average_active),
            "concurrency_utilization": _rounded(report.summary.utilization),
            "scheduler_underfill_seconds": _rounded(
                report.summary.scheduler_underfill_seconds
            ),
            "idle_slot_seconds": _rounded(report.summary.idle_slot_seconds),
            "peak_queued_tests": report.summary.queued_peak,
            "phase_duration_seconds": {
                name: _rounded(duration)
                for name, duration in report.summary.phase_durations.items()
            },
        },
        "underfill_windows": [
            {
                "started_at_seconds": _rounded(item.started_at),
                "finished_at_seconds": _rounded(item.finished_at),
                "duration_seconds": _rounded(item.duration),
                "minimum_active_tests": item.minimum_active,
                "maximum_queued_tests": item.maximum_queued,
                "idle_slot_seconds": _rounded(item.idle_slot_seconds),
            }
            for item in report.underfill_windows
        ],
        "timeline": [
            {
                "at_seconds": _rounded(point.offset),
                "active_tests": point.active,
                "queued_tests": point.queued,
            }
            for point in report.timeline
        ],
        "tests": [
            {
                "nodeid": test.nodeid,
                "attempt": test.attempt,
                "worker": test.worker,
                "started_at_seconds": _rounded(
                    test.started_at - report.tests[0].started_at
                ),
                "finished_at_seconds": _rounded(
                    test.finished_at - report.tests[0].started_at
                ),
                "duration_seconds": _rounded(test.duration),
                "outcome": test.outcome,
                "incomplete": test.incomplete,
                "phases": [
                    {
                        "name": phase.name,
                        "duration_seconds": _rounded(phase.duration),
                        "outcome": phase.outcome,
                    }
                    for phase in test.phases
                ],
            }
            for test in report.tests
        ],
    }


def terminal_lines(report: PoolWatchReport) -> list[str]:
    target = (
        str(report.target.configured)
        if report.target.configured is not None
        else f"unknown (peak baseline {report.target.effective})"
    )
    lines = [
        _metric("Configured concurrency", target),
        _metric("Target source", report.target.source),
        _metric("Peak active tests", str(report.summary.peak_active)),
        _metric("Average active tests", f"{report.summary.average_active:.2f}"),
        _metric(
            "Concurrency utilization",
            f"{report.summary.utilization * 100:.1f}%",
        ),
        _metric(
            "Scheduler underfill",
            _format_duration(report.summary.scheduler_underfill_seconds),
        ),
        _metric("Peak queued tests", str(report.summary.queued_peak)),
        _metric(
            "Idle slot-seconds",
            f"{report.summary.idle_slot_seconds:,.2f}",
        ),
    ]
    if report.underfill_windows:
        longest = max(report.underfill_windows, key=lambda item: item.duration)
        lines.extend(
            [
                "",
                "Scheduler underfill detected",
                (f"  Active: {longest.minimum_active} / {report.target.effective}"),
                f"  Queued: up to {longest.maximum_queued}",
                f"  Duration: {_format_duration(longest.duration)}",
                "  Likely cause: scheduler slots were not refilled while work was queued.",
            ]
        )
    elif not report.target.supports_underfill_detection:
        lines.extend(
            [
                "",
                "Underfill diagnosis unavailable without a configured concurrency target.",
                "Pass --poolwatch-target=N for definitive scheduler underfill detection.",
            ]
        )
    return lines


def write_json(report: PoolWatchReport, path: Path) -> None:
    payload = json.dumps(
        report_to_dict(report), ensure_ascii=False, indent=2, sort_keys=False
    )
    _atomic_write(path, payload + "\n")


def write_html(report: PoolWatchReport, path: Path) -> None:
    _atomic_write(path, render_html(report))


def render_html(report: PoolWatchReport) -> str:
    summary = report.summary
    target_text = (
        str(report.target.configured)
        if report.target.configured is not None
        else f"Unknown · peak baseline {report.target.effective}"
    )
    cards = [
        ("Configured concurrency", target_text),
        ("Peak active", str(summary.peak_active)),
        ("Average active", f"{summary.average_active:.2f}"),
        ("Utilization", f"{summary.utilization * 100:.1f}%"),
        ("Scheduler underfill", _format_duration(summary.scheduler_underfill_seconds)),
        ("Idle slot-seconds", f"{summary.idle_slot_seconds:,.2f}"),
    ]
    card_html = "".join(
        (
            '<article class="metric">'
            f"<span>{html.escape(label)}</span>"
            f"<strong>{html.escape(value)}</strong>"
            "</article>"
        )
        for label, value in cards
    )

    underfill_rows = (
        "".join(
            (
                "<tr>"
                f"<td>{item.started_at:.3f}s</td>"
                f"<td>{item.duration:.3f}s</td>"
                f"<td>{item.minimum_active} / {report.target.effective}</td>"
                f"<td>{item.maximum_queued}</td>"
                f"<td>{item.idle_slot_seconds:.3f}</td>"
                "</tr>"
            )
            for item in report.underfill_windows
        )
        or '<tr><td colspan="5" class="empty">No scheduler underfill detected.</td></tr>'
    )

    slowest = sorted(report.tests, key=lambda item: item.duration, reverse=True)[:10]
    test_rows = (
        "".join(
            (
                "<tr>"
                f"<td><code>{html.escape(test.nodeid)}</code></td>"
                f"<td>{html.escape(test.worker)}</td>"
                f"<td>{html.escape(test.outcome)}</td>"
                f"<td>{test.duration:.3f}s</td>"
                "</tr>"
            )
            for test in slowest
        )
        or '<tr><td colspan="4" class="empty">No test timings captured.</td></tr>'
    )

    phase_rows = (
        "".join(
            (f"<tr><td>{html.escape(name)}</td><td>{duration:.3f}s</td></tr>")
            for name, duration in summary.phase_durations.items()
        )
        or '<tr><td colspan="2" class="empty">No phase timings captured.</td></tr>'
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PoolWatch report</title>
<style>
:root {{
  color-scheme: light;
  --page: #f3f4f5;
  --cell: #ffffff;
  --cell-muted: #f6f8fa;
  --ink: #24292f;
  --muted: #66707b;
  --border: #d0d7de;
  --border-strong: #afb8c1;
  --accent: #f37626;
  --accent-strong: #c65316;
  --active: #2a7f62;
  --queued: #356fa3;
  --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}}
* {{ box-sizing: border-box; }}
::selection {{ background: #ffe0cc; color: var(--ink); }}
body {{
  margin: 0;
  background: var(--page);
  color: var(--ink);
  font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}}
main {{
  counter-reset: output;
  width: min(1180px, calc(100% - 24px));
  margin: 24px auto 48px;
  padding: 0 28px 56px;
  background: var(--cell);
  border: 1px solid var(--border);
  border-top: 4px solid var(--accent);
}}
header {{
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: end;
  padding: 22px 0 18px;
  border-bottom: 1px solid var(--border);
}}
h1 {{
  margin: 3px 0 0;
  font: 400 clamp(1.8rem, 4vw, 2.65rem)/1.15 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  letter-spacing: -.025em;
}}
h1 span {{
  color: var(--accent-strong);
  font-weight: 600;
}}
.eyebrow {{
  color: var(--accent-strong);
  font: 600 .76rem/1.4 var(--mono);
  letter-spacing: .015em;
}}
.meta {{
  color: var(--muted);
  text-align: right;
  font: .75rem/1.6 var(--mono);
}}
.grid {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  margin: 24px 0 30px;
  overflow: hidden;
  background: var(--border);
  border: 1px solid var(--border);
}}
.grid::before {{
  content: "Out [0]: summary";
  grid-column: 1 / -1;
  padding: 8px 12px;
  color: var(--accent-strong);
  background: var(--cell-muted);
  font: .75rem/1.4 var(--mono);
}}
.metric {{
  min-width: 0;
  padding: 14px 16px;
  background: var(--cell);
}}
.metric span {{
  display: block;
  color: var(--muted);
  font: .7rem/1.4 var(--mono);
  text-transform: uppercase;
  letter-spacing: .045em;
}}
.metric strong {{
  display: block;
  margin-top: 6px;
  overflow-wrap: anywhere;
  font: 600 1.22rem/1.4 var(--mono);
}}
section {{
  counter-increment: output;
  margin-top: 18px;
  padding: 0 16px 18px;
  overflow-x: auto;
  background: var(--cell);
  border: 1px solid var(--border);
  border-left: 3px solid var(--border-strong);
}}
h2 {{
  margin: 0 -16px 16px;
  padding: 9px 12px;
  background: var(--cell-muted);
  border-bottom: 1px solid var(--border);
  font-size: .92rem;
  font-weight: 500;
}}
h2::before {{
  content: "Out [" counter(output) "]: ";
  color: var(--accent-strong);
  font: .75rem/1 var(--mono);
}}
.chart {{ width: 100%; min-width: 620px; height: auto; display: block; }}
.chart text {{ font-family: var(--mono); }}
table {{ width: 100%; border-collapse: collapse; font-size: .86rem; }}
th {{
  color: var(--muted);
  background: var(--cell-muted);
  font: 600 .7rem/1.4 var(--mono);
  text-align: left;
  text-transform: uppercase;
  letter-spacing: .045em;
}}
th, td {{ border-bottom: 1px solid var(--border); padding: 9px 10px; }}
tr:last-child td {{ border-bottom: 0; }}
code {{ color: var(--queued); font: .82rem/1.5 var(--mono); overflow-wrap: anywhere; }}
.empty {{ color: var(--muted); text-align: center; padding: 24px; font-family: var(--mono); }}
.legend {{ color: var(--muted); margin-top: 8px; font: .75rem/1.4 var(--mono); }}
.dot {{ display: inline-block; height: 7px; margin-right: 6px; width: 7px; }}
@media (max-width: 760px) {{
  header {{ align-items: start; flex-direction: column; }}
  .meta {{ text-align: left; }}
  .grid {{ grid-template-columns: 1fr 1fr; }}
}}
@media (max-width: 520px) {{
  main {{ width: calc(100% - 12px); margin: 6px auto 24px; padding: 0 12px 36px; }}
  header {{ padding-top: 16px; }}
  .grid {{ grid-template-columns: 1fr; }}
  h1 {{ font-size: 1.9rem; }}
  section {{ padding-right: 10px; padding-left: 10px; }}
  h2 {{ margin-right: -10px; margin-left: -10px; }}
}}
</style>
</head>
<body>
<main>
  <header>
    <div>
      <div class="eyebrow">pytest-poolwatch / read-only execution notebook</div>
      <h1>Pool<span>Watch</span></h1>
    </div>
    <div class="meta">
      {html.escape(report.generated_at)}<br>
      Target source: {html.escape(report.target.source)}
    </div>
  </header>
  <div class="grid">{card_html}</div>
  <section>
    <h2>Active tests over time</h2>
    {_svg_chart(report.timeline, "active", report.target.effective, "#2a7f62", target=True)}
    <div class="legend">
      <span class="dot" style="background:#2a7f62"></span>active tests
      &nbsp;&nbsp;<span class="dot" style="background:#f37626"></span>configured target
    </div>
  </section>
  <section>
    <h2>Queued tests over time</h2>
    {_svg_chart(report.timeline, "queued", summary.queued_peak, "#356fa3")}
    <div class="legend"><span class="dot" style="background:#356fa3"></span>tests not yet started</div>
  </section>
  <section>
    <h2>Scheduler underfill windows</h2>
    <table>
      <thead><tr><th>Start</th><th>Duration</th><th>Active</th><th>Queued</th><th>Idle slot-s</th></tr></thead>
      <tbody>{underfill_rows}</tbody>
    </table>
  </section>
  <section>
    <h2>Pytest phase time</h2>
    <table><thead><tr><th>Phase</th><th>Aggregate duration</th></tr></thead><tbody>{phase_rows}</tbody></table>
  </section>
  <section>
    <h2>Slowest test attempts</h2>
    <table>
      <thead><tr><th>Test</th><th>Worker</th><th>Outcome</th><th>Duration</th></tr></thead>
      <tbody>{test_rows}</tbody>
    </table>
  </section>
</main>
</body>
</html>
"""


def _svg_chart(
    points: tuple[TimelinePoint, ...],
    field: str,
    ceiling: int,
    color: str,
    *,
    target: bool = False,
) -> str:
    width, height = 960, 260
    left, right, top, bottom = 48, 18, 18, 34
    plot_width = width - left - right
    plot_height = height - top - bottom
    duration = points[-1].offset if points else 0.0
    max_value = max(
        ceiling,
        max((int(getattr(point, field)) for point in points), default=0),
        1,
    )

    def x(offset: float) -> float:
        return left + (offset / duration * plot_width if duration else 0)

    def y(value: int) -> float:
        return top + plot_height - (value / max_value * plot_height)

    path_points: list[tuple[float, float]] = []
    for index, point in enumerate(points):
        value = int(getattr(point, field))
        point_x = x(point.offset)
        if index and path_points:
            path_points.append((point_x, path_points[-1][1]))
        path_points.append((point_x, y(value)))
    if path_points and duration:
        path_points.append((x(duration), path_points[-1][1]))
    path = " ".join(
        ("M" if index == 0 else "L") + f"{point_x:.2f},{point_y:.2f}"
        for index, (point_x, point_y) in enumerate(path_points)
    )

    grid = "".join(
        (
            f'<line x1="{left}" y1="{grid_y:.2f}" x2="{width - right}" '
            f'y2="{grid_y:.2f}" stroke="#e1e4e8" stroke-width="1"/>'
            f'<text x="{left - 8}" y="{grid_y + 4:.2f}" fill="#66707b" '
            f'font-size="11" text-anchor="end">{label}</text>'
        )
        for label in {0, max_value // 2, max_value}
        for grid_y in [y(label)]
    )
    target_line = ""
    if target and ceiling:
        target_y = y(ceiling)
        target_line = (
            f'<line x1="{left}" y1="{target_y:.2f}" x2="{width - right}" '
            f'y2="{target_y:.2f}" stroke="#f37626" stroke-width="2" '
            'stroke-dasharray="7 7"/>'
        )
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{html.escape(field)} over time">'
        f"{grid}{target_line}"
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="3" '
        'stroke-linejoin="round"/>'
        f'<text x="{left}" y="{height - 8}" fill="#66707b" font-size="11">0s</text>'
        f'<text x="{width - right}" y="{height - 8}" fill="#66707b" '
        f'font-size="11" text-anchor="end">{duration:.2f}s</text>'
        "</svg>"
    )


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _metric(label: str, value: str) -> str:
    return f"{label + ':':<31}{value:>12}"


def _format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes, remainder = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {remainder:.1f}s"
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours}h {minutes}m {remainder:.0f}s"


def _rounded(value: float) -> float:
    return round(value, 6)
