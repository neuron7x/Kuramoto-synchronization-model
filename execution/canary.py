# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Live experiment guardrails for canary deployments."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Callable, Mapping, MutableMapping, Optional

from execution.risk import KillSwitch


@dataclass(frozen=True)
class MetricThreshold:
    """Defines acceptable bounds for a monitored metric."""

    lower: float | None = None
    upper: float | None = None

    def breaches(self, value: float) -> Optional[float]:
        if self.lower is not None and value < self.lower:
            return value - self.lower
        if self.upper is not None and value > self.upper:
            return value - self.upper
        return None


@dataclass(frozen=True)
class CanaryDecision:
    """Decision produced by the canary controller after evaluating metrics."""

    action: str
    reason: str
    breaches: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class CanaryConfig:
    """Configuration for canary risk guardrails."""

    traffic_share: float = 0.05
    max_relative_drawdown: float = 0.05
    metric_thresholds: Mapping[str, MetricThreshold] = field(default_factory=dict)
    grace_period: int = 5
    cooldown_seconds: float = 60.0


class CanaryController:
    """Monitor live metrics and trigger automatic disable when guardrails breach."""

    def __init__(
        self,
        config: CanaryConfig,
        *,
        kill_switch: KillSwitch | None = None,
        time_source: Callable[[], float] = time,
    ) -> None:
        self._config = config
        self._kill_switch = kill_switch
        self._time = time_source
        self._observations = 0
        self._pnl_high_water = 0.0
        self._last_disable: float | None = None

    def _relative_drawdown(self, pnl: float) -> float:
        self._pnl_high_water = max(self._pnl_high_water, pnl)
        if self._pnl_high_water == 0:
            return 0.0
        return max(0.0, (self._pnl_high_water - pnl) / max(abs(self._pnl_high_water), 1e-6))

    def _cooldown_active(self) -> bool:
        if self._last_disable is None:
            return False
        return (self._time() - self._last_disable) < self._config.cooldown_seconds

    def evaluate(self, metrics: Mapping[str, float]) -> CanaryDecision:
        """Evaluate live metrics and decide whether to keep the canary enabled."""

        self._observations += 1
        breaches: MutableMapping[str, float] = {}

        pnl = float(metrics.get("pnl", 0.0))
        drawdown = self._relative_drawdown(pnl)
        if drawdown >= self._config.max_relative_drawdown:
            breaches["drawdown"] = drawdown

        for name, threshold in self._config.metric_thresholds.items():
            if name not in metrics:
                continue
            value = float(metrics[name])
            delta = threshold.breaches(value)
            if delta is not None:
                breaches[name] = delta

        if self._observations <= self._config.grace_period:
            return CanaryDecision("continue", "grace-period", {})

        if breaches and not self._cooldown_active():
            if self._kill_switch is not None:
                self._kill_switch.trigger("canary guardrail breach")
            self._last_disable = self._time()
            return CanaryDecision("disable", "guardrail-breach", dict(breaches))

        return CanaryDecision("continue", "healthy" if not breaches else "cooldown", dict(breaches))

    def reset(self) -> None:
        """Reset the controller state, typically after disabling the canary."""

        self._observations = 0
        self._pnl_high_water = 0.0
        self._last_disable = None


__all__ = [
    "CanaryConfig",
    "CanaryController",
    "CanaryDecision",
    "MetricThreshold",
]
