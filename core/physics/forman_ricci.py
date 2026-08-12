# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T3 — Forman-Ricci Curvature as real-time fragility monitor.

What this module ACTUALLY computes
-----------------------------------
This implementation computes the **unweighted, combinatorial** Forman-Ricci
curvature on a **binary** graph::

    κ_F(i,j) = 4 - d_i - d_j + 3·|{triangles containing (i,j)}|

where d_i, d_j are node degrees on an adjacency built by thresholding the
**absolute** correlation, ``|ρ_ij| > threshold``. Two consequences follow,
and both are declared as machine-readable provenance on
:class:`FormanRicciResult` (``weighted=False``, ``signed=False``,
``information_loss``) rather than hidden:

* **edge-weight magnitude is discarded** — once an edge clears the
  threshold its correlation magnitude does not enter the curvature, so two
  graphs with identical above-threshold topology but different magnitudes
  produce identical output. This is NOT the weighted Sreejith curvature.
* **correlation sign is discarded** — ``|ρ|`` collapses ρ = +0.8 and
  ρ = −0.8 onto the same edge, so anti-correlation structure is erased; the
  output is a *derived unsigned, unweighted topology descriptor*.

The general **weighted** Forman-Ricci of Sreejith et al. (2016) is::

    κ_F(e_{ij}) = w_{ij} · (w_i⁻¹ + w_j⁻¹)
                  - w_{ij} · Σ_{e∈parallel(e_{ij})} (w_{ij}⁻¹ + w_e⁻¹)

and is retained below only as the reference definition — it is **not** what
this O(1)-per-edge combinatorial monitor evaluates. The combinatorial form
is O(1) per edge after degree precomputation vs O(Δ³) for Ollivier-Ricci
(Δ = max degree).

Composite signal:
    κ_min(t) → 0  =  herding  =  raise margin requirements
    κ_min(t) << 0  =  fragmented  =  normal

Dual-track strategy:
    - Forman-Ricci on FULL graph: O(E) total, real-time feasible
    - Ollivier-Ricci on MST subgraph: O(N·Δ_MST²) ≈ O(N), high accuracy

Validated: Sandhu et al. 2016 showed Ricci curvature detects
housing bubble → we verify reproducibility on same methodology.

References:
    Sreejith et al. "Forman curvature for complex networks" (2016)
    Sandhu et al. "Graph curvature for differentiating cancer networks" (2016)
    Samal et al. "Comparative analysis of Ollivier-Ricci and Forman-Ricci" (2018)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

#: Provenance constants for the binarized, unweighted correlation graph this
#: monitor builds. ``|ρ| > threshold`` discards both edge-weight magnitude and
#: correlation sign, so every result declares the same representation and loss.
_REPRESENTATION: str = "graph"  # unsigned, unweighted simple graph
_INFORMATION_LOSS: tuple[str, ...] = ("edge_weight_magnitude", "correlation_sign")
#: Layer ownership and claim-boundary provenance. This is a market-state
#: structural descriptor (Layer B), not a physical-model output: it asserts no
#: oscillator state, prediction, or financial edge. These fields are a
#: DECLARATIVE provenance contract, not enforcement: a consumer that reads
#: ``physical_claim`` learns the value is descriptor-only, but nothing forces
#: that read. In particular :class:`DualTrackRicciMonitor` (``margin_multiplier``
#: / ``is_herding``) consumes the descriptor WITHOUT checking these fields, so
#: that path remains an un-enforced descriptor→action promotion — documented
#: here as a known gap, not closed by the label.
_LAYER: str = "market_descriptor"
_CLAIM_BOUNDARY: str = "derived_unsigned_unweighted_topology_descriptor"
_PROJECTION_POLICY: str = "abs_correlation_threshold_binary"
#: Non-finite (NaN/inf) correlations are excluded from the graph (never an
#: edge — ``np.abs(inf) > threshold`` would otherwise create a phantom edge)
#: and their count is recorded in ``nonfinite_input_count`` rather than being
#: silently coerced to zero.
_NAN_POLICY: str = "nonfinite_excluded_and_recorded"
#: Boundary a *consumer* of the descriptor must honour. :class:`DualTrackRicciMonitor`
#: turns the descriptor into a margin/herding signal; this constant marks that
#: such outputs are advisory transforms of a Layer-B descriptor, NOT a validated
#: physical model or trading edge. It is a machine-readable label on the consumer
#: so the descriptor→action promotion is named at the boundary, not only in prose.
_DESCRIPTOR_CONSUMER_BOUNDARY: str = (
    "advisory_transform_of_layer_b_descriptor__not_validated_physical_or_trading_claim"
)
#: κ_min value at which the margin policy *begins* to escalate. This is a policy
#: choice — the escalation onset — NOT a lower bound on the Forman curvature.
#: The combinatorial Forman-Ricci κ_F = 4 - d_i - d_j + 3·T_ij is UNBOUNDED below
#: (a hub edge of degree d with no triangles gives κ_F = 4 - 2d, e.g. -96 at
#: d=50), so any κ_min ≤ this onset is treated as "fragmented → base margin" by
#: design. Using a named constant keeps the magic number and the false-bound
#: comment that previously sat at the call site out of the code.
_MARGIN_ESCALATION_ONSET: float = -2.0


