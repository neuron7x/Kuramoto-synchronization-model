# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Trading strategy representation and evolutionary optimization.

This module defines the Strategy abstraction used throughout the agent system,
along with mutation operators for evolutionary parameter optimization. Strategies
encapsulate both configuration parameters and performance metrics.

Key Components:
    Strategy: Core strategy representation with parameters and scoring
    generate_mutation: Gaussian perturbation for parameter evolution
    validate_params: Enforce parameter bounds and constraints
    simulate_performance: Walk-forward evaluation with observability

The Strategy class supports evolutionary optimization through mutation operators
that perturb numeric parameters with controlled randomness. This enables gradient-
free optimization of trading rules in non-stationary market environments.

Performance simulation uses deterministic walk-forward validation to compute
risk-adjusted returns. Results are instrumented with OpenTelemetry for production
observability and debugging.

Parameter Constraints:
    - lookback: [5, 500] bars
    - threshold: [0.0, 5.0] standard deviations
    - risk_budget: [0.01, 10.0] Kelly fraction multiplier

Example:
    >>> strategy = Strategy("mean_reversion", {"lookback": 20, "threshold": 2.0})
    >>> mutant = strategy.generate_mutation(scale=0.2)
    >>> score = strategy.simulate_performance(price_data)
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict

import numpy as np
import pandas as pd

from observability.tracing import pipeline_span


@dataclass
class Strategy:
    name: str
    params: Dict[str, Any]
    score: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def generate_mutation(self, *, scale: float = 0.1) -> "Strategy":
        rng = np.random.default_rng()
        new_params: Dict[str, Any] = {}
        for key, value in self.params.items():
            if isinstance(value, (int, float)):
                perturb = rng.normal(loc=0.0, scale=abs(value) * scale + 1e-6)
                candidate = value + perturb
                if isinstance(value, int):
                    candidate = max(1, int(round(candidate)))
                new_params[key] = candidate
            else:
                new_params[key] = value
        mutated = Strategy(name=f"{self.name}_mut", params=new_params)
        mutated.validate_params()
        return mutated

    def validate_params(self) -> None:
        lookback = int(self.params.get("lookback", 20))
        self.params["lookback"] = max(5, min(lookback, 500))
        threshold = float(self.params.get("threshold", 0.0))
        self.params["threshold"] = max(0.0, min(threshold, 5.0))
        risk = float(self.params.get("risk_budget", 1.0))
        self.params["risk_budget"] = max(0.01, min(risk, 10.0))

    def simulate_performance(self, data: Any) -> float:
        """Deterministic walk-forward score using rolling mean-reversion logic."""

        self.validate_params()

        def _update_diagnostics(
            equity_curve: np.ndarray, positions: np.ndarray
        ) -> None:
            if equity_curve.size == 0:
                self.params["last_equity_curve"] = []
                self.params["max_drawdown"] = 0.0
                self.params["trades"] = 0
                return

            peak = np.maximum.accumulate(np.concatenate([[0.0], equity_curve]))[1:]
            drawdown = equity_curve - peak
            self.params["last_equity_curve"] = equity_curve.tolist()
            self.params["max_drawdown"] = (
                float(drawdown.min()) if drawdown.size else 0.0
            )
            self.params["trades"] = (
                int(np.count_nonzero(np.diff(positions))) if positions.size else 0
            )

        with pipeline_span("signals.simulate_performance", strategy=self.name) as span:
            if data is None:
                series = pd.Series(np.linspace(100.0, 101.0, 256), dtype=float)
            else:
                series = _to_price_series(data)

            if span is not None:
                span.set_attributes(
                    {
                        "series.length": int(series.size),
                        "series.has_index": isinstance(series.index, pd.DatetimeIndex),
                    }
                )

            series = series.astype(float)
            if isinstance(series.index, pd.DatetimeIndex):
                series = series[~series.index.duplicated(keep="last")].sort_index()
            series = series.replace([np.inf, -np.inf], np.nan)
            if series.isna().all():
                self.score = 0.0
                _update_diagnostics(
                    np.array([], dtype=float), np.array([], dtype=float)
                )
                return self.score
            series = series.ffill().bfill()

            returns = series.pct_change(fill_method=None)
            returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
            if returns.empty:
                self.score = 0.0
                _update_diagnostics(
                    np.array([], dtype=float), np.array([], dtype=float)
                )
                return self.score

            lookback = int(self.params.get("lookback", 20))
            threshold = float(self.params.get("threshold", 0.5))
            risk_budget = float(self.params.get("risk_budget", 1.0))
            if span is not None:
                span.set_attributes(
                    {
                        "params.lookback": float(lookback),
                        "params.threshold": float(threshold),
                        "params.risk_budget": float(risk_budget),
                        "returns.length": int(len(returns)),
                    }
                )
            effective_lookback = max(1, min(lookback, len(returns)))

            rolling_mean = (
                returns.rolling(
                    window=effective_lookback, min_periods=effective_lookback
                )
                .mean()
                .fillna(0.0)
            )
            rolling_vol = (
                returns.rolling(window=effective_lookback, min_periods=1)
                .std(ddof=0)
                .replace(0.0, np.nan)
                .ffill()
                .bfill()
                .fillna(1e-6)
            )
            zscore = (
                (rolling_mean / rolling_vol).replace([np.inf, -np.inf], 0.0).fillna(0.0)
            )
            signal = np.where(
                zscore > threshold, -1.0, np.where(zscore < -threshold, 1.0, 0.0)
            )
            if signal.size:
                position = np.concatenate(([0.0], signal[:-1])) * risk_budget
            else:
                position = np.array([], dtype=float)

            pnl = position * returns.to_numpy()
            equity = np.cumsum(pnl)
            _update_diagnostics(equity, position)
            if equity.size == 0:
                self.score = 0.0
                return self.score

            sharpe = np.mean(pnl) / (np.std(pnl) + 1e-9)
            terminal = equity[-1]
            raw_score = terminal + 0.5 * sharpe
            self.score = float(np.clip(raw_score, -1.0, 2.0))
            if span is not None:
                span.set_attributes(
                    {
                        "score": float(self.score),
                        "trades": int(self.params.get("trades", 0)),
                    }
                )
            return self.score


