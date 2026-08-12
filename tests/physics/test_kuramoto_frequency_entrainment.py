# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Executable witnesses for the ``kuramoto_frequency_entrainment`` law.

Catalog law (physics_contracts/catalog.yaml, kuramoto.frequency_entrainment):
    Above K_c a macroscopic cluster locks to a common mean frequency Omega.
    K > K_c => exists Omega : |<dtheta_j/dt>_t - Omega| -> 0 for j in locked set
    validity: N >= 256, integration time > 50/gamma
    source:   Acebron et al., Rev. Mod. Phys. 77 (2005)

INV-K2/INV-K3 family. The mean-field Kuramoto critical coupling for a Lorentzian
natural-frequency distribution of half-width ``gamma`` is the EXACT
``K_c = 2*gamma`` (NEVER hardcoded — derived from gamma here). Above it a
macroscopic fraction of oscillators — including ones whose natural frequency is
many half-widths off-centre — phase-lock and share a single rotation frequency
``Omega`` (≈ 0 for a symmetric distribution centred at 0). Below it every
oscillator drifts at (essentially) its own natural frequency and no macroscopic
common-frequency cluster exists, so an entrainment claim there is falsified.

The instantaneous per-oscillator frequency ``<dtheta_j/dt>`` is measured as the
time-averaged phase velocity over the final third of the (unwrapped) trajectory
produced by the canonical finite-N RK4 integrator in ``core.kuramoto.engine`` —
the physics is reused, not re-derived.

Empirically calibrated (seed=7, gamma=0.5, N=256, dt=0.05, T=120 > 50/gamma):
    K = 3*K_c  -> locked_fraction=0.875, detuned-locked=0.816, Omega=-0.031,
                  locked-set common-frequency spread=0.00128
    K = 0.3*K_c-> detuned-locked=0.000, corr(<dtheta/dt>, omega_nat)=1.000
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest
from numpy.typing import NDArray

from core.kuramoto.config import KuramotoConfig
from core.kuramoto.engine import KuramotoEngine

pytestmark = pytest.mark.heavy_math

# --- Calibrated ensemble (validity gate: N >= 256, T > 50/gamma) -------------
GAMMA: float = 0.5  # Lorentzian half-width; K_c = 2*gamma (NEVER hardcode K_c).
N_OSC: int = 256  # validity floor N >= 256.
DT: float = 0.05
TOTAL_TIME: float = 120.0  # 120 > 50/gamma = 100 (validity floor).
SEED: int = 7

SUPERCRITICAL_FACTOR: float = 3.0  # K = 3*K_c (well above onset).
SUBCRITICAL_FACTOR: float = 0.3  # K = 0.3*K_c (incoherent regime).

# Membership band for "shares the mean-field frequency Omega". Frequencies are
# in rad/time; a locked oscillator sits within LOCK_TOL_FACTOR*gamma of Omega.
LOCK_TOL_FACTOR: float = 0.1
# An oscillator is "genuinely detuned" if its natural frequency is at least
# DETUNED_FACTOR*gamma off-centre: locking *these* to Omega is the actual
# entrainment signature (not the triviality that near-zero-omega units sit near
# Omega even uncoupled).
DETUNED_FACTOR: float = 0.5
# Asserted common-frequency tightness of the locked cluster (independent of, and
# tighter than, the membership band) and the allowed |Omega| drift band.
ENTRAIN_SPREAD_FACTOR: float = 0.05
OMEGA_BAND_FACTOR: float = 0.2


@dataclass(frozen=True)
class EntrainmentReport:
    """Measured entrainment observables for one coupling strength."""

    coupling: float
    k_c: float
    locked_fraction: float
    detuned_locked_fraction: float
    omega_lock: float
    locked_spread: float
    freq_natural_corr: float
    n_detuned: int


def _lorentzian_natural_frequencies(
    rng: np.random.Generator, n: int, gamma: float
) -> NDArray[np.float64]:
    """Draw N Lorentzian (Cauchy, half-width gamma) frequencies, centred at 0."""
    omega: NDArray[np.float64] = gamma * rng.standard_cauchy(n)
    # Robust re-centring so the symmetric mean-field rotation frequency is ~0.
    return omega - float(np.median(omega))


def _measure_entrainment(k_factor: float, *, seed: int = SEED) -> EntrainmentReport:
    """Integrate the finite-N Kuramoto ODE and measure frequency entrainment.

    ``<dtheta_j/dt>`` is the time-averaged phase velocity over the final third of
    the unwrapped trajectory; ``Omega`` is the population median of those
    velocities (the mean-field rotation frequency); the locked set is the
    oscillators within ``LOCK_TOL_FACTOR*gamma`` of ``Omega``.
    """
    rng = np.random.default_rng(seed)
    k_c = 2.0 * GAMMA
    coupling = k_factor * k_c
    steps = int(round(TOTAL_TIME / DT))

    omega = _lorentzian_natural_frequencies(rng, N_OSC, GAMMA)
    theta0 = rng.uniform(-np.pi, np.pi, N_OSC)
    cfg = KuramotoConfig(
        N=N_OSC, K=coupling, omega=omega, dt=DT, steps=steps, theta0=theta0, seed=seed
    )
    phases = KuramotoEngine(cfg).run().phases

    window = steps // 3
    # Engine phases accumulate unbounded (no wrapping), so a plain finite
    # difference over the final window is the time-averaged instantaneous freq.
    avg_freq = (phases[-1] - phases[-1 - window]) / (window * DT)
    omega_lock = float(np.median(avg_freq))
    deviation = np.abs(avg_freq - omega_lock)

    lock_tol = LOCK_TOL_FACTOR * GAMMA
    locked = deviation < lock_tol
    detuned = np.abs(omega) > DETUNED_FACTOR * GAMMA
    n_detuned = int(detuned.sum())
    detuned_locked_fraction = (
        float((locked & detuned).sum()) / float(n_detuned) if n_detuned > 0 else float("nan")
    )
    locked_spread = float(deviation[locked].max()) if bool(locked.any()) else float("nan")
    freq_natural_corr = float(np.corrcoef(avg_freq, omega)[0, 1])

    return EntrainmentReport(
        coupling=coupling,
        k_c=k_c,
        locked_fraction=float(locked.mean()),
        detuned_locked_fraction=detuned_locked_fraction,
        omega_lock=omega_lock,
        locked_spread=locked_spread,
        freq_natural_corr=freq_natural_corr,
        n_detuned=n_detuned,
    )