@dataclass(frozen=True, slots=True)
class FormanRicciResult:
    """Result of the unweighted combinatorial Forman-Ricci computation.

    The provenance fields make the representation honest and machine-auditable:
    the underlying graph is built by thresholding ``|ρ|``, so it is unsigned
    (``signed=False``) and unweighted (``weighted=False``), and
    ``information_loss`` records exactly what the ``|ρ| > threshold`` projection
    discards. They are constants for this estimator, not tunable outputs.
    """

    edge_curvatures: dict[tuple[int, int], float]
    kappa_min: float
    kappa_mean: float
    kappa_max: float
    herding_index: float  # fraction of edges with κ > 0
    representation: str = _REPRESENTATION
    weighted: bool = False
    signed: bool = False
    information_loss: tuple[str, ...] = _INFORMATION_LOSS
    layer: str = _LAYER
    physical_claim: bool = False
    claim_boundary: str = _CLAIM_BOUNDARY
    projection_policy: str = _PROJECTION_POLICY
    nan_policy: str = _NAN_POLICY
    #: Count of off-diagonal **matrix entries** (directed, not unordered pairs)
    #: whose correlation was non-finite (NaN/inf) and therefore excluded from the
    #: graph. A symmetric NaN at both (i,j) and (j,i) counts as 2; a one-sided
    #: NaN counts as 1. Zero ⟺ every off-diagonal correlation was finite.
    nonfinite_input_count: int = 0


