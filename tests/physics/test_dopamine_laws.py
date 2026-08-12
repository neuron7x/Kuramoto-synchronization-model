# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Executable falsification witnesses for two dopamine laws.

Two *scopes* of the real dopamine code are exercised here, and they are NOT
interchangeable:

* **RAW TD controller** — ``geosync.core.neuro.dopamine.dopamine_controller``
  ``DopamineController.compute_rpe`` implements the canonical Schultz-Dayan-
  Montague (1997) TD(0) prediction error::

        δ = r + γ · V(s') − V(s)

  with ∂δ/∂r = 1 (INV-DA7) — i.e. the raw signal is *unbounded* in the reward.

* **Execution adapter** — ``core.neuro.dopamine_execution_adapter``
  ``DopamineExecutionAdapter.compute_rpe`` applies a tanh squash::

        DA = tanh(scale · ((pnl − pred) − |slippage|))

  so the *emitted* dopamine signal is bounded, |DA| ≤ 1 (INV-DA8).

Law 1 — ``dopamine_rpe_zero_steady_state`` (INV-DA5 / INV-DA2, Robbins-Monro):
    In a *stationary* reward environment the running E[δ] of the RAW controller
    converges to zero, because TD(0) drives the value estimate to its fixed
    point V* = r/(1−γ) (single recurrent state, V(s')=V(s)). The negative
    control shows the claim is genuinely falsifiable: under a *non-stationary*
    (drifting) reward the value estimate perpetually lags, so E[δ] is pinned at
    slope/lr ≠ 0, and an out-of-spec γ fails closed.

Law 2 — ``dopamine_bounded_signal`` (INV-DA8):
    Every finite input through the ADAPTER yields a finite |DA| ≤ DA_max. The
    negative control demonstrates the bound is load-bearing: the RAW controller
    (∂δ/∂r = 1) overshoots DA_max for the same magnitude — it is the tanh squash
    that enforces the bound — and a non-finite input lies outside the finite-
    input contract (so it is not a valid bounded signal).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from core.neuro.dopamine_execution_adapter import DopamineExecutionAdapter
from core.neuro.signal_bus import NeuroSignalBus
from geosync.core.neuro.dopamine import DopamineController

# ── Shared constants ────────────────────────────────────────────────────────
_CONFIG_PATH = Path("config/dopamine.yaml")
DA_MAX = 1.0  # INV-DA8: tanh saturates at ±1 → the emitted-signal bound.
_GAMMA = 0.9  # explicit discount; V* = r/(1−γ) finite, geometric TD convergence.
_LR = 0.1  # learning_rate_v shipped in config/dopamine.yaml (time-constant 1/(lr·(1−γ))).
_TOL = 5e-3  # |E[δ]| equilibrium tolerance (INV-DA5).


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    """Stage the shipped dopamine config into a scratch dir (no repo mutation)."""
    target = tmp_path / "dopamine.yaml"
    target.write_text(_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def _run_td(staged_config: Path, rewards: list[float], gamma: float = _GAMMA) -> list[float]:
    """Drive the RAW controller over a single recurrent state and return δ_t.

    Single recurrent state ⇒ V(s') = V(s) = v, so δ = r + γ·v − v = r − (1−γ)·v.
    Value is updated by the production ``update_value_estimate`` (TD(0), lr from
    config). No reimplementation: ``compute_rpe`` is the real RAW TD error.
    """
    ctrl = DopamineController(str(staged_config))
    deltas: list[float] = []
    for r in rewards:
        v = ctrl.value_estimate
        delta = ctrl.compute_rpe(reward=r, value=v, next_value=v, discount_gamma=gamma)
        ctrl.update_value_estimate(delta)
        deltas.append(delta)
    return deltas


def _abs_tail_mean(xs: list[float], tail: int) -> float:
    """|mean| of the last ``tail`` samples (the running E[δ] estimator)."""
    window = xs[-tail:]
    return abs(sum(window) / len(window))


# ── Law 1: dopamine_rpe_zero_steady_state (INV-DA5) ─────────────────────────


def test_rpe_converges_to_zero_under_stationary_reward(config_path: Path) -> None:
    """INV-DA5 (positive): stationary reward ⇒ tail E[δ] → 0 (Robbins-Monro).

    A stationary stochastic reward r_t ~ N(r_mean, σ²) drives TD(0) to its fixed
    point V* = r_mean/(1−γ); at equilibrium E[δ] = r_mean − (1−γ)·E[V] = 0. We
    assert the tail running mean |E[δ]| sits below tolerance after convergence.
    """
    rng = np.random.default_rng(7)
    n_steps, tail_n = 6000, 1500
    r_mean, sigma = 0.5, 0.05
    rewards = (r_mean + sigma * rng.standard_normal(n_steps)).tolist()

    deltas = _run_td(config_path, rewards)
    tail_mean = _abs_tail_mean(deltas, tail_n)

    assert tail_mean < _TOL, (
        f"INV-DA5 VIOLATED: tail |E[δ]|={tail_mean:.6f} ≥ tol={_TOL:.6f}; "
        f"expected E[δ]→0 at TD equilibrium in a STATIONARY reward environment "
        f"(δ=r+γV'−V, single recurrent state, V*=r/(1−γ); Robbins-Monro, "
        f"Schultz-Dayan-Montague 1997). "
        f"r_mean={r_mean}, σ={sigma}, γ={_GAMMA}, lr={_LR}, "
        f"n_steps={n_steps}, tail={tail_n}"
    )


def test_nonstationary_reward_keeps_rpe_biased(config_path: Path) -> None:
    """INV-DA5 (negative control): non-stationarity falsifies the zero steady state.

    A persistently drifting reward r_t = r0 + slope·t makes the value estimate
    perpetually lag, so the quasi-steady δ is pinned at slope/lr ≠ 0: E[δ] does
    NOT converge to zero. Also asserts an out-of-spec γ fails closed — no silent
    steady state is fabricated.
    """
    n_steps, tail_n = 6000, 1500
    slope = 0.01
    rewards = (0.5 + slope * np.arange(n_steps, dtype=np.float64)).tolist()

    deltas = _run_td(config_path, rewards)
    tail_bias = _abs_tail_mean(deltas, tail_n)

    assert tail_bias > _TOL, (
        f"INV-DA5 NEGATIVE-CONTROL FAILED: tail |E[δ]|={tail_bias:.6f} ≤ "
        f"tol={_TOL:.6f}; a NON-stationary (drifting) reward must keep E[δ] away "
        f"from zero (quasi-steady δ≈slope/lr) — the steady-state claim is only "
        f"valid under stationarity. slope={slope}, lr={_LR}, γ={_GAMMA}, "
        f"n_steps={n_steps}, tail={tail_n}"
    )

    # Fail-closed: γ ∉ (0, 1] is rejected (INV-DA3), never silently steadied.
    ctrl = DopamineController(str(config_path))
    with pytest.raises(ValueError):
        ctrl.compute_rpe(reward=1.0, value=0.0, next_value=0.0, discount_gamma=1.5)


# ── Law 2: dopamine_bounded_signal (INV-DA8) ────────────────────────────────


def test_adapter_signal_bounded_under_finite_fuzz() -> None:
    """INV-DA8 (positive): every finite adapter input yields finite |DA| ≤ DA_max.

    Fuzzes (realized_pnl, predicted_return, slippage) across many decades of
    finite magnitude — including 1e18 boundary inputs — through the real
    tanh-squashed adapter and asserts the bound holds on every sample.
    """
    adapter = DopamineExecutionAdapter(NeuroSignalBus())
    rng = np.random.default_rng(11)
    max_abs = 0.0

    for scale in (1e0, 1e3, 1e6, 1e9, 1e12):
        pnl = rng.uniform(-scale, scale, size=400).tolist()
        pred = rng.uniform(-scale, scale, size=400).tolist()
        slip = rng.uniform(0.0, scale, size=400).tolist()
        for p, q, s in zip(pnl, pred, slip):
            da = adapter.compute_rpe(realized_pnl=p, predicted_return=q, slippage=s)
            assert math.isfinite(da), (
                f"INV-DA8 VIOLATED: non-finite DA={da} for finite input "
                f"(pnl={p}, pred={q}, slip={s}); the adapter must map every "
                f"finite input to a finite signal."
            )
            assert abs(da) <= DA_MAX, (
                f"INV-DA8 VIOLATED: |DA|={abs(da):.6f} > DA_max={DA_MAX:.1f} "
                f"for finite input (pnl={p}, pred={q}, slip={s}); the emitted "
                f"dopamine signal must be bounded by tanh saturation. scale={scale}"
            )
            max_abs = max(max_abs, abs(da))

    for p, q, s in ((1e18, -1e18, 0.0), (-1e18, 1e18, 0.0), (0.0, 0.0, 1e18)):
        da = adapter.compute_rpe(realized_pnl=p, predicted_return=q, slippage=s)
        assert math.isfinite(da) and abs(da) <= DA_MAX, (
            f"INV-DA8 VIOLATED: boundary input (pnl={p}, pred={q}, slip={s}) "
            f"produced DA={da}, expected finite |DA| ≤ {DA_MAX:.1f}."
        )

    assert max_abs <= DA_MAX, (
        f"INV-DA8 VIOLATED: observed max |DA|={max_abs:.6f} > DA_max={DA_MAX:.1f} "
        f"over the finite fuzz sweep."
    )


def test_unbounded_raw_signal_falsifies_bound_adapter_enforces(config_path: Path) -> None:
    """INV-DA8 (negative control): the bound is load-bearing, not vacuous.

    The RAW controller (∂δ/∂r = 1, INV-DA7) overshoots DA_max for a single large
    reward — were that raw δ emitted as the dopamine signal it would falsify
    |DA| ≤ DA_max. The same magnitude through the tanh adapter stays bounded, so
    the squash is what enforces the contract. A non-finite input lies OUTSIDE the
    finite-input contract and must be screened upstream (it is not bounded).
    """
    ctrl = DopamineController(str(config_path))
    raw = ctrl.compute_rpe(reward=50.0, value=0.0, next_value=0.0, discount_gamma=_GAMMA)
    assert abs(raw) > DA_MAX, (
        f"INV-DA8 NEGATIVE-CONTROL FAILED: raw TD δ={raw:.4f} did not exceed "
        f"DA_max={DA_MAX:.1f}; the RAW controller (∂δ/∂r=1, INV-DA7) is "
        f"unbounded by construction and must overshoot the adapter bound, "
        f"otherwise the tanh squash would be untested."
    )

    adapter = DopamineExecutionAdapter(NeuroSignalBus())
    bounded = adapter.compute_rpe(realized_pnl=50.0, predicted_return=0.0)
    assert abs(bounded) <= DA_MAX, (
        f"INV-DA8 VIOLATED: adapter DA={bounded:.6f} for pnl=50.0 exceeded "
        f"DA_max={DA_MAX:.1f}; the tanh squash must bound the same magnitude the "
        f"raw controller leaves unbounded."
    )

    # Saturating limit: +∞ maps EXACTLY onto the bound (tanh(∞)=1) — no overflow.
    saturated = adapter.compute_rpe(realized_pnl=math.inf, predicted_return=0.0)
    assert math.isfinite(saturated) and abs(saturated) <= DA_MAX, (
        f"INV-DA8 VIOLATED: +∞ input produced DA={saturated}, expected the "
        f"saturating bound (|DA|≤{DA_MAX:.1f}) with no overflow past DA_max."
    )

    # Contract-domain boundary: a NaN input is OUT of the finite-input contract;
    # INV-DA8 guarantees finiteness only ∀ finite input. A NaN propagates, i.e.
    # it is NOT a valid bounded signal and must be screened before emission.
    nan_out = adapter.compute_rpe(realized_pnl=math.nan, predicted_return=0.0)
    assert not math.isfinite(nan_out), (
        f"INV-DA8 SCOPE: a NaN input must surface as a non-finite signal "
        f"(got DA={nan_out}); the finiteness guarantee holds only for finite "
        f"inputs, so non-finite inputs must fail closed upstream."
    )
