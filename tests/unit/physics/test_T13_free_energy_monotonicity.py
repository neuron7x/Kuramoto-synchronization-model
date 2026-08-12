# SPDX-License-Identifier: MIT
"""T13 (monotonicity companion) — INV-FE1 per-decision tightening.

The companion file (`test_T13_free_energy_components.py`) verifies
INV-FE2 — every Helmholtz component (U, T, S) stays non-negative on
each gate evaluation.

INV-FE1 reads "F non-increasing under active inference." The gate
implementation in :mod:`core.physics.free_energy_trading_gate`
enforces this per-decision via the hard rule
``allowed = (delta_F <= 0.0)`` — every *accepted* move lowers (or
holds) F. This file pins that per-decision invariant as a property,
and adds the contrapositive: any non-allowed decision must have
``delta_F > 0`` (strict). Two complementary directions of the same
contract; together they fence the gate against silent loosening.

Why this is stronger than the existing component test
-----------------------------------------------------

INV-FE2 catches drift in U/T/S sub-routines. INV-FE1 catches drift
in the *gate policy itself*: if a future refactor introduces a
hysteresis band, an "accept on tie", or a probabilistic accept,
this test fails immediately without depending on integration timing
or numerical tolerances. The acceptance rule is algebraic; the test
matches that algebra.

Across-step trajectory testing is *not* feasible here: the gate's
``F_before`` depends on the current step's ``recent_returns``, which
typically vary, so the inter-step F sequence drifts from environment
shocks rather than from policy. The per-decision contract is the
right granularity for INV-FE1 in this codebase.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.physics.free_energy_trading_gate import FreeEnergyTradingGate


@pytest.mark.parametrize("seed", [13, 42, 101, 2024, 9999])
def test_inv_fe1_every_allowed_decision_has_non_positive_delta_f(seed: int) -> None:
    """INV-FE1: any decision with allowed=True must satisfy delta_F ≤ 0.

    Drives the gate with 200 random (before, after, returns) triples,
    then sweeps every produced decision and asserts the per-decision
    contract. Tolerance is ULP-only — the gate's rule is algebraic.
    """
    rng = np.random.default_rng(seed=seed)
    gate = FreeEnergyTradingGate(T_base=0.60, q=1.5, vol_reference=0.01)
    ulp_tolerance = 1e-12

    decisions = []
    for _ in range(200):
        n_assets = int(rng.integers(2, 8))
        pos_before = rng.uniform(0.0, 5.0, size=n_assets)
        pos_after = rng.uniform(0.0, 5.0, size=n_assets)
        returns = rng.uniform(-0.05, 0.05, size=n_assets)
        decisions.append(
            gate.check(
                positions_before=pos_before,
                positions_after=pos_after,
                recent_returns=returns,
            )
        )

    allowed_count = sum(1 for d in decisions if d.allowed)
    assert allowed_count > 0, (
        f"degenerate fixture at seed={seed}: 0 / 200 allowed decisions; "
        "the FE1 invariant is vacuous on a fully-rejecting gate, "
        "and the test would not exercise the contract."
    )

    for idx, d in enumerate(decisions):
        if not d.allowed:
            continue
        assert d.delta_F <= ulp_tolerance, (
            f"INV-FE1 VIOLATED on decision {idx}/200 at seed={seed}: "
            f"allowed=True but delta_F = {d.delta_F:.6e} > "
            f"ULP tolerance {ulp_tolerance:.0e}. "
            f"F_before={d.F_before:.6e}, F_after={d.F_after:.6e}. "
            "Physical reasoning: the gate's policy is "
            "`allowed = (delta_F <= 0)` — any accepted decision with "
            "positive delta_F means the policy was loosened or the "
            "delta_F arithmetic drifted from the F values it summarises."
        )


@pytest.mark.parametrize("seed", [13, 42, 101, 2024, 9999])
def test_inv_fe1_every_rejected_decision_has_strictly_positive_delta_f(seed: int) -> None:
    """INV-FE1 contrapositive: allowed=False ⟹ delta_F > 0 (strictly).

    Reject-on-ties would be a silent loosening. This test asserts the
    rejection set is exactly ``delta_F > 0``.
    """
    rng = np.random.default_rng(seed=seed)
    gate = FreeEnergyTradingGate(T_base=0.60, q=1.5, vol_reference=0.01)

    rejected = []
    for _ in range(200):
        n_assets = int(rng.integers(2, 8))
        pos_before = rng.uniform(0.0, 5.0, size=n_assets)
        pos_after = rng.uniform(0.0, 5.0, size=n_assets)
        returns = rng.uniform(-0.05, 0.05, size=n_assets)
        d = gate.check(
            positions_before=pos_before,
            positions_after=pos_after,
            recent_returns=returns,
        )
        if not d.allowed:
            rejected.append(d)

    assert len(rejected) > 0, (
        f"degenerate fixture at seed={seed}: 0 rejections; "
        "the contrapositive is vacuous and the test would not exercise "
        "the rejection rule."
    )

    for idx, d in enumerate(rejected):
        assert d.delta_F > 0.0, (
            f"INV-FE1 contrapositive VIOLATED on rejected decision "
            f"{idx} at seed={seed}: allowed=False but "
            f"delta_F = {d.delta_F:.6e} ≤ 0. "
            "Physical reasoning: a gate that rejects a non-positive "
            "delta_F is over-restrictive — INV-FE1 only mandates "
            "rejection when F would rise."
        )


def test_inv_fe1_delta_f_equals_f_after_minus_f_before_exactly() -> None:
    """INV-FE1 lemma: delta_F == F_after − F_before to machine precision.

    The decision dataclass exposes all three fields — drift between
    them would silently break any downstream consumer that consumes
    delta_F instead of recomputing.
    """
    rng = np.random.default_rng(seed=271828)
    gate = FreeEnergyTradingGate(T_base=0.60, q=1.5, vol_reference=0.01)
    ulp_tolerance = 1e-12

    for _ in range(50):
        n_assets = int(rng.integers(2, 6))
        pos_before = rng.uniform(0.0, 4.0, size=n_assets)
        pos_after = rng.uniform(0.0, 4.0, size=n_assets)
        returns = rng.uniform(-0.04, 0.04, size=n_assets)
        d = gate.check(
            positions_before=pos_before,
            positions_after=pos_after,
            recent_returns=returns,
        )
        residual = abs(d.delta_F - (d.F_after - d.F_before))
        assert residual < ulp_tolerance, (
            f"INV-FE1 lemma VIOLATED: delta_F={d.delta_F:.6e} "
            f"!= F_after − F_before = {d.F_after - d.F_before:.6e}, "
            f"residual={residual:.3e} > {ulp_tolerance:.0e}. "
            "Physical reasoning: a downstream consumer that gates on "
            "delta_F instead of recomputing the difference would draw "
            "wrong conclusions from a drifted field."
        )
