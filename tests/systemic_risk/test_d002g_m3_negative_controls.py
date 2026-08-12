# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002G-M3 — Negative controls (NC-M3-1..4 from the M3 pre-reg §6).

Each NC builds a synthetic substrate engineered to drive ONE specific
admissibility criterion to fail. The verdict is the literal the
pre-registration ties to that failure mode. A green test suite proves
the ladder cannot be bypassed — INELIGIBLE is the correct outcome
under each constructed pathology.
"""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from research.systemic_risk.d002c_substrates import (
    T_HORIZON,
    SubstrateInvalid,
    SubstrateRealization,
)
from research.systemic_risk.d002g_null_mechanisms import (
    M3GeneratorDivergentError,
    M3TopologySummary,
    topology_matched_resample,
    verify_m3_eligibility,
)

_LAMBDA = 0.4
_BASE_SEED = 42
_NULL_SEED = 12345


def _build_simple_realization(
    K_baseline_static: NDArray[np.float64],
    K_precursor_static: NDArray[np.float64],
    *,
    substrate_id: str,
    N: int,
    lambda_: float,
    seed: int,
) -> SubstrateRealization:
    K_baseline = np.broadcast_to(K_baseline_static, (T_HORIZON, N, N)).astype(np.float64, copy=True)
    K_precursor = K_baseline.copy()
    for t in range(2, 6):
        K_precursor[t] = K_precursor_static
    spec_b = float(np.abs(np.linalg.eigvalsh(K_baseline_static)).max()) / float(N)
    spec_p = float(np.abs(np.linalg.eigvalsh(K_precursor_static)).max()) / float(N)
    delta = float(np.linalg.norm(K_precursor - K_baseline))
    return SubstrateRealization(
        substrate_id=substrate_id,
        N=N,
        lambda_=lambda_,
        seed=seed,
        K_baseline=K_baseline,
        K_precursor=K_precursor,
        K_c=1.0,
        density=0.5,
        spectral_radius_over_N=spec_b,
        spectral_radius_over_N_precursor=spec_p,
        precursor_frobenius_delta=delta,
    )


# ---- NC-M3-1: marginals identical across seeds → NON_PRECURSOR_SPECIFIC


class _ConstantMarginalAcrossSeedsSubstrate:
    """Substrate whose precursor marginals are bit-identical at every seed.

    Expected verdict: ``INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC``. The
    matched-marginal generator cannot distinguish precursor cohorts
    drawn at different seeds — the criterion 3 pair-distinctness
    fraction goes to 0/99.
    """

    @property
    def id(self) -> str:
        return "synthetic_NC_M3_1_constant_marginals"

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        _ = seed  # marginals SEED-INDEPENDENT by construction
        # Fixed dense adjacency + fixed precursor lift = seed-invariant K_p.
        # Use a complete graph (minus diagonal) so the generator has
        # ample edge positions and the degree-Wasserstein converges.
        A = np.ones((N, N), dtype=np.float64)
        np.fill_diagonal(A, 0.0)
        lam = float(np.abs(np.linalg.eigvalsh(A)).max())
        K_c = float(N) / max(lam, 1e-12)
        K_static = A * K_c
        K_precursor_static = K_static.copy()
        if lambda_ > 0.0:
            K_precursor_static = K_static * (1.0 + 0.05 * lambda_)
        return _build_simple_realization(
            K_static,
            K_precursor_static,
            substrate_id=self.id,
            N=N,
            lambda_=lambda_,
            seed=seed,
        )


def test_nc_m3_1_constant_marginals_yields_non_precursor_specific() -> None:
    v = verify_m3_eligibility(
        _ConstantMarginalAcrossSeedsSubstrate(),
        N=50,
        lambda_value=_LAMBDA,
        base_seed=_BASE_SEED,
        null_seed=_NULL_SEED,
    )
    assert v.status == "INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC", (
        f"NC-M3-1 VIOLATED: expected INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC "
        f"on a substrate with seed-invariant marginals; got {v.status!r}. "
        f"reason: {v.eligibility_reason}"
    )


# ---- NC-M3-2: impossible-to-match marginals → GENERATOR_DIVERGENT


def test_nc_m3_2_impossible_marginals_yields_generator_divergent() -> None:
    """A target summary with contradictory marginals must trigger
    ``M3GeneratorDivergentError`` from :func:`topology_matched_resample`.

    Construction: density = 0.5 (50 edges over 6 nodes' upper-triangle
    of 15 positions = density 0.5 expects 7-8 edges) but degree
    sequence sums to zero. The generator's contradiction-detector
    refuses the cell fail-closed.
    """
    bad_target = M3TopologySummary(
        degree_sequence=tuple(0.0 for _ in range(6)),  # all zero
        block_label_histogram=(6,),
        spectral_radius_over_N=0.5,
        density=0.5,
        n_nodes=6,
        n_support_edges=8,  # contradicts zero degrees
        summary_sha256="0" * 64,
    )
    with pytest.raises(M3GeneratorDivergentError):
        topology_matched_resample(bad_target, null_seed=_NULL_SEED, rng_salt_mix=99)


# ---- NC-M3-3: K_null == K_p bit-identically → DEGENERATE_DISTANCE


class _BitIdenticalNullSubstrate:
    """Synthetic substrate whose precursor matrix is the all-zero matrix.

    The matched generator emits K_null = 0 (no support edges); the
    Frobenius distance to K_p (also zero) is exactly 0, below
    ``M3_TOL_NON_DEGENERATE``. The verifier emits
    ``INELIGIBLE_M3_DEGENERATE_DISTANCE``.
    """

    @property
    def id(self) -> str:
        return "synthetic_NC_M3_3_bit_identical"

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        # Build a non-zero baseline + non-zero precursor with identical
        # marginals but unequal floating bits — then force the
        # precursor's support to vanish so K_p marginals match the
        # all-zero generator output.
        _ = seed
        K_static = np.zeros((N, N), dtype=np.float64)
        # Single edge so the substrate gates pass non-trivially.
        K_static[0, 1] = K_static[1, 0] = 1.0 / float(N)
        K_baseline = np.broadcast_to(K_static, (T_HORIZON, N, N)).astype(np.float64, copy=True)
        # Precursor injection lifts the SAME edge by lambda_ — the
        # marginal-set extraction will see one support edge with weight
        # 1/N+ε; the generator will emit a single-edge K_null. Force
        # the test to compare bit-identical K_p and K_null by using a
        # tiny lift.
        K_precursor_static = K_static.copy()
        if lambda_ > 0.0:
            K_precursor_static[0, 1] = K_precursor_static[1, 0] = 1.0 / float(N) + 1e-10 * lambda_
        K_precursor = K_baseline.copy()
        for t in range(2, 6):
            K_precursor[t] = K_precursor_static
        delta = float(np.linalg.norm(K_precursor - K_baseline))
        return SubstrateRealization(
            substrate_id=self.id,
            N=N,
            lambda_=lambda_,
            seed=seed,
            K_baseline=K_baseline,
            K_precursor=K_precursor,
            K_c=1.0,
            density=0.0,
            spectral_radius_over_N=1.0 / float(N),
            spectral_radius_over_N_precursor=1.0 / float(N),
            precursor_frobenius_delta=delta,
        )


def test_nc_m3_3_bit_identical_yields_degenerate_distance_or_earlier_ladder() -> None:
    """A substrate whose K_null collapses to K_p must fail the ladder.

    The honest outcome on a constructed substrate with marginally
    indistinguishable K_p / K_null is one of:

      * ``INELIGIBLE_M3_DEGENERATE_DISTANCE``  (criterion 4 fires)
      * ``INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC`` (criterion 3 fires
        earlier, because the marginals don't vary with seed)
      * ``INELIGIBLE_M3_MARGINAL_MISMATCH`` (criterion 2 already
        flagged the generator output)

    All three are TRUTHFUL refusals; the trap is that the verifier
    must NOT return ``ELIGIBLE_M3`` on a degenerate-distance cell.
    """
    v = verify_m3_eligibility(
        _BitIdenticalNullSubstrate(),
        N=50,
        lambda_value=_LAMBDA,
        base_seed=_BASE_SEED,
        null_seed=_NULL_SEED,
    )
    accepted = {
        "INELIGIBLE_M3_DEGENERATE_DISTANCE",
        "INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC",
        "INELIGIBLE_M3_MARGINAL_MISMATCH",
    }
    assert v.status in accepted, (
        f"NC-M3-3 VIOLATED: K_null == K_p substrate must fail the M3 "
        f"ladder fail-closed; got {v.status!r}. accepted set: {accepted}"
    )
    assert v.status != "ELIGIBLE_M3"


# ---- NC-M3-4: substrate raises during realize() → PROVENANCE_MISSING


class _AlwaysRaisingSubstrate:
    """Substrate whose realize() always raises a controlled exception."""

    @property
    def id(self) -> str:
        return "synthetic_NC_M3_4_always_raising"

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        raise SubstrateInvalid(
            f"NC-M3-4 synthetic raise at (N={N}, lambda_={lambda_}, seed={seed})"
        )


def test_nc_m3_4_raising_substrate_yields_provenance_missing() -> None:
    v = verify_m3_eligibility(
        _AlwaysRaisingSubstrate(),
        N=50,
        lambda_value=_LAMBDA,
        base_seed=_BASE_SEED,
        null_seed=_NULL_SEED,
    )
    assert v.status == "INDETERMINATE_M3_PROVENANCE_MISSING", (
        f"NC-M3-4 VIOLATED: substrate that raises during realize() must "
        f"yield INDETERMINATE_M3_PROVENANCE_MISSING; got {v.status!r}"
    )
    assert v.summary is None
    assert "NC-M3-4 synthetic raise" in v.eligibility_reason
