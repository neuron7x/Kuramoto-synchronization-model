# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""P0-1 Codex review fix — M6 placebo MUST sample off the original support.

Attack
------
Prior to this patch, ``_realize_m6`` sampled placebo edges via
``rng.choice(n_total_upper, size=n_support, replace=False)``. The pool
included the privileged ΔK support indices, so sampled placebo edges
could overlap original precursor topology. R2-B then aggregated under
a "placebo" cohort that still carried slices of the true precursor —
biasing R2-B optimistic and silently weakening the supplementary gate.

Fix
---
``_realize_m6`` now restricts the candidate pool to
``upper_triangle ∖ support_mask``. If the off-support pool has fewer
entries than the support size, the cell is REFUSED with
``M6InsufficientCandidatePool`` (fail-closed) rather than sampling
with replacement or reusing privileged sites.

Properties tested (all P0):
  1. zero-overlap with privileged support across ≥50 placebo realisations
  2. determinism: same seed → identical placebo indices
  3. seed sensitivity: different seed → likely different placebo indices
  4. insufficient pool → fail-closed (no PASS, no overlap, refusal verdict)
  5. metadata invariants: ``placebo_overlap_count == 0`` ALWAYS and
     ``placebo_overlap_forbidden == True`` ALWAYS

The test exercises the realise primitive directly through a synthetic
substrate so the support mask is known by construction.

Invariant tag: this is INFRASTRUCTURE for the D-002G null discipline.
The CLAUDE.md physics-first protocol routes ``*null*`` patterns to the
D-002G governance layer; no INV-K/INV-RC/INV-* test applies because
the synthetic K is a hand-built provenance fixture, not a Kuramoto
trajectory. The contract being checked is the support-exclusion
inferential rule, not a physical invariant.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest
from numpy.typing import NDArray

from research.systemic_risk.d002c_substrates import (
    PRECURSOR_INJECTION_WINDOW,
    SubstrateRealization,
)
from research.systemic_risk.d002g_null_mechanisms import (
    M6_PLACEBO_SALT,
    M6InsufficientCandidatePool,
    deterministic_mix,
    realize_null,
)

# 50-trial statistical battery against M6 support leakage — gate behind `slow`
# so python-fast-tests stays under its 20-min cap. Strike acceptor's
# measurement_command runs without the `-m "not slow"` filter.
pytestmark = pytest.mark.slow

# ---------------------------------------------------------------------------
# Synthetic substrate with a HAND-PINNED support mask.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SyntheticM6Substrate:
    """Substrate whose ΔK support is fixed by construction.

    Implements the minimal :class:`research.systemic_risk.d002c_substrates.Substrate`
    interface: ``id``, ``version``, ``realize(N, lambda_, seed)``. The
    realisation broadcasts a static K across the T_HORIZON axis so the
    M6 sampler reads the same K_p / K_0 at every time index.

    Parameters control the placebo's combinatorial properties:

      * ``support_indices_in_upper_tri`` — exact set of upper-triangle
        indices where ΔK is nonzero. The M6 sampler MUST sample only
        OFF this set.
      * ``support_magnitude`` — value placed at each support edge.
    """

    N: int
    support_indices_in_upper_tri: tuple[int, ...]
    support_magnitude: float = 0.7
    id: str = "synthetic_m6_substrate"
    version: str = "test_v1"

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        if N != self.N:
            raise ValueError(f"synthetic substrate fixed to N={self.N}, got {N}")
        K_0 = self._build_K0(N)
        if lambda_ <= 0.0:
            # Baseline: no precursor injection — K_precursor mirrors baseline.
            K_p = K_0.copy()
        else:
            K_p = self._build_Kp(K_0, lambda_)
        T = 8  # canonical T_HORIZON in d002c_substrates
        K_0_traj = np.broadcast_to(K_0[None, :, :], (T, N, N)).astype(np.float64)
        K_p_traj = np.broadcast_to(K_p[None, :, :], (T, N, N)).astype(np.float64)
        # SubstrateRealization is locked by d002c_substrates; the test
        # synthetic only needs the fields the M6 sampler reads
        # (K_baseline, K_precursor). The remaining fields are filled
        # with values that satisfy the dataclass contract but are
        # irrelevant to this test's invariants (we bypass the
        # ``Substrate`` calibration gates by going directly through
        # ``realize_null`` → ``_realize_m6`` and reading K_baseline /
        # K_precursor slices).
        return SubstrateRealization(
            substrate_id=self.id,
            N=int(N),
            lambda_=float(lambda_),
            seed=int(seed),
            K_baseline=K_0_traj,
            K_precursor=K_p_traj,
            K_c=1.0,
            density=0.5,
            spectral_radius_over_N=1.0,
            spectral_radius_over_N_precursor=1.0,
            precursor_frobenius_delta=float(np.linalg.norm(K_p_traj - K_0_traj)),
        )

    def _build_K0(self, N: int) -> NDArray[np.float64]:
        # Baseline: tiny off-diagonal Erdős–Rényi-style scaffolding so K_0
        # is not exactly zero (matches non-degenerate substrates).
        # Deterministic — no RNG; we want the realisation pinned.
        K = np.zeros((N, N), dtype=np.float64)
        # Add a thin baseline so K_0 is not all-zero.
        for i in range(N - 1):
            K[i, i + 1] = 0.05
            K[i + 1, i] = 0.05
        return K

    def _build_Kp(self, K_0: NDArray[np.float64], lambda_: float) -> NDArray[np.float64]:
        N = K_0.shape[0]
        iu_r, iu_c = np.triu_indices(N, k=1)
        n_upper = iu_r.size
        K_p = K_0.copy()
        delta_upper = np.zeros(n_upper, dtype=np.float64)
        for idx in self.support_indices_in_upper_tri:
            if idx < 0 or idx >= n_upper:
                raise ValueError(f"support index {idx} out of range for N={N}")
            delta_upper[idx] = float(self.support_magnitude * lambda_)
        delta = np.zeros_like(K_0)
        delta[iu_r, iu_c] = delta_upper
        delta = delta + delta.T  # symmetrize
        return K_p + delta


