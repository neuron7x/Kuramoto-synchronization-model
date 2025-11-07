"""TACL (Thermodynamic Agent Change Law) guard implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from runtime.metrics import gauge_set


@dataclass
class _StepState:
    lat_ms: float = 0.0
    coverage: float = 1.0
    cpu_util: float = 0.0


class TACLGuard:
    """Monitors free-energy like metric to ensure monotonic descent."""

    def __init__(self, w_lat: float, w_coh: float, w_cost: float) -> None:
        self.w_lat = w_lat
        self.w_coh = w_coh
        self.w_cost = w_cost
        self._step: Optional[_StepState] = None
        self._denied = 0

    def begin_step(self) -> None:
        self._step = _StepState()

    def end_step(self, lat_ms: float, coverage: float, cpu_util: float) -> bool:
        if self._step is None:
            self.begin_step()
        self._step = _StepState(lat_ms=lat_ms, coverage=coverage, cpu_util=cpu_util)
        F = self.w_lat * lat_ms + self.w_coh * (1.0 - coverage) + self.w_cost * cpu_util
        gauge_set("tacl_free_energy", F)
        gauge_set("tradepulse_step_latency_ms", lat_ms)
        gauge_set("tradepulse_coverage", coverage)
        gauge_set("tradepulse_drawdown", cpu_util)
        return True

    def approve_change(self, tag: str, delta_F: float, override: bool = False) -> bool:
        if delta_F > 0.0 and not override:
            self._denied += 1
            gauge_set("tacl_change_denied_total", float(self._denied))
            return False
        gauge_set("tacl_change_denied_total", float(self._denied))
        return True


__all__ = ["TACLGuard"]
