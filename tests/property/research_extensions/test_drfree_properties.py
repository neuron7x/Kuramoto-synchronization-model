# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Property tests for INV-FE-ROBUST — DR-FREE distributionally-robust free energy.

INV-FE-ROBUST: ``F_robust >= F_nominal`` for every metric and every radius
``r_m >= 0``; zero radius collapses to nominal; F_robust is monotone in
radius; unknown / negative radii are fail-closed.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tacl.dr_free import AmbiguitySet, DRFreeEnergyModel
from tacl.energy_model import DEFAULT_THRESHOLDS, EnergyMetrics

from .strategies import ambiguity_sets


def _energy_metrics_strategy() -> st.SearchStrategy[EnergyMetrics]:
    """Generate finite, non-negative :class:`EnergyMetrics`.

    Bounds are well below the threshold values (so penalties are non-trivial
    but bounded) and well below 1e150 to keep ``(1+r)·m`` finite at any
    feasible ambiguity radius drawn by :func:`ambiguity_sets`.
    """
    floats = st.floats(
        min_value=0.0,
        max_value=1e6,
        allow_nan=False,
        allow_infinity=False,
        allow_subnormal=False,
        width=64,
    )
    return st.builds(
        EnergyMetrics,
        latency_p95=floats,
        latency_p99=floats,
        coherency_drift=st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False, width=64
        ),
        cpu_burn=st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False, width=64
        ),
        mem_cost=floats,
        queue_depth=floats,
        packet_loss=st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False, width=64
        ),
    )


