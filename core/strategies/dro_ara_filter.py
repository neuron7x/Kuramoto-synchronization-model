# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""DRO-ARA regime filter for primary trading signals.

The DRO-ARA v7 observer is a regime classifier, not a standalone alpha (empirical
IC is in the `HEADROOM_ONLY` band — see `scripts/research/dro_ara_ic_fx.py`).
Its highest-value use is as a *gate* on another primary signal: pass-through when
the market is CRITICAL with a converging/stable trend, scale down on TRANSITION,
go flat when the regime is DRIFT or INVALID.

Contract:
    regime_multiplier is a deterministic function of (regime, trend) only;
    no floating-point tolerances are introduced — boundaries compare exact
    enum values. Fail-closed: INVALID → 0.0 exactly.
"""

from __future__ import annotations

from typing import Final

from numpy.typing import NDArray

from core.dro_ara import Regime, geosync_observe

__all__ = [
    "MULTIPLIER_CRITICAL",
    "MULTIPLIER_TRANSITION",
    "MULTIPLIER_DRIFT",
    "MULTIPLIER_INVALID",
    "regime_multiplier",
    "apply_regime_filter",
]

MULTIPLIER_CRITICAL: Final[float] = 1.0
MULTIPLIER_TRANSITION: Final[float] = 0.5
MULTIPLIER_DRIFT: Final[float] = 0.0
MULTIPLIER_INVALID: Final[float] = 0.0


def regime_multiplier(regime: str, trend: str | None) -> float:
    """Map (regime, trend) → position-size multiplier in [0, 1].

    * CRITICAL + trend ∈ {CONVERGING, STABLE} → 1.0
    * CRITICAL + DIVERGING                    → 0.5 (converging-check failed)
    * TRANSITION                              → 0.5
    * DRIFT                                   → 0.0
    * INVALID                                 → 0.0 (fail-closed)
    """
    if regime == Regime.INVALID.value:
        return MULTIPLIER_INVALID
    if regime == Regime.DRIFT.value:
        return MULTIPLIER_DRIFT
    if regime == Regime.TRANSITION.value:
        return MULTIPLIER_TRANSITION
    if regime == Regime.CRITICAL.value:
        if trend in ("CONVERGING", "STABLE"):
            return MULTIPLIER_CRITICAL
        return MULTIPLIER_TRANSITION
    return MULTIPLIER_INVALID


def apply_regime_filter(
    raw_signal: float,
    price_window: NDArray,
    *,
    window: int = 512,
    step: int = 64,
) -> tuple[float, dict[str, object]]:
    """Scale ``raw_signal`` by the DRO-ARA regime multiplier for ``price_window``.

    Returns a pair ``(filtered_signal, observation)`` where ``observation`` is
    the raw output of :func:`core.dro_ara.geosync_observe` augmented with the
    chosen ``multiplier`` under the key ``regime_multiplier``.

    Fail-closed: any :class:`ValueError` raised by ``geosync_observe`` (constant
    input, NaN, too short) propagates to the caller; callers that want
    silent-flat behaviour must catch and zero explicitly.
    """
    out = geosync_observe(price_window, window=window, step=step)
    mult = regime_multiplier(str(out["regime"]), out.get("trend"))  # type: ignore[arg-type]
    out["regime_multiplier"] = mult
    return float(raw_signal) * mult, out
