# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
r"""Adversarial convergence + work-convention proof for the Jarzynski equality.

This battery goes beyond the single-tolerance INV-ST2 anchor in
``test_T8_stochastic_thermodynamics.py``. It proves three things that a
hand-tuned tolerance cannot:

* **INV-ST2 anchor** — ⟨e^{−βW}⟩ matches e^{−βΔF}=0.5 for the reference
  stiffness ramp k_i=1 → k_f=4 (kT=1), within the registered 0.05 band.
* **CONVERGENCE-RATE proof** — the standard error of the Jarzynski estimator
  scales as 1/√N. We fit log(SE) vs log(N) over four ensemble sizes and assert
  the slope is ≈ −0.5. An overfit / accidentally-passing tolerance would NOT
  reproduce the Monte-Carlo scaling law; this defeats "the bound just happened
  to hold for one ensemble size".
* **FACTOR-2 ADVERSARIAL** — re-deriving the work with the wrong Sekimoto
  convention (dW = Δk·x², i.e. dropping the load-bearing ½, "off by a factor of
  2") biases ⟨e^{−βW}⟩ from 0.5 to ≈0.31. The INV-ST2 anchor DETECTS this; the
  test asserts the wrong convention is caught, not silently passed.
* **Equipartition fail-closed** — a tiny ensemble or a mis-initialised
  variance trips the pre-ramp INV-ST1 witness and raises ``ValueError``.

Math anchors
------------
* Equipartition: E[x²] = kT/k (Boltzmann equilibrium of ½ k x²).
* Free energy: ΔF = −(1/2β)·ln(k_i/k_f); e^{−βΔF} = sqrt(k_i/k_f) = 0.5.
* Monte-Carlo: SE of an ensemble-mean estimator ∝ 1/√N (slope −½ in log-log).

The heavy four-ensemble convergence proof is marked ``@pytest.mark.heavy_math``
(a PR-gating compute-intensive suite, deselectable from the fast lane); a
small-N fast variant keeps the convergence signal in the default suite.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.physics.stochastic_thermodynamics import (
    delta_free_energy,
    equipartition_band,
    jarzynski_average,
    stiffness_ramp_work,
)

_KI = 1.0
_KF = 4.0
_KT = 1.0
_TARGET = float(np.sqrt(_KI / _KF))  # = e^{−βΔF} = 0.5
_SLOPE_SEEDS = tuple(range(24))  # replicas per ensemble for the SE estimate


def _ramp_work_wrong_convention(
    seed: int,
    *,
    ensemble: int,
    tau: float = 1.0,
    dt: float = 0.005,
    ki: float = _KI,
    kf: float = _KF,
    kT: float = _KT,
    gamma: float = 1.0,
) -> np.ndarray:
    r"""Reference ramp re-derived with the WRONG (factor-2) work convention.

    Identical dynamics and RNG stream to :func:`stiffness_ramp_work`, but the
    work increment drops the Sekimoto ½: ``dW = Δk·x²`` instead of the correct
    ``dW = ½·Δk·x²``. Every work value is therefore doubled. This is the
    adversarial injection the suite must DETECT.
    """
    rng = np.random.default_rng(seed)
    n_steps = int(tau / dt)
    x = rng.standard_normal(ensemble) * float(np.sqrt(kT / ki))
    work = np.zeros(ensemble, dtype=np.float64)
    noise_scale = float(np.sqrt(2.0 * gamma * kT * dt))
    for i in range(n_steps):
        k_cur = ki + (kf - ki) * i / n_steps
        k_next = ki + (kf - ki) * (i + 1) / n_steps
        work += (k_next - k_cur) * x * x  # WRONG: missing the ½ → off by 2
        drift = (dt / gamma) * k_next * x
        x = x - drift + noise_scale * rng.standard_normal(ensemble)
    return work


def _se_of_jarzynski(ensemble: int) -> float:
    """Empirical standard error of ⟨e^{−βW}⟩ over the replica seeds."""
    estimates = [
        jarzynski_average(
            stiffness_ramp_work(seed, ensemble=ensemble, ki=_KI, kf=_KF, kT=_KT),
            kT=_KT,
        )
        for seed in _SLOPE_SEEDS
    ]
    return float(np.std(estimates, ddof=1))


# --------------------------------------------------------------------------- #
# INV-ST2 anchor                                                              #
# --------------------------------------------------------------------------- #
def test_INV_ST2_jarzynski_matches_free_energy() -> None:
    """INV-ST2: ⟨e^{−βW}⟩ = e^{−βΔF} = 0.5 within the registered 0.05 band."""
    tol = 0.05  # registered INV-ST2 relative tolerance (measured ≤0.004)
    dF = delta_free_energy(_KI, _KF, _KT)
    analytic = float(np.exp(-dF / _KT))
    assert abs(analytic - _TARGET) < 1e-12, (
        f"setup: e^(−βΔF)={analytic:.6f} must equal sqrt(ki/kf)={_TARGET:.6f}."
    )
    for seed in (1, 7, 42, 123):
        work = stiffness_ramp_work(seed, ki=_KI, kf=_KF, kT=_KT)
        jar = jarzynski_average(work, kT=_KT)
        rel_dev = abs(jar - _TARGET) / _TARGET
        assert rel_dev < tol, (
            f"INV-ST2 VIOLATED: ⟨e^(−βW)⟩={jar:.4f} vs target {_TARGET:.4f}, "
            f"rel_dev={rel_dev:.4f} exceeds {tol:.2f} at seed={seed}."
        )


# --------------------------------------------------------------------------- #
# CONVERGENCE-RATE proof (defeats overfit tolerance)                          #
# --------------------------------------------------------------------------- #
def _assert_convergence_slope(ensembles: tuple[int, ...], *, atol: float) -> float:
    """Fit log(SE) vs log(N); assert Monte-Carlo slope −½. Returns the slope."""
    log_n = np.log(np.asarray(ensembles, dtype=np.float64))
    log_se = np.log(np.asarray([_se_of_jarzynski(n) for n in ensembles]))
    slope = float(np.polyfit(log_n, log_se, 1)[0])
    assert abs(slope - (-0.5)) < atol, (
        f"CONVERGENCE-RATE VIOLATED: log(SE) vs log(N) slope={slope:.3f}, "
        f"expected −0.5 ± {atol} (Monte-Carlo 1/√N scaling). A tolerance that "
        f"passes by luck rather than convergence would not reproduce this. "
        f"Ensembles={ensembles}."
    )
    return slope


@pytest.mark.heavy_math
def test_jarzynski_convergence_rate_one_over_sqrt_n_heavy() -> None:
    """Rigorous 1/√N proof over {1000, 5000, 20000, 40000}: slope ≈ −0.5 ± 0.1.

    This is the asymptotic Monte-Carlo lever-arm: the large-ensemble range
    resolves the −1/2 scaling exponent cleanly (measured ≈ −0.484). A tolerance
    that passed by luck on a single ensemble would not reproduce this slope.
    """
    slope = _assert_convergence_slope((1000, 5000, 20000, 40000), atol=0.1)
    assert slope < -0.4  # belt-and-braces: unambiguously in the 1/√N regime


def test_jarzynski_convergence_rate_decays_fast() -> None:
    """Fast small-N variant: SE strictly decreases with N and decays ∝ ~1/√N.

    At small ensembles the Jarzynski SE carries finite-N bias variance, so the
    log-log slope is steeper than the asymptotic −1/2 (≈ −0.7 here). We do NOT
    fake the asymptotic exponent on a short lever-arm; instead we assert the two
    falsifiable facts that survive at this scale: (1) the standard error is
    strictly monotone decreasing in N, and (2) the slope is firmly negative and
    brackets the 1/√N law (−0.9 < slope < −0.3). The exact −0.5 exponent is
    proved by the ``@pytest.mark.heavy_math`` companion above.
    """
    ensembles = (500, 2000, 8000)
    ses = [_se_of_jarzynski(n) for n in ensembles]
    assert all(ses[i] > ses[i + 1] for i in range(len(ses) - 1)), (
        f"CONVERGENCE-RATE VIOLATED: SE not monotone decreasing in N: {ses}. "
        f"A bound holding by luck would not show monotone Monte-Carlo decay."
    )
    slope = float(np.polyfit(np.log(ensembles), np.log(ses), 1)[0])
    assert -0.9 < slope < -0.3, (
        f"CONVERGENCE-RATE VIOLATED: small-N log(SE)–log(N) slope={slope:.3f} "
        f"does not bracket the 1/√N law (−0.9, −0.3). Ensembles={ensembles}."
    )


# --------------------------------------------------------------------------- #
# FACTOR-2 ADVERSARIAL                                                         #
# --------------------------------------------------------------------------- #
def test_factor_two_work_convention_is_detected() -> None:
    """Injecting dW = Δk·x² (missing the ½, off by 2) is DETECTED by INV-ST2.

    The correct Sekimoto convention gives ⟨e^(−βW)⟩ ≈ 0.5; doubling every work
    value collapses it to ≈0.31 (~38 % bias). The INV-ST2 0.05 band, which the
    correct convention clears, must REJECT the wrong one — proving the guard is
    convention-sensitive and the factor-2 bug cannot pass silently.
    """
    tol = 0.05
    for seed in (1, 7, 42, 123):
        correct = jarzynski_average(
            stiffness_ramp_work(seed, ki=_KI, kf=_KF, kT=_KT), kT=_KT
        )
        wrong = jarzynski_average(
            _ramp_work_wrong_convention(seed, ensemble=40_000), kT=_KT
        )
        rel_correct = abs(correct - _TARGET) / _TARGET
        rel_wrong = abs(wrong - _TARGET) / _TARGET
        assert rel_correct < tol, (
            f"sanity: correct convention should pass, got rel_dev={rel_correct:.4f}."
        )
        assert rel_wrong >= tol, (
            f"FACTOR-2 NOT DETECTED: wrong convention ⟨e^(−βW)⟩={wrong:.4f} "
            f"(rel_dev={rel_wrong:.4f}) slipped inside the {tol:.2f} band. The "
            f"missing-½ work bug would pass silently. seed={seed}."
        )
        # Direction check: the bug specifically *lowers* the average well below
        # target (doubled work ⇒ smaller e^{−βW}).
        assert wrong < correct - 0.1, (
            f"FACTOR-2 direction: wrong={wrong:.4f} should be far below "
            f"correct={correct:.4f} at seed={seed}."
        )


# --------------------------------------------------------------------------- #
# Equipartition fail-closed (pre-ramp INV-ST1 witness)                        #
# --------------------------------------------------------------------------- #
def test_equipartition_band_scales_one_over_sqrt_n() -> None:
    """The registered band is n_sigma·sqrt(2/(N−1)), i.e. ∝ 1/√N, not tuned."""
    # Exact closed form: band(N) = 6·sqrt(2/(N−1)).
    for n in (100, 400, 1000, 40_000):
        assert abs(equipartition_band(n) - 6.0 * float(np.sqrt(2.0 / (n - 1)))) < 1e-12
    # Asymptotically (N≫1) quadrupling N halves the band (1/√N); at large N the
    # −1 correction is negligible.
    ratio = equipartition_band(10_000) / equipartition_band(40_000)
    assert abs(ratio - 2.0) < 1e-3, (
        f"band ratio {ratio:.6f} should approach 2.0 for a 4× ensemble (1/√N)."
    )


def test_tiny_ensemble_trips_equipartition_witness() -> None:
    """A tiny ensemble cannot carry the witness ⇒ fail-closed ValueError."""
    with pytest.raises(ValueError, match="INV-ST1 witness requires ensemble"):
        stiffness_ramp_work(7, ensemble=10, ki=_KI, kf=_KF, kT=_KT)


def test_wrong_init_variance_trips_equipartition_witness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mis-initialised Var(x) ≠ kT/k_i trips the pre-ramp INV-ST1 witness.

    We patch the RNG draw so the initial ensemble has variance ≈4·(kT/k_i)
    instead of kT/k_i; the 6-σ equipartition band (≈4 %) must reject it before
    any work accrues.
    """
    real_default_rng = np.random.default_rng

    class _WrongInitRng:
        """RNG facade whose FIRST ``standard_normal`` draw has 4× the variance.

        The pre-ramp INV-ST1 witness consumes the first draw and must fire on
        the inflated variance; later draws (the Langevin noise) are never reached
        because the witness raises first, so this minimal facade is sufficient.
        """

        def __init__(self, seed: int) -> None:
            self._gen = real_default_rng(seed)
            self._first = True

        def standard_normal(self, size: int) -> FloatArray:
            out = np.asarray(self._gen.standard_normal(size), dtype=np.float64)
            if self._first:
                self._first = False
                return out * 2.0  # wrong σ²: 4× the equipartition variance
            return out

    monkeypatch.setattr(np.random, "default_rng", _WrongInitRng)
    with pytest.raises(ValueError, match="INV-ST1 VIOLATED"):
        stiffness_ramp_work(7, ensemble=40_000, ki=_KI, kf=_KF, kT=_KT)


def test_jarzynski_ess_underflow_guard_fires() -> None:
    """A pathological work array (one dominant low-W draw) trips the ESS guard."""
    work = np.concatenate([np.array([-50.0]), np.full(9_999, 50.0)]).astype(np.float64)
    with pytest.raises(ValueError, match="ESS/M"):
        jarzynski_average(work, kT=_KT)


def test_jarzynski_rejects_nonfinite_work() -> None:
    """Non-finite work is refused before it can corrupt the average."""
    work = np.array([0.1, np.inf, 0.2], dtype=np.float64)
    with pytest.raises(ValueError, match="finite"):
        jarzynski_average(work, kT=_KT)
