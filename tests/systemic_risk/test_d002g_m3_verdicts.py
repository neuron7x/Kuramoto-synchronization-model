# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002G-M3 — Verdict ladder tests (one per Literal value).

Each test triggers EXACTLY one branch of the verdict ladder and
asserts the verifier emits the corresponding literal. The synthetic
substrates are tiny adversarial probes designed to drive a single
admissibility criterion to fail; the prereg-scoped substrates carry
their own truthful verdicts in
``test_d002g_m3_eligibility_matrix.py``.
"""

from __future__ import annotations

import numpy as np
import pytest

from research.systemic_risk.d002c_substrates import (
    T_HORIZON,
    BlockStructuredSubstrate,
    RicciFlowSubstrate,
    SubstrateInvalid,
    SubstrateRealization,
    TemporalKtSubstrate,
)
from research.systemic_risk.d002g_null_mechanisms import (
    M3EligibilityVerdict,
    M3NotEligibleError,
    realize_null,
    verify_m3_eligibility,
)

_LAMBDA = 0.4
_BASE_SEED = 42
_NULL_SEED = 12345


# ---- Helpers ---------------------------------------------------------


class _RaisingSubstrate:
    """Substrate whose realize() raises a controlled exception."""

    @property
    def id(self) -> str:
        return "synthetic_raising_substrate"

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        raise SubstrateInvalid(f"synthetic raise at N={N}, lambda_={lambda_}, seed={seed}")


class _ConstantMarginalSubstrate:
    """Substrate whose precursor marginals are seed-invariant.

    Triggers ``INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC`` because the
    matched-marginal generator cannot distinguish precursor cohorts
    drawn at different seeds.
    """

    @property
    def id(self) -> str:
        return "synthetic_constant_marginal"

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        # Constant pattern: every seed yields the SAME K_baseline +
        # K_precursor; precursor marginals are seed-invariant.
        _ = seed
        K_baseline_2d = np.eye(N, dtype=np.float64) * 0.0
        # Build a fixed-density adjacency pattern.
        for i in range(N - 1):
            K_baseline_2d[i, i + 1] = 1.0
            K_baseline_2d[i + 1, i] = 1.0
        lam = float(np.abs(np.linalg.eigvalsh(K_baseline_2d)).max())
        K_c = float(N) / max(lam, 1e-12)
        K_static = K_baseline_2d * K_c
        K_baseline = np.broadcast_to(K_static, (T_HORIZON, N, N)).astype(np.float64).copy()
        K_precursor = K_baseline.copy()
        if lambda_ > 0.0:
            lift = K_static * 0.10 * lambda_
            for t in range(2, 6):
                K_precursor[t] = K_static + lift
        delta = float(np.linalg.norm(K_precursor - K_baseline))
        return SubstrateRealization(
            substrate_id=self.id,
            N=N,
            lambda_=lambda_,
            seed=seed,
            K_baseline=K_baseline,
            K_precursor=K_precursor,
            K_c=K_c,
            density=2.0 / float(N - 1),
            spectral_radius_over_N=1.0,
            spectral_radius_over_N_precursor=1.0,
            precursor_frobenius_delta=delta,
        )


# ---- Verdict ladder tests --------------------------------------------


def test_verdict_eligible_m3_on_ricci_flow() -> None:
    """ricci_flow at locked grid emits ELIGIBLE_M3.

    The substrate is M1-eligible already; M3 eligibility doesn't
    upgrade its B1 status, but the verifier correctly recognises the
    substrate's precursor produces seed-distinct marginals + a
    convergent matched generator.
    """
    v = verify_m3_eligibility(
        RicciFlowSubstrate(),
        N=50,
        lambda_value=_LAMBDA,
        base_seed=_BASE_SEED,
        null_seed=_NULL_SEED,
    )
    assert v.status == "ELIGIBLE_M3", (
        f"M3-VERDICT VIOLATED: expected ELIGIBLE_M3 on ricci_flow "
        f"at locked grid; got {v.status!r}. "
        f"reason: {v.eligibility_reason}. "
        f"This is the canonical happy path; failure indicates the "
        f"verifier ladder regressed."
    )
    assert v.summary is not None
    assert v.match_report is not None
    assert v.match_report.all_within_tolerance


def test_verdict_ineligible_m3_non_precursor_specific_block_structured() -> None:
    """block_structured emits INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC.

    Its precursor lift is seed-deterministic (block-structured lift is
    identical across seeds), so the M3 marginal is not informative.
    """
    v = verify_m3_eligibility(
        BlockStructuredSubstrate(),
        N=50,
        lambda_value=_LAMBDA,
        base_seed=_BASE_SEED,
        null_seed=_NULL_SEED,
    )
    assert v.status == "INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC", (
        f"M3-VERDICT VIOLATED: expected INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC "
        f"on block_structured; got {v.status!r}. "
        f"block_structured is seed-deterministic by design — its "
        f"precursor marginals MUST collapse the precursor-specificity "
        f"criterion fail-closed."
    )


def test_verdict_ineligible_m3_non_precursor_specific_temporal_coupling() -> None:
    """temporal_coupling emits INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC.

    Same root cause as block_structured — temporal_coupling inherits
    the block_structured base and is seed-deterministic at λ>0.
    """
    v = verify_m3_eligibility(
        TemporalKtSubstrate(),
        N=50,
        lambda_value=_LAMBDA,
        base_seed=_BASE_SEED,
        null_seed=_NULL_SEED,
    )
    assert v.status == "INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC"


def test_verdict_indeterminate_m3_provenance_missing() -> None:
    """Substrate that raises during realize() → INDETERMINATE_M3_PROVENANCE_MISSING."""
    v = verify_m3_eligibility(
        _RaisingSubstrate(),
        N=50,
        lambda_value=_LAMBDA,
        base_seed=_BASE_SEED,
        null_seed=_NULL_SEED,
    )
    assert v.status == "INDETERMINATE_M3_PROVENANCE_MISSING"
    assert v.summary is None
    assert "synthetic raise" in v.eligibility_reason


def test_realize_null_m3_raises_m3_not_eligible_on_block_structured() -> None:
    """realize_null with strategy M3 fails closed on ineligible substrate."""
    with pytest.raises(M3NotEligibleError) as excinfo:
        realize_null(
            BlockStructuredSubstrate(),
            strategy="M3_TOPOLOGY_CONDITIONED",
            base_seed=_BASE_SEED,
            N=50,
            lambda_value=_LAMBDA,
            null_seed=_NULL_SEED,
        )
    verdict = excinfo.value.verdict
    assert isinstance(verdict, M3EligibilityVerdict)
    assert verdict.status == "INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC"


def test_realize_null_m3_eligible_emits_strategy_metadata() -> None:
    """realize_null with strategy M3 on ELIGIBLE substrate stamps metadata."""
    real = realize_null(
        RicciFlowSubstrate(),
        strategy="M3_TOPOLOGY_CONDITIONED",
        base_seed=_BASE_SEED,
        N=50,
        lambda_value=_LAMBDA,
        null_seed=_NULL_SEED,
    )
    assert real.strategy == "M3_TOPOLOGY_CONDITIONED"
    assert real.metadata["null_strategy"] == "M3_TOPOLOGY_CONDITIONED"
    assert real.metadata["m3_salt"] == 523
    assert real.metadata["eligibility_status"] == "ELIGIBLE_M3"
    assert "preserved_topology_summary_sha256" in real.metadata
    assert "match_report" in real.metadata
