# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Microbenchmarks for the compat clock primitives.

These benchmarks document the expected cost of the clock layer so future
regressions are obvious. They are *not* correctness tests — pytest-benchmark
reports the numbers and will only fail if the collector itself breaks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from core.compat import UTC, FrozenClock, SystemClock, monotonic_ns, utc_now


@pytest.mark.benchmark(group="compat")
def test_bench_utc_now(benchmark: Any) -> None:
    benchmark(utc_now)


@pytest.mark.benchmark(group="compat")
def test_bench_monotonic_ns(benchmark: Any) -> None:
    benchmark(monotonic_ns)


@pytest.mark.benchmark(group="compat")
def test_bench_system_clock_now(benchmark: Any) -> None:
    clock = SystemClock()
    benchmark(clock.now)


@pytest.mark.benchmark(group="compat")
def test_bench_frozen_clock_now(benchmark: Any) -> None:
    clock = FrozenClock(instant=datetime(2026, 1, 1, tzinfo=UTC))
    benchmark(clock.now)


@pytest.mark.benchmark(group="compat")
def test_bench_frozen_clock_monotonic(benchmark: Any) -> None:
    clock = FrozenClock(instant=datetime(2026, 1, 1, tzinfo=UTC))
    benchmark(clock.monotonic_ns)


@pytest.mark.benchmark(group="compat")
def test_bench_frozen_clock_advance(benchmark: Any) -> None:
    clock = FrozenClock(instant=datetime(2026, 1, 1, tzinfo=UTC))

    def _advance() -> None:
        clock.advance(nanoseconds=1)

    benchmark(_advance)
