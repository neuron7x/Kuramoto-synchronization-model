# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Simulation hypothesis as a physical, experimentally testable problem.

This module does NOT compute P(we are in a simulation). That framing is
philosophical and unfalsifiable. Instead it enumerates a set of concrete
physical signatures whose presence or absence would either:

  (a) constrain the hardware class on which a simulation could run, or
  (b) rule out a finite-resolution simulation at currently observable scales.

INV-SIMULATION-FALSIFICATION (P1, statistical):
    The simulation hypothesis is operationalized as a registry of
    enumerable signatures, each with a published prediction, an
    explicit detectability threshold, and a current observation
    status. The hypothesis is *falsifiable* iff at least one such
    signature has a threshold within reach of current or near-future
    instruments AND a documented null observation up to that
    threshold.

References:

- Bekenstein, J. D. (1981). Universal upper bound on the entropy-to-energy
  ratio for bounded systems. Phys. Rev. D 23, 287.
- 't Hooft, G. (1993). Dimensional reduction in quantum gravity.
  arXiv:gr-qc/9310026.
- Susskind, L. (1995). The world as a hologram. J. Math. Phys. 36, 6377.
- Beane, S. R., Davoudi, Z., Savage, M. J. (2014). Constraints on the
  universe as a numerical simulation. Eur. Phys. J. A 50, 148.
  arXiv:1210.1847.

This module is opt-in research infrastructure. It makes no claim about
whether the universe is simulated; it only mechanizes the logical
contract that *any* such claim must reduce to enumerable signatures
with measurable thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal

__all__ = [
    "CANONICAL_SIGNATURES",
    "FalsificationLadder",
    "FalsificationSignature",
    "ObservationStatus",
    "ReasoningTier",
    "SignatureEvaluation",
    "build_canonical_ladder",
    "evaluate_signature_observation",
]


ReasoningTier = Literal["DERIVED", "ANALOGICAL"]
"""Strength of the link between an observable and the simulation hypothesis.

DERIVED:
    The signature's prediction follows from a specific peer-reviewed
    derivation that explicitly treats the universe-as-simulation
    framing (e.g. Beane/Davoudi/Savage 2014 for cubic-lattice imprints
    on cosmic rays and on photon dispersion; 't Hooft 1993 / Susskind
    1995 for holography → Planck-scale resolution).

ANALOGICAL:
    The signature is plausibly *interpretable* as a simulation
    fingerprint, but no published paper derives the threshold from a
    concrete substrate model. The link is by analogy and the entry
    exists to keep the ladder honest about which signatures are
    genuinely derived versus interpretive.

This field exists to surface, at the contract layer, the asymmetric
evidential weight of canonical signatures — a uniform contract weight
across all six entries would silently inflate ANALOGICAL signatures to
the same status as DERIVED ones.
"""


class ObservationStatus(str, Enum):
    """Discrete states of a falsification signature against observation.

    NOT_OBSERVED: signature has been searched for at least to its
        detectability threshold and no positive detection exists.
        This *does not* refute the simulation hypothesis; it bounds
        a hardware class above the threshold.
    OPEN: the signature is below current instrument reach. Neither
        confirmed nor refuted; included to make the ladder honest
        about its blind spots.
    RULED_OUT: a positive detection at or above threshold has been
        reported and independently corroborated. Continuous-physics
        models that forbid the signature are then constrained.
    """

    NOT_OBSERVED = "NOT_OBSERVED"
    OPEN = "OPEN"
    RULED_OUT = "RULED_OUT"


@dataclass(frozen=True, slots=True)
class FalsificationSignature:
    """One enumerable signature linking the simulation hypothesis to a
    measurable physical observable.

    Each signature is a hard contract: a violation has units, a
    threshold, and a published reference. Probability is not a field;
    only status against observation.
    """

    signature_id: str
    name: str
    prediction_under_simulation: str
    detectability_threshold: float
    detectability_units: str
    current_observation_status: ObservationStatus
    current_observation_value: float | None
    reference: str
    reasoning_tier: ReasoningTier


