# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Typed, fail-closed trace of one discrete Ricci-flow step on a market graph.

:class:`RicciFlowTrace` is a *trace object*, not a solver. It wraps the values
produced by the already-shipped Ricci primitives —
``core.indicators.ricci.mean_ricci`` (Ollivier–Ricci curvature),
``core.indicators.gauss_bonnet.gauss_bonnet_residual`` (exact Knill/ℚ
Gauss–Bonnet integrity), and the discrete flow energy ``F = Σ_e κ_e²`` from the
``core.kuramoto.ricci_flow`` family — and refuses to record a trace that
violates a curvature law:

* a curvature above the universal upper bound ``κ ≤ 1`` (INV-RC1),
* a price-graph curvature outside its declared band ``κ ∈ [−1, 1]`` (INV-RC3),
* a flow energy that *increases* while the verdict claims non-increase
  (``ricci.flow_monotonicity``: ``F(t+1) ≤ F(t)·(1+1e-9)``),
* a non-zero **exact** Gauss–Bonnet residual (corrupted/tampered topology,
  ``ricci.gauss_bonnet``),
* a missing validity domain.

No new Ricci mathematics is introduced here. The trace only *binds and checks*
the outputs of the existing primitives.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

import networkx as nx

from core.indicators.gauss_bonnet import gauss_bonnet_residual
from core.indicators.ricci import mean_ricci
from physics_contracts.manifold.contracts import canonical_digest

__all__ = [
    "PRICE_GRAPH_DOMAIN",
    "RicciFlowTrace",
    "classify_monotonicity",
    "flow_energy",
    "build_ricci_flow_trace",
]

# Validity-domain token that activates the symmetric price-graph band κ∈[−1,1]
# (INV-RC3 / catalog ricci.ollivier_bounds). Any other domain string is treated
# as a general topology where only the universal upper bound κ≤1 is enforced.
PRICE_GRAPH_DOMAIN: Final[str] = "build_price_graph"

# Universal Ollivier–Ricci upper bound: κ = 1 − W₁/d ≤ 1 since W₁ ≥ 0 (INV-RC1).
_KAPPA_UPPER: Final[float] = 1.0
# Symmetric lower bound, valid only on the price-graph embedding (INV-RC3).
_KAPPA_PRICE_LOWER: Final[float] = -1.0
# Numerical slack of the flow-monotonicity law, taken verbatim from the catalog
# tolerance ``F(t+1) ≤ F(t)·(1+1e-9)`` — a formula-derived bound, not a magic
# epsilon.
_FLOW_MONOTONICITY_SLACK: Final[float] = 1.0e-9

_MONOTONICITY_VERDICTS: Final[frozenset[str]] = frozenset(
    {"non_increasing", "increased", "not_applicable"}
)


def _is_finite(x: float) -> bool:
    return x == x and x not in (float("inf"), float("-inf"))


