# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the X-10R-2 reciprocity-aware controls (GH issue #636).

Closes the FIX B6 debt from PR #635: the density-only sweep is
extended to a (reciprocity × density) grid, the substrate generators
expose a `reciprocity_keep_p` parameter, and
`run_reciprocity_aware_recovery` walks the grid producing a
`ReciprocityAwareRecoveryCertificate` whose `tested_at_reciprocity`
is non-empty.

These tests pin three contracts:
  1. The substrate generators preserve their previous behaviour at
     `reciprocity_keep_p = 1.0` (default) and reduce the achieved
     reciprocity ratio per the closed-form mapping at lower keep_p.
  2. The reciprocity-aware sweep produces an aggregate certificate
     with a non-trivial `tested_at_reciprocity` envelope when each
     cell's Gate-5 sweep passes.
  3. The mapping `reciprocity_keep_p_for_target(r) = r/(2-r)` is
     consistent with the achieved-vs-target relation observed
     empirically.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from research.reconstruction.positive_control import (
    ReciprocityAwareRecoveryCertificate,
    compute_reciprocity_ratio,
    ground_truth_core_periphery,
    ground_truth_hierarchical,
    reciprocity_keep_p_for_target,
    run_reciprocity_aware_recovery,
    run_recovery_on_substrate,
)

# ---------------------------------------------------------------------------
# Reciprocity helpers — closed-form properties
# ---------------------------------------------------------------------------


def test_compute_reciprocity_ratio_one_for_fully_bidirectional() -> None:
    """A fully bidirectional substrate has r = 1."""
    w = ground_truth_core_periphery(n=40, core_frac=0.30, seed=0)
    assert compute_reciprocity_ratio(w) == pytest.approx(1.0, abs=1e-12)


def test_compute_reciprocity_ratio_zero_for_empty() -> None:
    """No edges ⇒ r = 0 (denominator-safe)."""
    assert compute_reciprocity_ratio(np.zeros((10, 10))) == 0.0


def test_compute_reciprocity_ratio_unidirectional_chain() -> None:
    """A pure cycle 0→1→2→0 has r = 0 (no reciprocal edge)."""
    w = np.zeros((3, 3))
    w[0, 1] = 1.0
    w[1, 2] = 1.0
    w[2, 0] = 1.0
    assert compute_reciprocity_ratio(w) == 0.0


def test_compute_reciprocity_ratio_rejects_non_square() -> None:
    with pytest.raises(ValueError, match="square"):
        compute_reciprocity_ratio(np.zeros((4, 5)))


def test_keep_p_for_target_inverts_closed_form() -> None:
    """`r = 2p / (1 + p)` ⇔ `p = r / (2 - r)` over the unit interval."""
    for r_target in [0.0, 0.1, 0.3, 0.5, 0.7, 1.0]:
        p = reciprocity_keep_p_for_target(r_target)
        # Forward map.
        if r_target == 1.0:
            assert p == pytest.approx(1.0, abs=1e-12)
        elif r_target == 0.0:
            assert p == 0.0
        else:
            r_check = 2.0 * p / (1.0 + p)
            assert r_check == pytest.approx(r_target, abs=1e-12)


def test_keep_p_for_target_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        reciprocity_keep_p_for_target(-0.1)
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        reciprocity_keep_p_for_target(1.5)


# ---------------------------------------------------------------------------
# Substrate generators — reciprocity_keep_p contract
# ---------------------------------------------------------------------------


def test_cp_default_keep_p_preserves_full_reciprocity() -> None:
    """Default `reciprocity_keep_p = 1.0` ⇒ all bidirectional pairs intact."""
    w = ground_truth_core_periphery(n=60, core_frac=0.30, seed=11)
    assert compute_reciprocity_ratio(w) == pytest.approx(1.0, abs=1e-12)


def test_cp_keep_p_zero_drives_reciprocity_to_zero() -> None:
    """`reciprocity_keep_p = 0.0` ⇒ no bidirectional pairs survive."""
    w = ground_truth_core_periphery(n=60, core_frac=0.30, seed=12, reciprocity_keep_p=0.0)
    assert compute_reciprocity_ratio(w) == pytest.approx(0.0, abs=1e-12)


def test_cp_keep_p_half_lands_near_predicted_ratio() -> None:
    """`reciprocity_keep_p = 1/3` should land near `r ≈ 0.5` (closed form)."""
    keep_p = reciprocity_keep_p_for_target(0.5)
    # Average over a few seeds to dampen finite-N variance.
    achieved: list[float] = []
    for s in (1, 2, 3, 4, 5):
        w = ground_truth_core_periphery(n=120, core_frac=0.30, seed=s, reciprocity_keep_p=keep_p)
        achieved.append(compute_reciprocity_ratio(w))
    mean_achieved = float(np.mean(achieved))
    # ±0.10 envelope absorbs finite-N variance at N=120 with 5 seeds.
    assert math.isclose(
        mean_achieved, 0.5, abs_tol=0.10
    ), f"expected r ≈ 0.5, got mean(achieved)={mean_achieved:.3f} across seeds {(1, 2, 3, 4, 5)}"


def test_hierarchical_keep_p_zero_drives_reciprocity_to_zero() -> None:
    w = ground_truth_hierarchical(n=80, n_tiers=4, seed=13, reciprocity_keep_p=0.0)
    assert compute_reciprocity_ratio(w) == pytest.approx(0.0, abs=1e-12)


