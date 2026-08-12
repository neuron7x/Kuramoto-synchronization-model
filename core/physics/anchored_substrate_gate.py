# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Anchored substrate gate — composition of ANCHORED-tier invariants.

INV-ANCHORED-SUBSTRATE-GATE (P0, conditional, ANCHORED):
    A substrate is *thermodynamically admissible* iff it simultaneously
    satisfies the two ANCHORED-tier physical bounds:

        (1) INV-BEKENSTEIN-COGNITIVE — spatial/capacity:
                I_observed ≤ 2π·E·R / (ℏ·c·ln 2)   bits

        (2) INV-ARROW-OF-TIME — temporal/entropy:
                Σ_net = ΔS_system + ΔI_observer ≥ 0   bits

    Both must hold. Either failing makes the substrate inadmissible
    under the gate; the gate returns a structured witness that names
    which axis (or both) failed.

    NOTE: The gate does NOT certify "cognitive capability". Many
    non-cognitive systems (a rock, a glass of water, a planet)
    trivially satisfy both bounds. Passing the gate is a *necessary*
    condition for any cognition-relevant claim — never a sufficient
    one. Earlier wording in this module said "admissible for
    cognitive computation" and "cognitive-engineering kernel"; that
    was an inferential overclaim and has been removed in
    chore/substrate-gate-honest-naming.

Provenance: ANCHORED.
    The gate composes only the two ANCHORED invariants. Both
    ingredients trace to peer-reviewed established physics:
      - Bekenstein 1981 (Phys. Rev. D 23, 287)
      - 't Hooft 1993 (gr-qc/9310026); Susskind 1995 (J. Math. Phys.
        36, 6377)
      - Landauer 1961 (IBM J. Res. Dev. 5, 183)
      - Bennett 1982 (Int. J. Theor. Phys. 21, 905)

    EXTRAPOLATED-tier invariants (INV-OBSERVER-BANDWIDTH,
    INV-COSMOLOGICAL-COMPUTE, INV-JACOBSON-OBSERVER,
    INV-SIMULATION-FALSIFICATION) are deliberately NOT composed here.
    Mixing tiers in one gate would dilute the gate's epistemic
    standing. Future modules may compose EXTRAPOLATED axes into a
    separate `extrapolated_substrate_gate` once the EXTRAPOLATED
    contracts are themselves validated.

Operational consequence: prior to this module, the claim "substrate
holds composably" appeared in PR descriptions and docs but was not
checkable. Each invariant had its own witness function tested
independently; nothing exercised the composition. This module makes
the composition executable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from core.physics.arrow_of_time import (
    ArrowOfTimeWitness,
    ObserverEntropyLedger,
    assess_arrow_of_time,
)
from core.physics.thermodynamic_budget import bekenstein_cognitive_ceiling

__all__ = [
    "DEFAULT_GATE_POLICY",
    "AnchoredSubstrateGateWitness",
    "GatePolicy",
    "PROVENANCE_TIER",
    "SubstrateGateInputs",
    "assess_anchored_substrate_gate",
]

PROVENANCE_TIER: Literal["ANCHORED", "EXTRAPOLATED", "SPECULATIVE"] = "ANCHORED"

# Gate composition policy. ANCHORED_ONLY is the only currently-implemented
# policy: the composite verdict considers ANCHORED-tier axes (Bekenstein
# + Arrow) only. EXTRAPOLATED and SPECULATIVE axes (observer-bandwidth,
# cosmological-compute, jacobson) may produce concerns independently but
# DO NOT silently veto the composite under this policy. Future policies
# (e.g. ALL_TIERS, ANCHORED_PLUS_EXTRAPOLATED) require an explicit API
# extension — adding a new Literal value AND updating consumers — never
# a silent behavior change.
GatePolicy = Literal["ANCHORED_ONLY"]
DEFAULT_GATE_POLICY: GatePolicy = "ANCHORED_ONLY"


@dataclass(frozen=True, slots=True)
class SubstrateGateInputs:
    """Inputs required to assess the anchored substrate gate.

    Spatial/capacity axis (INV-BEKENSTEIN-COGNITIVE):
    - radius_m: bounding-sphere radius of the substrate, in metres.
    - energy_J: total energy contained in the substrate, in joules.
    - observed_information_bits: information content claimed for the
      substrate. Must be non-negative and finite. The gate compares
      this against 2π·E·R/(ℏ·c·ln 2).

    Temporal/entropy axis (INV-ARROW-OF-TIME):
    - entropy_ledger: ObserverEntropyLedger over a non-empty window.
      The gate calls `assess_arrow_of_time` on this ledger and uses
      the witness's `is_arrow_consistent` field.
    """

    radius_m: float
    energy_J: float
    observed_information_bits: float
    entropy_ledger: ObserverEntropyLedger


