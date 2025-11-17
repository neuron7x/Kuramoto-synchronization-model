"""Unit tests for performance benchmarking utilities."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable

import pytest

from tests.performance import conftest as perf_conftest


class _DummyStats(dict):
    @property
    def stats(self) -> "_DummyStats":
        return self


class _DummyBenchmark:
    def __init__(self, median: float) -> None:
        self.stats = _DummyStats({"median": median})

    def pedantic(
        self,
        func: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        rounds: int = 0,
        warmup_rounds: int = 0,
    ) -> Any:
        kwargs = kwargs or {}
        return func(*args, **kwargs)


class _DummyRequest:
    def __init__(
        self,
        benchmark: _DummyBenchmark,
        *,
        workerinput: dict[str, Any] | None,
        numprocesses: int = 0,
        nodeid: str = "tests/performance/test_dummy.py::test_case",
    ) -> None:
        self._benchmark = benchmark
        self.node = SimpleNamespace(nodeid=nodeid)
        self.config = SimpleNamespace(
            workerinput=workerinput,
            option=SimpleNamespace(numprocesses=numprocesses),
        )

    def getfixturevalue(self, name: str) -> _DummyBenchmark:
        if name == "benchmark":
            return self._benchmark
        raise pytest.FixtureLookupError(name, None)


def _clear_monitor() -> None:
    perf_conftest._monitor.records.clear()


def test_benchmark_guard_reports_concurrency_adjusted_budget() -> None:
    baseline_key = "dummy.benchmark"
    baselines = {baseline_key: 1.0}
    benchmark = _DummyBenchmark(median=1.5)
    request = _DummyRequest(benchmark, workerinput={"workercount": "4"})

    runner = perf_conftest.benchmark_guard.__wrapped__(
        request=request,
        benchmark_baselines=baselines,
    )

    try:
        with pytest.raises(AssertionError) as excinfo:
            runner(lambda: "ok", baseline_key=baseline_key)
    finally:
        _clear_monitor()

    message = str(excinfo.value)
    assert "allowed 36.0%" in message


def test_pytest_terminal_summary_labels_median(monkeypatch: pytest.MonkeyPatch) -> None:
    record = perf_conftest._BenchmarkRecord(
        test_id="tests/performance/test_case.py::test_latency",
        name="example.benchmark",
        observed=0.012,
        baseline=0.010,
        threshold=0.10,
    )
    perf_conftest._monitor.records = [record]

    captured: list[str] = []

    class _DummyReporter:
        def write_sep(
            self, sep: str, msg: str
        ) -> None:  # pragma: no cover - behaviour simple
            captured.append(f"{sep}:{msg}")

        def write_line(self, line: str) -> None:
            captured.append(line)

    monkeypatch.setattr(
        perf_conftest, "_persist_benchmark_artifacts", lambda records: None
    )

    try:
        perf_conftest.pytest_terminal_summary(_DummyReporter(), exitstatus=0)
    finally:
        _clear_monitor()

    header_line = next(line for line in captured if "median (s)" in line)
    assert "median (s)" in header_line
