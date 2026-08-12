# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for DR-FREE distributionally robust free-energy primitives.

INV-FE-ROBUST — robust free energy dominates nominal under any non-negative
box ambiguity set; with zero ambiguity it equals nominal; the wrapper never
mutates the base EnergyModel.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tacl import (
    AmbiguitySet,
    DRFreeEnergyModel,
    DRFreeResult,
    EnergyMetrics,
    EnergyModel,
    robust_energy_state,
)


def _nominal_metrics() -> EnergyMetrics:
    return EnergyMetrics(
        latency_p95=70.0,
        latency_p99=100.0,
        coherency_drift=0.05,
        cpu_burn=0.6,
        mem_cost=5.0,
        queue_depth=20.0,
        packet_loss=0.002,
    )


def test_robust_free_energy_dominates_nominal() -> None:
    """INV-FE-ROBUST: F_robust >= F_nominal for every penalty-increasing metric."""
    model = DRFreeEnergyModel()
    metrics = _nominal_metrics()
    radii = {
        "latency_p95": 0.10,
        "latency_p99": 0.20,
        "coherency_drift": 0.30,
        "cpu_burn": 0.05,
        "mem_cost": 0.15,
        "queue_depth": 0.40,
        "packet_loss": 0.50,
    }
    ambiguity = AmbiguitySet(radii=radii)
    result = model.evaluate_robust(metrics, ambiguity)

    assert result.robust_free_energy >= result.nominal_free_energy - 1e-12, (
        "INV-FE-ROBUST VIOLATED: F_robust must dominate F_nominal; "
        f"observed robust={result.robust_free_energy:.6f}, "
        f"nominal={result.nominal_free_energy:.6f}, "
        f"margin={result.robust_margin:.6f}, with radii={radii}."
    )
    assert result.robust_margin >= -1e-12, (
        "INV-FE-ROBUST VIOLATED: robust_margin must be non-negative; "
        f"observed margin={result.robust_margin:.6e}, expected >=0, with radii={radii}."
    )


def test_zero_ambiguity_equals_nominal() -> None:
    """INV-FE-ROBUST: r_m=0 ∀ m ⟹ F_robust == F_nominal exactly."""
    model = DRFreeEnergyModel()
    metrics = _nominal_metrics()
    ambiguity = AmbiguitySet(radii={name: 0.0 for name in model.known_metrics})
    result = model.evaluate_robust(metrics, ambiguity)
    assert result.robust_free_energy == pytest.approx(result.nominal_free_energy, abs=1e-12), (
        "INV-FE-ROBUST VIOLATED: zero ambiguity must equal nominal; "
        f"observed robust={result.robust_free_energy:.12f}, "
        f"nominal={result.nominal_free_energy:.12f}, expected equality, "
        "with all radii=0."
    )


def test_monotone_in_radius() -> None:
    """INV-FE-ROBUST: increasing any radius cannot decrease F_robust."""
    model = DRFreeEnergyModel()
    metrics = _nominal_metrics()
    base_radii = {name: 0.05 for name in model.known_metrics}
    failures: list[str] = []
    for delta in (0.0, 0.1, 0.5, 1.0, 5.0):
        radii = {name: 0.05 + delta for name in model.known_metrics}
        result = model.evaluate_robust(metrics, AmbiguitySet(radii=radii))
        prev = model.evaluate_robust(metrics, AmbiguitySet(radii=base_radii))
        if result.robust_free_energy + 1e-12 < prev.robust_free_energy:
            failures.append(
                f"delta={delta} F_new={result.robust_free_energy:.6f} "
                f"< F_prev={prev.robust_free_energy:.6f}"
            )
    assert not failures, (
        "INV-FE-ROBUST VIOLATED: F_robust must be monotone non-decreasing in radius; "
        f"observed violations={failures}, expected none, with delta∈{{0,0.1,0.5,1,5}}."
    )


def test_unknown_metric_rejected() -> None:
    """INV-FE-ROBUST: unknown metric names are rejected fail-closed."""
    model = DRFreeEnergyModel()
    metrics = _nominal_metrics()
    with pytest.raises(ValueError, match="Unknown ambiguity metrics"):
        model.evaluate_robust(metrics, AmbiguitySet(radii={"bogus_metric": 0.1}))


def test_negative_radius_rejected() -> None:
    """INV-FE-ROBUST: negative radii are rejected fail-closed."""
    with pytest.raises(ValueError, match="Negative radius"):
        AmbiguitySet(radii={"latency_p95": -0.01})


