# SPDX-License-Identifier: MIT
"""Ott-Antonsen dimensionality reduction for Kuramoto dynamics.

The most important theoretical advance in synchronization theory since
Kuramoto (1975). Ott & Antonsen (2008) showed that for Lorentzian-
distributed natural frequencies, the infinite-N Kuramoto model reduces
to a SINGLE complex ODE for the order parameter z(t) = R(t)·exp(iΨ(t)):

    dz/dt = -(Δ + iω₀)·z + (K/2)·(z − z·|z|²)

The synchronising coupling gain is linear in z (NOT z̄). On the real
axis with ω₀ = 0 the conjugate form is numerically identical, which is
exactly why an ω₀ = 0 / real-z test cannot see a z↔z̄ swap — the OA
falsification battery must probe ω₀ ≠ 0 (see test_T23_*).

where:
    Δ = half-width of the Lorentzian frequency distribution
    ω₀ = center frequency (mean natural frequency)
    K = coupling strength
    z = R·exp(iΨ) = complex order parameter

This means:
    - N-body → 1-body: instead of N coupled ODEs, ONE complex ODE
    - EXACT in thermodynamic limit (N → ∞)
    - Analytical K_c = 2Δ (critical coupling from ODE bifurcation)
    - Analytical R_∞ = √(1 − 2Δ/K) for K > K_c (steady-state R)
    - 10,000x speedup over N-body simulation for R(t) trajectory
    - Bifurcation diagram in closed form

For GeoSync:
    - Feed Δ, ω₀ from market data → get R(t) trajectory analytically
    - Compare analytical R(t) with empirical R(t) → model validation
    - Predict K_c from estimated coupling → regime transition forecast
    - Stability of synchronized state → Kelly confidence scaling

References:
    Ott & Antonsen (2008). "Low dimensional behavior of large systems
    of globally coupled oscillators." Chaos, 18(3), 037113.

    Ott & Antonsen (2009). "Long time evolution of phase oscillator
    systems." Chaos, 19(2), 023117.

Invariants:
    INV-OA1: |z(t)| ≤ 1 always (order parameter bound)
    INV-OA2: K > 2Δ ⟹ R_∞ = √(1 − 2Δ/K) (analytical steady state)
    INV-OA3: K < 2Δ ⟹ R → 0 (subcritical decay, matches INV-K2)

INV-OA2 as a runtime oracle:
    The supercritical steady state R_∞ = √(1 − 2Δ/K) is the EXACT fixed point
    of the OA ODE (Ott & Antonsen 2008, Eq. 2.13). It is not a target the
    integrator aims at — it is the closed-form answer the integrator MUST
    reproduce. Disagreement between the late-time integrated R and √(1 − 2Δ/K)
    is therefore not "numerical drift to tolerate" but a step-size / CFL
    failure: the RK4 step has crossed its stability limit and is returning a
    physically wrong state. integrate() turns this into a fail-closed oracle —
    after a supercritical run it raises FloatingPointError(INV-OA2 ...) if the
    converged |z| departs from the closed form by more than ORACLE_TOL.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

# Machine epsilon for IEEE-754 float64 used by the integrator state.
_EPS: float = sys.float_info.epsilon  # ≈ 2.22e-16

# INV-OA2 runtime oracle tolerance. The exact supercritical fixed point
# R_∞ = √(1 − 2Δ/K) is reproduced by a *stable* RK4 step to ~1e-12 or better
# (empirically ~1e-14 in tests/unit/physics/test_T23b_*). ORACLE_TOL = 1e-3 is
# a conservative ceiling: it passes every stable integration with vast margin
# yet rejects a CFL-violating step, whose late-time R departs from the closed
# form by O(0.1–1) (it either over-saturates onto |z|=1 or collapses). The gap
# between "stable ~1e-12" and "unstable ~1e-1" is ~10 orders of magnitude, so
# the precise value of ORACLE_TOL is not load-bearing — any threshold in that
# void separates the two regimes. Documented bound, not a magic number.
ORACLE_TOL: float = 1e-3

# Repeller-domain floor for asymptotic-convergence claims (INV-OA2 / Task 3).
# The incoherent state z = 0 is the UNSTABLE fixed point of the supercritical OA
# ODE (dz/dt = 0 there). A trajectory seeded EXACTLY on it never leaves: it
# settles at R = 0 ≠ R_∞, so a convergence claim is unreachable from that seed.
# The smallest seed that is numerically DISTINGUISHABLE from the exact repeller
# in IEEE-754 float64 is a few ULPs of 1.0; below that, R0 *is* the repeller and
# its float neighbourhood. R0_MIN = 4·ε_mach is therefore machine-epsilon-
# derived, not a tuned constant: it rejects only seeds indistinguishable from
# z = 0, and leaves every legitimate "small perturbation" seed (e.g. the 0.01
# default) untouched. Plain integrate() still ABSTAINS on R0 = 0 (the unstable
# branch is a valid trajectory); the floor is enforced ONLY when the caller
# explicitly claims convergence via require_convergence=True.
R0_MIN: float = 4.0 * _EPS  # ≈ 8.88e-16


@dataclass(frozen=True, slots=True)
class OttAntonsenResult:
    """Result of Ott-Antonsen mean-field integration."""

    time: NDArray[np.float64]
    z: NDArray[np.complex128]  # complex order parameter z(t)
    R: NDArray[np.float64]  # |z(t)| = order parameter magnitude
    psi: NDArray[np.float64]  # arg(z(t)) = mean phase
    K_c: float  # critical coupling = 2Δ
    R_steady: float  # analytical R_∞ (0 if subcritical)
    is_supercritical: bool  # K > K_c


@dataclass(frozen=True, slots=True)
class ChimeraReport:
    """Chimera state detection report."""

    global_R: float  # global order parameter
    sector_R: NDArray[np.float64]  # per-sector order parameter
    sector_labels: list[str]  # sector names
    is_chimera: bool  # True if some sectors sync, others don't
    sync_sectors: list[str]  # sectors with R > threshold
    desync_sectors: list[str]  # sectors with R < threshold
    chimera_index: float  # std(sector_R) / mean(sector_R)


class OttAntonsenEngine:
    """Exact mean-field reduction of Kuramoto dynamics.

    Integrates the Ott-Antonsen ODE for z(t) instead of N coupled
    phase equations. Produces the exact R(t) trajectory in the
    thermodynamic limit (N → ∞).

    Usage::

        engine = OttAntonsenEngine(K=2.0, delta=0.5, omega0=0.0)
        result = engine.integrate(T=50.0, dt=0.01, R0=0.01)
        print(f"R_∞ = {result.R[-1]:.4f}, K_c = {result.K_c:.4f}")
    """

    def __init__(
        self,
        K: float,
        delta: float,
        omega0: float = 0.0,
    ) -> None:
        """
        Parameters
        ----------
        K : float
            Global coupling strength.
        delta : float
            Half-width of Lorentzian frequency distribution.
            g(ω) = (Δ/π) / ((ω − ω₀)² + Δ²)
        omega0 : float
            Center of frequency distribution (default 0).
        """
        # Fail-closed finiteness contract: a non-finite parameter would let the
        # NaN-blind |z| guard in integrate() silently propagate NaN/Inf past
        # INV-OA1 (|z| ≤ 1). Reject at construction.
        if not math.isfinite(K):
            raise ValueError(f"K must be finite, got {K}")
        if not (math.isfinite(delta) and delta > 0):
            raise ValueError(f"delta must be finite and > 0, got {delta}")
        if not math.isfinite(omega0):
            raise ValueError(f"omega0 must be finite, got {omega0}")
        self.K = float(K)
        self.delta = float(delta)
        self.omega0 = float(omega0)

    @property
    def K_c(self) -> float:
        """Critical coupling K_c = 2Δ (Ott-Antonsen bifurcation)."""
        return 2.0 * self.delta

    @property
    def R_steady(self) -> float:
        """Analytical steady-state R for K > K_c.

        R_∞ = √(1 − 2Δ/K) = √(1 − K_c/K)

        Returns 0.0 if K ≤ K_c (subcritical).
        """
        if self.K <= self.K_c:
            return 0.0
        return math.sqrt(1.0 - self.K_c / self.K)

    def _dz_dt(self, z: complex) -> complex:
        """Ott-Antonsen ODE right-hand side.

        dz/dt = -(Δ + iω₀)·z + (K/2)·(z − z·|z|²)

        The coupling contributes the synchronising gain +(K/2)·z
        (linear in z, NOT z̄) and the saturating cubic −(K/2)·|z|²·z.
        Ott & Antonsen, Chaos 18, 037113 (2008), Eq. 2.13.
        """
        z_abs_sq = z.real**2 + z.imag**2
        return -(self.delta + 1j * self.omega0) * z + (self.K / 2.0) * (z - z * z_abs_sq)

    def integrate(
        self,
        T: float = 50.0,
        dt: float = 0.01,
        R0: float = 0.01,
        psi0: float = 0.0,
        *,
        require_convergence: bool = False,
    ) -> OttAntonsenResult:
        """Integrate the Ott-Antonsen ODE via RK4.

        Parameters
        ----------
        T : float
            Total integration time.
        dt : float
            Time step.
        R0 : float
            Initial order parameter magnitude (default: small perturbation).
        psi0 : float
            Initial mean phase (default: 0).
        require_convergence : bool
            When True the caller CLAIMS the supercritical run converges to the
            closed-form attractor R_∞ = √(1 − 2Δ/K). That claim is only valid on
            the STABLE branch, which is reached from R0 > R0_MIN. Seeding a
            supercritical run at/below R0_MIN (the unstable incoherent fixed
            point z = 0 and its float neighbourhood) makes the attractor
            UNREACHABLE — the trajectory stalls on the repeller — so this raises
            ``ValueError`` instead of returning a spurious is_supercritical
            result whose R never reaches R_∞. When False (default) the run is a
            plain trajectory and R0 = 0 is a valid (unstable-branch) request.

        Returns
        -------
        OttAntonsenResult

        Domain
        ------
        Subcritical (K ≤ 2Δ): R(t→∞) → 0 for any R0 (INV-OA3). Supercritical
        (K > 2Δ): R(t→∞) → √(1 − 2Δ/K) from R0 > R0_MIN; the measure-zero seed
        R0 ∈ [0, R0_MIN] lies on the unstable branch and does NOT converge.
        """
        # Fail-closed integration contract (no silent numeric repair).
        if not (math.isfinite(dt) and dt > 0):
            raise ValueError(f"dt must be finite and > 0, got {dt}")
        if not (math.isfinite(T) and T > 0):
            raise ValueError(f"T must be finite and > 0, got {T}")
        if not math.isfinite(R0):
            raise ValueError(f"R0 must be finite, got {R0}")
        if not math.isfinite(psi0):
            raise ValueError(f"psi0 must be finite, got {psi0}")

        # Repeller-domain restriction for an explicit convergence claim. The
        # supercritical attractor R_∞ is unreachable from a seed on/below the
        # unstable fixed point z = 0; refuse the claim rather than return a
        # stalled trajectory mislabelled is_supercritical. Subcritical runs
        # converge to 0 from any seed, so the restriction binds only K > K_c.
        if require_convergence and self.K > self.K_c and R0 <= R0_MIN:
            raise ValueError(
                f"INV-OA2 repeller domain: supercritical convergence to "
                f"R_∞=√(1−2Δ/K)={self.R_steady:.6f} cannot be claimed from "
                f"R0={R0:.3e} ≤ R0_MIN={R0_MIN:.3e} (the unstable incoherent "
                f"fixed point z=0). Seed R0 > R0_MIN, or call integrate() "
                f"without require_convergence to obtain the unstable-branch "
                f"trajectory (K={self.K}, delta={self.delta})."
            )

        n_steps = int(T / dt)
        if n_steps < 1:
            raise ValueError(f"T/dt must yield ≥ 1 step, got T={T}, dt={dt}")
        time = np.linspace(0.0, T, n_steps + 1)
        z_arr = np.empty(n_steps + 1, dtype=np.complex128)

        # ----- INV-OA1 overshoot gate, tied to RK4 local truncation error -----
        # The unit disk |z| ≤ 1 is the exact invariant manifold of the OA ODE.
        # A *stable* RK4 step lands on it up to its local truncation error, which
        # for a smooth ODE is O((L·dt)^5) per step, where L is the dominant
        # Jacobian scale of the RHS dz/dt = -(Δ+iω₀)z + (K/2)(z − z|z|²). On the
        # disk the linear part scales as Δ and the coupling/cubic part as K, so
        # L = max(Δ, K) bounds the response rate. The legitimate overshoot a
        # round-off projection may absorb is therefore
        #     overshoot_bound = max(8·ε_mach, (L·dt)^5)
        # — the 8·ε_mach floor covers pure float64 round-off when (L·dt)^5
        # underflows it, and (L·dt)^5 covers a stable-but-coarse step. A genuine
        # CFL violation drives |z| past 1 by O(1), which is exponentially larger
        # than (L·dt)^5 for any L·dt near the stability limit, so true
        # instability still fails closed. This replaces the magic 1e-8 constant
        # with a bound derived from the integrator's own error order.
        rhs_scale = max(self.delta, abs(self.K))
        overshoot_bound = max(8.0 * _EPS, (rhs_scale * dt) ** 5)

        # Initial condition
        # INV-OA1: |z| ≤ 1 (R0 is finite by the guard above)
        R0 = min(R0, 1.0)
        z = complex(R0 * math.cos(psi0), R0 * math.sin(psi0))
        z_arr[0] = z

        # RK4 integration of the complex ODE
        for step in range(n_steps):
            k1 = self._dz_dt(z)
            k2 = self._dz_dt(z + 0.5 * dt * k1)
            k3 = self._dz_dt(z + 0.5 * dt * k2)
            k4 = self._dz_dt(z + dt * k3)
            z = z + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)

            # INV-OA1: |z| ≤ 1. The previous guard `if abs(z) > 1.0: z/=abs(z)`
            # was NaN-blind (nan > 1.0 is False, so NaN leaked) AND silently
            # renormalised a blown-up RK4 step onto the unit circle — turning a
            # subcritical run (K < 2Δ ⟹ R→0) into a spurious |z|=1 full-sync
            # verdict. Fail-closed instead: only round-off drift may be
            # projected; genuine instability / non-finite state raises.
            z_mag = abs(z)
            if not math.isfinite(z_mag):
                raise FloatingPointError(
                    f"INV-OA1: OA integration produced non-finite |z| at step "
                    f"{step} (K={self.K}, delta={self.delta}, dt={dt}); "
                    f"check inputs / reduce dt."
                )
            if z_mag > 1.0 + overshoot_bound:
                raise FloatingPointError(
                    f"INV-OA1 VIOLATED: OA integration unstable, |z|={z_mag:.6e} "
                    f"> 1 + {overshoot_bound:.3e} at step {step} "
                    f"(K={self.K}, delta={self.delta}, dt={dt}); RK4 past stability "
                    f"limit (overshoot beyond local truncation error) — reduce dt."
                )
            if z_mag > 1.0:
                # INV-OA1: |z| ≤ 1 on the unit disk. Only sub-overshoot-bound
                # round-off reaches here (true overshoot already raised above);
                # project it back to the disk rather than letting it accumulate.
                z = z / z_mag

            z_arr[step + 1] = z

        R = np.abs(z_arr).astype(np.float64)
        psi = np.angle(z_arr).astype(np.float64)

        # ----- INV-OA2 runtime oracle: CONVERGED steady state == closed form ---
        # For K > K_c the EXACT fixed point is R_∞ = √(1 − 2Δ/K). The oracle's
        # job is to catch a CFL / step-size failure: a dt past the RK4 stability
        # limit returns a stationary-but-WRONG state (over-saturated toward
        # |z|=1, or collapsed) instead of the closed form. It must NOT condemn a
        # numerically-stable run that simply has not finished relaxing — near
        # onset the relaxation time diverges as ~1/(K − K_c) (critical
        # slowing-down), so at finite T a stable trajectory can still be en route
        # to R_∞ with the integration step itself perfectly valid.
        #
        # The discriminator is STATIONARITY: a CFL-failed state is settled on the
        # wrong value (flat tail — empirically peak-to-peak drift ≈ 0 to machine
        # precision, far from R_∞); an under-converged near-onset run still has a
        # visibly drifting tail whose remaining drift is comparable to its
        # remaining distance-to-target (exponential relaxation). We therefore fire
        # only when the tail has truly stopped moving (peak-to-peak drift ≤
        # STATIONARITY_TOL = ORACLE_TOL/10) AND the settled value disagrees with
        # the closed form by more than ORACLE_TOL. The stationarity bar is set an
        # order of magnitude below the residual gate so a slow but still-relaxing
        # trajectory (drift ~ residual) is never misread as "settled on the wrong
        # value": critical slowing-down (relaxation time ~ 1/(K − K_c)) is a
        # legitimate finite-T artefact, not a CFL failure. A stable-but-still-
        # relaxing run is left to the per-step |z| gate above (true blow-up) and
        # to the caller's T/dt choice.
        #
        # The repeller NEIGHBOURHOOD R0 ≤ R0_MIN is excluded (not just R0 = 0):
        # the incoherent state z = 0 is the UNSTABLE fixed point of the
        # supercritical ODE (dz/dt = 0 there). Seeded on it — or so close that
        # the exponential escape time exceeds the run length T — the trajectory
        # is still sitting on the unstable branch at R ≈ 0 ≠ R_∞. Its tail is
        # stationary at ~0 by the SAME physics as a CFL failure, so the
        # stationarity discriminator cannot tell them apart; the oracle must
        # therefore ABSTAIN on R0 ≤ R0_MIN (the unstable branch / sub-escape
        # seed) and bind the stable branch only, reached from R0 > R0_MIN (the
        # documented "small perturbation" seed). Convergence FROM that domain is
        # the caller's explicit claim via require_convergence (guarded above).
        if self.K > self.K_c and R0 > R0_MIN:
            # bounds: tail window is the last 20% of samples, floored at 2 points
            # so peak-to-peak drift is well-defined (not a physics clamp).
            tail_n = max(2, (n_steps + 1) // 5)
            tail = R[-tail_n:]
            R_converged = float(np.mean(tail))
            tail_drift = float(np.max(tail) - np.min(tail))
            R_closed_form = self.R_steady  # = √(1 − 2Δ/K)
            oracle_residual = abs(R_converged - R_closed_form)
            tail_is_stationary = tail_drift <= ORACLE_TOL / 10.0
            # Repeller-stall guard: a finite-but-tiny R0 (above R0_MIN) whose
            # exponential escape time exceeds T sits STATIONARY near the unstable
            # fixed point R ≈ 0. That is the unstable branch, NOT a CFL failure —
            # a genuine CFL failure settles on a non-zero wrong PLATEAU near the
            # attractor (e.g. R≈0.71 vs R_∞≈0.866), never collapsed onto the
            # analytically-unstable R=0. The oracle therefore only condemns a
            # stationary mismatch once the trajectory has ESCAPED the repeller
            # basin (R_converged past the basin midpoint ½·R_∞); below that it is
            # under-escaped (finite-T / unstable-branch) and the oracle abstains.
            escaped_repeller = R_converged > 0.5 * R_closed_form
            if tail_is_stationary and escaped_repeller and oracle_residual > ORACLE_TOL:
                raise FloatingPointError(
                    f"INV-OA2 VIOLATED: settled steady state R={R_converged:.6e} "
                    f"(tail drift {tail_drift:.3e}) disagrees with the exact closed "
                    f"form √(1 − 2Δ/K)={R_closed_form:.6e} by {oracle_residual:.3e} "
                    f"> {ORACLE_TOL:.0e} (K={self.K}, delta={self.delta}, dt={dt}, "
                    f"T={T}). The trajectory has stopped moving on the WRONG value: "
                    f"the supercritical fixed point is exact, so a stationary "
                    f"mismatch is a step-size/CFL failure — reduce dt. Do not trust "
                    f"this R."
                )

        return OttAntonsenResult(
            time=time,
            z=z_arr,
            R=R,
            psi=psi,
            K_c=self.K_c,
            R_steady=self.R_steady,
            is_supercritical=self.K > self.K_c,
        )


def detect_chimera(
    phases: NDArray[np.float64],
    sector_assignments: NDArray[np.int64],
    sector_labels: list[str] | None = None,
    sync_threshold: float = 0.7,
    desync_threshold: float = 0.3,
) -> ChimeraReport:
    """Detect chimera states: partial synchronization across sectors.

    A chimera state occurs when some groups of oscillators synchronize
    while others remain incoherent — "synchronization coexists with
    disorder." In financial markets: tech stocks lock while energy
    trades independently.

    Parameters
    ----------
    phases : (N,) array
        Current phase of each oscillator.
    sector_assignments : (N,) array of int
        Sector index for each oscillator (0-indexed).
    sector_labels : list[str], optional
        Human-readable sector names.
    sync_threshold : float
        R above this = "synchronized" (default 0.7).
    desync_threshold : float
        R below this = "desynchronized" (default 0.3).

    Returns
    -------
    ChimeraReport
    """
    phases = np.asarray(phases, dtype=np.float64)
    sectors = np.asarray(sector_assignments, dtype=np.int64)
    # Fail-closed: n_sectors = max()+1 silently drops any oscillator with a
    # negative label (it matches no `sectors == s` mask), making the global and
    # per-sector order parameters mutually inconsistent. Require a non-empty,
    # 0-indexed non-negative assignment.
    if sectors.size == 0:
        raise ValueError("sector_assignments must be non-empty")
    if int(sectors.min()) < 0:
        raise ValueError(
            f"sector_assignments must be 0-indexed non-negative; got min={int(sectors.min())}"
        )
    n_sectors = int(sectors.max()) + 1

    if sector_labels is None:
        sector_labels = [f"sector_{i}" for i in range(n_sectors)]

    # Global order parameter
    global_z = np.mean(np.exp(1j * phases))
    global_R = float(np.abs(global_z))

    # Per-sector order parameter
    sector_R = np.zeros(n_sectors, dtype=np.float64)
    for s in range(n_sectors):
        mask = sectors == s
        if mask.sum() > 0:
            sector_z = np.mean(np.exp(1j * phases[mask]))
            sector_R[s] = float(np.abs(sector_z))

    # Chimera detection: some sectors sync, others desync
    sync_sectors = [sector_labels[i] for i in range(n_sectors) if sector_R[i] > sync_threshold]
    desync_sectors = [sector_labels[i] for i in range(n_sectors) if sector_R[i] < desync_threshold]
    is_chimera = len(sync_sectors) > 0 and len(desync_sectors) > 0

    # Chimera index: std/mean of sector R values (high = chimera-like)
    mean_R = float(np.mean(sector_R))
    chimera_index = float(np.std(sector_R) / mean_R) if mean_R > 1e-10 else 0.0

    return ChimeraReport(
        global_R=global_R,
        sector_R=sector_R,
        sector_labels=sector_labels,
        is_chimera=is_chimera,
        sync_sectors=sync_sectors,
        desync_sectors=desync_sectors,
        chimera_index=chimera_index,
    )
