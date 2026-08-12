# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Arrow of time in the presence of an internal observer (P1).

INV-ARROW-OF-TIME (P0, monotonic):
    For any observer-coupled closed system, the cumulative net entropy
    production over any non-empty contiguous time window is non-negative,
    where net entropy production = system entropy change + the Landauer
    floor cost of any information the observer has acquired:

        Σ_net = ΔS_system + (ΔI_observer · ln 2)   nats

    Equivalently in bits:

        Σ_net_bits = ΔS_system_bits + ΔI_observer_bits

    Σ_net >= 0 over any window. Local violations (e.g. Maxwell-demon
    style apparent reductions of S_system) must be paid for by the
    observer's information gain.

Provenance: ANCHORED.
    - Landauer 1961 (Phys. Rev. D-style minimum entropy cost of bit erasure)
    - Bennett 1982 (resolution of Maxwell demon paradox via the
      thermodynamic cost of information storage / erasure)
    - Penrose 1989 (cosmological-vs-thermodynamic arrow distinction
      contextualizing the observer-internal arrow)

This module operationalizes the well-established second law as it
applies to internal-observer ledgers. It is not a derivation of the
arrow of time from first principles; it is a witness that any
proposed reduction of system entropy must be matched by observer
information cost.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "ArrowOfTimeWitness",
    "ObserverEntropyLedger",
    "PROVENANCE_TIER",
    "assess_arrow_of_time",
    "cumulative_arrow_of_time",
    "landauer_floor_cost_bits",
    "net_entropy_production_bits",
]

# Discrete provenance tier. ANCHORED = derivable from peer-reviewed
# established physics; EXTRAPOLATED = research direction with at least
# one anchor; SPECULATIVE = schema only, no specific cited model. The
# tier is enforced by validate_tests.py: SPECULATIVE invariants cannot
# carry P0/P1 priority. No float "truth-coherence" — that introduced
# fake precision; tier is intentionally discrete.
PROVENANCE_TIER: Literal["ANCHORED", "EXTRAPOLATED", "SPECULATIVE"] = "ANCHORED"


@dataclass(frozen=True, slots=True)
class ObserverEntropyLedger:
    """One bookkeeping entry for an observer-coupled closed window.

    Both fields are in bits. system_entropy_change_bits may be negative
    (apparent local entropy reduction). observer_information_gain_bits
    must be non-negative (information cannot be unlearned without
    additional cost, which would form a separate ledger entry).
    """

    system_entropy_change_bits: float
    observer_information_gain_bits: float


@dataclass(frozen=True, slots=True)
class ArrowOfTimeWitness:
    """Diagnostic record from `assess_arrow_of_time`.

    Carries the input ledger plus the derived Landauer floor cost,
    the net entropy production, and a boolean witness of consistency
    with INV-ARROW-OF-TIME. The witness does not raise; callers
    decide whether to fail-closed on a False result.
    """

    ledger: ObserverEntropyLedger
    landauer_floor_cost_bits: float
    net_entropy_production_bits: float
    is_arrow_consistent: bool
    reason: str | None


def _check_finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(
            f"INV-HPC2 VIOLATED: {name} must be finite, got {value!r}. "
            "Finite inputs → finite outputs is a P0 contract; no silent repair."
        )


def landauer_floor_cost_bits(information_gain_bits: float) -> float:
    """Landauer floor cost in bits for storing or erasing the given gain.

    The floor cost in bits is numerically equal to the information gain
    in bits — multiplying by ln 2 lifts to nats, by k_B·T·ln 2 lifts to
    joules. Here we stay in bit-space, which is the proxy currency of
    the rest of GeoSync's thermodynamic_budget module.

    Negative information gain is a contract violation: information
    cannot be "ungained" within a single ledger entry. Such cases must
    be modeled as a separate erasure ledger.
    """
    _check_finite(information_gain_bits, "information_gain_bits")
    if information_gain_bits < 0.0:
        raise ValueError(
            "information_gain_bits must be non-negative; observer "
            "information loss must be modeled as a separate erasure "
            f"ledger entry, got {information_gain_bits}"
        )
    return information_gain_bits


def net_entropy_production_bits(ledger: ObserverEntropyLedger) -> float:
    """Σ_net (bits) = ΔS_system + Landauer floor cost of ΔI_observer."""
    _check_finite(ledger.system_entropy_change_bits, "system_entropy_change_bits")
    floor = landauer_floor_cost_bits(ledger.observer_information_gain_bits)
    net = ledger.system_entropy_change_bits + floor
    _check_finite(net, "net_entropy_production_bits")
    return net


def assess_arrow_of_time(ledger: ObserverEntropyLedger) -> ArrowOfTimeWitness:
    """Return a witness for INV-ARROW-OF-TIME on a single ledger entry.

    Consistent iff Σ_net >= 0. Non-raising; caller can fail-closed
    on `is_arrow_consistent is False`.
    """
    floor = landauer_floor_cost_bits(ledger.observer_information_gain_bits)
    net = net_entropy_production_bits(ledger)
    consistent = net >= 0.0
    reason: str | None
    if consistent:
        reason = None
    else:
        reason = (
            "INV-ARROW-OF-TIME: Σ_net < 0; observer information gain "
            f"({ledger.observer_information_gain_bits} bits) is insufficient to "
            f"offset system entropy decrease ({ledger.system_entropy_change_bits} bits)"
        )
    return ArrowOfTimeWitness(
        ledger=ledger,
        landauer_floor_cost_bits=floor,
        net_entropy_production_bits=net,
        is_arrow_consistent=consistent,
        reason=reason,
    )


def cumulative_arrow_of_time(ledgers: Iterable[ObserverEntropyLedger]) -> float:
    """Sum of net entropy production over a sequence of ledger entries.

    Must be >= 0 over any non-empty contiguous window per INV-ARROW-OF-TIME.
    Iterates the input once; suitable for streaming ledgers.
    """
    total = 0.0
    seen = False
    for entry in ledgers:
        seen = True
        total += net_entropy_production_bits(entry)
    if not seen:
        raise ValueError("cumulative_arrow_of_time requires a non-empty ledger window")
    _check_finite(total, "cumulative_arrow_of_time")
    return total
