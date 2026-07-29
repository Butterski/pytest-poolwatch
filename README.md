# pytest-poolwatch

`pytest-poolwatch` is a concurrency profiler and scheduler underfill detector for pytest. It observes public pytest reports, reconstructs when tests actually overlapped, and explains whether configured execution slots stayed busy while runnable tests were still queued.

It does not replace pytest's scheduler or fixture lifecycle.

## Quick start

```console
uv add --dev pytest-poolwatch
uv run pytest --poolwatch --poolwatch-target=40
```

PoolWatch prints a terminal summary after the test run:

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

Write machine-readable and visual reports without running a server:

```console
uv run pytest --poolwatch \
  --poolwatch-target=40 \
  --poolwatch-json=.poolwatch/run.json \
  --poolwatch-html=.poolwatch/run.html
```

The HTML report is self-contained and uses a compact, read-only Jupyter-style
notebook layout. It includes active tests, configured capacity, queued tests,
underfill windows, pytest phase totals, and the slowest test attempts.

## Configuration

Command-line options take precedence over pytest configuration:

```toml
[tool.pytest.ini_options]
poolwatch = true
poolwatch_target = 40
poolwatch_json = ".poolwatch/run.json"
poolwatch_html = ".poolwatch/run.html"
poolwatch_underfill_threshold = 0.1
```

| Option | Purpose |
| --- | --- |
| `--poolwatch` | Enable profiling and the terminal summary. |
| `--poolwatch-target=N` | Set the expected active-test capacity. |
| `--poolwatch-json=PATH` | Write the versioned JSON schema. Also enables PoolWatch. |
| `--poolwatch-html=PATH` | Write a self-contained HTML report. Also enables PoolWatch. |
| `--poolwatch-underfill-threshold=SECONDS` | Ignore shorter underfill windows. |

Exclude intentionally unrepresentative tests with:

```python
import pytest


@pytest.mark.poolwatch_ignore
def test_one_off_migration():
    ...
```

`poolwatch_blocking` is registered as a documentation marker for tests expected to block the event loop. Loop-stall attribution is planned for a later milestone; v0.1 does not claim loop responsiveness when it cannot measure it.

## What the metrics mean

PoolWatch reconstructs a test interval from the earliest pytest phase start to the latest phase stop. Report timestamps are preferred over `pytest_runtest_logstart` and `pytest_runtest_logfinish`: concurrent schedulers can emit the normal runtest protocol only after a coroutine has completed, while the report still contains its true setup/call/teardown timing.

The timeline uses a sweep-line algorithm over interval boundaries:

- **Peak active tests** is the largest number of overlapping test attempts.
- **Average active tests** is the time-weighted active-test area divided by the observed run duration.
- **Utilization** is that area divided by the product of target capacity and duration.
- **Idle slot-seconds** is the total unused configured capacity, including natural suite drain.
- **Scheduler underfill** counts only periods where tests are still queued and active tests are below a known target. Once the queue is empty, reduced concurrency is normal drain and is not diagnosed as underfill.

If no reliable limit is available, PoolWatch uses the observed peak as a reporting baseline and asks for `--poolwatch-target` before making a definitive underfill diagnosis.

## Compatibility

PoolWatch uses public pytest hooks and degrades conservatively:

| Runner/plugin | Target handling | Timing source |
| --- | --- | --- |
| pytest | Serial capacity of 1 | pytest phase reports |
| pytest-asyncio | Serial test protocols | pytest phase reports |
| pytest-asyncio-cooperative | Detects `max_asyncio_tasks` | scheduler-injected report timestamps |
| pytest-xdist | Detects numeric workers; observes workers for `auto` | controller reports with worker IDs |
| pytest-asyncio-concurrent | Uses observed peak unless a target is explicit | grouped phase reports |
| custom scheduler | Pass `--poolwatch-target=N` | public reports, then log hooks as fallback |

A target detected from both xdist and pytest-asyncio-cooperative is multiplied to represent total cross-worker capacity.

## PR #86 regression demo