def test_supercritical_locks_detuned_oscillators_to_common_frequency() -> None:
    """Positive witness: K = 3*K_c entrains a macroscopic, genuinely-detuned cluster."""
    report = _measure_entrainment(SUPERCRITICAL_FACTOR)
    lock_tol = LOCK_TOL_FACTOR * GAMMA
    entrain_spread = ENTRAIN_SPREAD_FACTOR * GAMMA
    omega_band = OMEGA_BAND_FACTOR * GAMMA

    assert report.locked_fraction > 0.5, (
        f"ENTRAINMENT VIOLATED: locked_fraction={report.locked_fraction:.4f} <= 0.5 "
        f"expected a MACROSCOPIC cluster locked to Omega above onset. "
        f"Locked = |<dtheta_j/dt> - Omega| < {lock_tol:.4f} rad/time. "
        f"Lorentzian K_c=2*gamma={report.k_c:.4f}. "
        f"At K={report.coupling:.4f} (=3*K_c), N={N_OSC}, gamma={GAMMA}, T={TOTAL_TIME}"
    )
    assert report.detuned_locked_fraction > 0.5, (
        f"ENTRAINMENT VIOLATED: detuned_locked_fraction={report.detuned_locked_fraction:.4f} "
        f"<= 0.5 — genuinely off-centre oscillators (|omega|>{DETUNED_FACTOR*GAMMA:.4f}) "
        f"must be pulled to the common Omega (this is entrainment, not triviality). "
        f"Lorentzian K_c=2*gamma={report.k_c:.4f}. "
        f"At K={report.coupling:.4f}, n_detuned={report.n_detuned}, N={N_OSC}, gamma={GAMMA}"
    )
    assert report.locked_spread < entrain_spread, (
        f"ENTRAINMENT VIOLATED: locked-set frequency spread={report.locked_spread:.5f} "
        f">= {entrain_spread:.4f} — the locked set must share ONE frequency Omega "
        f"(|<dtheta_j/dt> - Omega| -> 0). Lorentzian K_c=2*gamma={report.k_c:.4f}. "
        f"At K={report.coupling:.4f}, Omega={report.omega_lock:.5f}, N={N_OSC}, gamma={GAMMA}"
    )
    assert abs(report.omega_lock) < omega_band, (
        f"ENTRAINMENT VIOLATED: |Omega|={abs(report.omega_lock):.5f} >= {omega_band:.4f} — "
        f"a symmetric Lorentzian centred at 0 must lock near Omega=0. "
        f"Lorentzian K_c=2*gamma={report.k_c:.4f}. "
        f"At K={report.coupling:.4f}, N={N_OSC}, gamma={GAMMA}, T={TOTAL_TIME}"
    )


def test_subcritical_entrainment_claim_is_falsified() -> None:
    """Negative control: below K_c no macroscopic common-frequency cluster exists.

    Each oscillator drifts at (essentially) its own natural frequency, so a
    frequency-entrainment claim in the incoherent regime is falsified; invalid
    ensemble inputs (sub-floor N, non-finite K) additionally fail closed.
    """
    report = _measure_entrainment(SUBCRITICAL_FACTOR)
    assert report.detuned_locked_fraction < 0.05, (
        f"ENTRAINMENT FALSIFIER FAILED: detuned_locked_fraction="
        f"{report.detuned_locked_fraction:.4f} >= 0.05 below K_c — no detuned cluster "
        f"may lock to a common Omega in the incoherent regime. "
        f"Lorentzian K_c=2*gamma={report.k_c:.4f}. "
        f"At K={report.coupling:.4f} (=0.3*K_c), n_detuned={report.n_detuned}, N={N_OSC}"
    )
    assert report.freq_natural_corr > 0.9, (
        f"ENTRAINMENT FALSIFIER FAILED: corr(<dtheta/dt>, omega_nat)="
        f"{report.freq_natural_corr:.4f} <= 0.9 — below K_c each oscillator must run "
        f"at its OWN natural frequency (no entrainment). "
        f"Lorentzian K_c=2*gamma={report.k_c:.4f}. "
        f"At K={report.coupling:.4f}, N={N_OSC}, gamma={GAMMA}, T={TOTAL_TIME}"
    )

    # Invalid ensembles must fail closed (no silent entrainment on garbage).
    with pytest.raises(ValueError):
        KuramotoConfig(N=1, K=2.0 * GAMMA, dt=DT, steps=10)  # below N>=2 floor
    with pytest.raises(ValueError):
        KuramotoConfig(N=8, K=float("inf"), dt=DT, steps=10)  # non-finite coupling
