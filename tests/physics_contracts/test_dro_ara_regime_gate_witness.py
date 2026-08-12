# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witness for the DRO-ARA invalid-regime gate law.

Binds a pytest function to the catalog law ``dro_ara.invalid_regime_gate`` via
``@law`` and proves it holds in the real ``core.dro_ara.engine.geosync_observe``:

* ``dro_ara.invalid_regime_gate`` (INV-DRO3) — the INVALID regime is declared if
  and only if the series fails the stationarity (ADF) test OR its DFA fit R²
  falls below ``R2_MIN``. The equivalence is verified in both directions over a
  sweep that genuinely produces both INVALID and non-INVALID outcomes.

Sibling laws ``dro_ara.long_signal_gate`` and ``ecs.lyapunov_descent`` are left
unwitnessed here: a LONG signal could not be produced from any synthetic series
(it needs an ARA-loop CONVERGING/STABLE trend that random/OU inputs never
trigger), so its implication witness would be vacuous; and ecs.lyapunov_descent
has no dedicated registry invariant to anchor. Both are flagged honestly rather
than witnessed on a blind slice.

Nothing here is a market claim. These are regime-classifier-contract facts.
"""

from __future__ import annotations

import numpy as np

from core.dro_ara.engine import R2_MIN, Regime, geosync_observe
from physics_contracts.law import law


def _series(kind: int, seed: int) -> np.ndarray:
    """Three regimes of synthetic price path: random-walk, oscillatory, trend."""
    rng = np.random.default_rng(seed)
    if kind == 0:
        return 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, size=600)))
    if kind == 1:
        drift = np.cumsum(rng.normal(0.0, 1.0, size=600)) * 0.01
        return 100.0 + drift + 5.0 * np.sin(np.arange(600) / 20.0)
    return 100.0 * np.exp(np.cumsum(rng.normal(0.001, 0.02, size=600)))


@law("dro_ara.invalid_regime_gate", n_series=60, r2_min=0.9)
def test_invalid_regime_iff_nonstationary_or_low_r2() -> None:
    """INV-DRO3: regime == INVALID ⇔ (¬stationary ∨ r2 < R2_MIN).

    The classifier must declare INVALID exactly when the series fails the ADF
    stationarity test or its DFA fit R² is below the R2_MIN floor — no other
    path to INVALID, and never INVALID when both pass. The witness sweeps three
    families of synthetic paths and checks the bidirectional equivalence on each,
    with a vacuity guard that both INVALID and non-INVALID outcomes occur.
    """
    n_series = 60
    equivalence_failures = 0
    invalid_seen = 0
    valid_seen = 0
    for index in range(n_series):
        observation = geosync_observe(_series(index % 3, index))
        is_invalid = observation["regime"] == Regime.INVALID.value
        gate_condition = (not observation["stationary"]) or (observation["r2_dfa"] < R2_MIN)
        if is_invalid != gate_condition:
            equivalence_failures += 1
        invalid_seen += int(is_invalid)
        valid_seen += int(not is_invalid)
    assert equivalence_failures == 0, (
        "INV-DRO3 violated: observed equivalence_failures = "
        f"{equivalence_failures} of n_series={n_series} with r2_min={R2_MIN} must be 0; "
        "regime == INVALID must hold iff the series is non-stationary or r2 < R2_MIN"
    )
    assert invalid_seen > 0 and valid_seen > 0, (
        "INV-DRO3 vacuity guard: observed invalid_seen = "
        f"{invalid_seen} and valid_seen = {valid_seen} must both be > 0 "
        f"with r2_min={R2_MIN} over n_series={n_series}; the equivalence must be "
        "exercised on both outcomes"
    )
