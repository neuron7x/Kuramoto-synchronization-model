# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C — Substrate generators for the Signal Amplification Sweep.

Rationale
=========
Three substrate families, each producing a Kuramoto coupling
matrix K of shape ``(T_HORIZON, N, N)`` parameterised by
``(N, lambda_, seed)``. The temporal dimension is the
quarter-level horizon over which the sweep simulates a
precursor event; the precursor is injected into ``K`` during
the pre-event window, leaving ``K_baseline`` untouched.

  * :class:`RicciFlowSubstrate` — Erdős-Rényi base, Forman-Ricci
    curvature per edge, K_ij = K_c * (1 + 0.5 * κ̂_ij) where κ̂
    is curvature normalised to [-1, 1]. Precursor: positive κ
    shift on the top-10% strongest edges during the 2Q
    pre-event window.

  * :class:`BlockStructuredSubstrate` — tiered core/mid/periphery
    block matrix with the locked multiplier pattern
    (1.5/1.0/0.5/0.2 K_c). Precursor: additive λ-shift to the
    inter-block off-diagonal sub-blocks during the 2Q pre-event.

  * :class:`TemporalKtSubstrate` — block-structured baseline
    plus a deterministic sinusoidal modulation
    ``K(t) = K_c * (1 + 0.20 * sin(2π t / 4))``. Precursor:
    baseline-level λ shift applied to the temporal envelope
    during the 2Q pre-event.

Strict scope
============
Substrate construction ONLY. NO Kuramoto integration (that
lives in the sweep runner, C2.4). NO metric computation (that
lives in :mod:`d002c_metrics`). NO claim layer. Output is a
frozen :class:`SubstrateRealization` consumed downstream.

Calibration contract
====================
For each realisation, both ``K_baseline`` and ``K_precursor``
satisfy

  * symmetric (Hermitian) at every time slice
  * finite (no NaN / Inf)
  * mean-over-time spectral radius ``λ_max(K) / N ∈ [0.95, 1.05]``
    (gate G9). Calibrated post-construction via scalar scaling
    so the regime is reproducible across substrate families.
  * baseline density (off-diagonal nonzero fraction) within
    [0.05, 0.15] for substrates that have an underlying sparse
    topology (G6).
  * precursor injection produces a measurable Frobenius-norm
    delta ``||K_precursor - K_baseline||_F > 0`` for any
    ``lambda_ > 0`` (G10).

These are gates, not soft suggestions — a realisation that
violates any of them raises :class:`SubstrateInvalid`. The
sweep cannot proceed past such a failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

import numpy as np
from numpy.typing import NDArray

# ---------------------------------------------------------------------------
# Horizon constants — pinned to the D-002C pre-registration intent.
#
# The horizon is 8 quarters (2 years), with the event at quarter 6 and a
# 4Q pre-event window [2, 6). The precursor is injected into the LAST 2
# quarters of the pre-event window, i.e. quarters {4, 5}.
# ---------------------------------------------------------------------------
T_HORIZON: Final[int] = 8
EVENT_QUARTER: Final[int] = 6
PRE_EVENT_START_QUARTER: Final[int] = 2
PRE_EVENT_WINDOW: Final[range] = range(PRE_EVENT_START_QUARTER, EVENT_QUARTER)
PRECURSOR_INJECTION_WINDOW: Final[range] = range(EVENT_QUARTER - 2, EVENT_QUARTER)

# Gates G6 / G9 / G9-precursor
DENSITY_RANGE: Final[tuple[float, float]] = (0.05, 0.15)
# Baseline must sit at the critical-onset regime (ρ/N ≈ 1.0). Tight band so
# the three substrate families are spectrally comparable AT THE NULL.
SPECTRAL_RANGE: Final[tuple[float, float]] = (0.95, 1.05)
# Precursor is BY DESIGN an amplification — a precursor that didn't lift
# coupling would have nothing to detect. We allow up to +15% spectral
# radius lift but refuse contraction (ρ/N < 0.95) and any pathological
# explosion (ρ/N > 1.15) that would push the regime so far past onset
# that the metric saturates trivially. The precursor gate is asserted
# at lambda=1 (the maximum); lambdas in (0, 1) lift continuously and
# stay strictly inside the corresponding sub-interval.
PRECURSOR_SPECTRAL_RANGE: Final[tuple[float, float]] = (0.95, 1.15)

# Default Erdős-Rényi density for the Ricci substrate
DEFAULT_ER_DENSITY: Final[float] = 0.10

# Block structure (fractions sum to 1.0)
BLOCK_FRACTIONS: Final[tuple[float, float, float]] = (0.20, 0.30, 0.50)


