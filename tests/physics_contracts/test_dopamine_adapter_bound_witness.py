# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witness for the dopamine adapter bounded-signal law.

Binds the catalog law ``dopamine.bounded_signal`` to an executable ``@law``
witness and proves it holds in the real
``core.neuro.dopamine_execution_adapter.DopamineExecutionAdapter``:

* ``dopamine.bounded_signal`` — the adapter emits a saturating bounded signal,
  |δ| = |tanh(scale · raw_rpe)| ≤ 1, and δ is finite for every finite input
  (closed bound; tanh saturates to ±1 in float64 at extreme argument) (INV-DA8).

This is the ADAPTER bound, deliberately distinct from INV-DA7 which governs the
RAW controller's linearity (∂δ/∂r = 1). The adapter is NON-linear by design — the
tanh squashing is exactly what provides this bound — so it carries its own
invariant rather than inheriting the controller's. Nothing here is a market claim.
"""

from __future__ import annotations

import math

from core.neuro.dopamine_execution_adapter import DopamineExecutionAdapter
from core.neuro.signal_bus import NeuroSignalBus
from physics_contracts.law import law

# Closed bound: tanh saturates to exactly ±1.0 in float64, so |δ| ≤ 1 (≤, not <).
BOUND = 1.0
# Extreme finite magnitudes that drive tanh deep into saturation.
EXTREME = 1e9
# tanh_scale values: small, unit, and large all yield the same |δ| ≤ 1 bound.
TANH_SCALES = (0.1, 1.0, 25.0)


@law("dopamine.bounded_signal", n_scales=3, extreme_magnitude=EXTREME)
def test_adapter_signal_is_bounded_and_finite() -> None:
    """INV-DA8: |δ| = |tanh(scale·raw)| ≤ 1 and finite for every finite input.

    Sweeps a deterministic grid of (realized_pnl, predicted_return, slippage)
    inputs — including extreme finite magnitudes that drive tanh into saturation —
    across several tanh_scale settings. Every emitted δ must be finite and lie in
    the closed interval [−1, 1]; the witness tracks the worst |δ| observed.
    """
    n_scales = len(TANH_SCALES)
    inputs = (
        (0.0, 0.0, 0.0),
        (1.0, 0.5, 0.1),
        (-1.0, 0.5, 0.2),
        (EXTREME, -EXTREME, EXTREME),
        (-EXTREME, EXTREME, 0.0),
        (EXTREME, 0.0, EXTREME),
    )
    worst_abs_delta = 0.0
    all_finite = True
    for tanh_scale in TANH_SCALES:
        adapter = DopamineExecutionAdapter(NeuroSignalBus(), tanh_scale=tanh_scale)
        for realized_pnl, predicted_return, slippage in inputs:
            delta = adapter.compute_rpe(
                realized_pnl=realized_pnl,
                predicted_return=predicted_return,
                slippage=slippage,
            )
            all_finite = all_finite and math.isfinite(delta)
            worst_abs_delta = max(worst_abs_delta, abs(delta))

    assert all_finite, (
        "INV-DA8 violated: observed a non-finite δ from the adapter over "
        f"n_scales={n_scales} with extreme_magnitude={EXTREME:.0e}; every finite "
        "input must map to a finite tanh output"
    )
    assert worst_abs_delta <= BOUND, (
        "INV-DA8 violated: observed worst |δ| = "
        f"{worst_abs_delta:.6f} must be ≤ {BOUND:.1f} over n_scales={n_scales} "
        f"with extreme_magnitude={EXTREME:.0e}; the tanh adapter must saturate within [−1, 1]"
    )