@dataclass(frozen=True, slots=True)
class AnchoredSubstrateGateWitness:
    """Composite witness from `assess_anchored_substrate_gate`.

    Carries the per-axis sub-witnesses plus the composite verdict.
    Non-raising; caller fail-closes on
    `is_thermodynamically_admissible is False`. The flag answers
    only "do both anchored bounds hold for this substrate?" — it
    does NOT certify cognition.
    """

    inputs: SubstrateGateInputs
    bekenstein_ceiling_bits: float
    bekenstein_axis_holds: bool
    arrow_witness: ArrowOfTimeWitness
    arrow_axis_holds: bool
    is_thermodynamically_admissible: bool
    failure_axes: tuple[str, ...]
    reason: str | None
    policy_used: GatePolicy = "ANCHORED_ONLY"


def _check_finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(
            f"INV-HPC2 VIOLATED: {name} must be finite, got {value!r}. "
            "Finite inputs → finite outputs is a P0 contract; no silent repair."
        )


def _check_non_negative(value: float, name: str) -> None:
    if value < 0.0:
        raise ValueError(f"{name} must be non-negative, got {value}")


def assess_anchored_substrate_gate(
    inputs: SubstrateGateInputs,
    *,
    policy: GatePolicy = DEFAULT_GATE_POLICY,
) -> AnchoredSubstrateGateWitness:
    """Compose INV-BEKENSTEIN-COGNITIVE and INV-ARROW-OF-TIME.

    Returns a structured witness. The gate does not raise on physical
    violations (those are the gate's job to report); it raises only on
    malformed inputs (NaN/Inf, negative information count) per
    INV-HPC2 fail-closed.

    `policy` controls which tier set the composite verdict consumes.
    Currently only "ANCHORED_ONLY" is implemented — the verdict
    considers Bekenstein + Arrow only. EXTRAPOLATED / SPECULATIVE
    axes are NOT silently consulted under this policy. Future policy
    values require an explicit Literal extension; passing an unknown
    string fails fast (Literal-typed argument rejected by static
    type checkers AND runtime via the equality check below).
    """
    if policy != "ANCHORED_ONLY":
        raise ValueError(
            f"Unsupported gate policy {policy!r}; only 'ANCHORED_ONLY' is "
            "implemented. Adding a new policy requires extending GatePolicy "
            "Literal AND updating consumers — never a silent behavior change."
        )
    _check_finite(inputs.observed_information_bits, "observed_information_bits")
    _check_non_negative(inputs.observed_information_bits, "observed_information_bits")

    # Spatial/capacity axis. The bekenstein helper validates radius_m
    # and energy_J and raises on bad input.
    ceiling = bekenstein_cognitive_ceiling(inputs.radius_m, inputs.energy_J)
    bekenstein_holds = inputs.observed_information_bits <= ceiling

    # Temporal/entropy axis.
    arrow_witness = assess_arrow_of_time(inputs.entropy_ledger)
    arrow_holds = arrow_witness.is_arrow_consistent

    failures: list[str] = []
    if not bekenstein_holds:
        failures.append("BEKENSTEIN")
    if not arrow_holds:
        failures.append("ARROW")
    failure_tuple = tuple(failures)

    admissible = bekenstein_holds and arrow_holds
    reason: str | None
    if admissible:
        reason = None
    elif len(failure_tuple) == 1 and failure_tuple[0] == "BEKENSTEIN":
        reason = (
            "INV-BEKENSTEIN-COGNITIVE violated: "
            f"observed_information_bits={inputs.observed_information_bits} > "
            f"ceiling={ceiling} bits at (R={inputs.radius_m} m, "
            f"E={inputs.energy_J} J)."
        )
    elif len(failure_tuple) == 1 and failure_tuple[0] == "ARROW":
        reason = f"INV-ARROW-OF-TIME violated: {arrow_witness.reason}"
    else:
        reason = (
            "Both anchored axes failed: "
            f"INV-BEKENSTEIN-COGNITIVE (observed={inputs.observed_information_bits} > "
            f"ceiling={ceiling}); INV-ARROW-OF-TIME ({arrow_witness.reason})."
        )

    return AnchoredSubstrateGateWitness(
        inputs=inputs,
        bekenstein_ceiling_bits=ceiling,
        bekenstein_axis_holds=bekenstein_holds,
        arrow_witness=arrow_witness,
        arrow_axis_holds=arrow_holds,
        is_thermodynamically_admissible=admissible,
        failure_axes=failure_tuple,
        reason=reason,
        policy_used=policy,
    )
