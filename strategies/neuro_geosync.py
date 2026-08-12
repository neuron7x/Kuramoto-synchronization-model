# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from core.indicators.kuramoto_ricci_composite import (
    CompositeSignal,
    GeoSyncCompositeEngine,
)
from core.neuro import FractalMotivationEngine


@dataclass(slots=True)
class NeuroGeoSyncConfig:
    """Configuration for NeuroGeoSyncStrategy.

    - discount_rate: conceptual placeholder for temporal valuation; motivation engine already
      uses internal scales; we encode history via previous state instead of explicit discount here.
    - min_confidence: gate below which actions are suppressed (social-stress control analogue).
    - negative_curvature_gate: if static Ricci curvature is too negative, actions are suppressed.
    - warmup: first N samples return 0 (avoid early noise while composite stabilises).
    - motivation_scale: scales the modulation effect of the motivation signal on the action sign.
    - motivation_threshold: minimum absolute motivation value required for action; below this, signals suppressed.
    - state_scaling_factor: scaling factor applied to state vectors in hidden state construction.
    """

    discount_rate: float = 0.95
    min_confidence: float = 0.55
    negative_curvature_gate: float = -0.15
    warmup: int = 64
    motivation_scale: float = 0.5
    motivation_threshold: float = 0.05
    state_scaling_factor: float = 0.5


class NeuroGeoSyncStrategy:
    """Light-weight bridge between the composite engine and fractal motivation.

    Produces a discrete action per timestamp: +1 (long), 0 (flat), -1 (short).
    """

    def __init__(self, cfg: Optional[NeuroGeoSyncConfig] = None) -> None:
        self.cfg = cfg or NeuroGeoSyncConfig()
        self.engine = GeoSyncCompositeEngine()
        # Motivation engine operates on compact state vectors; choose a modest dimension
        self.motivation = FractalMotivationEngine(state_dim=8)
        self._prev_state_vec: np.ndarray | None = None

    def analyze_snapshot(self, bars: pd.DataFrame) -> CompositeSignal:
        """Return the latest composite snapshot for bars (must have DatetimeIndex)."""
        return self.engine.analyze_market(bars)

    @staticmethod
    def _state_from_signal(sig: CompositeSignal) -> np.ndarray:
        # Compact numeric summary for the motivation engine
        return np.asarray(
            [
                sig.kuramoto_R,
                sig.cross_scale_coherence,
                sig.static_ricci,
                sig.temporal_ricci,
                sig.topological_transition,
                sig.confidence,
                sig.entry_signal,
                sig.exit_signal,
            ],
            dtype=float,
        )

    def _hidden_states(self, state_vec: np.ndarray, prev: np.ndarray | None) -> np.ndarray:
        # Build a tiny set of contextual vectors for motivation coherence/fractal metrics
        if prev is None:
            delta = np.zeros_like(state_vec)
        else:
            delta = state_vec - prev
        return np.vstack(
            [
                state_vec,
                self.cfg.state_scaling_factor * state_vec,
                np.tanh(delta),
            ]
        )

    def _gate_and_modulate(
        self, sig: CompositeSignal, state_vec: np.ndarray, hidden: np.ndarray
    ) -> float:
        # Base decision from composite
        base = float(np.sign(sig.entry_signal)) if np.isfinite(sig.entry_signal) else 0.0

        # Confidence gate
        if sig.confidence < self.cfg.min_confidence:
            return 0.0

        # Negative curvature stress gate
        if sig.static_ricci < self.cfg.negative_curvature_gate:
            return 0.0

        # Motivation modulation (amygdala/goal-progress analogue)
        try:
            m = float(
                self.motivation.compute_contextual_motivation(
                    hidden_states=hidden,
                    current=state_vec,
                    previous=self._prev_state_vec,
                )
            )
        except Exception:
            m = 0.0

        # Scale sign by motivation: if motivation near-zero -> conservative flat
        if abs(m) < self.cfg.motivation_threshold:
            return 0.0

        return float(np.sign(base * (1.0 + self.cfg.motivation_scale * m))) if base != 0.0 else 0.0

    def generate_signals(
        self, bars: pd.DataFrame, price_col: str = "close", volume_col: str = "volume"
    ) -> pd.Series:
        """Return a series of actions (+1/0/−1) aligned to bars.index.

        Notes:
            - bars must have a DatetimeIndex and contain price_col and volume_col.
            - Warmup period returns 0.0 to avoid early noise.
        """
        if not isinstance(bars.index, pd.DatetimeIndex):
            raise ValueError("bars must have a DatetimeIndex")
        if price_col not in bars or volume_col not in bars:
            raise ValueError(f"bars must include '{price_col}' and '{volume_col}' columns")

        actions: list[float] = []
        self._prev_state_vec = None

        for i in range(len(bars)):
            window = bars.iloc[: i + 1]
            sig = self.analyze_snapshot(window)
            state_vec = self._state_from_signal(sig)
            hidden = self._hidden_states(state_vec, self._prev_state_vec)

            if i < self.cfg.warmup:
                action = 0.0
            else:
                action = self._gate_and_modulate(sig, state_vec, hidden)

            actions.append(action)
            self._prev_state_vec = state_vec

        return pd.Series(actions, index=bars.index, name="neuro_action")


def get_strategy(config: Optional[Dict[str, Any]] = None) -> NeuroGeoSyncStrategy:
    cfg = NeuroGeoSyncConfig(**(config or {}))
    return NeuroGeoSyncStrategy(cfg)
