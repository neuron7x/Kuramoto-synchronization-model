# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witness for the DRO-ARA long-signal gate law in the catalog.

Binds the catalog law ``dro_ara.long_signal_gate`` to an executable ``@law``
witness, citing the EXISTING registry invariant INV-DRO4 (no new invariant, no
count change):

* ``dro_ara.long_signal_gate`` — signal == LONG ⟹ regime == CRITICAL ∧
  rs > RS_LONG_THRESH ∧ trend ∈ {CONVERGING, STABLE} (INV-DRO4).

The implication is witnessed NON-VACUOUSLY: a LONG signal is genuinely reachable.
A persistent anti-persistent (mean-reverting, low-Hurst) price series with enough
samples (≥ window + step, so the ARA accumulates a settled variational-energy
trend) drives the observer into the CRITICAL regime with rs > 0.33 and a STABLE
trend, which fires LONG. The witness asserts at least one LONG is observed AND
that every LONG observed satisfies the three antecedents — so the gate is proven
sound (no LONG without its conditions) and live (LONG is not dead code).

Nothing here is a market claim — LONG is a regime-observer label, not a trade.
"""

from __future__ import annotations

import numpy as np

from core.dro_ara.engine import RS_LONG_THRESH, Regime, Signal, geosync_observe
from physics_contracts.law import law

# Samples per series — comfortably above window (512) + step (64) so the ARA
# accumulates a multi-window variational-energy trend (else trend is undefined).
SERIES_LENGTH = 2500
# Anti-persistent AR(1) coefficient: negative φ ⇒ mean reversion ⇒ low Hurst ⇒
# γ = 2H + 1 near 1 ⇒ rs = 1 − |γ − 1| comfortably above RS_LONG_THRESH.
AR_PHI = -0.6
NOISE_STD = 0.01
N_SEEDS = 24
_VALID_LONG_TRENDS = ("CONVERGING", "STABLE")


def _anti_persistent_prices(seed: int) -> np.ndarray:
    """Deterministic mean-reverting price path that can enter the CRITICAL regime."""
    rng = np.random.default_rng(seed=seed)
    increments = np.zeros(SERIES_LENGTH)
    for t in range(1, SERIES_LENGTH):
        increments[t] = AR_PHI * increments[t - 1] + rng.normal(0.0, NOISE_STD)
    return 100.0 * np.exp(np.cumsum(increments))


@law("dro_ara.long_signal_gate", n_seeds=N_SEEDS, series_length=SERIES_LENGTH)
def test_long_signal_implies_critical_high_rs_settled_trend() -> None:
    """INV-DRO4: every LONG implies CRITICAL ∧ rs > threshold ∧ settled trend.

    Sweeps deterministic anti-persistent series. For every series whose emitted
    signal is LONG, the regime must be CRITICAL, the risk scalar must exceed
    RS_LONG_THRESH, and the trend must be CONVERGING or STABLE. A separate guard
    requires at least one LONG across the sweep, so the implication is witnessed
    on live data rather than holding vacuously over an empty LONG set.
    """
    n_seeds = N_SEEDS
    n_long = 0
    violations = 0
    for seed in range(n_seeds):
        observation = geosync_observe(_anti_persistent_prices(seed))
        if observation["signal"] != Signal.LONG.value:
            continue
        n_long += 1
        ok = (
            observation["regime"] == Regime.CRITICAL.value
            and observation["risk_scalar"] > RS_LONG_THRESH
            and observation["trend"] in _VALID_LONG_TRENDS
        )
        if not ok:
            violations += 1

    assert violations == 0, (
        "INV-DRO4 violated: observed LONG signals breaking the antecedent = "
        f"{violations} must be 0 over n_seeds={n_seeds}; LONG requires CRITICAL ∧ "
        f"rs > {RS_LONG_THRESH} ∧ trend ∈ {_VALID_LONG_TRENDS}"
    )
    assert n_long >= 1, (
        "INV-DRO4 vacuity guard: observed LONG count = "
        f"{n_long} must be ≥ 1 over n_seeds={n_seeds}; the LONG gate must be "
        "reachable, not dead code — the implication cannot be witnessed on an empty set"
    )