class FormanRicciCurvature:
    """O(E) **unweighted** combinatorial Forman-Ricci over a binarized graph.

    The graph is built from a correlation matrix by ``|ρ_ij| > threshold``, so
    it is unsigned and unweighted; the Forman curvature of edge (i,j) is:
        κ_F(i,j) = 4 - d_i - d_j + 3·T_ij

    where T_ij = number of triangles containing edge (i,j). Edge weights and
    correlation signs do not enter — see the module docstring and the
    ``weighted`` / ``signed`` / ``information_loss`` provenance fields on
    :class:`FormanRicciResult`. This is deliberately not the weighted Sreejith
    curvature.

    This captures the same geometric intuition as Ollivier-Ricci
    (positive curvature = well-connected neighborhood = herding)
    but at O(1) per edge instead of O(Δ³).

    Parameters
    ----------
    threshold : float
        Correlation threshold for graph construction (default 0.5).
        Edge (i,j) exists if |ρ_ij| > threshold.
    """

    def __init__(self, threshold: float = 0.5) -> None:
        if not 0 < threshold < 1:
            raise ValueError(f"threshold must be in (0, 1), got {threshold}")
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        return self._threshold

    @staticmethod
    def _correlation_to_adjacency(corr: NDArray[np.float64], threshold: float) -> NDArray[np.bool_]:
        """Threshold absolute correlation into binary adjacency.

        Non-finite correlations (NaN/inf) are never edges. ``np.abs(inf) >
        threshold`` evaluates ``True`` and would otherwise create a phantom
        edge from an undefined correlation; requiring finiteness excludes both
        NaN and inf explicitly. Their count is recorded by the caller
        (``nonfinite_input_count``) so the exclusion is auditable, not silent.
        """
        adj = (np.abs(corr) > threshold) & np.isfinite(corr)
        np.fill_diagonal(adj, False)
        return adj

    @staticmethod
    def _count_triangles_per_edge(
        adj: NDArray[np.bool_],
    ) -> dict[tuple[int, int], int]:
        """Count triangles containing each edge. O(N·E) total."""
        n = adj.shape[0]
        adj_int = adj.astype(np.int32)
        # A² gives number of paths of length 2
        A2 = adj_int @ adj_int
        triangles: dict[tuple[int, int], int] = {}
        for i in range(n):
            for j in range(i + 1, n):
                if adj[i, j]:
                    # Number of common neighbors = triangles through (i,j)
                    triangles[(i, j)] = int(A2[i, j])
        return triangles

    def compute_from_correlation(self, corr: NDArray[np.float64]) -> FormanRicciResult:
        """Compute Forman-Ricci from correlation matrix.

        Parameters
        ----------
        corr : (N, N) correlation matrix.

        Returns
        -------
        FormanRicciResult with per-edge curvatures and summary stats.
        """
        corr = np.asarray(corr, dtype=np.float64)
        n = corr.shape[0]
        if corr.shape != (n, n):
            raise ValueError(f"Correlation must be square, got {corr.shape}")

        # Record off-diagonal non-finite correlations rather than letting them
        # silently vanish (NaN) or fabricate an edge (inf). The diagonal is the
        # self-correlation (1.0) and is excluded from the graph regardless.
        finite_mask = np.isfinite(corr)
        np.fill_diagonal(finite_mask, True)
        nonfinite_input_count = int(np.size(finite_mask) - np.count_nonzero(finite_mask))

        adj = self._correlation_to_adjacency(corr, self._threshold)
        degrees = adj.sum(axis=1).astype(int)
        triangles = self._count_triangles_per_edge(adj)

        edge_curvatures: dict[tuple[int, int], float] = {}
        for (i, j), t_ij in triangles.items():
            # Forman curvature: κ_F(i,j) = 4 - d_i - d_j + 3·T_ij
            kappa = 4.0 - degrees[i] - degrees[j] + 3.0 * t_ij
            edge_curvatures[(i, j)] = kappa

        if not edge_curvatures:
            return FormanRicciResult(
                edge_curvatures={},
                kappa_min=0.0,
                kappa_mean=0.0,
                kappa_max=0.0,
                herding_index=0.0,
                nonfinite_input_count=nonfinite_input_count,
            )

        values = np.array(list(edge_curvatures.values()))
        return FormanRicciResult(
            edge_curvatures=edge_curvatures,
            kappa_min=float(values.min()),
            kappa_mean=float(values.mean()),
            kappa_max=float(values.max()),
            herding_index=float(np.mean(values > 0)),
            nonfinite_input_count=nonfinite_input_count,
        )

    def compute_from_prices(
        self,
        prices: NDArray[np.float64],
        window: int = 30,
    ) -> FormanRicciResult:
        """Compute Forman-Ricci from price matrix via rolling correlation.

        Parameters
        ----------
        prices : (T, N) price history.
        window : int, rolling correlation window.

        Returns
        -------
        FormanRicciResult.
        """
        prices = np.asarray(prices, dtype=np.float64)
        if prices.ndim != 2 or prices.shape[0] < 2:
            raise ValueError(f"Expected (T≥2, N) array, got {prices.shape}")

        returns = np.diff(prices, axis=0) / np.maximum(np.abs(prices[:-1]), 1e-12)
        tail = returns[-window:] if returns.shape[0] > window else returns

        with np.errstate(invalid="ignore"):
            corr = np.corrcoef(tail, rowvar=False)
        # Do NOT silently coerce NaN→0 here: a zero-variance (constant) column
        # yields a NaN correlation row, and nan_to_num would hide it as a
        # below-threshold zero. Pass the raw correlation through so
        # compute_from_correlation excludes the non-finite entries from the
        # graph and records their count in nonfinite_input_count. The edge set
        # (and therefore the curvature) is unchanged for finite inputs.
        corr_arr: NDArray[np.float64] = np.atleast_2d(np.asarray(corr, dtype=np.float64))
        return self.compute_from_correlation(corr_arr)


