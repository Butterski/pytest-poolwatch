# Changelog

All notable changes to pytest-poolwatch are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.1] - 2026-07-29

### Fixed

- Pin the setup-uv GitHub Action to its official v8.1.0 commit so release
  workflows resolve the action reliably.

## [0.1.0] - 2026-07-29

### Added

- pytest concurrency collection through public report and lifecycle hooks.
- Sweep-line analysis of active tests, queued tests, utilization, idle
  slot-seconds, and scheduler underfill.
- Terminal summaries and atomic, schema-versioned JSON reports.
- Self-contained HTML reports with concurrency and queue timelines.
- Capacity discovery for serial pytest, pytest-xdist, and
  pytest-asyncio-cooperative when used independently.
- Ignore and documentation markers for workload-specific annotations.
- Deterministic PR #86 regression and cloud-job stress examples.

[Unreleased]: https://github.com/Butterski/pytest-poolwatch/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/Butterski/pytest-poolwatch/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Butterski/pytest-poolwatch/releases/tag/v0.1.0