@dataclass(frozen=True, slots=True)
class FalsificationLadder:
    """An immutable enumeration of falsification signatures.

    The ladder is *not* an inference engine. It is a registry whose
    purpose is to make implicit assumptions about the simulation
    hypothesis explicit and testable. A ladder is honest if every
    signature has either a published null bound (NOT_OBSERVED) or a
    documented inaccessibility (OPEN).
    """

    signatures: tuple[FalsificationSignature, ...]

    def status_summary(self) -> dict[str, int]:
        """Return counts of signatures by ObservationStatus.

        Useful for triage: a ladder dominated by OPEN entries is not
        yet a productive falsification surface.
        """
        counts: dict[str, int] = {s.value: 0 for s in ObservationStatus}
        for sig in self.signatures:
            counts[sig.current_observation_status.value] += 1
        return counts

    def signature_by_id(self, signature_id: str) -> FalsificationSignature:
        """O(N) lookup. Raises KeyError if no such signature."""
        for sig in self.signatures:
            if sig.signature_id == signature_id:
                return sig
        raise KeyError(f"unknown signature_id: {signature_id!r}")

    def signatures_by_tier(self) -> dict[str, tuple[FalsificationSignature, ...]]:
        """Bucket the ladder by `reasoning_tier`.

        Returns a dict with exactly two keys, "DERIVED" and "ANALOGICAL",
        each mapped to the tuple of signatures carrying that tier
        (preserving registry order). Both keys are always present even
        if a bucket is empty, so callers can iterate without KeyError.
        """
        derived: list[FalsificationSignature] = []
        analogical: list[FalsificationSignature] = []
        for sig in self.signatures:
            if sig.reasoning_tier == "DERIVED":
                derived.append(sig)
            else:
                analogical.append(sig)
        return {
            "DERIVED": tuple(derived),
            "ANALOGICAL": tuple(analogical),
        }

    def hardware_class_ruled_out(self, signature_id: str, observed_value: float) -> bool:
        """Return True iff `observed_value` exceeds the threshold of the
        named signature, i.e. the simulation hardware class predicting
        signal below threshold is ruled out by the observation.

        Raises:
            KeyError: signature_id not in ladder.
            ValueError: observed_value is non-finite.
        """
        if not _is_finite(observed_value):
            raise ValueError(f"observed_value must be finite, got {observed_value!r}")
        sig = self.signature_by_id(signature_id)
        return observed_value > sig.detectability_threshold


def _is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


# ---------------------------------------------------------------------------
# Canonical ladder — six pre-registered signatures.
#
# Each entry cites a peer-reviewed source. The thresholds are taken
# from the published bounds; the status reflects the latest published
# measurement at the time of registration. This registry is intended
# to be amended only by appending new signatures or by updating
# `current_observation_status` when a new measurement is published —
# never by silently editing thresholds.
# ---------------------------------------------------------------------------


_GZK_CUTOFF_EV: Final[float] = 5.0e19  # Greisen-Zatsepin-Kuzmin cutoff
_PLANCK_LENGTH_M: Final[float] = 1.616_255e-35