def test_keep_p_filter_preserves_one_edge_per_pair() -> None:
    """Filter must NOT zero out BOTH directions of a previously bidirectional
    pair — at least one edge must survive in every previously-edged pair.

    Otherwise total edge count drops too far and the substrate becomes
    disconnected on small N. This is the reason reciprocity is applied
    as a one-direction-drop, not a two-direction-drop.
    """
    rng_base = np.random.default_rng(42)
    w_full = ground_truth_core_periphery(n=40, core_frac=0.30, seed=7)
    n_pairs_before = int(((w_full > 0) & (w_full > 0).T).sum() / 2)
    # keep_p=0 ⇒ every bidirectional pair becomes unidirectional, but
    # the underlying pair STILL has at least one edge.
    w_uni = ground_truth_core_periphery(n=40, core_frac=0.30, seed=7, reciprocity_keep_p=0.0)
    n_pairs_after = int(((w_uni > 0) | (w_uni > 0).T).sum() / 2)
    assert n_pairs_after == n_pairs_before
    _ = rng_base  # keep deterministic seeding lineage explicit


# ---------------------------------------------------------------------------
# run_recovery_on_substrate — populates tested_at_reciprocity
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_run_recovery_populates_tested_reciprocity_when_passed() -> None:
    """`run_recovery_on_substrate` records the substrate's achieved
    reciprocity ratio in `tested_at_reciprocity` when Gate 5 passes."""
    w = ground_truth_core_periphery(n=80, core_frac=0.30, seed=42)
    cert = run_recovery_on_substrate("CP_80_recip", w, seed=42)
    assert cert.passed
    assert cert.tested_at_reciprocity != ()
    # Achieved reciprocity is in [0, 1].
    for r in cert.tested_at_reciprocity:
        assert 0.0 <= r <= 1.0


@pytest.mark.slow
def test_run_recovery_evidence_envelope_carries_reciprocity() -> None:
    """The certificate's evidence_envelope must surface the recorded
    reciprocity dimension when the sweep passed."""
    w = ground_truth_core_periphery(n=80, core_frac=0.30, seed=42)
    cert = run_recovery_on_substrate("CP_80_envelope", w, seed=42)
    env = cert.evidence_envelope()
    assert "reciprocity" in env
    lo, hi = env["reciprocity"]
    assert 0.0 <= lo <= hi <= 1.0


# ---------------------------------------------------------------------------
# run_reciprocity_aware_recovery — the X-10R-2 aggregate sweep
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_reciprocity_aware_sweep_passes_on_cp_substrate_at_default_grid() -> None:
    """Aggregate sweep at (r ∈ {0.30, 0.60, 1.00}) × (4-density) on CP at
    N=120 must produce a passing certificate. PR #635 substrates are
    spectrally robust enough to survive moderate reciprocity attenuation
    on the default density grid."""

    def factory(r_target: float, seed: int) -> np.ndarray:
        keep_p = reciprocity_keep_p_for_target(r_target)
        return ground_truth_core_periphery(
            n=120, core_frac=0.30, seed=seed, reciprocity_keep_p=keep_p
        )

    cert = run_reciprocity_aware_recovery(
        "CP_120_recipSweep",
        substrate_factory=factory,
        seed=42,
    )
    assert isinstance(cert, ReciprocityAwareRecoveryCertificate)
    assert cert.passed, f"reciprocity-aware sweep failed: {cert.failure_reasons}"
    assert len(cert.tested_at_reciprocity) == len(cert.target_reciprocity_grid)
    # Achieved reciprocity ratios must span a real range — not all clamped to 1.
    span = max(cert.tested_at_reciprocity) - min(cert.tested_at_reciprocity)
    assert span >= 0.4, (
        "reciprocity grid did not actually attenuate the substrate; "
        f"tested_at_reciprocity={cert.tested_at_reciprocity}"
    )


def test_reciprocity_aware_sweep_rejects_empty_grids() -> None:
    def factory(r_target: float, seed: int) -> np.ndarray:
        return ground_truth_core_periphery(n=40, seed=seed)

    with pytest.raises(ValueError, match="reciprocity_grid"):
        run_reciprocity_aware_recovery("X", substrate_factory=factory, reciprocity_grid=())
    with pytest.raises(ValueError, match="density_sweep"):
        run_reciprocity_aware_recovery("X", substrate_factory=factory, density_sweep=())


def test_reciprocity_aware_sweep_rejects_out_of_range_target() -> None:
    def factory(r_target: float, seed: int) -> np.ndarray:
        return ground_truth_core_periphery(n=40, seed=seed)

    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        run_reciprocity_aware_recovery("X", substrate_factory=factory, reciprocity_grid=(0.5, 1.5))


def test_reciprocity_aware_sweep_failed_cell_keeps_envelope_empty() -> None:
    """If ANY (r, d) cell fails, `tested_at_reciprocity` on the aggregate
    must be empty — a partial sweep cannot certify the regime."""

    # All-zero substrate fails Gate 5 trivially.
    def factory(r_target: float, seed: int) -> np.ndarray:
        return np.zeros((30, 30))

    cert = run_reciprocity_aware_recovery(
        "DEGENERATE",
        substrate_factory=factory,
        reciprocity_grid=(0.5, 1.0),
    )
    assert cert.passed is False
    assert cert.tested_at_reciprocity == ()


@pytest.mark.slow
def test_reciprocity_aware_cert_id_is_64_hex_and_seed_sensitive() -> None:
    def factory_a(r_target: float, seed: int) -> np.ndarray:
        keep_p = reciprocity_keep_p_for_target(r_target)
        return ground_truth_core_periphery(n=40, seed=seed, reciprocity_keep_p=keep_p)

    a = run_reciprocity_aware_recovery(
        "A", substrate_factory=factory_a, seed=10, reciprocity_grid=(1.0,)
    )
    b = run_reciprocity_aware_recovery(
        "A", substrate_factory=factory_a, seed=11, reciprocity_grid=(1.0,)
    )
    assert len(a.cert_id) == 64
    int(a.cert_id, 16)
    assert a.cert_id != b.cert_id