@dataclass
class PiAgent:
    strategy: Strategy
    hysteresis: float = 0.05

    def __post_init__(self) -> None:
        self._instability_score: float = 0.0
        self._cooldown: int = 0
        self.strategy.validate_params()

    def detect_instability(self, market_state: Dict[str, float]) -> bool:
        R = market_state.get("R", 0.0)
        dH = market_state.get("delta_H", 0.0)
        kappa = market_state.get("kappa_mean", 0.0)
        transition = market_state.get("transition_score", 0.0)
        hard_trigger = R > 0.75 and dH < 0 and kappa < 0
        score = (
            0.6 * max(R - 0.7, 0.0)
            + 0.25 * max(-dH, 0.0)
            + 0.15 * max(-kappa, 0.0)
            + 0.2 * transition
        )
        self._instability_score = 0.7 * self._instability_score + 0.3 * score
        threshold = self.strategy.params.get("instability_threshold", 0.2)
        triggered = (
            hard_trigger or self._instability_score > threshold
        ) and self._cooldown == 0
        if triggered:
            self._cooldown = 3
        elif self._cooldown > 0:
            self._cooldown -= 1
        return triggered

    def mutate(self) -> "PiAgent":
        return PiAgent(strategy=self.strategy.generate_mutation())

    def repair(self) -> None:
        for key, value in list(self.strategy.params.items()):
            if isinstance(value, (int, float)) and math.isnan(value):
                self.strategy.params[key] = 0.0
        self.strategy.validate_params()

    def evaluate_and_adapt(self, market_state) -> str:
        action = "hold"
        if self.detect_instability(market_state):
            action = "enter"
        elif market_state.get("phase_reversal", False) and self._instability_score < (
            self.strategy.params.get("instability_threshold", 0.2) - self.hysteresis
        ):
            action = "exit"
        return action


def _to_price_series(data: Any) -> pd.Series:
    if isinstance(data, pd.Series):
        return data.astype(float)
    if isinstance(data, pd.DataFrame):
        if "close" not in data.columns:
            raise ValueError("DataFrame must contain a 'close' column")
        return data["close"].astype(float)
    if isinstance(data, (list, tuple, np.ndarray)):
        return pd.Series(np.asarray(data, dtype=float))
    raise TypeError("Unsupported data type for simulate_performance")
