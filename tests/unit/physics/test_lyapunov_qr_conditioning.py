# SPDX-License-Identifier: MIT
"""Adversarial fail-closed battery for INV-LY4: QR conditioning guard.

The Benettin–Galgani–Strelcyn (1980) full-spectrum estimator is valid
ONLY while the tangent frame ``Q`` stays orthonormal. The historical
``maximum(|R_kk|, 1e-30)`` floor hid two failure modes — rank collapse
and orthonormality loss — by silently returning a ≈ −69-bit garbage
exponent dressed as a Lyapunov number. INV-LY4 rejects those runs with
``FloatingPointError`` instead.

This file pins three things:

* the WELL-CONDITIONED anchors (INV-LY1 linear, INV-LY2 harmonic) keep
  their exact admissible behaviour — the guard never fires on them;
* a rank-collapsing system (wide eigenvalue spread + sparse QR cadence)
  and an orthonormality-destroying ``dt`` RAISE rather than return the
  floored garbage exponent — and we PROVE the garbage was real by
  reproducing the old floored output and showing it is wrong;
* contract violations (``dt ≤ 0``, ``n_steps ≤ 0``, ``qr_every ∤
  n_steps``) still raise ``ValueError`` (INV-LY3 untouched).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import jax
import jax.numpy as jnp
import numpy as np
import pytest
from jax import Array

from core.physics.lyapunov_spectrum import (
    _ORTHO_TOL,
    _RDIAG_REL_FLOOR,
    lyapunov_spectrum,
)

# float64 is a precondition for INV-LY1/LY2/LY4 (the relative resolution
# threshold is tied to ``numpy.finfo(float64).eps``). Routed via an Any-typed
# alias because ``jax.config.update`` is untyped: a bare call trips mypy
# --strict no-untyped-call, and an inline type-suppression directive would add
# debt-ratchet debt.
_jax_config: Any = jax.config
_jax_config.update("jax_enable_x64", True)

RHS = Callable[[Array], Array]


def _diagonal(eigs: tuple[float, ...]) -> RHS:
    """Linear ``ẋ = D x`` with ``D = diag(eigs)``; spectrum ≡ ``eigs``."""
    D = jnp.diag(jnp.asarray(eigs, dtype=jnp.float64))

    def rhs(x: Array) -> Array:
        return D @ x

    return rhs


def _harmonic(omega: float = 1.0) -> RHS:
    """2-D harmonic oscillator (Hamiltonian); analytic spectrum (0, 0)."""
    A = jnp.array([[0.0, 1.0], [-(omega**2), 0.0]])

    def rhs(x: Array) -> Array:
        return A @ x

    return rhs


# ── Anchors: the guard must NOT fire on well-conditioned systems ─────────────


def test_INV_LY1_anchor_well_conditioned_linear_unchanged() -> None:
    """INV-LY1 still holds exactly: guard is silent on a benign linear flow.

    ``ẋ = diag(-1,-2,-3) x`` has spectrum ``(-1,-2,-3)``. The QR frame is
    perfectly conditioned (decay, no stretch blow-up), so INV-LY4 never
    fires and the recovered spectrum matches to the documented 1e-3 tol.
    """
    eigs = (-1.0, -2.0, -3.0)
    rep = lyapunov_spectrum(
        _diagonal(eigs), jnp.array([1.0, 1.0, 1.0]), dt=0.01, n_steps=5_000, qr_every=5
    )
    expected = jnp.array(sorted(eigs, reverse=True))
    err = float(jnp.max(jnp.abs(rep.spectrum - expected)))
    assert err < 1e-3, (
        f"INV-LY1 anchor broken by the conditioning guard: "
        f"spectrum={np.array(rep.spectrum)} expected={np.array(expected)} err={err:.3e}"
    )


def test_INV_LY2_anchor_harmonic_sum_zero_time_resolved() -> None:
    """INV-LY2 still holds: harmonic Σλ ≈ 0, the guard does not fire.

    The harmonic oscillator is the canonical Hamiltonian (symplectic
    pairing ⇒ Σλ = 0). It is well-conditioned for a resolved ``ω·dt``, so
    INV-LY4 stays silent while INV-LY2 is satisfied to 1e-3. We sample two
    integration horizons to show the sum-zero is time-resolved, not a
    single lucky T.
    """
    for n_steps in (5_000, 10_000):
        rep = lyapunov_spectrum(
            _harmonic(omega=1.0),
            jnp.array([1.0, 0.0]),
            dt=0.01,
            n_steps=n_steps,
            qr_every=10,
        )
        sum_lambda = float(jnp.sum(rep.spectrum))
        assert abs(sum_lambda) < 1e-3, (
            f"INV-LY2 anchor broken at T={n_steps * 0.01:.0f}: Σλ={sum_lambda:.3e} "
            f"spectrum={np.array(rep.spectrum)} — symplectic flow must pair to 0."
        )


# ── Fail-closed: rank collapse RAISES rather than flooring to garbage ────────


def test_INV_LY4_rank_collapse_raises_not_floored_garbage() -> None:
    """Wide eigenvalue spread + sparse QR cadence ⇒ FloatingPointError.

    ``ẋ = diag(40,-40) x`` integrated with ``qr_every=40`` lets the two
    tangent directions stretch by ``exp(80·T_outer)`` between
    reorthonormalisations, so ``min|R_kk| / max|R_kk|`` underflows below
    float64's relative resolution. The smallest direction is then below
    machine resolution and ``log|R_kk|`` is pure rounding noise. INV-LY4
    rejects the run; it must NOT return a 1e-30-floored exponent.
    """
    rhs = _diagonal((40.0, -40.0))
    with pytest.raises(FloatingPointError, match="INV-LY4 VIOLATED: tangent frame rank-collapsed"):
        lyapunov_spectrum(rhs, jnp.array([1.0, 1.0]), dt=0.05, n_steps=80, qr_every=40)


def test_INV_LY4_the_floored_path_would_have_been_wrong() -> None:
    """Prove the guard kills REAL garbage, not a hypothetical.

    Reproduce the historical ``maximum(|R_kk|, 1e-30)`` floored accumulation
    by hand on the exact rank-collapsing trajectory the guard rejects, and
    show the second exponent it would have returned is nowhere near the true
    value (true spectrum is (40, -40); the floored path collapses the
    contractive exponent to ≈ 0). The guard converts this silent wrong number
    into an explicit raise — that is the whole point of INV-LY4.
    """
    dt, qr_every, n_outer = 0.05, 40, 2
    D = jnp.diag(jnp.array([40.0, -40.0]))

    def rhs(x: Array) -> Array:
        return D @ x

    jac = jax.jacfwd(rhs)

    def _mid(_i: Array, c: tuple[Array, Array]) -> tuple[Array, Array]:
        x, Q = c
        f1 = rhs(x)
        J1 = jac(x)
        x_mid = x + 0.5 * dt * f1
        Q_mid = Q + 0.5 * dt * J1 @ Q
        f2 = rhs(x_mid)
        J2 = jac(x_mid)
        return (x + dt * f2, Q + dt * J2 @ Q_mid)

    x = jnp.array([1.0, 1.0])
    Q = jnp.eye(2)
    log_sum = jnp.zeros(2)
    for _ in range(n_outer):
        x, Q = jax.lax.fori_loop(0, qr_every, _mid, (x, Q))
        Q, R = jnp.linalg.qr(Q)
        log_sum = log_sum + jnp.log(jnp.maximum(jnp.abs(jnp.diag(R)), 1e-30))
    floored = np.sort(np.array(log_sum / (n_outer * qr_every * dt)))[::-1]

    # The contractive (−40) exponent is replaced by ≈ 0 floored garbage.
    true_min = -40.0
    assert abs(floored[-1] - true_min) > 30.0, (
        f"Expected the floored path to be grossly wrong on λ_min; got floored={floored}. "
        f"If this assertion fails the floor is not the hazard the guard removes."
    )

    # And the real function refuses to emit it.
    with pytest.raises(FloatingPointError, match="INV-LY4"):
        lyapunov_spectrum(rhs, jnp.array([1.0, 1.0]), dt=dt, n_steps=n_outer * qr_every, qr_every=qr_every)


def test_INV_LY4_blowup_dt_raises() -> None:
    """A ``dt`` so large the variational step explodes ⇒ FloatingPointError.

    ``ẋ = diag(5,1,-3) x`` with ``dt=10`` blows the tangent frame far past
    float64 range within a single sparse QR window; the frame is no longer a
    valid orthonormal basis. INV-LY4 raises rather than returning a floored
    exponent.
    """
    rhs = _diagonal((5.0, 1.0, -3.0))
    with pytest.raises(FloatingPointError, match="INV-LY4 VIOLATED"):
        lyapunov_spectrum(rhs, jnp.ones(3), dt=10.0, n_steps=100, qr_every=50)


def test_INV_LY4_thresholds_are_float64_tied() -> None:
    """The guard thresholds are derived from float64, not hand-tuned knobs.

    The relative R-diagonal floor equals ``numpy.finfo(float64).eps`` exactly
    (the smallest direction below this is unresolvable), and the orthonormality
    tolerance is the documented ≈ 1e6·eps headroom over the O(n·eps) residual a
    healthy reduced QR leaves. Pinning them prevents silent loosening.
    """
    assert _RDIAG_REL_FLOOR == float(np.finfo(np.float64).eps)
    assert _ORTHO_TOL == pytest.approx(1.0e-10)
    assert _ORTHO_TOL > _RDIAG_REL_FLOOR  # ortho headroom strictly above eps


# ── INV-LY3 contract violations still raise ValueError (unchanged) ───────────


@pytest.mark.parametrize(
    "kwargs,fragment",
    [
        ({"dt": 0.0}, "dt must be positive"),
        ({"dt": -1.0}, "dt must be positive"),
        ({"n_steps": 0}, "n_steps must be positive"),
        ({"n_steps": -10}, "n_steps must be positive"),
        ({"qr_every": 0}, "qr_every must be positive"),
        ({"n_steps": 10, "qr_every": 3}, "must divide"),
    ],
)
def test_INV_LY3_contract_violations_still_raise_value_error(
    kwargs: dict[str, Any], fragment: str
) -> None:
    """Conditioning guard does not swallow the existing fail-closed contract."""
    base: dict[str, Any] = {"dt": 0.01, "n_steps": 100, "qr_every": 1}
    base.update(kwargs)
    with pytest.raises(ValueError, match=fragment):
        lyapunov_spectrum(_diagonal((-1.0, -2.0)), jnp.array([1.0, 1.0]), **base)
