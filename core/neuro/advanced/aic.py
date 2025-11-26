"""Agency and insula control network."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any, Dict, Iterable

import numpy as np

from .config import NeuroAdvancedConfig
from .types import MarketContext, TradeOutcome, TradeResult


class AgencyControlNetwork:
    """Tracks perceived control, confidence and loss aversion."""

    def __init__(self, config: NeuroAdvancedConfig):
        self._cfg = config
        self._confidence = config.aic.initial_confidence
        self._decay = config.aic.confidence_decay
        self._volatility_impact = config.aic.volatility_impact
        self._loss_aversion = config.aic.loss_aversion_init
        self._insula_activation = 0.0
        self._recent_controls: deque[float] = deque(maxlen=50)
        self._history: deque[Dict[str, Any]] = deque(maxlen=config.history_size)
        self._win_rate = 0.5

    def update(
        self, trade: TradeResult, market_context: MarketContext
    ) -> Dict[str, float]:
        actual_control = self._compute_actual_control(trade, market_context)
        self._recent_controls.append(actual_control)

        delta = self._control_delta(trade, actual_control)
        delta -= market_context.volatility * self._volatility_impact
        self._confidence = float(
            np.clip((self._confidence + delta) * self._decay, 0.1, 0.95)
        )

        if trade.outcome == TradeOutcome.LOSS:
            penalty = abs(trade.loss_magnitude) * actual_control * 0.6
            self._insula_activation = float(
                np.clip(0.9 * self._insula_activation + 0.1 * penalty, 0.0, 1.0)
            )
            self._loss_aversion = min(2.6, self._loss_aversion * 1.02)
            self._win_rate *= 0.95
        elif trade.outcome == TradeOutcome.WIN:
            self._insula_activation = max(0.0, self._insula_activation * 0.9 - 0.03)
            self._loss_aversion = max(1.0, self._loss_aversion * 0.99)
            self._win_rate = self._win_rate * 0.95 + 0.05
        else:
            self._insula_activation *= 0.95

        self._history.append(
            {
                "timestamp": datetime.now(),
                "control": float(actual_control),
                "confidence": self._confidence,
                "insula": self._insula_activation,
            }
        )

        return {
            "control_confidence": self._confidence,
            "actual_control": float(actual_control),
            "insula_activation": self._insula_activation,
            "loss_aversion": self._loss_aversion,
            "win_rate": self._win_rate,
        }

    def size_modulator(self) -> float:
        base = 0.5 + self._confidence
        penalty = self._insula_activation * 0.5
        return float(np.clip(base * (1.0 - penalty), 0.3, 1.5))

    def state(self) -> Dict[str, Any]:
        avg_control = (
            float(np.mean(self._recent_controls)) if self._recent_controls else 0.5
        )
        confidence_trend = self._trend(
            [entry["confidence"] for entry in self._history][-50:]
        )
        return {
            "control_confidence": self._confidence,
            "insula_activation": self._insula_activation,
            "win_rate": self._win_rate,
            "loss_aversion_factor": self._loss_aversion,
            "avg_recent_control": avg_control,
            "confidence_trend": confidence_trend,
        }

    def _control_delta(self, trade: TradeResult, actual_control: float) -> float:
        if trade.outcome == TradeOutcome.WIN and actual_control > 0.7:
            delta = 0.08 * actual_control
        elif trade.outcome == TradeOutcome.LOSS and actual_control > 0.7:
            delta = -0.12 * actual_control * self._loss_aversion
        elif trade.outcome == TradeOutcome.WIN:
            delta = 0.03 * (1 - actual_control)
        else:
            delta = -0.02
        delta += self._cfg.aic.learning_sensitivity * (trade.signal_strength - 0.5)
        return delta

    def _compute_actual_control(
        self, trade: TradeResult, market_context: MarketContext
    ) -> float:
        base = float(trade.signal_strength) / max(trade.strategy_complexity, 1e-6)
        trend_factor = 1.0 - min(abs(market_context.trend_strength) * 0.3, 0.9)
        volatility_factor = 1.0 - min(market_context.volatility * 0.2, 0.95)
        return float(
            np.clip(
                base * trend_factor * volatility_factor * market_context.liquidity,
                0.0,
                1.0,
            )
        )

    @staticmethod
    def _trend(values: Iterable[float]) -> float:
        series = list(values)
        if len(series) < 2:
            return 0.0
        x_axis = np.arange(len(series))
        slope = float(np.polyfit(x_axis, series, 1)[0])
        return slope