def _placebo_upper_indices(K_p_minus_K_0_placebo: NDArray[np.float64], N: int) -> set[int]:
    iu_r, iu_c = np.triu_indices(N, k=1)
    upper = K_p_minus_K_0_placebo[iu_r, iu_c]
    return {int(i) for i in np.flatnonzero(np.abs(upper) > 1e-12)}


# ---------------------------------------------------------------------------
# Property 1: zero-overlap with privileged support across ≥50 trials.
# ---------------------------------------------------------------------------


def test_M6_placebo_zero_overlap_across_many_trials() -> None:
    """For each of ≥50 base seeds, placebo indices ∩ support = ∅."""
    N = 12  # |upper tri| = 66
    support = tuple(range(10))  # 10 privileged sites
    sub = _SyntheticM6Substrate(N=N, support_indices_in_upper_tri=support)
    support_set = set(support)

    trials = 60
    for s in range(trials):
        real = realize_null(
            sub,
            strategy="M6_PLACEBO_COUPLING",
            base_seed=s,
            N=N,
            lambda_value=0.5,
        )
        K_0 = sub._build_K0(N)
        placebo_delta = real.K_baseline - K_0
        placebo_idx = _placebo_upper_indices(placebo_delta, N)
        overlap = placebo_idx & support_set
        assert overlap == set(), (
            f"P0-1 VIOLATED: trial {s}/{trials} produced overlap "
            f"{sorted(overlap)} between placebo indices and privileged "
            f"support indices {sorted(support_set)}. Support exclusion "
            f"is not honoured by _realize_m6."
        )
        assert int(real.metadata["placebo_overlap_count"]) == 0, (
            f"P0-1 VIOLATED: metadata.placebo_overlap_count = "
            f"{real.metadata['placebo_overlap_count']} != 0 at trial {s}."
        )


# ---------------------------------------------------------------------------
# Property 2: determinism — same seed → identical placebo indices.
# ---------------------------------------------------------------------------


def test_M6_placebo_deterministic_for_fixed_seed() -> None:
    N = 10
    support = (0, 3, 7, 11)
    sub = _SyntheticM6Substrate(N=N, support_indices_in_upper_tri=support)

    a = realize_null(sub, strategy="M6_PLACEBO_COUPLING", base_seed=42, N=N, lambda_value=0.5)
    b = realize_null(sub, strategy="M6_PLACEBO_COUPLING", base_seed=42, N=N, lambda_value=0.5)

    K_0 = sub._build_K0(N)
    idx_a = _placebo_upper_indices(a.K_baseline - K_0, N)
    idx_b = _placebo_upper_indices(b.K_baseline - K_0, N)
    assert idx_a == idx_b, (
        "P0-1 VIOLATED: same base_seed produced different placebo index "
        f"sets a={sorted(idx_a)} b={sorted(idx_b)}. _realize_m6 must be "
        "deterministic under deterministic_mix seeding."
    )
    # Payload sha must also match (content-addressed identity).
    sha_msg = (
        "P0-1 VIOLATED: same seed → different payload_sha256; M6 RNG seeding has lost determinism."
    )
    assert a.payload_sha256 == b.payload_sha256, sha_msg


# ---------------------------------------------------------------------------
# Property 3: seed sensitivity — different seed → likely different indices.
# ---------------------------------------------------------------------------


