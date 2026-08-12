# SPDX-License-Identifier: MIT
"""Sakaguchi frustration α≠0 falsifier — closes a test blind manifold.

Grounds **INV-SAK1** (`.claude/physics/INVARIANTS.yaml`, kuramoto /
sakaguchi_frustration_sign): the phase-lag enters as
``sin(θ_j(t−τ) − θ_i − α)`` (minus α), and for identical all-to-all
oscillators the phase-locked collective frequency is
``Ω = ω₀ − (N−1)·κ·sin(α)``. This invariant was registered together
with this test because its prior absence is exactly why no test
mandated α ≠ 0 coverage.

Motivation
----------
The Ott–Antonsen conjugate defect (PR #745) hid for the module's
entire history because every INV-OA test fixed ω₀ = 0 on the real
axis, the measure-zero slice where the bug is a no-op. An audit for
the same *class* of blindness found that the Sakaguchi–Kuramoto
phase-lag term ``sin(θ_j(t−τ) − θ_i(t) − α_{ij})`` — used by the real
forward integrator ``core.kuramoto.synthetic._simulate_sdde`` and by
``core/kuramoto/network_engine.py`` — had **no test exercising
α ≠ 0**. The implemented sign is canonical (verified), but a future
``−α → +α`` regression would be invisible exactly like the OA case.

This test permanently closes that manifold with a derivation-backed,
maximally discriminative invariant on the *real* integrator.

Physics
-------
For ``N`` identical oscillators (ωᵢ ≡ ω₀), all-to-all coupling
``K_{ij}=κ`` (i≠j), zero delay, uniform frustration α, zero noise, the
in-phase synchronised state (all θᵢ equal) is a fixed point of the
relative dynamics and rotates at the collective frequency::

    Ω = ω₀ + Σ_j K_{ij}·sin(θ_j − θ_i − α)|_{θ_j=θ_i}
      = ω₀ − (N−1)·κ·sin(α)              (canonical Sakaguchi −α sign)

A sign error in the phase-lag term flips this to ω₀ + (N−1)κ·sin(α).
At α = 0 both collapse to ω₀ — that is the blind manifold; the
parametrisation below pins α ≠ 0 where the two hypotheses diverge by
``2(N−1)κ·sin(α)`` (≈1.25 rad/s at the values used), far above any
integrator tolerance.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.kuramoto.synthetic import _simulate_sdde


def _collective_frequency(theta: np.ndarray, dt: float) -> float:
    """Least-squares slope of the unwrapped mean phase over the tail."""
    unwrapped = np.unwrap(theta, axis=0)
    tail = unwrapped[int(0.6 * unwrapped.shape[0]) :]
    t = np.arange(tail.shape[0], dtype=np.float64) * dt
    slope: float = float(np.polyfit(t, tail.mean(axis=1), 1)[0])
    return slope


@pytest.mark.parametrize("alpha0", [0.0, 0.4, -0.7, 1.1])
def test_sakaguchi_collective_frequency_shift_sign(alpha0: float) -> None:
    """INV-SAK1 (qualitative): Ω = ω₀ − (N−1)·κ·sin(α) on the real integrator.

    Sweeps the frustration α and checks the collective-frequency
    direction against the canonical minus-α Sakaguchi law. α = 0 is
    the explicit blind-manifold control (both sign conventions agree
    there); α ≠ 0 is the genuine INV-SAK1 falsifier.
    """
    N, kappa, omega0, dt, steps = 3, 0.8, 0.5, 0.01, 20000
    K = kappa * (np.ones((N, N)) - np.eye(N))
    tau = np.zeros((N, N), dtype=np.int64)
    alpha = alpha0 * np.ones((N, N))
    omega = omega0 * np.ones(N)
    rng = np.random.default_rng(0)

    theta, _noise = _simulate_sdde(K, tau, alpha, omega, T=steps, dt=dt, sigma=0.0, rng=rng)

    R_final = float(np.abs(np.exp(1j * theta[-1]).mean()))
    assert R_final > 0.999, (
        f"identical all-to-all oscillators must phase-lock (R→1); got "
        f"R={R_final:.4f} at α={alpha0}. Without locking the collective "
        f"frequency is undefined and the sign test is vacuous."
    )

    omega_obs = _collective_frequency(theta, dt)
    canonical = omega0 - (N - 1) * kappa * np.sin(alpha0)
    sign_flipped = omega0 + (N - 1) * kappa * np.sin(alpha0)

    assert abs(omega_obs - canonical) < 1e-3, (
        f"Sakaguchi −α SIGN VIOLATED: observed Ω={omega_obs:.6f} ≠ "
        f"canonical ω₀−(N−1)κ·sin(α)={canonical:.6f} at α={alpha0} "
        f"(N={N}, κ={kappa}, ω₀={omega0}). Sign-flipped hypothesis "
        f"ω₀+(N−1)κ·sin(α)={sign_flipped:.6f}. A residual here is the "
        f"signature of a +α phase-lag regression — invisible at α=0."
    )

    if abs(alpha0) > 1e-9:
        # Discriminative-power guarantee: the canonical and sign-flipped
        # predictions must be far apart, so the assertion above is a
        # real falsifier, not a degenerate tautology.
        assert abs(canonical - sign_flipped) > 1e-2, (
            f"non-discriminative at α={alpha0}: canonical and "
            f"sign-flipped predictions coincide — this α is itself a "
            f"blind manifold and must not be used as a falsifier."
        )
