<div align="center">

# pytest-poolwatch

**See whether your pytest concurrency pool is actually full.**

[![PyPI](https://img.shields.io/pypi/v/pytest-poolwatch?logo=pypi&logoColor=white)](https://pypi.org/project/pytest-poolwatch/)
[![Python](https://img.shields.io/pypi/pyversions/pytest-poolwatch?logo=python&logoColor=white)](https://pypi.org/project/pytest-poolwatch/)
[![pytest](https://img.shields.io/badge/pytest-8.2%E2%80%939.x-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![CI](https://github.com/Butterski/pytest-poolwatch/actions/workflows/ci.yml/badge.svg)](https://github.com/Butterski/pytest-poolwatch/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/github/license/Butterski/pytest-poolwatch)](https://github.com/Butterski/pytest-poolwatch/blob/master/LICENSE)
[![Status: Alpha](https://img.shields.io/pypi/status/pytest-poolwatch)](https://pypi.org/project/pytest-poolwatch/)

Concurrency profiling and scheduler-underfill diagnostics for pytest.

[Documentation](https://github.com/Butterski/pytest-poolwatch/wiki) ·
[Examples](https://github.com/Butterski/pytest-poolwatch/wiki/Examples) ·
[JSON schema](https://github.com/Butterski/pytest-poolwatch/wiki/JSON-Report) ·
[Issues](https://github.com/Butterski/pytest-poolwatch/issues)

</div>

`pytest-poolwatch` reconstructs when tests actually overlapped and shows whether
configured execution slots stayed busy while runnable tests were still queued.
It observes public pytest reports; it does not replace the scheduler, runner, or
fixture lifecycle.

## Why PoolWatch?

Ordinary duration reports tell you which tests were slow. PoolWatch answers a
different question: **did the scheduler keep the available concurrency busy?**

- Measure peak and time-weighted average concurrency.
- Separate scheduler underfill from normal end-of-suite drain.
- Quantify utilization and idle slot-seconds.
- Inspect active and queued test timelines.
- Export versioned JSON and a self-contained HTML report.
- Work without a server, database, agent, or private pytest API.

## Installation

```console
python -m pip install pytest-poolwatch
```

With uv:

```console
uv add --dev pytest-poolwatch
```

Installing the package is enough for pytest to discover its `pytest11` plugin
entry point.

## Quick start

```console
pytest --poolwatch --poolwatch-target=40
```

PoolWatch adds a summary after the normal pytest result:

```text
============================= PoolWatch summary =============================
Configured concurrency:                 40
Target source:                command_line
Peak active tests:                      40
Average active tests:                 32.60
Concurrency utilization:             81.5%
Scheduler underfill:                17m 23s
Peak queued tests:                     126
Idle slot-seconds:                 4,912.00
```

Generate machine-readable and visual reports at the same time:

```console
pytest --poolwatch \
  --poolwatch-target=40 \
  --poolwatch-json=.poolwatch/run.json \
  --poolwatch-html=.poolwatch/run.html
```

The HTML report is a portable, read-only notebook containing concurrency and
queue charts, underfill windows, pytest phase totals, and the slowest attempts.

## The diagnostic that matters

PoolWatch does not label every idle slot as a scheduling problem:

| State | Queue | Active tests | Diagnosis |
| --- | ---: | ---: | --- |
| Work is waiting and capacity is unused | `> 0` | `< target` | Scheduler underfill |
| No work remains to start | `0` | `< target` | Normal suite drain |
| Capacity is unknown | any | observed peak | Baseline only; pass an explicit target for a definitive diagnosis |

This distinction is what exposed the refill bug fixed by
[pytest-asyncio-cooperative PR #86](https://github.com/willemt/pytest-asyncio-cooperative/pull/86):
the controlled pre-fix workload measured **34.2% utilization and 0.885s of
underfill**, while the fixed scheduler measured **73.1% utilization with no
material underfill**. Exact timings depend on the machine; the behavioral
assertions do not.

## Configuration

Command-line values take precedence over pytest configuration:

```toml
[tool.pytest.ini_options]
poolwatch = true
poolwatch_target = 40
poolwatch_json = ".poolwatch/run.json"
poolwatch_html = ".poolwatch/run.html"
poolwatch_underfill_threshold = 0.1
```

| CLI option | Purpose |
| --- | --- |
| `--poolwatch` | Enable profiling and the terminal summary. |
| `--poolwatch-target=N` | Set the expected active-test capacity. |
| `--poolwatch-json=PATH` | Write schema-versioned JSON and enable PoolWatch. |
| `--poolwatch-html=PATH` | Write self-contained HTML and enable PoolWatch. |
| `--poolwatch-underfill-threshold=SECONDS` | Ignore shorter underfill windows. |

Exclude a deliberately unrepresentative test:

```python
import pytest


@pytest.mark.poolwatch_ignore
def test_one_off_migration():
    ...
```

See the [configuration guide](https://github.com/Butterski/pytest-poolwatch/wiki/Configuration)
and [metrics reference](https://github.com/Butterski/pytest-poolwatch/wiki/Metrics-and-Diagnosis)
for the full behavior.

## Compatibility

| Runner or plugin | Status | Capacity source |
| --- | --- | --- |
| pytest | Supported | Serial capacity of 1 |
| pytest-asyncio | Supported | Serial test protocols |
| pytest-xdist | Supported | Numeric workers, or observed workers for `auto` |
| pytest-asyncio-cooperative | Supported on its own | `max_asyncio_tasks` |
| pytest-asyncio-concurrent | Conservative support | Explicit target or observed peak |
| Custom scheduler | Supported with configuration | `--poolwatch-target=N` |
| pytest-xdist + pytest-asyncio-cooperative | **Unsupported upstream combination** | Both plugins replace overlapping runtest-loop behavior |

When both schedulers are detected in an active run, PoolWatch prefers the xdist
worker count rather than inventing a combined capacity. Merely installing xdist
does not suppress cooperative-only capacity detection. Do not enable the two
schedulers together; their execution hooks conflict independently of PoolWatch.

PoolWatch relies on public pytest hooks and report timestamps. Compatibility
details and known limitations are documented in the
[compatibility guide](https://github.com/Butterski/pytest-poolwatch/wiki/Compatibility).

## Documentation

- [Getting started](https://github.com/Butterski/pytest-poolwatch/wiki/Getting-Started)
- [Configuration](https://github.com/Butterski/pytest-poolwatch/wiki/Configuration)
- [Metrics and diagnosis](https://github.com/Butterski/pytest-poolwatch/wiki/Metrics-and-Diagnosis)
- [Reports and JSON schema](https://github.com/Butterski/pytest-poolwatch/wiki/Reports)
- [Examples and the PR #86 regression](https://github.com/Butterski/pytest-poolwatch/wiki/Examples)
- [Architecture](https://github.com/Butterski/pytest-poolwatch/wiki/Architecture)
- [Development](https://github.com/Butterski/pytest-poolwatch/wiki/Development)
- [Release guide](https://github.com/Butterski/pytest-poolwatch/wiki/Release-Guide)
- [Project story and roadmap](https://github.com/Butterski/pytest-poolwatch/wiki/Project-Story)

## Development

```console
git clone https://github.com/Butterski/pytest-poolwatch.git
cd pytest-poolwatch
uv sync --locked --dev
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run coverage run -m pytest
uv run coverage combine
uv run coverage report
uv build
```

The test matrix covers Python 3.11–3.14. Releases are built from GitHub Releases
and published through PyPI Trusted Publishing.

## Scope

Version 0.1 measures test overlap, configured capacity, queued work, utilization,
and scheduler underfill. It does **not** currently measure event-loop lag or
attribute blocking calls. `poolwatch_blocking` is a documentation marker reserved
for that future work.

PoolWatch is distributed under the [MIT License](https://github.com/Butterski/pytest-poolwatch/blob/master/LICENSE).
Contributions and reproducible scheduler workloads are welcome.