@dataclass(frozen=True, slots=True)
class RicciFlowTrace:
    """One Ricci-flow step's before/after curvature + energy + GB integrity.

    ``gauss_bonnet_residual`` is carried as an exact :class:`fractions.Fraction`
    (never a float): the law admits *only* the exact rational zero, so a residual
    that is non-zero by even one part in a googol is a topology violation.
    """

    snapshot_id: str
    kappa_before: float
    kappa_after: float
    flow_energy_before: float
    flow_energy_after: float
    monotonicity_verdict: str
    gauss_bonnet_residual: Fraction
    validity_domain: str

    def __post_init__(self) -> None:
        if not self.snapshot_id:
            raise ValueError(
                "manifold.provenance_replay_identity VIOLATED: RicciFlowTrace has empty snapshot_id"
            )
        if not self.validity_domain:
            raise ValueError(
                "ricci.ollivier_bounds VIOLATED: RicciFlowTrace.validity_domain is empty "
                "(a curvature trace must declare the domain its κ-bounds hold over)"
            )
        lower = _KAPPA_PRICE_LOWER if self.validity_domain == PRICE_GRAPH_DOMAIN else float("-inf")
        for name, kappa in (("kappa_before", self.kappa_before), ("kappa_after", self.kappa_after)):
            if not _is_finite(kappa):
                raise ValueError(f"ricci.ollivier_bounds VIOLATED: {name} is non-finite")
            if kappa > _KAPPA_UPPER:
                raise ValueError(
                    f"INV-RC1 VIOLATED: {name}={kappa} exceeds the universal upper bound κ≤1"
                )
            if kappa < lower:
                raise ValueError(
                    f"INV-RC3 VIOLATED: {name}={kappa} below the price-graph band κ≥-1 "
                    f"declared by validity_domain={self.validity_domain!r}"
                )
        for name, energy in (
            ("flow_energy_before", self.flow_energy_before),
            ("flow_energy_after", self.flow_energy_after),
        ):
            if not _is_finite(energy) or energy < 0.0:
                raise ValueError(
                    f"ricci.flow_monotonicity VIOLATED: {name}={energy!r} must be finite and "
                    "non-negative (F = Σ κ_e² ≥ 0)"
                )
        if self.monotonicity_verdict not in _MONOTONICITY_VERDICTS:
            raise ValueError(
                f"ricci.flow_monotonicity VIOLATED: monotonicity_verdict "
                f"{self.monotonicity_verdict!r} not in {sorted(_MONOTONICITY_VERDICTS)}"
            )
        # Fail-closed monotonicity: claiming non-increase while the energy rose
        # past the law's numerical slack is exactly the over-claim the law forbids.
        if self.monotonicity_verdict == "non_increasing" and self.flow_energy_after > (
            self.flow_energy_before * (1.0 + _FLOW_MONOTONICITY_SLACK)
        ):
            raise ValueError(
                "ricci.flow_monotonicity VIOLATED: verdict='non_increasing' but "
                f"F_after={self.flow_energy_after} > F_before={self.flow_energy_before}·(1+1e-9); "
                "discrete Ricci-flow energy must be non-increasing on a static graph"
            )
        # Non-zero exact Gauss–Bonnet residual ⇒ corrupted topology, rejected.
        if self.gauss_bonnet_residual != 0:
            raise ValueError(
                "ricci.gauss_bonnet VIOLATED: exact Gauss–Bonnet residual "
                f"Σκ−χ = {self.gauss_bonnet_residual} ≠ 0; the curvature field is inconsistent "
                "with the graph topology — trace rejected fail-closed"
            )

    @property
    def trace_digest(self) -> str:
        """Deterministic content-address of the trace (replay identity)."""

        return canonical_digest(
            {
                "snapshot_id": self.snapshot_id,
                "kappa_before": self.kappa_before,
                "kappa_after": self.kappa_after,
                "flow_energy_before": self.flow_energy_before,
                "flow_energy_after": self.flow_energy_after,
                "monotonicity_verdict": self.monotonicity_verdict,
                "gauss_bonnet_residual": str(self.gauss_bonnet_residual),
                "validity_domain": self.validity_domain,
            }
        )


def flow_energy(edge_curvatures: Sequence[float]) -> float:
    """Discrete Ricci-flow energy ``F = Σ_e κ_e²`` (Perelman-like functional).

    Pure reduction over per-edge curvatures already produced by the existing
    Ricci primitives; introduces no curvature mathematics of its own.
    """

    total = 0.0
    for kappa in edge_curvatures:
        if not _is_finite(kappa):
            raise ValueError("flow_energy: edge curvature is non-finite")
        total += kappa * kappa
    return total


def classify_monotonicity(energy_before: float, energy_after: float) -> str:
    """Classify the flow-energy step against ``ricci.flow_monotonicity``.

    Returns ``"non_increasing"`` when the energy did not rise past the law's
    numerical slack, else ``"increased"``. The slack is the law's own
    ``(1+1e-9)`` factor, not a free parameter.
    """

    if not _is_finite(energy_before) or not _is_finite(energy_after):
        raise ValueError("classify_monotonicity: energies must be finite")
    if energy_after <= energy_before * (1.0 + _FLOW_MONOTONICITY_SLACK):
        return "non_increasing"
    return "increased"


def build_ricci_flow_trace(
    *,
    snapshot_id: str,
    graph_before: nx.Graph,
    graph_after: nx.Graph,
    edge_curvatures_before: Sequence[float],
    edge_curvatures_after: Sequence[float],
    validity_domain: str,
    curvature_field: Mapping[Hashable, object] | None = None,
) -> RicciFlowTrace:
    """Assemble a :class:`RicciFlowTrace` by wrapping the existing primitives.

    * ``kappa_before/after`` come from ``core.indicators.ricci.mean_ricci``.
    * ``flow_energy_before/after`` from :func:`flow_energy` over the caller's
      per-edge curvatures (already computed with the existing Ricci edge
      primitive).
    * ``gauss_bonnet_residual`` from
      ``core.indicators.gauss_bonnet.gauss_bonnet_residual`` on the *after*
      graph — exact and fail-closed against a tampered ``curvature_field``.

    No solver runs here; this is glue over primitives that already exist.
    """

    kappa_before = float(mean_ricci(graph_before))
    kappa_after = float(mean_ricci(graph_after))
    energy_before = flow_energy(edge_curvatures_before)
    energy_after = flow_energy(edge_curvatures_after)
    residual = gauss_bonnet_residual(graph_after, curvature=curvature_field)
    return RicciFlowTrace(
        snapshot_id=snapshot_id,
        kappa_before=kappa_before,
        kappa_after=kappa_after,
        flow_energy_before=energy_before,
        flow_energy_after=energy_after,
        monotonicity_verdict=classify_monotonicity(energy_before, energy_after),
        gauss_bonnet_residual=residual,
        validity_domain=validity_domain,
    )
