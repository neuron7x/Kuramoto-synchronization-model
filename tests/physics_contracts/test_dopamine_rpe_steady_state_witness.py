# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witness for the dopamine reward-prediction-error steady-state law.

Binds a pytest function to the catalog law ``dopamine.rpe_zero_steady_state`` via
``@law`` and proves it holds in the real ``DopamineExecutionAdapter``:

* ``dopamine.rpe_zero_steady_state`` (INV-DA5) — in a stationary reward
  environment whose realized rewards are symmetric about the prediction, the
  expected reward-prediction error converges to zero: E[δ] → 0.

The adapter applies δ = tanh(scale · (r − prediction)); for rewards symmetric
about the prediction the odd tanh makes E[δ] vanish by symmetry. The witness
estimates E[δ] over a large ensemble and requires it to sit within three
standard errors of zero (the ensemble-test discipline INV-DA5 declares).

This law was previously mis-flagged as lacking a clean invariant; INV-DA5 anchors
it and the adapter path is sound for the EXPECTATION (unlike INV-DA7's ∂δ/∂r,
which the tanh path does break — that one correctly targets the controller).

Nothing here is a market claim. These are reward-learning steady-state facts.
"""

from __future__ import annotations

import numpy as np

from core.neuro.dopamine_execution_adapter import DopamineExecutionAdapter
from core.neuro.signal_bus import NeuroSignalBus
from physics_contracts.law import law


@law("dopamine.rpe_zero_steady_state", n_samples=20000, n_environments=3)
def test_expected_rpe_converges_to_zero_in_stationary_environment() -> None:
    """INV-DA5: E[δ] → 0 when realized rewards are stationary about the prediction.

    For each of several stationary reward environments (symmetric realized rewards
    about a fixed prediction), the ensemble mean of δ = tanh(scale·(r − pred)) must
    lie within three standard errors of zero — the reward-prediction error has no
    bias at the value-function fixed point.
    """
    n_samples = 20000
    adapter = DopamineExecutionAdapter(NeuroSignalBus())
    environments = ((0.0, 0.01), (0.005, 0.02), (-0.003, 0.015))
    rng = np.random.default_rng(seed=0)
    worst_ratio = 0.0
    for prediction, sigma in environments:
        deltas = np.array(
            [
                adapter.compute_rpe(
                    realized_pnl=float(rng.normal(prediction, sigma)),
                    predicted_return=prediction,
                )
                for _ in range(n_samples)
            ]
        )
        mean_delta = float(deltas.mean())
        standard_error = float(deltas.std() / np.sqrt(n_samples))
        worst_ratio = max(worst_ratio, abs(mean_delta) / standard_error)
    assert worst_ratio <= 3.0, (
        "INV-DA5 violated: observed worst |E[δ]| / SE = "
        f"{worst_ratio:.3f} must be ≤ 3 over n_samples={n_samples} with seed=0; the "
        "expected reward-prediction error must vanish in a stationary environment"
    )