[pytest-asyncio-cooperative PR #86](https://github.com/willemt/pytest-asyncio-cooperative/pull/86) fixes a scheduler loop that replaced only one sidelined task after several active tasks completed together. The controlled workload in `examples/pr86/test_workload.py` makes the PR's exact precondition deterministic: its first `asyncio.wait(..., FIRST_COMPLETED)` result contains three completed tasks while more work remains queued.

The harness wraps `asyncio.wait` only inside the demo process. It removes the upstream plugin's unrelated immediate timeout polling and batches same-turn completions so the comparison isolates the one-replacement loop from the PR's refill-all loop across Python event-loop versions.

Run the released pre-fix scheduler:

```console
uv run --no-dev --group demo pytest -p no:asyncio \
  examples/pr86/test_workload.py \
  --max-asyncio-tasks=4 \
  --poolwatch \
  --poolwatch-underfill-threshold=0.05 \
  --poolwatch-json=.poolwatch/pr86-before.json \
  --poolwatch-html=.poolwatch/pr86-before.html
uv run --no-dev python examples/pr86/assert_report.py before .poolwatch/pr86-before.json
```

Run the exact fixed commit from the PR:

```console
uv run --no-dev \
  --with "pytest-asyncio-cooperative @ git+https://github.com/willemt/pytest-asyncio-cooperative@3cac81899122a5034405feaf38ec078e39100ddf" \
  pytest -p no:asyncio \
  examples/pr86/test_workload.py \
  --max-asyncio-tasks=4 \
  --poolwatch \
  --poolwatch-underfill-threshold=0.05 \
  --poolwatch-json=.poolwatch/pr86-after.json \
  --poolwatch-html=.poolwatch/pr86-after.html
uv run --no-dev python examples/pr86/assert_report.py after .poolwatch/pr86-after.json
```

The checker validates behavior rather than hard-coding invented benchmark numbers: the pre-fix run must contain a material underfill window and the fixed run must not.

A verified Windows/Python 3.13.5 run measured **34.2% utilization with 0.885s underfill before the fix**, versus **73.1% utilization with no material underfill at the fixed commit**. Exact timings remain workload- and machine-dependent.


## 800-job cloud simulation

`examples/cloud_jobs` is a larger end-to-end workload: 800 parameterized tests
load small JSON configs, submit them to an in-memory cloud service, poll for
completion, retrieve results, and validate both returned fields and a canonical
config checksum.

Each job deterministically represents 1?5 minutes of cloud work. The simulation
compresses one virtual minute to 10 ms, so jobs sleep for only 10?50 ms while the
scheduler still sees real queueing and completion pressure. Run all 800 with 40
cooperative slots against the exact PR #86 fixed commit:

```console
uv run --no-dev \
  --with "pytest-asyncio-cooperative @ git+https://github.com/willemt/pytest-asyncio-cooperative@3cac81899122a5034405feaf38ec078e39100ddf" \
  pytest -p no:asyncio \
  -W "ignore:FixtureDef.has_location is deprecated:pytest.PytestRemovedIn10Warning" \
  examples/cloud_jobs/test_cloud_jobs.py \
  --max-asyncio-tasks=40 \
  --poolwatch \
  --poolwatch-json=.poolwatch/cloud-jobs.json \
  --poolwatch-html=.poolwatch/cloud-jobs.html
uv run --no-dev python examples/cloud_jobs/assert_report.py \
  .poolwatch/cloud-jobs.json
```

The warning filter only removes deprecation spam emitted by the upstream
cooperative plugin. The checker remains timing-independent and verifies 800
collected and observed passing attempts, unique node IDs, target 40, and peak 40.

A verified Windows/Python 3.13.5 run completed all **800 tests in 2.13s**, reached
**40/40 peak concurrency**, measured **89.0% utilization**, and found **0ms
scheduler underfill**. Wall time and utilization are observations, not flaky
assertions. See the [full example notes](examples/cloud_jobs/README.md).

## Development

The project is managed entirely with [uv](https://docs.astral.sh/uv/):

```console
uv sync --locked --dev
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run coverage erase
uv run coverage run -m pytest
uv run coverage combine
uv run coverage report
uv build
```

The package has a typed `src/` layout and a `pytest11` entry point, so installing it is enough for pytest to discover the plugin.

## JSON stability

The top-level `schema_version` is `1`. New fields may be added compatibly within version 1; removing fields or changing their meaning requires a schema version bump.

## Non-goals for v0.1

PoolWatch does not provide a scheduler, custom test runner, fixture implementation, automatic thread offloading, web service, or AI-generated diagnosis. Event-loop watchdogs and user-defined async phases are intentionally deferred until they can be integrated without relying on private plugin APIs.
