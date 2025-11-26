"""Tests for the pytest terminal summary of benchmark regressions."""

from __future__ import annotations

from tests.performance import conftest as perf_conftest


class _DummyTerminalReporter:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write_sep(self, sep: str, message: str) -> None:
        self.lines.append(f"{sep} {message}")

    def write_line(self, line: str) -> None:
        self.lines.append(line)


def test_pytest_terminal_summary_reports_median_label() -> None:
    """pytest_terminal_summary prints the correct median label and values."""

    monitor = perf_conftest._monitor
    original_records = monitor.records
    monitor.records = []
    try:
        record = perf_conftest._BenchmarkRecord(
            test_id="tests/performance/test_sample.py::test_sample",
            name="sample-benchmark",
            observed=0.25,
            baseline=0.20,
            threshold=0.10,
        )
        monitor.add(record)

        reporter = _DummyTerminalReporter()
        perf_conftest.pytest_terminal_summary(reporter, exitstatus=0)

        assert any("median (s)" in line for line in reporter.lines)
        header_line = next(line for line in reporter.lines if "median (s)" in line)
        assert "mean (s)" not in header_line

        data_line = next(
            line
            for line in reporter.lines
            if "sample-benchmark" in line and "0.250000" in line
        )
        assert f"{record.observed:12.6f}" in data_line
    finally:
        monitor.records = original_records
