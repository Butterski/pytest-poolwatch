from __future__ import annotations

import json


def test_cli_writes_reports_and_terminal_summary(pytester) -> None:
    pytester.makepyfile(
        """
        def test_one():
            pass

        def test_two():
            pass
        """
    )

    result = pytester.runpytest_subprocess(
        "--poolwatch",
        "--poolwatch-target=1",
        "--poolwatch-json=artifacts/report.json",
        "--poolwatch-html=artifacts/report.html",
    )

    result.assert_outcomes(passed=2)
    result.stdout.fnmatch_lines(["*= PoolWatch summary =*", "*Peak active tests:*1*"])
    payload = json.loads(
        (pytester.path / "artifacts" / "report.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == 1
    assert payload["session"]["collected_tests"] == 2
    assert (pytester.path / "artifacts" / "report.html").exists()


def test_report_path_enables_poolwatch_without_flag(pytester) -> None:
    pytester.makepyfile("def test_one(): pass")

    result = pytester.runpytest_subprocess("--poolwatch-json=report.json")

    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*= PoolWatch summary =*"])
    assert (pytester.path / "report.json").exists()


def test_disabled_mode_has_no_summary(pytester) -> None:
    pytester.makepyfile("def test_one(): pass")

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(passed=1)
    assert "PoolWatch summary" not in result.stdout.str()
    assert not (pytester.path / "poolwatch.json").exists()


def test_ini_configuration_and_ignore_marker(pytester) -> None:
    pytester.makeini(
        """
        [pytest]
        poolwatch = true
        poolwatch_target = 1
        poolwatch_json = result.json
        """
    )
    pytester.makepyfile(
        """
        import pytest

        def test_kept():
            pass

        @pytest.mark.poolwatch_ignore
        def test_ignored():
            pass
        """
    )

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(passed=2)
    payload = json.loads((pytester.path / "result.json").read_text(encoding="utf-8"))
    assert payload["session"]["collected_tests"] == 1
    assert [item["nodeid"] for item in payload["tests"]] == [
        "test_ini_configuration_and_ignore_marker.py::test_kept"
    ]


def test_invalid_ini_target_is_a_usage_error(pytester) -> None:
    pytester.makeini("[pytest]\npoolwatch = true\npoolwatch_target = 0")
    pytester.makepyfile("def test_one(): pass")

    result = pytester.runpytest_subprocess()

    assert result.ret != 0
    result.stderr.fnmatch_lines(["*poolwatch_target must be greater than zero*"])


def test_xdist_target_and_worker_timings(pytester) -> None:
    pytester.makepyfile(
        """
        import time
        import pytest

        @pytest.mark.parametrize("value", range(4))
        def test_parallel(value):
            time.sleep(0.15)
        """
    )

    result = pytester.runpytest_subprocess(
        "-n=2",
        "--poolwatch",
        "--poolwatch-json=xdist.json",
    )

    result.assert_outcomes(passed=4)
    payload = json.loads((pytester.path / "xdist.json").read_text(encoding="utf-8"))
    assert payload["target"]["configured"] == 2
    assert payload["target"]["source"] == "pytest-xdist"
    assert {item["worker"] for item in payload["tests"]} == {"gw0", "gw1"}
    assert payload["summary"]["peak_active_tests"] == 2
