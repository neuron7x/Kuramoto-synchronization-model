# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Dopamine ↔ Execution Feedback Adapter.

Bridges real execution outcomes (realized P&L, slippage) to dopamine
reward prediction error (RPE) signals on the NeuroSignalBus.

Theoretical basis:
    Schultz 1997 — midbrain dopamine neurons encode TD prediction errors:
        RPE = (actual reward) − (predicted reward)
    Positive RPE → reinforcement; negative RPE → behavioural extinction.

The adapter normalises raw RPE to [-1, 1] via tanh scaling so that
downstream consumers (learning rate modulation, GABA inhibition) receive
a bounded, comparable signal regardless of P&L magnitude.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.neuro.signal_bus import NeuroSignalBus


class DopamineExecutionAdapter:
    """Bridge execution outcomes to dopamine RPE on the NeuroSignalBus.

    Parameters
    ----------
    bus : NeuroSignalBus
        Signal bus instance for publishing dopamine RPE.
    slippage_penalty_scale : float
        Multiplier converting raw slippage to RPE penalty (default 1.0).
    tanh_scale : float
        Scaling factor inside tanh for normalisation (default 1.0).
        Larger values make the mapping more sensitive near zero.
    """

    def __init__(
        self,
        bus: "NeuroSignalBus",
        slippage_penalty_scale: float = 1.0,
        tanh_scale: float = 1.0,
    ) -> None:
        self._bus = bus
        self._slippage_penalty_scale = slippage_penalty_scale
        self._tanh_scale = tanh_scale

    # ── Core RPE computation (Schultz 1997 TD error) ─────────────────

    def compute_rpe(
        self,
        realized_pnl: float,
        predicted_return: float,
        slippage: float = 0.0,
    ) -> float:
        """Compute reward prediction error normalised to [-1, 1].

        RPE_raw = (realized_pnl - predicted_return) - slippage_penalty
        RPE     = tanh(scale * RPE_raw)

        Parameters
        ----------
        realized_pnl : float
            Actual profit/loss from the trade.
        predicted_return : float
            Model's predicted return before execution.
        slippage : float
            Observed execution slippage (non-negative).

        Returns
        -------
        float
            Normalised RPE in [-1, 1].
        """
        slippage_penalty = abs(slippage) * self._slippage_penalty_scale
        raw_rpe = (realized_pnl - predicted_return) - slippage_penalty
        return math.tanh(self._tanh_scale * raw_rpe)

    # ── Trade result integration ─────────────────────────────────────

    def update_from_trade(self, trade_result: dict) -> float:
        """Extract fields from a trade result dict, compute RPE, publish.

        Expected keys in *trade_result*:
            ``pnl`` (float) — realised P&L
            ``predicted_return`` (float, optional, default 0.0)
            ``slippage`` (float, optional, default 0.0)

        Returns
        -------
        float
            The computed (normalised) RPE.
        """
        pnl = float(trade_result.get("pnl", 0.0))
        predicted = float(trade_result.get("predicted_return", 0.0))
        slippage = float(trade_result.get("slippage", 0.0))

        rpe = self.compute_rpe(pnl, predicted, slippage)
        self._bus.publish_dopamine(rpe)
        return rpe

    # ── Secondary reward signal: rolling Sharpe delta ────────────────

    @staticmethod
    def compute_sharpe_delta(
        returns: list[float],
        window: int = 20,
    ) -> float:
        """Compute change in rolling Sharpe ratio as secondary reward.

        If fewer than ``window`` returns are available, the delta is 0.0.

        Parameters
        ----------
        returns : list[float]
            Sequence of period returns (newest last).
        window : int
            Rolling window size (default 20).

        Returns
        -------
        float
            Sharpe(latest window) − Sharpe(previous window).
        """
        if len(returns) < 2 * window:
            return 0.0

        def _sharpe(segment: list[float]) -> float:
            n = len(segment)
            if n == 0:
                return 0.0
            mean = sum(segment) / n
            var = sum((x - mean) ** 2 for x in segment) / n
            std = math.sqrt(var) if var > 0 else 1e-12
            return mean / std

        recent = returns[-window:]
        previous = returns[-2 * window : -window]
        return _sharpe(recent) - _sharpe(previous)