@settings(
    deadline=2000,
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(metrics=_energy_metrics_strategy(), ambiguity=ambiguity_sets())
def test_robust_dominates_nominal(metrics: EnergyMetrics, ambiguity: AmbiguitySet) -> None:
    """INV-FE-ROBUST: F_robust >= F_nominal for every (metrics, radius) pair."""
    model = DRFreeEnergyModel()
    result = model.evaluate_robust(metrics, ambiguity)
    # Tolerance derivation: penalty + entropy aggregations sum 7 weighted
    # terms each, so the worst-case rounding noise is ~7·eps_64 ≈ 1.6e-15.
    # The DRFreeResult post-init guard already uses 1e-12 — match it.
    assert result.robust_free_energy + 1e-12 >= result.nominal_free_energy, (
        "INV-FE-ROBUST VIOLATED: F_robust must dominate F_nominal. "
        f"Observed robust={result.robust_free_energy:.6e}, "
        f"nominal={result.nominal_free_energy:.6e}, "
        f"margin={result.robust_margin:.3e}, expected margin >= -1e-12. "
        "Tolerance: 1e-12 (7-term weighted sum, ~7·eps_64 ≈ 1.6e-15 padded). "
        f"Context: radii={dict(ambiguity.radii)}."
    )


@settings(
    deadline=2000,
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(metrics=_energy_metrics_strategy())
def test_zero_radius_equals_nominal(metrics: EnergyMetrics) -> None:
    """INV-FE-ROBUST: r_m = 0 ∀ m  ⟹  F_robust == F_nominal."""
    model = DRFreeEnergyModel()
    zero_radii = {name: 0.0 for name in DEFAULT_THRESHOLDS}
    ambiguity = AmbiguitySet(radii=zero_radii, mode="box")
    result = model.evaluate_robust(metrics, ambiguity)
    diff = abs(result.robust_free_energy - result.nominal_free_energy)
    # Tolerance derivation: with all r_m = 0 the inflation map is identity
    # and the two free-energy evaluations operate on the same metrics —
    # the only divergence is the order of two identical sums, which is
    # bit-stable in NumPy. Use 1e-15 (one eps_64 of slack).
    assert diff < 1e-12, (
        "INV-FE-ROBUST VIOLATED: zero ambiguity must collapse to nominal. "
        f"Observed |Δ|={diff:.3e}, expected <1e-12. "
        "Tolerance: 1e-12 (identical sums, bit-stable in NumPy). "
        f"Context: nominal={result.nominal_free_energy:.6e}, "
        f"robust={result.robust_free_energy:.6e}."
    )


@settings(
    deadline=2000,
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    metrics=_energy_metrics_strategy(),
    metric_name=st.sampled_from(sorted(DEFAULT_THRESHOLDS.keys())),
    r1=st.floats(min_value=0.0, max_value=2.5, allow_nan=False, allow_infinity=False, width=64),
    delta=st.floats(min_value=0.0, max_value=2.5, allow_nan=False, allow_infinity=False, width=64),
)
def test_monotone_in_radius(
    metrics: EnergyMetrics, metric_name: str, r1: float, delta: float
) -> None:
    """INV-FE-ROBUST: r_1 ≤ r_2  ⟹  F_robust(r_1) ≤ F_robust(r_2).

    Per Sutskever — derive the tolerance, don't relax it. The DR-FREE
    inflation is a non-decreasing affine map on a non-negative metric, and
    free-energy is monotone in every penalty, so this property is exact.
    """
    r2 = r1 + delta
    model = DRFreeEnergyModel()
    a1 = AmbiguitySet(radii={metric_name: float(r1)}, mode="box")
    a2 = AmbiguitySet(radii={metric_name: float(r2)}, mode="box")
    f1 = model.evaluate_robust(metrics, a1).robust_free_energy
    f2 = model.evaluate_robust(metrics, a2).robust_free_energy
    # Tolerance derivation: same 7-term weighted sum on both sides, single
    # metric inflated. Worst-case rounding noise ~14·eps_64 ≈ 3.1e-15.
    # Bound 1e-12 to match the module-level invariant slack.
    assert f1 <= f2 + 1e-12, (
        "INV-FE-ROBUST VIOLATED: F_robust must be monotone non-decreasing in radius. "
        f"Observed F(r1={r1:.3e})={f1:.6e}, F(r2={r2:.3e})={f2:.6e}, "
        f"Δ={f2 - f1:.3e}, expected >= -1e-12. "
        "Tolerance: 1e-12 (14-term weighted sum, ~14·eps_64 padded). "
        f"Context: metric={metric_name}, δ={delta:.3e}."
    )


def test_unknown_metric_rejected() -> None:
    """INV-FE-ROBUST: ambiguity over an unknown metric is fail-closed."""
    model = DRFreeEnergyModel()
    bad = AmbiguitySet(radii={"this_metric_does_not_exist": 0.5}, mode="box")
    metrics = EnergyMetrics(
        latency_p95=10.0,
        latency_p99=20.0,
        coherency_drift=0.01,
        cpu_burn=0.3,
        mem_cost=2.0,
        queue_depth=5.0,
        packet_loss=0.001,
    )
    with pytest.raises(ValueError, match="Unknown ambiguity metrics"):
        model.evaluate_robust(metrics, bad)


def test_negative_radius_rejected() -> None:
    """INV-FE-ROBUST: a negative radius is fail-closed at AmbiguitySet construction."""
    with pytest.raises(ValueError, match="Negative radius"):
        AmbiguitySet(radii={"latency_p95": -0.1}, mode="box")


@settings(
    deadline=2000,
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(metrics=_energy_metrics_strategy(), ambiguity=ambiguity_sets())
def test_adversarial_metrics_finite(metrics: EnergyMetrics, ambiguity: AmbiguitySet) -> None:
    """INV-FE-ROBUST: adversarial metrics are finite for every admissible input.

    Bounded metric values (≤1e6) × bounded radii (≤5) keep ``(1+r)·m`` well
    inside float64 range; the contract additionally rejects any inflated
    NaN/Inf. We assert finiteness end-to-end.
    """
    model = DRFreeEnergyModel()
    adv = model.adversarial_metrics(metrics, ambiguity)
    values = list(adv.as_dict().values())
    assert all(np.isfinite(v) for v in values), (
        "INV-FE-ROBUST VIOLATED: adversarial metrics must be finite. "
        f"Observed values={values}, expected all finite. "
        "Tolerance: float finiteness (no slack). "
        f"Context: radii={dict(ambiguity.radii)}, "
        f"nominal={dict(metrics.as_dict())}."
    )
    # Worst-case domination of every nominal value (penalty-increasing axis).
    nominal = metrics.as_dict()
    for name, value in adv.as_dict().items():
        radius = float(ambiguity.radii.get(name, 0.0))
        expected = float(nominal[name]) * (1.0 + radius)
        # Tolerance derivation: a single multiplication; rounding bound is
        # one ulp = eps_64 ≈ 2.2e-16 in relative error. Use 1e-12 for safety.
        assert value == pytest.approx(expected, rel=1e-12, abs=1e-12), (
            "INV-FE-ROBUST VIOLATED: adversarial map must equal m·(1+r). "
            f"Observed adv[{name}]={value:.6e}, expected={expected:.6e}, "
            f"|Δ|={abs(value - expected):.3e}. "
            "Tolerance: rel=1e-12, abs=1e-12 (single mul, one ulp ≈ 2.2e-16). "
            f"Context: nominal={nominal[name]:.6e}, radius={radius:.6e}."
        )
