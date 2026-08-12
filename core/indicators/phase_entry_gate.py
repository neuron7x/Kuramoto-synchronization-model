# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""π-system composite entry gate.

This module is the formal closure of the author's 2025 research thread
``04_ЕМЕРДЖЕНТНІ_КОГНІТИВНІ_СИСТЕМИ/Емерджентна синхронізація та
когнітивна π-система для автономного трейдингу.odt``. The thread
proposed a four-primitive entry rule for long/short decisions on a
multi-asset panel. All four primitives already exist in GeoSync:

=================  ======================================================
primitive           GeoSync module
=================  ======================================================
R (Kuramoto)        core/indicators/kuramoto.py
ΔH (entropy)        core/indicators/entropy.py  (or any discrete entropy)
κ̄ (Ricci)          core/indicators/ricci.py
H_DFA (Hurst)       core/indicators/hurst.py
=================  ======================================================

This file does **not** recompute them. It only composes pre-computed
scalar readings into a deterministic ``Signal`` per the rule:

    LONG  if  R > r_threshold
          and ΔH < delta_h_threshold
          and κ̄ < kappa_threshold
          and H_DFA > hurst_long_threshold

    SHORT if  R > r_threshold
          and ΔH < delta_h_threshold
          and κ̄ < kappa_threshold
          and H_DFA < hurst_short_threshold

    NEUTRAL otherwise.

Both directions require the **same** synchronisation/entropy/curvature
conditions — the only asymmetry is the Hurst exponent (persistence vs
anti-persistence). This mirrors the original archive rule and keeps the
decision fail-closed: a low-R, flat-entropy, zero-curvature regime
always returns NEUTRAL regardless of trend direction.

Every evaluation returns a ``GateReading`` with:

* ``signal`` — the enum decision,
* ``conditions`` — per-primitive booleans (what fired, what didn't),
* ``diagnostics`` — the raw input values, so the caller can audit why.

Honesty contract
----------------
``evaluate`` refuses to return a directional signal when any input is
non-finite (NaN/Inf) or any threshold condition is ambiguous. NaN in,
NEUTRAL out. This matches agent/invariants.INV_004_nan_policy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

__all__ = [
    "PhaseEntryGateConfig",
    "Signal",
    "GateConditions",
    "GateReading",
    "PhaseEntryGate",
    "DEFAULT_PHASE_ENTRY_CONFIG",
]


class Signal(Enum):
    """Tri-state gate output."""

    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class PhaseEntryGateConfig:
    """Thresholds defining the π-system entry rule.

    Defaults are the values from the original archive document. They
    are hand-tuned on BTC 15m bars circa 2025 and should be
    re-calibrated per asset/timeframe before production use — but they
    are the canonical reference point for reproducibility.
    """

    #: Kuramoto order parameter must exceed this to register "sync".
    r_threshold: float = 0.75
    #: Entropy delta must be at most this (i.e. entropy *decreasing*).
    delta_h_threshold: float = -0.05
    #: Mean Ricci curvature must be at most this (focusing topology).
    kappa_threshold: float = -0.1
    #: Hurst exponent for LONG — above this = persistent / trending.
    hurst_long_threshold: float = 0.55
    #: Hurst exponent for SHORT — below this = mean-reverting regime.
    hurst_short_threshold: float = 0.45

    def __post_init__(self) -> None:
        if not 0.0 <= self.r_threshold <= 1.0:
            raise ValueError(f"r_threshold must be in [0,1], got {self.r_threshold}")
        if not 0.0 <= self.hurst_long_threshold <= 1.0:
            raise ValueError(f"hurst_long_threshold out of [0,1]: {self.hurst_long_threshold}")
        if not 0.0 <= self.hurst_short_threshold <= 1.0:
            raise ValueError(f"hurst_short_threshold out of [0,1]: {self.hurst_short_threshold}")
        if self.hurst_short_threshold >= self.hurst_long_threshold:
            raise ValueError(
                "hurst_short_threshold must be strictly below hurst_long_threshold, "
                f"got short={self.hurst_short_threshold} long={self.hurst_long_threshold}",
            )


#: Canonical defaults — import this when you want the "textbook" gate.
DEFAULT_PHASE_ENTRY_CONFIG: Final[PhaseEntryGateConfig] = PhaseEntryGateConfig()


@dataclass(frozen=True, slots=True)
class GateConditions:
    """Per-primitive boolean conditions that fired in an evaluation."""

    r_sync: bool
    entropy_decreasing: bool
    curvature_focusing: bool
    persistent_long: bool
    mean_reverting_short: bool

    def as_dict(self) -> dict[str, bool]:
        return {
            "r_sync": self.r_sync,
            "entropy_decreasing": self.entropy_decreasing,
            "curvature_focusing": self.curvature_focusing,
            "persistent_long": self.persistent_long,
            "mean_reverting_short": self.mean_reverting_short,
        }


@dataclass(frozen=True, slots=True)
class GateReading:
    """Full audit trail of a single gate evaluation."""

    signal: Signal
    conditions: GateConditions
    diagnostics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "signal": self.signal.value,
            "conditions": self.conditions.as_dict(),
            "diagnostics": dict(self.diagnostics),
        }