class SubstrateInvalid(RuntimeError):
    """Substrate realisation violates the calibration / shape contract."""


@dataclass(frozen=True)
class SubstrateRealization:
    """Frozen output of one substrate realisation.

    ``K_baseline`` is the null trajectory (no precursor).
    ``K_precursor`` carries the precursor injection during
    :data:`PRECURSOR_INJECTION_WINDOW`. Outside that window the
    two trajectories are identical.
    """

    substrate_id: str
    N: int
    lambda_: float
    seed: int
    K_baseline: NDArray[np.float64]  # shape (T_HORIZON, N, N)
    K_precursor: NDArray[np.float64]  # shape (T_HORIZON, N, N)
    K_c: float
    density: float
    spectral_radius_over_N: float
    # New (Codex P1 fix, 2026-05-11): gate G9 was previously asserted only
    # on K_baseline; this is now also asserted on K_precursor with a
    # wider but bounded range (PRECURSOR_SPECTRAL_RANGE). A precursor
    # that pushed K outside the comparable regime would bias the
    # downstream metric comparison; the gate refuses such realisations
    # fail-closed.
    spectral_radius_over_N_precursor: float
    precursor_frobenius_delta: float


class Substrate(Protocol):
    """Protocol for substrate generators."""

    @property
    def id(self) -> str: ...

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization: ...


# ---------------------------------------------------------------------------
# Shared validation
# ---------------------------------------------------------------------------


def _verify_K_trajectory(K: NDArray[np.float64], *, where: str) -> None:
    """Raise SubstrateInvalid unless K is shape (T,N,N), finite, symmetric."""
    if K.ndim != 3:
        raise SubstrateInvalid(f"{where}: K must be 3-D (T,N,N); got {K.shape}")
    if not np.all(np.isfinite(K)):
        raise SubstrateInvalid(f"{where}: K contains non-finite values")
    # symmetric at every time slice
    asym = np.max(np.abs(K - np.swapaxes(K, -1, -2)))
    if asym > 1e-9:
        raise SubstrateInvalid(f"{where}: K not symmetric (max asymmetry {asym:.3e})")


def _spectral_radius_mean(K: NDArray[np.float64]) -> float:
    """Mean of largest absolute eigenvalue across time slices."""
    radii = [float(np.abs(np.linalg.eigvalsh(K[t])).max()) for t in range(K.shape[0])]
    return float(np.mean(radii))


def _enforce_calibration_gates(
    *,
    K_baseline: NDArray[np.float64],
    K_precursor: NDArray[np.float64],
    lambda_: float,
    density: float | None,
    substrate_id: str,
    N: int,
) -> tuple[float, float, float]:
    """Run gates G6, G7, G8, G9 (baseline + precursor), G10.

    Returns
    -------
    (spectral_radius_over_N_baseline, spectral_radius_over_N_precursor, delta)

    Notes
    -----
    Codex P1 fix (2026-05-11): gate G9 was previously asserted only on
    ``K_baseline``; the precursor trajectory was constructed but never
    spectrally validated. That allowed a realisation whose precursor
    exceeded the comparable-regime band to pass silently (e.g.
    ``BlockStructuredSubstrate(lambda_=1.0)`` was producing
    ``ρ/N ≈ 1.052`` on the precursor, beyond the baseline gate hi).
    Both trajectories are now spectrally validated, against their own
    ranges (:data:`SPECTRAL_RANGE` for baseline,
    :data:`PRECURSOR_SPECTRAL_RANGE` for precursor — wider but bounded,
    reflecting that the precursor IS by design an amplification).
    """
    _verify_K_trajectory(K_baseline, where=f"{substrate_id}.K_baseline")
    _verify_K_trajectory(K_precursor, where=f"{substrate_id}.K_precursor")

    spec_baseline = _spectral_radius_mean(K_baseline) / float(N)
    lo, hi = SPECTRAL_RANGE
    if not (lo <= spec_baseline <= hi):
        raise SubstrateInvalid(
            f"{substrate_id}: baseline spectral_radius_over_N={spec_baseline:.4f} "
            f"outside [{lo}, {hi}] (gate G9 baseline failed)"
        )

    spec_precursor = _spectral_radius_mean(K_precursor) / float(N)
    p_lo, p_hi = PRECURSOR_SPECTRAL_RANGE
    if not (p_lo <= spec_precursor <= p_hi):
        raise SubstrateInvalid(
            f"{substrate_id}: precursor spectral_radius_over_N={spec_precursor:.4f} "
            f"outside [{p_lo}, {p_hi}] (gate G9 precursor failed) — "
            f"at lambda_={lambda_:.4f}. The precursor injection pushed K "
            f"past the comparable-regime band; downstream metric "
            f"comparison would be biased."
        )

    if density is not None:
        d_lo, d_hi = DENSITY_RANGE
        if not (d_lo <= density <= d_hi):
            raise SubstrateInvalid(
                f"{substrate_id}: density={density:.4f} outside [{d_lo}, {d_hi}] (gate G6 failed)"
            )

    delta = float(np.linalg.norm(K_precursor - K_baseline))
    # Gate G10: any lambda_ > 0 must produce strictly positive Frobenius delta.
    if lambda_ > 0.0 and delta <= 0.0:
        raise SubstrateInvalid(
            f"{substrate_id}: lambda_={lambda_:.4f} > 0 but precursor delta "
            f"is {delta:.3e} (gate G10 failed)"
        )
    # And lambda_ == 0 means null run — delta MUST be exactly zero.
    if lambda_ == 0.0 and delta != 0.0:
        raise SubstrateInvalid(
            f"{substrate_id}: lambda_=0 but precursor delta is {delta:.3e} "
            "(null run must be identical to baseline)"
        )
    return spec_baseline, spec_precursor, delta


