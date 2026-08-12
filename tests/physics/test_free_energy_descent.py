# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for thermo.free_energy_descent (INV-FE1 / INV-FE2).

Law: without external forcing, the free energy F = U - T*S of the trading gate
is non-increasing (dF/dt <= 0). The real primitive reused here is
``core.physics.free_energy_trading_gate.FreeEnergyTradingGate`` — the same gate
referenced by INV-FE1/INV-FE2 in CLAUDE.md. No free-energy functional is
reimplemented in this test.

Unforced dynamics model: proportional position *relaxation* toward zero (no
external capital/leverage injected). Shrinking every position by one factor
leaves the normalized Tsallis weights — and therefore S_q — invariant, while the
risk exposure U = sum_i |pos_i|*|ret_i| strictly shrinks. Hence
dF = dU = (shrink-1)*U_before < 0 each step: a genuine, gate-admitted free-energy
descent rather than a tautology over an arbitrary sequence.

External forcing (position *growth*, i.e. injected leverage) raises U and drives
dF > 0; the gate must detect and reject it (allowed=False). That is the
discriminating negative control: if descent were assumed unconditionally the
forced step would be silently admitted.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.physics.free_energy_trading_gate import FreeEnergyTradingGate

# Float slack only. Calibration (seeded relaxation, 8 seeds x 40 steps) measured a
# worst single-step increment of -5.3e-6 (strictly negative), so any positive
# excess above this floor signals a real INV-FE1 violation, not round-off.
DESCENT_TOL = 1e-9


def _unforced_trajectory(
    seed: int,
    n_assets: int = 6,
    n_steps: int = 40,
    shrink: float = 0.85,
) -> tuple[np.ndarray, list[bool], float, float, float]:
    """Run the real gate over an unforced relaxation trajectory.

    Returns (F_trajectory, admitted_flags, min_U, min_T, min_S) so the caller can
    assert both INV-FE1 (monotone descent) and INV-FE2 (non-negative components).
    """
    rng = np.random.default_rng(seed)
    gate = FreeEnergyTradingGate(T_base=0.60, q=1.5)
    returns = np.abs(rng.normal(0.0, 0.01, size=n_assets)) + 1e-3
    cur = rng.normal(0.0, 1.0, size=n_assets)
    # Hold T constant (no external thermal forcing): isolate dF = dU descent.
    t_lob = gate.compute_T_LOB(realized_volatility=0.012)

    f_traj: list[float] = []
    admitted: list[bool] = []
    min_u = np.inf
    min_t = np.inf
    min_s = np.inf
    for step in range(n_steps):
        nxt = cur * shrink
        d = gate.check(cur, nxt, returns, T_LOB=t_lob)
        if step == 0:
            f_traj.append(d.F_before)
        f_traj.append(d.F_after)
        admitted.append(d.allowed)
        min_u = min(min_u, d.U_before, d.U_after)
        min_t = min(min_t, d.T_LOB)
        min_s = min(min_s, d.S_q_before, d.S_q_after)
        cur = nxt
    return np.asarray(f_traj, dtype=np.float64), admitted, float(min_u), float(min_t), float(min_s)


def test_unforced_free_energy_is_nonincreasing() -> None:
    """Positive witness (INV-FE1): F(t) is monotone non-increasing, unforced.

    Sweeps seeds so the descent is a property of the gate dynamics, not of one
    lucky trajectory. Also checks INV-FE2 (U, T, S_q all >= 0) along the path,
    while allowing F itself to be negative (Helmholtz).
    """
    worst_increment = -np.inf
    f_min_seen = np.inf
    for seed in range(8):
        f_traj, admitted, min_u, min_t, min_s = _unforced_trajectory(seed)
        increments = np.diff(f_traj)
        seed_worst = float(increments.max())
        worst_increment = max(worst_increment, seed_worst)
        f_min_seen = min(f_min_seen, float(f_traj.min()))

        assert all(admitted), (
            f"INV-FE1 VIOLATED: an unforced relaxation step was NOT gate-admitted "
            f"(some delta_F > 0) at seed={seed}. "
            f"F = U - T*S must descend without external forcing; admitted={admitted}. "
            f"Source: core.physics.free_energy_trading_gate.FreeEnergyTradingGate."
        )
        # INV-FE2: components are individually non-negative (F may be negative).
        assert min_u >= 0.0 and min_t >= 0.0 and min_s >= -1e-12, (
            f"INV-FE2 VIOLATED: a free-energy component went negative at seed={seed} "
            f"(min U={min_u:.3e}, min T={min_t:.3e}, min S_q={min_s:.3e}). "
            f"INV-FE2 guards U>=0, T>=0, S_q>=0 (not the composite F). "
            f"Source: free_energy_trading_gate.FreeEnergyTradingGate."
        )

    assert worst_increment <= DESCENT_TOL, (
        f"INV-FE1 VIOLATED: worst single-step dF={worst_increment:.3e} > tol={DESCENT_TOL:.1e}. "
        f"Without external forcing, free energy F=U-T*S must be non-increasing (dF/dt<=0). "
        f"Measured over 8 seeds x 40 unforced relaxation steps; floor is float slack only. "
        f"Helmholtz F may be negative — min F seen={f_min_seen:.4f} — but its INCREMENTS may not "
        f"be positive. Source: free_energy_trading_gate.FreeEnergyTradingGate.check."
    )


def test_external_forcing_raising_free_energy_is_rejected() -> None:
    """Negative control (INV-FE1): forcing that raises F is detected and rejected.

    Discriminating: a tautological 'descent' would silently admit the forced
    move. Here injected leverage (position growth) raises U => dF>0, and the gate
    must report allowed=False with delta_F>0. Also asserts the gate fails closed
    on an unphysical (negative) temperature rather than inverting the entropy term.
    """
    rng = np.random.default_rng(11)
    gate = FreeEnergyTradingGate(T_base=0.60, q=1.5)
    n_assets = 6
    returns = np.abs(rng.normal(0.0, 0.01, size=n_assets)) + 1e-3
    pos = rng.normal(0.0, 1.0, size=n_assets)
    t_lob = gate.compute_T_LOB(realized_volatility=0.012)

    # External forcing: grow positions (inject leverage) -> U up -> F up.
    forced = gate.check(pos, pos * 1.4, returns, T_LOB=t_lob)
    assert forced.delta_F > 0.0, (
        f"NEGATIVE CONTROL INERT: forced leverage growth did not raise F "
        f"(delta_F={forced.delta_F:.3e}); the control cannot discriminate INV-FE1. "
        f"Expected dF>0 under external forcing. "
        f"Source: free_energy_trading_gate.FreeEnergyTradingGate.check."
    )
    assert not forced.allowed, (
        f"INV-FE1 VIOLATED: a forcing step with delta_F={forced.delta_F:.3e}>0 was ADMITTED. "
        f"The gate must reject any move that increases free energy (dF/dt<=0 only). "
        f"U_before={forced.U_before:.4f} U_after={forced.U_after:.4f}. "
        f"Source: free_energy_trading_gate.FreeEnergyTradingGate.check."
    )

    # Fail-closed on an unphysical thermal context (negative temperature).
    with pytest.raises(ValueError, match="INV-FE2: T_LOB must be finite and"):
        gate.check(pos, pos * 0.85, returns, T_LOB=-1.0)