def test_M6_placebo_different_seeds_likely_differ() -> None:
    N = 12
    support = (0, 5, 9, 14, 20)
    sub = _SyntheticM6Substrate(N=N, support_indices_in_upper_tri=support)

    seeds = [1, 7, 11, 19, 23, 41]
    idx_sets: list[frozenset[int]] = []
    K_0 = sub._build_K0(N)
    for s in seeds:
        r = realize_null(sub, strategy="M6_PLACEBO_COUPLING", base_seed=s, N=N, lambda_value=0.5)
        idx_sets.append(frozenset(_placebo_upper_indices(r.K_baseline - K_0, N)))

    # At least 2 distinct sets across this small grid — not a strict
    # 100% spec but a sanity gate against silent collapse to a single
    # placebo realisation across all seeds.
    unique = len(set(idx_sets))
    assert unique >= 2, (
        f"P0-1 VIOLATED: across seeds {seeds} only {unique} unique "
        "placebo index sets; M6 RNG seeding may have collapsed."
    )

    # deterministic_mix(base_seed, M6_PLACEBO_SALT) MUST produce
    # distinct seeds across these base_seeds.
    mixed = [deterministic_mix(s, M6_PLACEBO_SALT) for s in seeds]
    mix_msg = f"P0-1 VIOLATED: deterministic_mix collisions across seeds {seeds}: mixed={mixed}"
    assert len(set(mixed)) == len(mixed), mix_msg


# ---------------------------------------------------------------------------
# Property 4: insufficient pool → fail-closed (no overlap, no PASS).
# ---------------------------------------------------------------------------


def test_M6_placebo_refuses_when_support_exceeds_off_support_pool() -> None:
    """Force |support| > |upper_triangle ∖ support| → must raise.

    For N=4 the upper triangle has 6 entries. If support = 5 of those,
    the off-support pool has 1 entry but |support|=5 > 1. The realiser
    MUST refuse fail-closed with M6InsufficientCandidatePool. It MUST
    NOT (a) silently allow overlap, (b) sample with replacement, or
    (c) return a degenerate placebo == baseline.
    """
    N = 4  # |upper tri| = 6
    support = (0, 1, 2, 3, 4)  # 5/6 sites privileged → off-pool size = 1
    sub = _SyntheticM6Substrate(N=N, support_indices_in_upper_tri=support)
    with pytest.raises(M6InsufficientCandidatePool):
        realize_null(
            sub,
            strategy="M6_PLACEBO_COUPLING",
            base_seed=0,
            N=N,
            lambda_value=0.5,
        )


# ---------------------------------------------------------------------------
# Property 5: metadata invariants — placebo_overlap_count == 0 ALWAYS;
# placebo_overlap_forbidden == True ALWAYS; null_strategy stamped.
# ---------------------------------------------------------------------------


def test_M6_metadata_records_overlap_zero_and_forbidden_true() -> None:
    N = 10
    support = (0, 2, 4, 8)
    sub = _SyntheticM6Substrate(N=N, support_indices_in_upper_tri=support)
    for s in range(0, 30):
        r = realize_null(sub, strategy="M6_PLACEBO_COUPLING", base_seed=s, N=N, lambda_value=0.7)
        md = r.metadata
        assert int(md.get("placebo_overlap_count", -1)) == 0, (
            f"P0-1 VIOLATED: seed {s}: placebo_overlap_count = "
            f"{md.get('placebo_overlap_count')} ≠ 0"
        )
        assert bool(md.get("placebo_overlap_forbidden")) is True, (
            f"P0-1 VIOLATED: seed {s}: placebo_overlap_forbidden = "
            f"{md.get('placebo_overlap_forbidden')!r} (must be True)"
        )
        assert md.get("null_strategy") == "M6_PLACEBO_COUPLING", (
            f"P0-1 VIOLATED: seed {s}: null_strategy = "
            f"{md.get('null_strategy')!r} (expected 'M6_PLACEBO_COUPLING')"
        )
        assert int(md.get("original_support_count", -1)) == int(
            md.get("placebo_support_count", -1)
        ), (
            f"P0-1 VIOLATED: seed {s}: support_count mismatch "
            f"orig={md.get('original_support_count')} "
            f"placebo={md.get('placebo_support_count')}"
        )
        # Sanity: candidate_pool_size must be ≥ placebo_support_count.
        cps = int(md.get("candidate_pool_size", -1))
        psc = int(md.get("placebo_support_count", -1))
        cps_msg = (
            f"P0-1 VIOLATED: seed {s}: candidate_pool_size={cps} < placebo_support_count={psc}"
        )
        assert cps >= psc, cps_msg


# ---------------------------------------------------------------------------
# Sanity: PRECURSOR_INJECTION_WINDOW is non-empty (regression guard).
# ---------------------------------------------------------------------------


def test_precursor_injection_window_non_empty() -> None:
    """Sanity: the locked PRECURSOR_INJECTION_WINDOW must be non-empty.

    The M6 sampler reads ``inject_t = int(next(iter(PRECURSOR_INJECTION_WINDOW)))``;
    an empty window would crash before the support-exclusion logic
    runs. This guard keeps the contract observable.
    """
    window_msg = (
        "PRECURSOR_INJECTION_WINDOW is empty; M6 placebo cannot index a precursor injection time."
    )
    assert len(PRECURSOR_INJECTION_WINDOW) > 0, window_msg