def _calibrate_spectral_radius(
    M: NDArray[np.float64], *, target_N: int
) -> tuple[NDArray[np.float64], float]:
    """Scale M so its largest absolute eigenvalue equals N. Returns (K, K_c)."""
    lam = float(np.abs(np.linalg.eigvalsh(M)).max())
    if lam <= 0.0:
        raise SubstrateInvalid(f"cannot calibrate: spectral radius {lam:.3e} <= 0")
    K_c = float(target_N) / lam
    return M * K_c, K_c


# ---------------------------------------------------------------------------
# S1: Ricci-flow weighted Erdős-Rényi
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RicciFlowSubstrate:
    """Erdős-Rényi base, Forman-Ricci-weighted coupling, top-10% κ precursor.

    Forman-Ricci on an unweighted graph:

        κ_F(i,j) = 4 - deg(i) - deg(j) + 3 · #{triangles containing (i,j)}

    O(N²) construction (matrix product gives triangles_ij) — fast for
    the swept N ≤ 200 regime. Raw κ_F is unbounded; we normalise to
    ``κ̂ ∈ [-1, 1]`` before applying ``K = M_struct · (1 + 0.5 κ̂)``
    so the multiplier stays strictly positive (a sign-flipped K_ij
    would invert Kuramoto's attractive coupling — masked as a soft
    bug we explicitly refuse).
    """

    er_density: float = DEFAULT_ER_DENSITY

    @property
    def id(self) -> str:
        return "ricci_flow"

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        if N < 4:
            raise SubstrateInvalid("ricci_flow: N must be >= 4")
        rng = np.random.default_rng(seed)
        # 1) Erdős-Rényi adjacency (symmetric, no self-loops)
        upper = rng.random((N, N)) < self.er_density
        A_bool = np.triu(upper, k=1)
        A_bool = A_bool | A_bool.T
        np.fill_diagonal(A_bool, False)
        A = A_bool.astype(np.float64)
        if not A.any():
            raise SubstrateInvalid(
                f"ricci_flow: ER realisation at p={self.er_density} produced "
                f"an empty graph (seed={seed}, N={N})"
            )
        # 2) Forman-Ricci κ per edge
        deg = A.sum(axis=1)
        triangles = A @ A  # triangles_ij = # common neighbours when (i,j)∈E
        kappa = 4.0 - deg[:, None] - deg[None, :] + 3.0 * triangles
        kappa = kappa * A  # zero where no edge
        # 3) Normalise κ to [-1, 1] over the edge set
        finite_kappa = kappa[A.astype(bool)]
        scale = max(float(np.abs(finite_kappa).max()), 1.0)
        kappa_hat = kappa / scale
        # 4) Structural matrix M = adjacency * (1 + 0.5 κ̂)
        M = A * (1.0 + 0.5 * kappa_hat)
        K_calibrated, K_c = _calibrate_spectral_radius(M, target_N=N)
        K_baseline = np.broadcast_to(K_calibrated, (T_HORIZON, N, N)).astype(np.float64).copy()
        # 5) Precursor: shift top-10% strongest edges by +0.20·λ during the
        #    precursor injection window. Top-10% selected on the upper
        #    triangle to avoid duplication.
        K_precursor = K_baseline.copy()
        if lambda_ > 0.0:
            iu = np.triu_indices(N, k=1)
            strengths = K_calibrated[iu]
            mask_edges = strengths > 0
            if not mask_edges.any():
                raise SubstrateInvalid(
                    "ricci_flow: no positive-strength edges to inject precursor on"
                )
            thresh = float(np.quantile(strengths[mask_edges], 0.90))
            top_mask = np.zeros_like(K_calibrated, dtype=bool)
            sel = (strengths >= thresh) & mask_edges
            top_mask[iu[0][sel], iu[1][sel]] = True
            top_mask = top_mask | top_mask.T  # symmetric
            shift = 0.20 * lambda_ * top_mask.astype(np.float64)
            K_event = K_calibrated * (1.0 + shift)
            for t in PRECURSOR_INJECTION_WINDOW:
                K_precursor[t] = K_event
        density = float(A.sum() / (N * (N - 1)))
        spec_b, spec_p, delta = _enforce_calibration_gates(
            K_baseline=K_baseline,
            K_precursor=K_precursor,
            lambda_=lambda_,
            density=density,
            substrate_id=self.id,
            N=N,
        )
        return SubstrateRealization(
            substrate_id=self.id,
            N=N,
            lambda_=lambda_,
            seed=seed,
            K_baseline=K_baseline,
            K_precursor=K_precursor,
            K_c=K_c,
            density=density,
            spectral_radius_over_N=spec_b,
            spectral_radius_over_N_precursor=spec_p,
            precursor_frobenius_delta=delta,
        )


