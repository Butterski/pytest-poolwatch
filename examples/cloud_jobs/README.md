# Cloud-job concurrency demo

This workload gives PoolWatch 800 distinct async tests to observe by default.
Pass `--cloud-job-count=N` to generate a different number. Every test:

1. reads and submits a small JSON job config;
2. waits for deterministic, random-looking cloud work lasting 1–5 virtual minutes;
3. polls the job every 30 virtual seconds;
4. retrieves the result and validates its fields and config checksum.

No test sleeps for real minutes. The exported
`REAL_SECONDS_PER_VIRTUAL_MINUTE` scale is `0.010`, so one virtual minute is
10 ms and the cloud-work stage takes 10–50 ms per test. Each job derives its
duration from the fixed seed `0xC10D` plus its numeric ID. Assertions use the
virtual clock rather than wall-clock timing, so slow machines cannot make a test
fail.

Run the complete workload with 40 cooperative slots. The command pins the exact
commit containing the refill-all change from PR #86:

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
```

On PowerShell, the same command can be entered on one line or continued with
backticks instead of backslashes.

The warning filter only silences a known pytest 10 deprecation emitted once per
test by the upstream cooperative plugin; it does not hide workload failures.

For example, this larger run collects 3,000 identical deterministic job
definitions for both scheduler versions and targets 150 cooperative slots:

```console
uv run --no-dev \
  --with "pytest-asyncio-cooperative @ git+https://github.com/willemt/pytest-asyncio-cooperative@3cac81899122a5034405feaf38ec078e39100ddf" \
  pytest -p no:asyncio \
  -W "ignore:FixtureDef.has_location is deprecated:pytest.PytestRemovedIn10Warning" \
  examples/cloud_jobs/test_cloud_jobs.py \
  --cloud-job-count=3000 \
  --max-asyncio-tasks=150 \
  --poolwatch \
  --poolwatch-json=.poolwatch/cloud-jobs-3000-fixed.json \
  --poolwatch-html=.poolwatch/cloud-jobs-3000-fixed.html
```

Check the report's non-timing invariants:

```console
uv run --no-dev python examples/cloud_jobs/assert_report.py \
  .poolwatch/cloud-jobs.json \
  --expected-tests=800 \
  --expected-concurrency=40
```

The two expectation options default to 800 and 40, so they may be omitted for
the standard run. For the larger example, pass `--expected-tests=3000` and
`--expected-concurrency=150`.

Expected bounds:

- exactly the requested number of collected, observed, passing attempts with unique node IDs;
- configured and peak concurrency matching the requested slot count;
- virtual job duration between 60 and 300 seconds (10–50 ms real time).

Utilization and underfill are intentionally not asserted. This is a scheduler
stress workload: completion batches expose refill behavior, including the behavior
changed by
[pytest-asyncio-cooperative PR #86](https://github.com/willemt/pytest-asyncio-cooperative/pull/86).
The checker prints utilization so releases can be compared without making the
example flaky.

The repository's `demo` dependency group pins released version 0.40.0 for the
regression comparison. That version is pre-fix; using `--group demo` instead of
the fixed `--with` requirement above intentionally exercises its one-at-a-time
refill behavior.

The report checker has no wall-clock upper bound. Its invariants remain valid on
slow or heavily loaded machines; a sub-second-to-low-seconds runtime is only an
expected local observation.

For a quick smoke run, generate 100 cases:

```console
uv run --no-dev \
  --with "pytest-asyncio-cooperative @ git+https://github.com/willemt/pytest-asyncio-cooperative@3cac81899122a5034405feaf38ec078e39100ddf" \
  pytest -p no:asyncio \
  examples/cloud_jobs/test_cloud_jobs.py \
  -W "ignore:FixtureDef.has_location is deprecated:pytest.PytestRemovedIn10Warning" \
  --cloud-job-count=100 \
  --max-asyncio-tasks=8
```