def test_adversarial_metrics_are_finite() -> None:
    """INV-FE-ROBUST: adversarial metrics remain finite for moderate radii."""
    model = DRFreeEnergyModel()
    metrics = _nominal_metrics()
    ambiguity = AmbiguitySet(radii={name: 1.0 for name in model.known_metrics})
    adv = model.adversarial_metrics(metrics, ambiguity)
    payload = adv.as_dict()
    failures: list[str] = []
    for name, value in payload.items():
        if not (value == value) or value == float("inf"):
            failures.append(f"{name}={value}")
    assert not failures, (
        "INV-FE-ROBUST VIOLATED: adversarial_metrics must be finite; "
        f"observed non-finite={failures}, expected none, with radius=1.0 ∀ m."
    )


def test_robust_state_warning_and_dormant_thresholds() -> None:
    """INV-FE-ROBUST: state classifier respects warning/crisis thresholds."""
    model = DRFreeEnergyModel()
    metrics = _nominal_metrics()
    ambiguity = AmbiguitySet(radii={name: 0.0 for name in model.known_metrics})
    result = model.evaluate_robust(metrics, ambiguity)
    F = result.robust_free_energy

    state_normal = robust_energy_state(result, warning_threshold=F + 1.0, crisis_threshold=F + 2.0)
    state_warning = robust_energy_state(
        result, warning_threshold=F - 0.001, crisis_threshold=F + 1.0
    )
    state_dormant = robust_energy_state(
        result, warning_threshold=F - 1.0, crisis_threshold=F - 0.001
    )

    assert state_normal == "NORMAL", (
        "INV-FE-ROBUST VIOLATED: classifier returned wrong state; "
        f"observed='{state_normal}', expected='NORMAL', with F={F}, "
        "warn=F+1, crisis=F+2."
    )
    assert state_warning == "WARNING", (
        "INV-FE-ROBUST VIOLATED: classifier returned wrong state; "
        f"observed='{state_warning}', expected='WARNING', with F={F}, "
        "warn=F-0.001, crisis=F+1."
    )
    assert state_dormant == "DORMANT", (
        "INV-FE-ROBUST VIOLATED: classifier returned wrong state; "
        f"observed='{state_dormant}', expected='DORMANT', with F={F}, "
        "warn=F-1, crisis=F-0.001."
    )


def test_nominal_energy_model_unchanged() -> None:
    """INV-FE-ROBUST: DR-FREE never mutates the base EnergyModel state.

    We capture the model's nominal evaluation before and after a DR-FREE
    call and assert pointwise equality.
    """
    base = EnergyModel()
    metrics = _nominal_metrics()
    f_before, internal_before, entropy_before, penalties_before = base.free_energy(metrics)

    wrapper = DRFreeEnergyModel(base)
    wrapper.evaluate_robust(
        metrics,
        AmbiguitySet(radii={name: 0.5 for name in base.metrics}),
    )

    f_after, internal_after, entropy_after, penalties_after = base.free_energy(metrics)
    failures: list[str] = []
    if f_before != f_after:
        failures.append(f"free_energy {f_before} != {f_after}")
    if internal_before != internal_after:
        failures.append(f"internal {internal_before} != {internal_after}")
    if entropy_before != entropy_after:
        failures.append(f"entropy {entropy_before} != {entropy_after}")
    if dict(penalties_before) != dict(penalties_after):
        failures.append("penalties differ")
    assert not failures, (
        "INV-FE-ROBUST VIOLATED: base model state mutated by DR-FREE; "
        f"observed differences={failures}, expected pure composition, "
        "with nominal metrics."
    )


def test_tla_spec_lint_documents_required_safety_properties() -> None:
    """The TLA spec advertises all five required safety properties.

    TLC may not be installed in CI; in that case we still want a textual
    audit trail proving that the spec lists the properties this Python
    module implements.
    """
    spec_path = Path(__file__).resolve().parents[2] / "formal" / "tla" / "RobustFreeEnergyGate.tla"
    assert spec_path.exists(), f"TLA spec missing at {spec_path}"
    text = spec_path.read_text(encoding="utf-8")
    required = [
        "TypeOK",
        "NominalBounded",
        "RobustDominatesNominal",
        "ZeroAmbiguityEqualsNominal",
        "FailClosedOnMalformedAmbiguity",
    ]
    missing = [name for name in required if not re.search(rf"\b{name}\b", text)]
    assert not missing, (
        "INV-FE-ROBUST VIOLATED: TLA spec is missing required safety properties; "
        f"observed missing={missing}, expected all of {required} present in {spec_path.name}."
    )


def test_dr_free_result_dataclass_invariant() -> None:
    """DRFreeResult enforces robust >= nominal at construction time."""
    metrics = _nominal_metrics()
    with pytest.raises(ValueError, match="INV-FE-ROBUST"):
        DRFreeResult(
            nominal_free_energy=2.0,
            robust_free_energy=1.0,
            internal_energy=1.0,
            entropy=0.5,
            adversarial_metrics=metrics,
            ambiguity_set=AmbiguitySet(radii={}),
            robust_margin=-1.0,
        )
