# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""DR-FREE — distributionally robust free-energy minimization.

Status
------
EXPERIMENTAL. Pure composition over :class:`tacl.EnergyModel`. The base
model is never mutated; a DR-FREE evaluation only returns adversarially
inflated metrics and the resulting robust free energy.

Background
----------
We follow the worst-case-over-ambiguity formulation introduced for
free-energy controllers in *Nature Communications* 2025
(s41467-025-67348-6). Given a per-metric **box** ambiguity set with
radius ``r_m ≥ 0``, the adversarial metric for any **penalty-increasing**
metric ``m`` is

.. math::

    m^{adv} = m \\cdot (1 + r_m).

Robust free energy is then

.. math::

    F^{robust}(\\mathbf{m}, \\mathcal{U}) = F\bigl(\\mathbf{m}^{adv}\bigr)
    \\ge F(\\mathbf{m}) = F^{nominal}.

The inequality holds because every metric in :class:`tacl.EnergyMetrics`
is a non-negative penalty whose ratio-to-threshold can only grow under
non-negative inflation, hence the internal energy can only grow and the
entropy can only shrink.

Invariants
----------
- ``F^{robust} >= F^{nominal}`` for every metric and every ``r_m >= 0``
  (``INV-FE-ROBUST``).
- Zero ambiguity (``r_m = 0`` ∀ m) ⟹ ``F^{robust} == F^{nominal}``.
- Monotone in radius: increasing any ``r_m`` cannot decrease
  ``F^{robust}``.
- Unknown metric names are rejected (fail-closed).
- Negative radii are rejected.

No-alpha disclaimer
-------------------
This module is a controller-level robustness primitive. It does not
constitute a trading signal nor a claim of out-of-sample edge.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final, Literal, Mapping

from .energy_model import EnergyMetrics, EnergyModel

__all__ = [
    "AmbiguitySet",
    "DRFreeResult",
    "DRFreeEnergyModel",
    "robust_energy_state",
]


_AmbiguityMode = Literal["box"]
_KNOWN_AMBIGUITY_MODES: Final[frozenset[str]] = frozenset({"box"})


@dataclass(frozen=True, slots=True)
class AmbiguitySet:
    """Box ambiguity set: per-metric multiplicative radius ``r_m >= 0``.

    Only metrics referenced in the underlying :class:`EnergyModel` are
    accepted; missing metrics default to radius 0 (i.e. no perturbation).
    """

    radii: Mapping[str, float]
    mode: _AmbiguityMode = "box"

    def __post_init__(self) -> None:
        if self.mode not in _KNOWN_AMBIGUITY_MODES:
            raise ValueError(
                f"Unknown ambiguity mode '{self.mode}'; "
                f"supported: {sorted(_KNOWN_AMBIGUITY_MODES)}."
            )
        for name, radius in self.radii.items():
            if not isinstance(name, str):
                raise ValueError("AmbiguitySet keys must be strings.")
            if radius < 0.0:
                raise ValueError(f"Negative radius for metric '{name}': {radius}.")


@dataclass(frozen=True, slots=True)
class DRFreeResult:
    """Bundle of nominal + robust free-energy diagnostics."""

    nominal_free_energy: float
    robust_free_energy: float
    internal_energy: float
    entropy: float
    adversarial_metrics: EnergyMetrics
    ambiguity_set: AmbiguitySet
    robust_margin: float

    def __post_init__(self) -> None:
        if not (self.robust_free_energy + 1e-12 >= self.nominal_free_energy):
            raise ValueError(
                "INV-FE-ROBUST violated: robust_free_energy must dominate nominal "
                f"(observed robust={self.robust_free_energy}, "
                f"nominal={self.nominal_free_energy})."
            )


class DRFreeEnergyModel:
    """Composition wrapper that adds DR-FREE evaluation to an EnergyModel.

    Parameters
    ----------
    base_model:
        Optional :class:`tacl.EnergyModel`. When ``None`` a default
        instance is constructed; the base model is **never mutated**.
    """

    def __init__(self, base_model: EnergyModel | None = None) -> None:
        self._base = base_model if base_model is not None else EnergyModel()

    @property
    def base_model(self) -> EnergyModel:
        return self._base

    @property
    def known_metrics(self) -> frozenset[str]:
        return frozenset(self._base.metrics)

    def adversarial_metrics(
        self,
        metrics: EnergyMetrics,
        ambiguity: AmbiguitySet,
    ) -> EnergyMetrics:
        """Return the worst-case (penalty-inflated) metrics under ``ambiguity``.

        Each known metric ``m`` is mapped to ``m * (1 + r_m)``; missing
        radii default to 0. Unknown metric names raise :class:`ValueError`.
        """
        if ambiguity.mode != "box":
            raise ValueError(f"Unsupported ambiguity mode: {ambiguity.mode}.")

        known = self.known_metrics
        unknown = set(ambiguity.radii) - known
        if unknown:
            raise ValueError(
                f"Unknown ambiguity metrics: {sorted(unknown)}; known: {sorted(known)}."
            )

        as_dict = dict(metrics.as_dict())
        for name, radius in ambiguity.radii.items():
            if radius < 0.0:
                raise ValueError(f"Negative radius for metric '{name}': {radius}.")
            inflated = float(as_dict[name]) * (1.0 + float(radius))
            if not (inflated == inflated) or inflated == float("inf"):
                raise ValueError(f"adversarial_metrics produced non-finite value for '{name}'.")
            as_dict[name] = inflated

        return replace(metrics, **as_dict)

    def evaluate_robust(
        self,
        metrics: EnergyMetrics,
        ambiguity: AmbiguitySet,
    ) -> DRFreeResult:
        """Evaluate nominal and worst-case free energy under ``ambiguity``."""
        nominal_F, _, _, _ = self._base.free_energy(metrics)
        adv = self.adversarial_metrics(metrics, ambiguity)
        robust_F, robust_internal, robust_entropy, _ = self._base.free_energy(adv)
        margin = float(robust_F - nominal_F)
        return DRFreeResult(
            nominal_free_energy=float(nominal_F),
            robust_free_energy=float(robust_F),
            internal_energy=float(robust_internal),
            entropy=float(robust_entropy),
            adversarial_metrics=adv,
            ambiguity_set=ambiguity,
            robust_margin=margin,
        )


def robust_energy_state(
    result: DRFreeResult,
    *,
    warning_threshold: float,
    crisis_threshold: float,
) -> Literal["NORMAL", "WARNING", "DORMANT"]:
    """Map a robust free-energy reading to a coarse fail-closed state.

    Returns ``"DORMANT"`` when ``robust_free_energy >= crisis_threshold``,
    ``"WARNING"`` when ``>= warning_threshold`` (but below crisis), else
    ``"NORMAL"``. Thresholds must satisfy ``warning_threshold <= crisis_threshold``.
    """
    if not (warning_threshold <= crisis_threshold):
        raise ValueError("warning_threshold must be <= crisis_threshold.")
    F = result.robust_free_energy
    if F >= crisis_threshold:
        return "DORMANT"
    if F >= warning_threshold:
        return "WARNING"
    return "NORMAL"