# ---------------------------------------------------------------------------
# S2: Block-structured tiered (core / mid / periphery)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BlockStructuredSubstrate:
    """Tiered block matrix with the locked core/mid/periphery multiplier
    pattern. Precursor: additive λ-shift on the inter-block off-diagonal
    sub-blocks (core↔mid, core↔periphery, mid↔periphery) during the 2Q
    pre-event window. Within-block multipliers remain at their locked
    values; the precursor models a structural coupling lift between
    tiers, which is the regime D-002C predicts to be detectable.
    """

    block_fractions: tuple[float, float, float] = BLOCK_FRACTIONS

    @property
    def id(self) -> str:
        return "block_structured"

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        if N < 6:
            raise SubstrateInvalid("block_structured: N must be >= 6")
        f_core, f_mid, _f_per = self.block_fractions
        n_core = max(1, int(round(f_core * N)))
        n_mid = max(1, int(round(f_mid * N)))
        n_per = N - n_core - n_mid
        if n_per <= 0:
            raise SubstrateInvalid(
                f"block_structured: degenerate split (core={n_core}, "
                f"mid={n_mid}, periphery={n_per}) at N={N}"
            )
        # Multiplier matrix W (NxN) before K_c calibration
        # core-core=1.5, core-mid=1.0, core-per=1.0, mid-mid=1.0,
        # mid-per=0.5, per-per=0.2
        W = np.zeros((N, N), dtype=np.float64)
        i_core = slice(0, n_core)
        i_mid = slice(n_core, n_core + n_mid)
        i_per = slice(n_core + n_mid, N)
        W[i_core, i_core] = 1.5
        W[i_core, i_mid] = 1.0
        W[i_mid, i_core] = 1.0
        W[i_core, i_per] = 1.0
        W[i_per, i_core] = 1.0
        W[i_mid, i_mid] = 1.0
        W[i_mid, i_per] = 0.5
        W[i_per, i_mid] = 0.5
        W[i_per, i_per] = 0.2
        np.fill_diagonal(W, 0.0)
        _ = seed  # block substrate is fully deterministic in N, lambda_
        K_calibrated, K_c = _calibrate_spectral_radius(W, target_N=N)
        K_baseline = np.broadcast_to(K_calibrated, (T_HORIZON, N, N)).astype(np.float64).copy()
        # Precursor: additive lift on the inter-block sub-blocks
        K_precursor = K_baseline.copy()
        if lambda_ > 0.0:
            lift = np.zeros((N, N), dtype=np.float64)
            shift_mag = 0.25 * lambda_ * K_c
            lift[i_core, i_mid] = shift_mag
            lift[i_mid, i_core] = shift_mag
            lift[i_core, i_per] = shift_mag
            lift[i_per, i_core] = shift_mag
            lift[i_mid, i_per] = shift_mag
            lift[i_per, i_mid] = shift_mag
            np.fill_diagonal(lift, 0.0)
            K_event = K_calibrated + lift
            for t in PRECURSOR_INJECTION_WINDOW:
                K_precursor[t] = K_event
        # density is structural (no random graph) — equal to fraction
        # of nonzero off-diagonal entries in the locked pattern.
        density = float(np.count_nonzero(W) / (N * (N - 1)))
        spec_b, spec_p, delta = _enforce_calibration_gates(
            K_baseline=K_baseline,
            K_precursor=K_precursor,
            lambda_=lambda_,
            density=None,  # block substrate is fully connected, density gate N/A
            substrate_id=self.id,
            N=N,
        )
        return SubstrateRealization(
            substrate_id=self.id,
            N=N,
            lambda_=lambda_,
            seed=seed,
            K_baseline=K_baseline,
            K_precursor=K_precursor,
            K_c=K_c,
            density=density,
            spectral_radius_over_N=spec_b,
            spectral_radius_over_N_precursor=spec_p,
            precursor_frobenius_delta=delta,
        )


