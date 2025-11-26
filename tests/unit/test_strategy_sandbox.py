from __future__ import annotations

import math
import time

import pytest

from core.agent.sandbox import SandboxLimits, StrategySandbox, StrategySandboxError
from core.agent.strategy import Strategy


class _MarkingStrategy(Strategy):
    def __init__(self) -> None:
        super().__init__(name="mark", params={})

    def simulate_performance(self, data):
        self.params["touched"] = True
        return 1.25


class _SlowStrategy(Strategy):
    def __init__(self) -> None:
        super().__init__(name="slow", params={})

    def simulate_performance(self, data):  # pragma: no cover - executed in subprocess
        time.sleep(0.5)
        return 0.0


class _HungryStrategy(Strategy):
    def __init__(self) -> None:
        super().__init__(name="hungry", params={})

    def simulate_performance(self, data):  # pragma: no cover - executed in subprocess
        # Allocate more than 8 MiB to trigger RLIMIT_AS guard.
        return float(len(bytearray(16 * 1024 * 1024)))


def test_strategy_sandbox_returns_result() -> None:
    sandbox = StrategySandbox(
        limits=SandboxLimits(
            cpu_time_seconds=1.0, wall_time_seconds=2.0, memory_bytes=64 * 1024 * 1024
        )
    )
    strategy = _MarkingStrategy()

    result = sandbox.run(strategy, data=None)

    assert math.isclose(result.score, 1.25, rel_tol=1e-9)
    assert result.strategy.params["touched"] is True


def test_strategy_sandbox_enforces_timeout() -> None:
    sandbox = StrategySandbox(
        limits=SandboxLimits(
            cpu_time_seconds=1.0, wall_time_seconds=0.1, memory_bytes=64 * 1024 * 1024
        )
    )

    with pytest.raises(StrategySandboxError) as excinfo:
        sandbox.run(_SlowStrategy(), data=None)

    assert isinstance(excinfo.value.__cause__, TimeoutError)


def test_strategy_sandbox_enforces_memory_limit() -> None:
    sandbox = StrategySandbox(
        limits=SandboxLimits(
            cpu_time_seconds=1.0, wall_time_seconds=2.0, memory_bytes=8 * 1024 * 1024
        )
    )

    with pytest.raises(StrategySandboxError) as excinfo:
        sandbox.run(_HungryStrategy(), data=None)

    assert isinstance(excinfo.value.__cause__, MemoryError)