def _finite(*values: float) -> bool:
    return all(math.isfinite(v) for v in values)


class PhaseEntryGate:
    """Deterministic composite gate — stateless, reusable, thread-safe."""

    def __init__(self, config: PhaseEntryGateConfig | None = None) -> None:
        self._config = config or DEFAULT_PHASE_ENTRY_CONFIG

    @property
    def config(self) -> PhaseEntryGateConfig:
        return self._config

    def evaluate(
        self,
        *,
        r_kuramoto: float,
        delta_h: float,
        kappa_mean: float,
        hurst: float,
    ) -> GateReading:
        """Compose the four scalars into a single signal + audit trail.

        Parameters
        ----------
        r_kuramoto
            Kuramoto order parameter, expected ∈ [0, 1].
        delta_h
            Entropy delta ``H(t) - H(t-1)``. Negative → ordering.
        kappa_mean
            Mean Ricci curvature over the correlation graph.
        hurst
            Hurst exponent ∈ [0, 1].

        Returns
        -------
        GateReading
            Signal + per-condition booleans + raw diagnostics.
        """
        diagnostics: dict[str, float] = {
            "r_kuramoto": float(r_kuramoto),
            "delta_h": float(delta_h),
            "kappa_mean": float(kappa_mean),
            "hurst": float(hurst),
        }

        if not _finite(r_kuramoto, delta_h, kappa_mean, hurst):
            # Honesty contract: NaN in → NEUTRAL out.
            return GateReading(
                signal=Signal.NEUTRAL,
                conditions=GateConditions(
                    r_sync=False,
                    entropy_decreasing=False,
                    curvature_focusing=False,
                    persistent_long=False,
                    mean_reverting_short=False,
                ),
                diagnostics=diagnostics,
            )

        cfg = self._config
        r_sync = r_kuramoto > cfg.r_threshold
        entropy_decreasing = delta_h < cfg.delta_h_threshold
        curvature_focusing = kappa_mean < cfg.kappa_threshold
        persistent_long = hurst > cfg.hurst_long_threshold
        mean_reverting_short = hurst < cfg.hurst_short_threshold

        base_trigger = r_sync and entropy_decreasing and curvature_focusing

        if base_trigger and persistent_long:
            signal = Signal.LONG
        elif base_trigger and mean_reverting_short:
            signal = Signal.SHORT
        else:
            signal = Signal.NEUTRAL

        return GateReading(
            signal=signal,
            conditions=GateConditions(
                r_sync=r_sync,
                entropy_decreasing=entropy_decreasing,
                curvature_focusing=curvature_focusing,
                persistent_long=persistent_long,
                mean_reverting_short=mean_reverting_short,
            ),
            diagnostics=diagnostics,
        )
