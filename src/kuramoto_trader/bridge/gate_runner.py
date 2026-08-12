"""Execution gate pipeline: market phase -> order parameter -> decision."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .market_phase_live import MarketPhaseLive


@dataclass(frozen=True)
class GateDecision:
    state: str
    execution_allowed: bool
    R: float | None


class ExecutionGate:
    def __init__(self, threshold: float = 0.65):
        self.threshold = float(threshold)

    def decide(self, r: float | None) -> GateDecision:
        if r is None:
            return GateDecision("SENSOR_ABSENT", False, None)
        if r >= self.threshold:
            return GateDecision("READY", True, float(r))
        return GateDecision("BLOCKED", False, float(r))


class GateRunner:
    def __init__(self, threshold: float = 0.65, window: int = 256):
        self.market = MarketPhaseLive(window=window)
        self.gate = ExecutionGate(threshold=threshold)
        self._history: list[dict[str, object]] = []

    def tick(self, price: float, ts: pd.Timestamp) -> GateDecision:
        phase = self.market.update(price, ts)
        ps = self.market.phase_series().dropna()
        r_val = None if len(ps) == 0 else float(abs(np.mean(np.exp(1j * ps.to_numpy()))))
        decision = self.gate.decide(r_val if phase is not None else None)
        self._history.append(
            {
                "ts": pd.Timestamp(ts),
                "R": decision.R,
                "state": decision.state,
                "execution_allowed": decision.execution_allowed,
            }
        )
        return decision

    def history(self) -> pd.DataFrame:
        return pd.DataFrame(self._history, columns=["ts", "R", "state", "execution_allowed"])