CANONICAL_SIGNATURES: Final[tuple[FalsificationSignature, ...]] = (
    FalsificationSignature(
        signature_id="SIM-HOLOGRAPHIC-SATURATION",
        name="Holographic information-bound saturation",
        prediction_under_simulation=(
            "If the substrate is a finite-resolution simulation, no "
            "physical region should store I > 2π·E·R/(ℏ·c·ln 2) bits. "
            "Saturation has only been observed in black-hole entropy "
            "calculations; any non-BH system at saturation would be a "
            "direct measurement of the substrate's resolution limit."
        ),
        detectability_threshold=1.0,
        detectability_units="ratio I_observed / I_max(Bekenstein)",
        current_observation_status=ObservationStatus.NOT_OBSERVED,
        current_observation_value=None,
        reference=(
            "Bekenstein 1981 (Phys. Rev. D 23, 287); "
            "'t Hooft 1993 (gr-qc/9310026); "
            "Susskind 1995 (J. Math. Phys. 36, 6377)."
        ),
        reasoning_tier="ANALOGICAL",
    ),
    FalsificationSignature(
        signature_id="SIM-LATTICE-UHECR",
        name="Cubic-lattice anisotropy in ultra-high-energy cosmic rays",
        prediction_under_simulation=(
            "A simulation on a cubic spacetime lattice would imprint "
            "preferred-direction structure on cosmic rays above the "
            "GZK cutoff (~5×10^19 eV). Continuous physics predicts "
            "isotropy at the percent level after deflection."
        ),
        detectability_threshold=_GZK_CUTOFF_EV,
        detectability_units="eV (cosmic-ray energy threshold)",
        current_observation_status=ObservationStatus.NOT_OBSERVED,
        current_observation_value=None,
        reference=(
            "Beane, Davoudi, Savage (2014). "
            "Constraints on the universe as a numerical simulation. "
            "Eur. Phys. J. A 50, 148. arXiv:1210.1847."
        ),
        reasoning_tier="DERIVED",
    ),
    FalsificationSignature(
        signature_id="SIM-PLANCK-DISCRETIZATION",
        name="Direct probe of spacetime discretization at Planck scale",
        prediction_under_simulation=(
            "If the simulation grid is Planck-scale, energies above "
            "~10^28 eV should reveal pixelation or grid axes. Current "
            "instruments are 14 orders of magnitude below this scale; "
            "the signature is enumerated to keep the ladder honest "
            "about its inaccessibility."
        ),
        detectability_threshold=_PLANCK_LENGTH_M,
        detectability_units="m (probed length scale)",
        current_observation_status=ObservationStatus.OPEN,
        current_observation_value=None,
        reference=("'t Hooft 1993 (gr-qc/9310026); Susskind 1995 (J. Math. Phys. 36, 6377)."),
        reasoning_tier="DERIVED",
    ),
    FalsificationSignature(
        signature_id="SIM-LATTICE-DISPERSION",
        name="Energy-dependent photon dispersion from cosmological sources",
        prediction_under_simulation=(
            "A discretized substrate would induce energy-dependent "
            "differences in photon arrival times from gamma-ray bursts "
            "and other transients at MeV–GeV energies. Continuous "
            "physics predicts arrival simultaneity to first order."
        ),
        detectability_threshold=1.0,
        detectability_units="ratio Δt_observed / Δt_predicted_lattice",
        current_observation_status=ObservationStatus.NOT_OBSERVED,
        current_observation_value=None,
        reference=("Beane, Davoudi, Savage (2014), §IV. Eur. Phys. J. A 50, 148."),
        reasoning_tier="DERIVED",
    ),
    FalsificationSignature(
        signature_id="SIM-COMPUTE-COMPLEXITY-WALL",
        name="Asymptotic wall in deep quantum-circuit fidelity",
        prediction_under_simulation=(
            "A finite-hardware substrate must asymptotically degrade "
            "fidelity of large quantum circuits beyond some qubit "
            "count or depth. Continuous physics predicts no such "
            "wall — only environmental decoherence governs fidelity."
        ),
        detectability_threshold=1.0,
        detectability_units="ratio degradation_observed / decoherence_predicted",
        current_observation_status=ObservationStatus.OPEN,
        current_observation_value=None,
        reference=(
            "Bekenstein-bound holography ('t Hooft 1993; Susskind 1995) "
            "applied to quantum-information capacity."
        ),
        reasoning_tier="ANALOGICAL",
    ),
    FalsificationSignature(
        signature_id="SIM-CMB-MULTIPOLE-CUTOFF",
        name="Power-spectrum cutoff at high CMB multipole",
        prediction_under_simulation=(
            "A finite-grid simulation would impose a maximum effective "
            "multipole on the cosmic microwave background power "
            "spectrum. Continuous physics predicts smooth roll-off "
            "governed by Silk damping only."
        ),
        detectability_threshold=2500.0,
        detectability_units="multipole ℓ_max",
        current_observation_status=ObservationStatus.NOT_OBSERVED,
        current_observation_value=None,
        reference=("Beane, Davoudi, Savage (2014); context for cosmological observables."),
        reasoning_tier="DERIVED",
    ),
)