# ---------------------------------------------------------------------------
# S3: Temporal K(t) modulation on a block-structured base
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TemporalKtSubstrate:
    """Block-structured base + deterministic sinusoidal modulation.

        K(t) = K_c_baseline · (1 + 0.20 · sin(2π t / period_quarters))

    where period_quarters is the locked period of the K(t) envelope
    (default 4 quarters → one full cycle per year). The amplitude
    0.20 is the locked modulation depth; the spectral radius
    averaged over the period equals the base block-structured
    radius (sinusoid integrates to zero over a full period).

    Precursor: a constant additive lift on the baseline envelope
    during the 2Q pre-event window, scaled by lambda_. The
    precursor and the sinusoid are orthogonal mechanisms (additive),
    not multiplicative — they probe distinct physical effects.
    """

    period_quarters: int = 4
    amplitude: float = 0.20

    @property
    def id(self) -> str:
        return "temporal_coupling"

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        if N < 6:
            raise SubstrateInvalid("temporal_coupling: N must be >= 6")
        if self.period_quarters < 2:
            raise SubstrateInvalid("temporal_coupling: period_quarters must be >= 2")
        # Base structure = block substrate at λ=0 (no precursor in the base)
        base = BlockStructuredSubstrate(block_fractions=BLOCK_FRACTIONS).realize(
            N=N, lambda_=0.0, seed=seed
        )
        K_base_static = base.K_baseline[0]  # all time slices identical at λ=0
        envelope = 1.0 + self.amplitude * np.sin(
            2.0 * np.pi * np.arange(T_HORIZON) / float(self.period_quarters)
        )
        K_baseline = np.stack(
            [K_base_static * float(envelope[t]) for t in range(T_HORIZON)],
            axis=0,
        )
        K_precursor = K_baseline.copy()
        if lambda_ > 0.0:
            additive = 0.15 * lambda_ * base.K_c
            lift = np.where(K_base_static > 0, additive, 0.0)
            for t in PRECURSOR_INJECTION_WINDOW:
                K_precursor[t] = K_baseline[t] + lift
        spec_b, spec_p, delta = _enforce_calibration_gates(
            K_baseline=K_baseline,
            K_precursor=K_precursor,
            lambda_=lambda_,
            density=None,
            substrate_id=self.id,
            N=N,
        )
        return SubstrateRealization(
            substrate_id=self.id,
            N=N,
            lambda_=lambda_,
            seed=seed,
            K_baseline=K_baseline,
            K_precursor=K_precursor,
            K_c=base.K_c,
            density=base.density,
            spectral_radius_over_N=spec_b,
            spectral_radius_over_N_precursor=spec_p,
            precursor_frobenius_delta=delta,
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


ALL_SUBSTRATES: Final[tuple[Substrate, ...]] = (
    RicciFlowSubstrate(),
    BlockStructuredSubstrate(),
    TemporalKtSubstrate(),
)

SUBSTRATE_BY_ID: Final[dict[str, Substrate]] = {s.id: s for s in ALL_SUBSTRATES}


__all__ = [
    "T_HORIZON",
    "EVENT_QUARTER",
    "PRE_EVENT_START_QUARTER",
    "PRE_EVENT_WINDOW",
    "PRECURSOR_INJECTION_WINDOW",
    "DENSITY_RANGE",
    "SPECTRAL_RANGE",
    "PRECURSOR_SPECTRAL_RANGE",
    "DEFAULT_ER_DENSITY",
    "BLOCK_FRACTIONS",
    "SubstrateInvalid",
    "SubstrateRealization",
    "Substrate",
    "RicciFlowSubstrate",
    "BlockStructuredSubstrate",
    "TemporalKtSubstrate",
    "ALL_SUBSTRATES",
    "SUBSTRATE_BY_ID",
]
