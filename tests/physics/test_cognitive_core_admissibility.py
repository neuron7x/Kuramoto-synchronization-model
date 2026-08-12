# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for cognitive_core_admissibility — the system value function over invariants.

The cognitive core (``core.physics.cognitive_core.CognitiveCore``) is the single
deterministic gate that routes a live snapshot through every applicable physical
invariant and returns one fail-closed admissibility verdict:

    V(snapshot) = GO  iff  the snapshot lies inside the invariant manifold.

Positive witness: a nominal in-manifold snapshot is admissible (GO), and EVERY
gate is load-bearing — a snapshot that violates exactly one invariant is rejected
for THAT invariant alone (no dead or redundant gate). Negative control: the core
never vacuously approves — an empty snapshot and a non-finite (fail-closed) field
both yield NO_GO, and a planted single violation names its binding constraint.

This is the above-academic guarantee for the core as a control object: it is
total (covers the live spine), fail-closed (no silent pass), and minimal (every
gate necessary).
"""
from __future__ import annotations

import math

from core.physics.cognitive_core import (
    GATED_FIELDS,
    CognitiveCore,
    Decision,
    Status,
)

# A nominal snapshot strictly inside the invariant manifold (every gate active).
_NOMINAL: dict[str, object] = {
    "order_parameter_R": 0.5,  # INV-K1 in [0,1]
    "z_abs": 0.4,  # INV-OA1 |z| <= 1
    "ollivier_kappa": 0.2,  # INV-RC1 <= 1
    "gamma": 1.5,  # INV-DRO2 >= 0
    "serotonin_level": 0.3,  # INV-5HT2 in [0,1]
    "gaba_gate": 0.8,  # INV-GABA1 in [0,1]
    "dopamine_signal": 0.5,  # INV-DA8 |.| <= 1
    "kelly_fraction": 0.25,  # INV-KELLY2 in [0,1]
    "free_energy_components": (1.0, 0.5, 0.2),  # INV-FE2 each >= 0
}

# One out-of-manifold value per invariant, keyed by the gated field. Each violates
# exactly the gate on that field and nothing else.
_SINGLE_VIOLATIONS: dict[str, tuple[str, object]] = {
    "order_parameter_R": ("INV-K1", 1.5),
    "z_abs": ("INV-OA1", 1.2),
    "ollivier_kappa": ("INV-RC1", 1.5),
    "gamma": ("INV-DRO2", -0.1),
    "serotonin_level": ("INV-5HT2", 1.3),
    "gaba_gate": ("INV-GABA1", -0.1),
    "dopamine_signal": ("INV-DA8", 1.5),
    "kelly_fraction": ("INV-KELLY2", 1.5),
    "free_energy_components": ("INV-FE2", (-1.0, 0.5, 0.2)),
}


def test_nominal_snapshot_is_admissible_and_every_gate_is_load_bearing() -> None:
    """Positive witness: nominal -> GO, and each invariant gate is necessary (minimal core).

    The nominal snapshot lies inside the manifold so the value function returns
    GO with no violations. Then, for each gated field, a snapshot that violates
    ONLY that invariant must be rejected for THAT invariant alone — proving the
    gate is load-bearing (no dead weight) and uniquely responsible for its bound.
    """
    core = CognitiveCore()

    nominal = core.admissibility(_NOMINAL)
    assert nominal.decision is Decision.GO and nominal.status is Status.ADMISSIBLE, (
        f"COGNITIVE-CORE ADMISSIBILITY VIOLATED: a nominal in-manifold snapshot was "
        f"not admissible (decision={nominal.decision}, status={nominal.status}, "
        f"violations={nominal.violations}). The value function must return GO inside "
        f"the invariant manifold. snapshot fields={sorted(_NOMINAL)}"
    )
    assert len(nominal.gates) == len(_NOMINAL), (
        f"COGNITIVE-CORE COVERAGE VIOLATED: nominal activated {len(nominal.gates)} "
        f"gates but the snapshot carries {len(_NOMINAL)} gated fields; every present "
        f"field must be gated (totality). gated_fields={sorted(GATED_FIELDS)}"
    )

    # Every gate is load-bearing: violate exactly one invariant, expect exactly that one.
    assert set(_SINGLE_VIOLATIONS) == set(_NOMINAL), (
        "test setup invariant: a single-violation case must exist for every gated field."
    )
    for field_name, (invariant, bad_value) in _SINGLE_VIOLATIONS.items():
        snap = dict(_NOMINAL)
        snap[field_name] = bad_value
        verdict = core.admissibility(snap)
        assert verdict.decision is Decision.NO_GO, (
            f"COGNITIVE-CORE ADMISSIBILITY VIOLATED: snapshot violating {invariant} "
            f"({field_name}={bad_value!r}) was admitted (decision={verdict.decision}). "
            f"A reality-divergence must fire the gate, not pass silently."
        )
        assert verdict.violations == (invariant,), (
            f"COGNITIVE-CORE MINIMALITY VIOLATED: violating only {invariant} produced "
            f"violations={verdict.violations}; expected exactly ({invariant!r},). Either "
            f"the gate is not load-bearing or another gate fired spuriously."
        )
        assert verdict.binding_constraint == invariant, (
            f"COGNITIVE-CORE ROUTING VIOLATED: binding_constraint="
            f"{verdict.binding_constraint!r}, expected {invariant!r} for "
            f"{field_name}={bad_value!r}."
        )


def test_core_never_vacuously_approves_and_fails_closed() -> None:
    """Negative control: empty / non-finite / planted-violation snapshots all yield NO_GO.

    The core must never return GO without evidence. An empty snapshot activates no
    gate -> INSUFFICIENT -> NO_GO (no vacuous approval). A non-finite field is
    fail-closed -> NO_GO. A single planted violation -> NO_GO with the binding
    constraint named. If any of these were admitted, the value function would
    leak controllability.
    """
    core = CognitiveCore()

    empty = core.admissibility({})
    assert empty.decision is Decision.NO_GO and empty.status is Status.INSUFFICIENT, (
        f"COGNITIVE-CORE VACUITY VIOLATED: an empty snapshot was not refused "
        f"(decision={empty.decision}, status={empty.status}). No applicable invariant "
        f"must never be approved — the core cannot vacuously pass."
    )

    for bad in (math.nan, math.inf, -math.inf, "not-a-number", None):
        snap = dict(_NOMINAL)
        snap["order_parameter_R"] = bad
        verdict = core.admissibility(snap)
        assert verdict.decision is Decision.NO_GO and "INV-K1" in verdict.violations, (
            f"COGNITIVE-CORE FAIL-CLOSED VIOLATED: non-finite order_parameter_R="
            f"{bad!r} was not rejected (decision={verdict.decision}, "
            f"violations={verdict.violations}). A non-finite field must fail closed."
        )

    # A single planted violation is rejected with its constraint named.
    snap = dict(_NOMINAL)
    snap["ollivier_kappa"] = 2.0  # INV-RC1 upper bound is 1
    verdict = core.admissibility(snap)
    assert (
        verdict.decision is Decision.NO_GO
        and verdict.binding_constraint == "INV-RC1"
    ), (
        f"COGNITIVE-CORE ROUTING VIOLATED: planted INV-RC1 violation (ollivier_kappa=2.0) "
        f"gave decision={verdict.decision}, binding_constraint={verdict.binding_constraint}."
    )

    # INV-FE2 structural fail-closed: the composite gate must reject a non-triple,
    # a wrong-length triple, and a triple with ANY non-finite component (each of
    # U, T, S independently). These exercise both disjunctive guards in the gate.
    fe2_malformed: list[object] = [
        3.0,  # not a sequence at all
        (1.0, 0.5),  # wrong length (2 != 3)
        (1.0, 0.5, 0.2, 0.1),  # wrong length (4 != 3)
        (math.nan, 0.5, 0.2),  # U non-finite
        (1.0, math.inf, 0.2),  # T non-finite
        (1.0, 0.5, "x"),  # S non-scalar
    ]
    for bad_components in fe2_malformed:
        snap = dict(_NOMINAL)
        snap["free_energy_components"] = bad_components
        verdict = core.admissibility(snap)
        assert verdict.decision is Decision.NO_GO and "INV-FE2" in verdict.violations, (
            f"COGNITIVE-CORE FAIL-CLOSED VIOLATED: malformed free_energy_components="
            f"{bad_components!r} was not rejected (decision={verdict.decision}, "
            f"violations={verdict.violations}). A non-triple, wrong-length, or "
            f"non-finite component must fail closed under INV-FE2."
        )
