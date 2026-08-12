# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import types
from typing import Any, Callable

import pytest

from tests.performance import conftest as perf_conftest


class _DummyStats(dict[str, float]):
    """Mapping-like stats wrapper mirroring pytest-benchmark's API."""

    def __init__(self, median: float) -> None:
        super().__init__(median=median)
        self.stats = self


class _DummyBenchmark:
    """Minimal stand-in for :mod:`pytest-benchmark`'s fixture."""

    def __init__(self, observed: float) -> None:
        self._observed = observed
        self.stats: _DummyStats | None = None

    def pedantic(
        self,
        func: Callable[..., Any],
        *,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        rounds: int,
        warmup_rounds: int,
    ) -> Any:
        # The production code only inspects ``benchmark.stats`` after the call,
        # so we simply record the desired median value and execute the function.
        self.stats = _DummyStats(self._observed)
        return func(*args, **kwargs)


class _DummyRequest:
    """Request shim exposing the attributes accessed by ``benchmark_guard``."""

    def __init__(self, benchmark: _DummyBenchmark) -> None:
        self._benchmark = benchmark
        self.node = types.SimpleNamespace(nodeid="dummy::test")
        self.config = types.SimpleNamespace(
            workerinput={"workercount": "2"},
            option=types.SimpleNamespace(numprocesses=0),
        )

    def getfixturevalue(self, name: str) -> _DummyBenchmark:
        if name != "benchmark":  # pragma: no cover - defensive guard
            msg = f"unexpected fixture request: {name}"
            raise pytest.FixtureLookupError(name, None, msg)  # type: ignore[arg-type]
        return self._benchmark


def _make_runner(observed: float) -> Callable[..., Any]:
    baseline_key = "sample-benchmark"
    baselines = {baseline_key: 1.0}
    benchmark = _DummyBenchmark(observed)
    request = _DummyRequest(benchmark)

    runner_factory = perf_conftest.benchmark_guard.__wrapped__  # type: ignore[attr-defined]
    return runner_factory(request, baselines)


def test_benchmark_guard_reports_adjusted_threshold() -> None:
    """Concurrent workers increase the allowed regression reported to users."""

    runner = _make_runner(observed=1.30)

    with pytest.raises(AssertionError) as excinfo:
        runner(lambda: None, baseline_key="sample-benchmark")

    assert "+30.0%" in str(excinfo.value)
    assert "allowed 22.0%" in str(excinfo.value)