class DualTrackRicciMonitor:
    """Advisory fragility monitor over a Layer-B descriptor: Forman (full) + Ollivier (MST).

    Forman on full graph for speed. Ollivier on MST for accuracy. This is a
    *consumer* of :class:`FormanRicciResult` — an unsigned/unweighted structural
    descriptor — and re-expresses it as margin/herding language. Those outputs
    (``margin_multiplier``, ``is_herding``, ``fragility_trend``) are advisory
    transforms of that descriptor, NOT a validated physical model or trading
    edge; the boundary is declared machine-readably on
    :attr:`descriptor_consumer_boundary`. "Fragility"/"margin"/"herding" here are
    names for descriptor regimes, not asserted market outcomes.

    Parameters
    ----------
    forman_threshold : float
        Correlation threshold for Forman graph (default 0.5).
    correlation_window : int
        Rolling window for correlation estimation (default 30).
    margin_multiplier_base : float
        Base margin requirement (default 1.0, i.e. 100%).
    margin_sensitivity : float
        How much margin increases per unit κ increase toward 0 (default 2.0).
    """

    #: Machine-readable boundary every consumer of this monitor's outputs must
    #: honour: margin/herding values are advisory transforms of a Layer-B
    #: descriptor, never a validated physical or trading claim.
    descriptor_consumer_boundary: str = _DESCRIPTOR_CONSUMER_BOUNDARY

    def __init__(
        self,
        forman_threshold: float = 0.5,
        correlation_window: int = 30,
        margin_multiplier_base: float = 1.0,
        margin_sensitivity: float = 2.0,
    ) -> None:
        self._forman = FormanRicciCurvature(threshold=forman_threshold)
        self._window = correlation_window
        self._margin_base = margin_multiplier_base
        self._margin_sensitivity = margin_sensitivity
        self._history: list[FormanRicciResult] = []

    @property
    def history(self) -> list[FormanRicciResult]:
        return list(self._history)

    def update(self, prices: NDArray[np.float64]) -> FormanRicciResult:
        """Process new price data and update fragility state.

        Parameters
        ----------
        prices : (T, N) price history.

        Returns
        -------
        FormanRicciResult for current state.
        """
        result = self._forman.compute_from_prices(prices, self._window)
        self._history.append(result)
        return result

    def margin_multiplier(self, result: FormanRicciResult | None = None) -> float:
        """Compute margin requirement multiplier from curvature.

        κ_min → 0  means herding → increase margin.
        κ_min ≤ onset means fragmented → base margin.

        Multiplier = base · max(1, 1 + sensitivity · max(0, κ_min − onset))

        ``onset`` (:data:`_MARGIN_ESCALATION_ONSET`, default −2) is the κ_min at
        which escalation begins; it is a *policy choice*, not a bound on κ_F
        (the combinatorial Forman curvature is unbounded below). For
        κ_min ≤ onset the inner ``max(0, …)`` saturates to 0, so the multiplier
        floors at ``base`` — the documented "fragmented → base margin" regime,
        not a silently discarded value.
        At κ_min = 0 (herding): multiplier = base · (1 − sensitivity·onset).

        Boundary: this consumes a Layer-B structural descriptor and does NOT
        read ``result.physical_claim`` / ``result.claim_boundary``. The
        returned multiplier is descriptor-derived and is not a validated
        trading signal; promoting it to a live margin policy requires separate
        validation. This is the known un-enforced descriptor→action path.
        """
        if result is None:
            if not self._history:
                return self._margin_base
            result = self._history[-1]

        # bounds: escalation onset, NOT a bound on κ_F (combinatorial
        # Forman-Ricci is unbounded below). This max() is the policy floor
        # "κ_min ≤ onset → base margin", not a claim that κ_F ≥ onset.
        kappa_shifted = max(0.0, result.kappa_min - _MARGIN_ESCALATION_ONSET)
        return self._margin_base * max(1.0, 1.0 + self._margin_sensitivity * kappa_shifted)

    def is_herding(self, result: FormanRicciResult | None = None) -> bool:
        """Detect herding: κ_min approaching 0 or positive.

        Descriptor-only: a structural-coherence flag, not a validated market
        prediction; this does not read ``result.physical_claim``.
        """
        if result is None:
            if not self._history:
                return False
            result = self._history[-1]
        return result.kappa_min > -1.0

    def fragility_trend(self, lookback: int = 10) -> float:
        """Compute fragility trend: positive = increasing fragility.

        Returns slope of κ_min over last `lookback` observations.
        Positive slope means κ_min rising toward 0 = increasing herding.
        """
        if len(self._history) < 2:
            return 0.0
        recent = self._history[-lookback:]
        kappas = [r.kappa_min for r in recent]
        if len(kappas) < 2:
            return 0.0
        x = np.arange(len(kappas), dtype=np.float64)
        coeffs = np.polyfit(x, kappas, 1)
        return float(coeffs[0])


__all__ = [
    "FormanRicciCurvature",
    "FormanRicciResult",
    "DualTrackRicciMonitor",
]
