# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002G-P3 — M2 injection-sequence sub-domain admissibility tests.

The injection-sequence sub-domain probes substrates whose precursor
is a discrete event sequence (a list of (t, ΔK(t)) tuples). The
verifier admits a permutation IFF the substrate has >= 2 distinct
events AND the substrate does NOT stake a lag-coupling contract on
event order (temporal_coupling does, and is REFUSED).

Honest stance: on the locked prereg grid no substrate is ELIGIBLE
under injection_sequence. The tests verify the negative verdicts
plus the contract semantics on a synthetic substrate that DOES
expose a non-degenerate sequence.

Scope discipline
----------------
Infrastructure tests only. No canonical sweep. No D-002G PASS claim.
No ledger mutation.
"""

from __future__ import annotations

import numpy as np
import pytest

from research.systemic_risk.d002c_substrates import (
    SUBSTRATE_BY_ID,
    T_HORIZON,
    Substrate,
    SubstrateInvalid,
    SubstrateRealization,
)
from research.systemic_risk.d002g_null_mechanisms import (
    M2_INJECTION_SEQUENCE_SALT,
    M2NotEligibleError,
    realize_m2_injection_sequence_null,
    realize_null,
    verify_m2_injection_sequence_eligibility,
)

_FAST_N = 50
_LAMBDA = 0.4
_BASE_SEED = 42
_NULL_SEED = 12345


def _ricci() -> Substrate:
    return SUBSTRATE_BY_ID["ricci_flow"]


def _block() -> Substrate:
    return SUBSTRATE_BY_ID["block_structured"]


def _temporal() -> Substrate:
    return SUBSTRATE_BY_ID["temporal_coupling"]


class _SyntheticInjectionSequenceSubstrate:
    """Substrate with admissible (non-degenerate) injection-event sequence.

    Emits N×N coupling with PRECURSOR_INJECTION_WINDOW = {4, 5}. The
    two events differ in magnitude (event at t=4 is 1×, at t=5 is
    2×) but share the same support topology. ID is NOT
    'temporal_coupling' so the contract-violation gate does not fire.
    """

    @property
    def id(self) -> str:
        return "synthetic_injection_sequence_admissible"

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        if N < 4:
            raise SubstrateInvalid("synthetic: N must be >= 4")
        M = np.ones((N, N), dtype=np.float64)
        np.fill_diagonal(M, 0.0)
        lam = float(np.abs(np.linalg.eigvalsh(M)).max())
        K_c = float(N) / lam
        K_static = M * K_c
        K_baseline = np.broadcast_to(K_static, (T_HORIZON, N, N)).astype(np.float64).copy()
        K_precursor = K_baseline.copy()
        if lambda_ > 0.0:
            base_lift = 0.05 * lambda_ * K_c * np.where(K_static > 0, 1.0, 0.0)
            # Two distinct events at t=4 (×1) and t=5 (×2)
            K_precursor[4] = K_baseline[4] + base_lift
            K_precursor[5] = K_baseline[5] + 2.0 * base_lift
        _ = seed
        spec_b = float(
            np.mean([np.abs(np.linalg.eigvalsh(K_baseline[t])).max() for t in range(T_HORIZON)])
        ) / float(N)
        spec_p = float(
            np.mean([np.abs(np.linalg.eigvalsh(K_precursor[t])).max() for t in range(T_HORIZON)])
        ) / float(N)
        delta = float(np.linalg.norm(K_precursor - K_baseline))
        return SubstrateRealization(
            substrate_id=self.id,
            N=N,
            lambda_=lambda_,
            seed=seed,
            K_baseline=K_baseline,
            K_precursor=K_precursor,
            K_c=K_c,
            density=1.0,
            spectral_radius_over_N=spec_b,
            spectral_radius_over_N_precursor=spec_p,
            precursor_frobenius_delta=delta,
        )


class _SingleEventSubstrate:
    """Substrate that injects at only one time slice → MISSING_DOMAIN."""

    @property
    def id(self) -> str:
        return "synthetic_single_event_injection"

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        M = np.ones((N, N), dtype=np.float64)
        np.fill_diagonal(M, 0.0)
        lam = float(np.abs(np.linalg.eigvalsh(M)).max())
        K_c = float(N) / lam
        K_static = M * K_c
        K_baseline = np.broadcast_to(K_static, (T_HORIZON, N, N)).astype(np.float64).copy()
        K_precursor = K_baseline.copy()
        if lambda_ > 0.0:
            lift = 0.05 * lambda_ * K_c * np.where(K_static > 0, 1.0, 0.0)
            # Inject only at t=4 (single event)
            K_precursor[4] = K_baseline[4] + lift
        _ = seed
        spec_b = float(
            np.mean([np.abs(np.linalg.eigvalsh(K_baseline[t])).max() for t in range(T_HORIZON)])
        ) / float(N)
        spec_p = float(
            np.mean([np.abs(np.linalg.eigvalsh(K_precursor[t])).max() for t in range(T_HORIZON)])
        ) / float(N)
        delta = float(np.linalg.norm(K_precursor - K_baseline))
        return SubstrateRealization(
            substrate_id=self.id,
            N=N,
            lambda_=lambda_,
            seed=seed,
            K_baseline=K_baseline,
            K_precursor=K_precursor,
            K_c=K_c,
            density=1.0,
            spectral_radius_over_N=spec_b,
            spectral_radius_over_N_precursor=spec_p,
            precursor_frobenius_delta=delta,
        )


class _BadProvenanceSubstrate:
    """Substrate that raises during realize() → INDETERMINATE_PROVENANCE_MISSING."""

    @property
    def id(self) -> str:
        return "synthetic_bad_provenance"

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        raise SubstrateInvalid("simulated provenance failure")


# -------------------------------------------------------------------
# 8 required tests
# -------------------------------------------------------------------


def test_p3_injection_sequence_preserves_topology_hash() -> None:
    """Realised injection-sequence null preserves per-event topology hash."""
    sub = _SyntheticInjectionSequenceSubstrate()
    v = verify_m2_injection_sequence_eligibility(
        sub, N=10, lambda_value=_LAMBDA, base_seed=_BASE_SEED, null_seed=_NULL_SEED
    )
    assert v.status == "ELIGIBLE_M2_INJECTION_SEQUENCE", v.eligibility_reason
    _K_null, meta = realize_m2_injection_sequence_null(
        sub, base_seed=_BASE_SEED, null_seed=_NULL_SEED, lambda_value=_LAMBDA, N=10
    )
    assert meta["preserved_topology_hash"] == v.preserved_topology_hash


def test_p3_injection_sequence_preserves_event_multiset() -> None:
    """Permuted sequence has the same event-magnitude multiset."""
    sub = _SyntheticInjectionSequenceSubstrate()
    from research.systemic_risk.d002g_null_mechanisms import _extract_injection_sequence

    _b, _p, events, _t = _extract_injection_sequence(
        sub, base_seed=_BASE_SEED, lambda_value=_LAMBDA, N=10
    )
    orig_norms = sorted(float(np.linalg.norm(e)) for e in events)
    _K_null, meta = realize_m2_injection_sequence_null(
        sub, base_seed=_BASE_SEED, null_seed=_NULL_SEED, lambda_value=_LAMBDA, N=10
    )
    # The realisation emits the first permuted event as the static K_null;
    # the multiset of |events| is preserved by construction (permutation).
    perm_order = meta["event_order_permutation"]
    permuted_norms = sorted(float(np.linalg.norm(events[i])) for i in perm_order)
    assert permuted_norms == orig_norms


def test_p3_injection_sequence_changes_order_when_admissible() -> None:
    """ELIGIBLE realisation actually emits a non-identity ordering (probabilistic)."""
    sub = _SyntheticInjectionSequenceSubstrate()
    # 2-event permutations have 2 outcomes; with locked seed the order
    # is deterministic — check the permutation is one of the 2 valid
    # orderings, and that for SOME seeds it differs from identity.
    found_non_identity = False
    for seed_override in (1, 2, 3, 4, 5, 6, 7, 8):
        _K, meta = realize_m2_injection_sequence_null(
            sub, base_seed=_BASE_SEED, null_seed=seed_override, lambda_value=_LAMBDA, N=10
        )
        if list(meta["event_order_permutation"]) != [0, 1]:
            found_non_identity = True
            break
    assert found_non_identity, "no non-identity permutation found in 8 seeds"


def test_p3_injection_sequence_same_seed_bit_identical() -> None:
    """Same (base_seed, null_seed) yields bit-identical K_null."""
    sub = _SyntheticInjectionSequenceSubstrate()
    K1, m1 = realize_m2_injection_sequence_null(
        sub, base_seed=_BASE_SEED, null_seed=_NULL_SEED, lambda_value=_LAMBDA, N=10
    )
    K2, m2 = realize_m2_injection_sequence_null(
        sub, base_seed=_BASE_SEED, null_seed=_NULL_SEED, lambda_value=_LAMBDA, N=10
    )
    assert np.array_equal(K1, K2)
    assert m1["event_order_permutation"] == m2["event_order_permutation"]


def test_p3_injection_sequence_different_seed_diverges_when_admissible() -> None:
    """Different null_seed eventually yields different permutation."""
    sub = _SyntheticInjectionSequenceSubstrate()
    perms: set[tuple[int, ...]] = set()
    for ns in range(50):
        _K, meta = realize_m2_injection_sequence_null(
            sub, base_seed=_BASE_SEED, null_seed=ns, lambda_value=_LAMBDA, N=10
        )
        perms.add(tuple(meta["event_order_permutation"]))
    assert len(perms) >= 2, f"single permutation across 50 seeds: {perms}"


def test_p3_injection_sequence_fails_closed_on_single_event() -> None:
    """Substrate with 1 event in window → MISSING_DOMAIN."""
    sub = _SingleEventSubstrate()
    v = verify_m2_injection_sequence_eligibility(
        sub, N=10, lambda_value=_LAMBDA, base_seed=_BASE_SEED, null_seed=_NULL_SEED
    )
    assert v.status == "INELIGIBLE_M2_INJECTION_SEQUENCE_MISSING_DOMAIN", v.eligibility_reason


def test_p3_injection_sequence_fails_closed_on_contract_violation() -> None:
    """temporal_coupling staked lag-coupling contract → CONTRACT_VIOLATION."""
    sub = _temporal()
    v = verify_m2_injection_sequence_eligibility(
        sub, N=_FAST_N, lambda_value=_LAMBDA, base_seed=_BASE_SEED, null_seed=_NULL_SEED
    )
    assert v.status == "INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION", v.eligibility_reason
    assert v.metadata["contract"] == "sinusoidal_envelope_times_injection_window"


def test_p3_injection_sequence_rejects_missing_provenance() -> None:
    """Substrate that raises during realize() → INDETERMINATE_PROVENANCE_MISSING."""
    sub = _BadProvenanceSubstrate()
    v = verify_m2_injection_sequence_eligibility(
        sub, N=10, lambda_value=_LAMBDA, base_seed=_BASE_SEED, null_seed=_NULL_SEED
    )
    expected = "INDETERMINATE_M2_INJECTION_SEQUENCE_PROVENANCE_MISSING"
    assert v.status == expected, v.eligibility_reason


# -------------------------------------------------------------------
# Additional dispatch & salt checks
# -------------------------------------------------------------------


def test_p3_injection_sequence_salt_is_locked_prime_distinct() -> None:
    """M2_INJECTION_SEQUENCE_SALT == 419 and is distinct from siblings."""
    from research.systemic_risk.d002g_null_mechanisms import (
        M2_NODE_PAYLOAD_SALT,
        M2_PLACEBO_SALT,
    )

    assert M2_INJECTION_SEQUENCE_SALT == 419
    assert M2_INJECTION_SEQUENCE_SALT != M2_PLACEBO_SALT
    assert M2_INJECTION_SEQUENCE_SALT != M2_NODE_PAYLOAD_SALT


def test_p3_injection_sequence_realize_null_dispatch_routes() -> None:
    """realize_null(shuffle_domain='injection_sequence') routes to inj-seq path."""
    sub = _SyntheticInjectionSequenceSubstrate()
    real = realize_null(
        sub,
        strategy="M2_TOPOLOGY_PRESERVING_SHUFFLE",
        base_seed=_BASE_SEED,
        N=10,
        lambda_value=_LAMBDA,
        null_seed=_NULL_SEED,
        shuffle_domain="injection_sequence",
    )
    assert real.metadata["shuffle_domain"] == "injection_sequence"
    assert real.metadata["eligibility_status"] == "ELIGIBLE_M2_INJECTION_SEQUENCE"


def test_p3_injection_sequence_dispatch_fails_closed_on_prereg_substrates() -> None:
    """Prereg substrates fail-closed under injection_sequence dispatch."""
    for sub in (_ricci(), _block(), _temporal()):
        with pytest.raises(M2NotEligibleError):
            realize_null(
                sub,
                strategy="M2_TOPOLOGY_PRESERVING_SHUFFLE",
                base_seed=_BASE_SEED,
                N=_FAST_N,
                lambda_value=_LAMBDA,
                null_seed=_NULL_SEED,
                shuffle_domain="injection_sequence",
            )
