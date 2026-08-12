# SPDX-License-Identifier: MIT
"""Falsification battery for LAW T6: bit-identical reproducibility kit.

Invariants under test:
* INV-DET1 | universal | identical canonical inputs ⇒ identical state_hash.
* INV-DET2 | universal | 1-ULP perturbation ⇒ different state_hash.
* INV-DET3 | universal | every contract violation → ValueError.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.physics.determinism_kit import (
    ReplayManifest,
    canonicalize_state,
    state_hash,
    trajectory_hash,
    verify_replay,
)

# ── INV-DET1: identical inputs ⇒ identical hash ─────────────────────────────


def test_INV_DET1_identical_states_hash_identically() -> None:
    """100 random states: hash is stable on repeat (same array object)."""
    rng = np.random.default_rng(seed=0)
    for _ in range(100):
        x = rng.normal(0, 1.0, size=8).astype(np.float64)
        assert state_hash(x) == state_hash(x)


def test_INV_DET1_canonicalisation_collapses_all_NaN_patterns() -> None:
    """Quiet-NaN, signalling-NaN, and signed-NaN hash identically.

    Without canonicalisation, IEEE-754 has 2**52 NaN bit-patterns —
    each would produce a distinct hash even though they all denote
    "not-a-number". This test pins the collapse.
    """
    qnan = np.array([np.float64(np.nan)], dtype=np.float64)
    snan = np.frombuffer(np.uint64(0x7FF7FFFFFFFFFFFF).tobytes(), dtype=np.float64)
    neg_nan = np.array([-np.float64(np.nan)], dtype=np.float64)
    h_qnan = state_hash(qnan)
    h_snan = state_hash(snan)
    h_neg_nan = state_hash(neg_nan)
    assert h_qnan == h_snan == h_neg_nan, (
        f"INV-DET1 VIOLATED: distinct NaN bit-patterns hash differently. "
        f"qNaN={h_qnan[:8]} sNaN={h_snan[:8]} -NaN={h_neg_nan[:8]}"
    )


def test_INV_DET1_negative_zero_collapses_to_positive_zero() -> None:
    """``-0.0`` and ``+0.0`` hash identically post-canonicalisation."""
    pos = np.array([0.0, 0.0, 0.0], dtype=np.float64)
    neg = np.array([-0.0, -0.0, 0.0], dtype=np.float64)
    assert state_hash(pos) == state_hash(neg)


def test_INV_DET1_subnormal_flush_to_zero() -> None:
    """Subnormals canonicalised to +0; INV-DET1 honoured across float-classes."""
    zero = np.array([0.0], dtype=np.float64)
    # Smallest subnormal float64: 2**-1074
    subnormal = np.array([np.float64(5e-324)], dtype=np.float64)
    assert state_hash(zero) == state_hash(subnormal)


# ── INV-DET2: 1-ULP perturbation ⇒ different hash ───────────────────────────


def test_INV_DET2_single_ulp_perturbation_changes_hash() -> None:
    """A 1-ULP bump in any component flips at least one byte of SHA-256."""
    rng = np.random.default_rng(seed=42)
    for trial in range(50):
        x = rng.normal(0, 1.0, size=8).astype(np.float64)
        # Avoid hitting NaN/0 components — use absolute values + offset.
        x = np.abs(x) + 1.0
        h0 = state_hash(x)
        for i in range(x.size):
            x_pert = x.copy()
            x_pert[i] = np.nextafter(x_pert[i], np.inf)
            assert state_hash(x_pert) != h0, (
                f"INV-DET2 VIOLATED at trial {trial}, component {i}: "
                f"single-ULP bump produced identical hash"
            )


def test_INV_DET2_dtype_aliasing_blocked() -> None:
    """Same byte content in float32 vs float64 ⇒ different hashes.

    Otherwise an array of float32 zeros could collide with the first
    half of an array of float64 zeros.
    """
    f32 = np.zeros(4, dtype=np.float32)
    f64 = np.zeros(2, dtype=np.float64)  # 8 bytes each — same total size
    assert state_hash(f32) != state_hash(f64)


def test_INV_DET2_shape_aliasing_blocked() -> None:
    """Same byte content but different shape ⇒ different hashes."""
    flat = np.zeros(8, dtype=np.float64)
    matrix = np.zeros((2, 4), dtype=np.float64)
    assert state_hash(flat) != state_hash(matrix)


def test_INV_DET2_trajectory_order_sensitivity() -> None:
    """Permuting trajectory rows changes ``trajectory_hash``."""
    rng = np.random.default_rng(seed=3)
    traj = rng.normal(0, 1.0, size=(20, 6)).astype(np.float64)
    h_original = trajectory_hash(traj)
    h_reversed = trajectory_hash(traj[::-1].copy())
    assert h_original != h_reversed, "INV-DET2 VIOLATED: reversed trajectory hashed identically"


# ── INV-DET3: fail-closed contracts ─────────────────────────────────────────


def test_INV_DET3_canonicalize_rejects_int_dtype() -> None:
    with pytest.raises(ValueError, match="floating dtype"):
        canonicalize_state(np.array([1, 2, 3], dtype=np.int64))


def test_INV_DET3_canonicalize_rejects_empty() -> None:
    with pytest.raises(ValueError, match="cannot canonicalise empty"):
        canonicalize_state(np.array([], dtype=np.float64))


def test_INV_DET3_canonicalize_rejects_unsupported_precision() -> None:
    with pytest.raises(ValueError, match="only float32 and float64"):
        canonicalize_state(np.array([1.0], dtype=np.float16))


def test_INV_DET3_trajectory_hash_rejects_1d() -> None:
    with pytest.raises(ValueError, match="2-D array"):
        trajectory_hash(np.zeros(8, dtype=np.float64))


def test_INV_DET3_trajectory_hash_rejects_3d() -> None:
    with pytest.raises(ValueError, match="2-D array"):
        trajectory_hash(np.zeros((2, 3, 4), dtype=np.float64))


def test_INV_DET3_trajectory_hash_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty trajectory"):
        trajectory_hash(np.zeros((0, 4), dtype=np.float64))


# ── End-to-end: ReplayManifest round-trip ───────────────────────────────────


def test_replay_manifest_round_trip_succeeds_on_byte_equal_traj() -> None:
    """Sealed manifest verifies byte-equal re-execution."""
    rng = np.random.default_rng(seed=11)
    traj = rng.normal(0, 1.0, size=(50, 4)).astype(np.float64)
    x0_h = state_hash(traj[0])
    traj_h = trajectory_hash(traj)
    manifest = ReplayManifest(
        integrator_id="midpoint-rk2/test",
        seed=11,
        dt=0.01,
        n_steps=49,
        x0_hash=x0_h,
        traj_hash=traj_h,
    )
    assert verify_replay(traj, manifest) is True


def test_replay_manifest_detects_tampered_trajectory() -> None:
    """A 1-ULP bump in any cell of the re-executed trajectory ⇒ False."""
    rng = np.random.default_rng(seed=12)
    traj = rng.normal(0, 1.0, size=(30, 5)).astype(np.float64)
    manifest = ReplayManifest(
        integrator_id="midpoint-rk2/test",
        seed=12,
        dt=0.01,
        n_steps=29,
        x0_hash=state_hash(traj[0]),
        traj_hash=trajectory_hash(traj),
    )
    tampered = traj.copy()
    tampered[7, 2] = np.nextafter(tampered[7, 2], np.inf)
    assert verify_replay(tampered, manifest) is False


# ── Negative control: canonicalisation cannot trivially erase distinctions ───


def test_negative_control_distinct_finite_values_distinct_hashes() -> None:
    """Two arrays differing in a single non-special-value component
    must produce distinct hashes.

    If canonicalisation accidentally collapsed *all* values of similar
    magnitude into one bucket, the hash would be vacuously stable. The
    negative control proves it does not.
    """
    a = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    b = np.array([1.0, 2.0, 4.0], dtype=np.float64)
    assert state_hash(a) != state_hash(b)