def build_canonical_ladder() -> FalsificationLadder:
    """Return the immutable canonical ladder of six pre-registered signatures.

    Calling this function multiple times returns equal-by-value ladders
    that share the same underlying CANONICAL_SIGNATURES tuple.
    """
    return FalsificationLadder(signatures=CANONICAL_SIGNATURES)


@dataclass(frozen=True, slots=True)
class SignatureEvaluation:
    """Result of evaluating one signature against one observation.

    The evaluation is a *point* result on a single (signature, observed)
    pair. It NEVER infers global probability of simulation. It NEVER
    aggregates across signatures. It NEVER produces a substrate-state
    verdict.

    Fields preserve the per-signature contract for downstream consumers
    (loggers, evidence ledgers, audits). The reasoning_tier flows
    through unchanged from the source signature so a consumer can
    weight DERIVED vs ANALOGICAL evidence honestly.
    """

    signature_id: str
    reasoning_tier: ReasoningTier
    observation_status: ObservationStatus
    detectability_threshold: float
    detectability_units: str
    observed_value: float
    hardware_class_ruled_out: bool
    reason: str | None


def evaluate_signature_observation(
    signature_id: str,
    observed_value: float,
    *,
    ladder: FalsificationLadder | None = None,
) -> SignatureEvaluation:
    """Point-evaluate one observation against one named signature.

    Returns a structured SignatureEvaluation carrying the per-signature
    threshold, the reasoning_tier (DERIVED vs ANALOGICAL), and a
    boolean for whether the observation rules out the corresponding
    hardware class. Does NOT infer simulation probability. Does NOT
    aggregate across signatures.

    Args:
        signature_id: e.g. "SIM-LATTICE-UHECR". Must exist in the
            ladder; unknown ids raise KeyError.
        observed_value: numeric measurement to compare against the
            signature's detectability_threshold. Must be finite;
            non-finite values raise ValueError.
        ladder: optional ladder to evaluate against; defaults to the
            canonical ladder. The ladder argument exists so future
            non-canonical ladders can be evaluated through the same
            point-eval surface without monkey-patching the canonical.

    Raises:
        KeyError: signature_id not in ladder.
        ValueError: observed_value is non-finite.
    """
    if not _is_finite(observed_value):
        raise ValueError(
            f"observed_value must be finite, got {observed_value!r}; "
            "point-eval refuses to produce a verdict on unphysical input."
        )
    target_ladder = ladder if ladder is not None else build_canonical_ladder()
    signature = target_ladder.signature_by_id(signature_id)
    ruled_out = observed_value > signature.detectability_threshold
    if ruled_out:
        reason: str | None = (
            f"observation {observed_value} {signature.detectability_units} "
            f"exceeds detectability threshold "
            f"{signature.detectability_threshold} {signature.detectability_units} "
            f"for {signature_id}; the simulation hardware class predicting "
            "signal below threshold is ruled out by this observation."
        )
    else:
        reason = None
    return SignatureEvaluation(
        signature_id=signature.signature_id,
        reasoning_tier=signature.reasoning_tier,
        observation_status=signature.current_observation_status,
        detectability_threshold=signature.detectability_threshold,
        detectability_units=signature.detectability_units,
        observed_value=observed_value,
        hardware_class_ruled_out=ruled_out,
        reason=reason,
    )
