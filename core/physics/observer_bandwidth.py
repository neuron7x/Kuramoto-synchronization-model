# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Observer bandwidth bound on decoherence rate (P2).

INV-OBSERVER-BANDWIDTH (P2, conditional, SPECULATIVE):
    For any observer-system pair under a Zurek-style decoherence
    coupling, the effective decoherence rate Γ of the system from the
    observer's perspective is upper-bounded by the observer's
    information-acquisition rate (bandwidth) Σ̇_observer:

        Γ ≤ Σ̇_observer

    Equivalently: an observer cannot resolve, and therefore cannot
    decohere from its own perspective, faster than its finite
    bit-acquisition rate allows.

Provenance: SPECULATIVE.
    - Zurek (2003): Decoherence, einselection, and the quantum origins
      of the classical. Rev. Mod. Phys. 75, 715.
      (adjacent context: anchors the decoherence framework, but does
      not derive an observer-bandwidth ceiling on Γ.)
    - Lieb-Robinson (1972): The finite group velocity of quantum spin
      systems. Comm. Math. Phys. 28, 251.
      (adjacent context: bounds info-propagation speed in lattice
      systems, not the bandwidth-observer-decoherence claim.)

Schema-only honesty: the unit equivalence "1 bit/s ↔ 1 Hz of
resolvable events" is an ansatz that makes the inequality
dimensionally admissible by convention, not by physical first
principles. Lieb-Robinson 1972 bounds info-propagation in lattice
systems — adjacent context, not direct derivation of the
bandwidth-observer-decoherence claim. The two cited references jointly
provide adjacent support; they do not derive Γ ≤ Σ̇. Tier therefore
honestly downgraded EXTRAPOLATED → SPECULATIVE; per validator
check 5, SPECULATIVE caps priority at P2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "BandwidthWitness",
    "ObserverBandwidth",
    "PROVENANCE_TIER",
    "SystemDecoherence",
    "assess_bandwidth_bound",
    "decoherence_rate_hz",
    "observer_bandwidth_hz",
]

# Discrete provenance tier; see arrow_of_time.py for definition.
PROVENANCE_TIER: Literal["ANCHORED", "EXTRAPOLATED", "SPECULATIVE"] = "SPECULATIVE"


@dataclass(frozen=True, slots=True)
class SystemDecoherence:
    """Effective decoherence rate of a system under an observer coupling.

    rate_hz: Γ in Hz (1/s). Must be finite and non-negative; Γ = 0 means
    the system is not decohering (perfect isolation).
    """

    rate_hz: float


@dataclass(frozen=True, slots=True)
class ObserverBandwidth:
    """Information-acquisition rate of an observer.

    bits_per_second: Σ̇ in bit/s. Must be finite and non-negative.
    A purely passive observer (Σ̇ = 0) cannot decohere any system.
    """

    bits_per_second: float


@dataclass(frozen=True, slots=True)
class BandwidthWitness:
    """Diagnostic for INV-OBSERVER-BANDWIDTH.

    Carries the inputs, the boundary slack (Σ̇ - Γ), the
    bound-consistency boolean, and a reason on violation.
    """

    decoherence: SystemDecoherence
    bandwidth: ObserverBandwidth
    slack_hz: float
    is_bound_consistent: bool
    reason: str | None


def _check_finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(
            f"INV-HPC2 VIOLATED: {name} must be finite, got {value!r}. "
            "Finite inputs → finite outputs is a P0 contract; no silent repair."
        )


def _check_non_negative(value: float, name: str) -> None:
    if value < 0.0:
        raise ValueError(
            f"{name} must be non-negative for a bandwidth/decoherence rate, got {value}"
        )


def decoherence_rate_hz(rate_hz: float) -> SystemDecoherence:
    """Construct a validated SystemDecoherence from a Hz scalar."""
    _check_finite(rate_hz, "decoherence_rate_hz")
    _check_non_negative(rate_hz, "decoherence_rate_hz")
    return SystemDecoherence(rate_hz=rate_hz)


def observer_bandwidth_hz(bits_per_second: float) -> ObserverBandwidth:
    """Construct a validated ObserverBandwidth from a bit/s scalar."""
    _check_finite(bits_per_second, "observer_bandwidth_bits_per_second")
    _check_non_negative(bits_per_second, "observer_bandwidth_bits_per_second")
    return ObserverBandwidth(bits_per_second=bits_per_second)


def assess_bandwidth_bound(
    decoherence: SystemDecoherence,
    bandwidth: ObserverBandwidth,
) -> BandwidthWitness:
    """Return a witness for INV-OBSERVER-BANDWIDTH on one observer-system pair.

    Treats 1 bit/s of observer bandwidth as 1 Hz of resolvable
    decoherence-event rate (information-rate equivalence). A coupling
    where Γ > Σ̇ violates the bound: the observer cannot resolve more
    decoherence events per second than its bit-acquisition rate.

    Non-raising; caller fail-closes on `is_bound_consistent is False`.
    """
    bound_hz = bandwidth.bits_per_second  # 1 bit/s = 1 Hz of resolvable events
    slack = bound_hz - decoherence.rate_hz
    consistent = slack >= 0.0
    reason: str | None
    if consistent:
        reason = None
    else:
        reason = (
            "INV-OBSERVER-BANDWIDTH: Γ > Σ̇; system decoherence rate "
            f"({decoherence.rate_hz} Hz) exceeds observer bandwidth "
            f"({bandwidth.bits_per_second} bit/s); the observer cannot "
            "resolve faster than it acquires bits."
        )
    return BandwidthWitness(
        decoherence=decoherence,
        bandwidth=bandwidth,
        slack_hz=slack,
        is_bound_consistent=consistent,
        reason=reason,
    )
