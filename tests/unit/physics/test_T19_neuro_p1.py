# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T19 — P1 neuromodulation invariant witnesses.

Six P1 invariants covering serotonin, GABA, and dopamine subsystems:

* **INV-5HT3** — Higher stress produces higher serotonin (pre-desensitisation).
  Qualitative / monotonicity test.

* **INV-GABA4** — vol -> 0 implies inhibition -> 0. Asymptotic / convergence
  test on the GABAPositionGate.

* **INV-GABA5** — vol -> inf implies inhibition -> 1. Asymptotic / convergence
  test on the GABAPositionGate.

* **INV-DA2** — V -> V* under standard TD(0) conditions (Robbins-Monro
  convergence). Asymptotic / convergence test on DopamineController.

* **INV-DA4** — Value estimate stabilises with fixed reward. Asymptotic /
  convergence test measuring late-time variance < early-time variance.

* **INV-DA5** — E[delta] approx 0 at equilibrium. Statistical / ensemble test
  on the TD(0) RPE after warm-up.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import numpy as np
import pytest

from core.neuro.gaba_position_gate import GABAPositionGate
from core.neuro.serotonin_ode import SerotoninODE
from core.neuro.signal_bus import NeuroSignalBus
from geosync.core.neuro.dopamine import DopamineController

_CONFIG_PATH = Path("config/dopamine.yaml")


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def dopamine_controller(tmp_path: Path) -> DopamineController:
    """Load shipped dopamine config into a scratch directory.

    Mirrors the fixture pattern from T11 so the witness uses exactly the
    production config without mutating the repo copy.
    """
    target = tmp_path / "dopamine.yaml"
    target.write_text(_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return DopamineController(str(target))


# ── INV-5HT3: Higher stress -> higher serotonin (pre-desensitisation) ──


def test_higher_stress_produces_higher_serotonin() -> None:
    """INV-5HT3: Higher stress -> higher serotonin (pre-desensitisation).

    Sweeps three increasing stress levels. For each level, creates a fresh
    ODE (default params) and integrates 50 steps so the system reaches a
    quasi-steady state dominated by the stress input. The resulting serotonin
    level must be strictly monotonically increasing with stress.
    """
    stress_levels: List[float] = [0.1, 0.3, 0.5]  # INV-5HT3: sweep values
    n_steps: int = 50  # INV-5HT3: integration steps per stress level
    dt: float = 1.0  # INV-5HT3: RK4 time step

    recorded_levels: List[float] = []

    for stress in stress_levels:
        ode = SerotoninODE()  # fresh ODE each time, default params
        for _ in range(n_steps):
            ode.step(stress=stress, dt=dt)
        recorded_levels.append(ode.level)

    for i in range(1, len(stress_levels)):
        assert recorded_levels[i] > recorded_levels[i - 1], (
            f"INV-5HT3 VIOLATED: "
            f"observed level={recorded_levels[i]:.6f} at stress={stress_levels[i]:.2f} "
            f"is not greater than level={recorded_levels[i - 1]:.6f} "
            f"at stress={stress_levels[i - 1]:.2f}. "
            f"Expected monotonic increase pre-desensitisation. "
            f"steps={n_steps}, dt={dt}, "
            f"all_levels={[f'{v:.6f}' for v in recorded_levels]}"
        )


# ── INV-GABA4: vol -> 0 implies inhibition -> 0 ────────────────────


def test_gaba_inhibition_decreases_toward_zero_as_vix_decreases() -> None:
    """INV-GABA4: vol -> 0 implies inhibition -> 0.

    Simulates a trajectory of decreasing VIX values through the
    GABAPositionGate, checking that the late-time inhibition values
    converge toward zero as the volatility input vanishes.
    """
    bus = NeuroSignalBus()
    gate = GABAPositionGate(bus=bus)

    vix_trajectory: List[float] = [80.0, 40.0, 20.0, 10.0, 5.0, 1.0, 0.1]
    # INV-GABA4: decreasing VIX trajectory toward zero. The gate uses a
    # rectified sigmoid 2*sigmoid(z)-1 so a vanishing driver gives inhibition
    # -> 0, NOT the 0.5 floor of a plain sigmoid; the convergence bound is
    # therefore tight (a plain-sigmoid regression would leave final ~0.5 and
    # fail this 0.05 bound).
    convergence_threshold: float = 0.05

    trajectory: List[float] = []
    for vix in vix_trajectory:
        inh = gate.update_inhibition(
            vix=vix,
            volatility=0.0,  # INV-GABA4: isolate VIX contribution
            rpe=0.0,  # INV-GABA4: no RPE contribution
        )
        trajectory.append(inh)

    # Monotonicity: each inhibition <= previous
    for i in range(1, len(trajectory)):
        assert trajectory[i] <= trajectory[i - 1], (
            f"INV-GABA4 VIOLATED: "
            f"observed inhibition={trajectory[i]:.6f} at vix={vix_trajectory[i]:.1f} "
            f"exceeds inhibition={trajectory[i - 1]:.6f} "
            f"at vix={vix_trajectory[i - 1]:.1f}. "
            f"Expected monotonic decrease toward 0 as vol -> 0. "
            f"steps={len(vix_trajectory)}, w_vix={gate.w_vix}"
        )

    # Convergence: late-time value (final) should be low
    final = trajectory[-1]
    assert final < convergence_threshold, (
        f"INV-GABA4 VIOLATED: "
        f"observed final inhibition={final:.6f} at vix=0.1 "
        f"exceeds threshold={convergence_threshold:.2f}. "
        f"Expected inhibition -> 0 as vol -> 0. "
        f"steps={len(vix_trajectory)}, w_vix={gate.w_vix}"
    )


def test_gaba_dead_calm_market_has_zero_inhibition() -> None:
    """INV-GABA4 (exact baseline): zero stress drivers => inhibition 0.

    A plain sigmoid(z) floors the gate at sigmoid(0) = 0.5, permanently
    inhibiting position size by half even when VIX, realized volatility and
    the (rectified) RPE penalty are all zero. That contradicts INV-GABA4. The
    rectified sigmoid 2*sigmoid(0)-1 = 0 sends a dead-calm market to no
    inhibition. This test FAILS on the prior plain-sigmoid gate (returns 0.5).
    """
    gate = GABAPositionGate(bus=NeuroSignalBus())
    inhibition = gate.update_inhibition(vix=0.0, volatility=0.0, rpe=0.0)
    assert inhibition == 0.0, (
        f"INV-GABA4 VIOLATED: dead-calm inhibition={inhibition:.6f}, expected 0.0. "
        f"A non-zero baseline (e.g. the 0.5 plain-sigmoid floor) inhibits every "
        f"calm-market position. At vix=0, volatility=0, rpe=0, w_vix={gate.w_vix}."
    )


# ── INV-GABA5: vol -> inf implies inhibition -> 1 ──────────────────


def test_gaba_inhibition_approaches_one_as_vix_increases() -> None:
    """INV-GABA5: vol -> inf implies inhibition -> 1.

    Simulates a trajectory of increasing VIX values through the
    GABAPositionGate, checking that the late-time inhibition values
    converge toward 1 as the volatility input grows.
    """
    bus = NeuroSignalBus()
    gate = GABAPositionGate(bus=bus)

    vix_trajectory: List[float] = [10.0, 50.0, 100.0, 500.0, 1000.0, 5000.0]
    # INV-GABA5: increasing VIX trajectory toward infinity
    saturation_bound: float = 0.99  # epsilon: saturation floor at vix=5000

    trajectory: List[float] = []
    for vix in vix_trajectory:
        inh = gate.update_inhibition(
            vix=vix,
            volatility=0.0,  # INV-GABA5: isolate VIX contribution
            rpe=0.0,  # INV-GABA5: no RPE contribution
        )
        trajectory.append(inh)

    # Monotonicity: each inhibition >= previous
    for i in range(1, len(trajectory)):
        assert trajectory[i] >= trajectory[i - 1], (
            f"INV-GABA5 VIOLATED: "
            f"observed inhibition={trajectory[i]:.6f} at vix={vix_trajectory[i]:.1f} "
            f"is less than inhibition={trajectory[i - 1]:.6f} "
            f"at vix={vix_trajectory[i - 1]:.1f}. "
            f"Expected monotonic increase toward 1 as vol -> inf. "
            f"steps={len(vix_trajectory)}, w_vix={gate.w_vix}"
        )

    # Saturation: late-time value (final) must be close to 1
    final = trajectory[-1]
    assert final > saturation_bound, (
        f"INV-GABA5 VIOLATED: "
        f"observed final inhibition={final:.6f} at vix=5000 "
        f"does not exceed {saturation_bound}. "
        f"Expected inhibition -> 1 as vol -> inf. "
        f"steps={len(vix_trajectory)}, w_vix={gate.w_vix}"
    )


# ── INV-DA2: V -> V* under standard conditions (Robbins-Monro) ─────


def test_dopamine_value_converges_to_fixed_reward(
    dopamine_controller: DopamineController,
) -> None:
    """INV-DA2: V -> V* under standard TD(0) conditions.

    Iterates compute_rpe + update_value_estimate with a fixed reward=1.0
    for 3000 steps. The TD(0) update with constant reward and gamma < 1
    converges V toward r / (1 - gamma). After convergence, RPE should be
    near zero.
    """
    n_iterations: int = 3000  # INV-DA2: convergence steps (slow due to lr*(1-gamma)~0.002)
    fixed_reward: float = 1.0  # INV-DA2: constant reward signal
    rpe_tolerance: float = 0.05  # tolerance: RPE near-zero threshold

    gamma: float = float(dopamine_controller.config["discount_gamma"])

    for _ in range(n_iterations):
        v = dopamine_controller.value_estimate
        dopamine_controller.compute_rpe(
            reward=fixed_reward,
            value=v,
            next_value=v,
            discount_gamma=gamma,
        )
        dopamine_controller.update_value_estimate()

    final_rpe = abs(dopamine_controller.last_rpe)
    v_star = fixed_reward / (1.0 - gamma)
    assert final_rpe < rpe_tolerance, (
        f"INV-DA2 VIOLATED: "
        f"observed |RPE|={final_rpe:.6f} after {n_iterations} steps "
        f"exceeds tolerance={rpe_tolerance:.4f}. "
        f"Expected V -> V* = r/(1-gamma) = {v_star:.4f}. "
        f"gamma={gamma}, V_final={dopamine_controller.value_estimate:.6f}"
    )


# ── INV-DA4: V stabilises with fixed reward ─────────────────────────


def test_dopamine_value_estimate_stabilises(
    dopamine_controller: DopamineController,
) -> None:
    """INV-DA4: Value estimate stabilises with fixed reward.

    Runs 3000 TD(0) steps with fixed reward and tracks the value_estimate
    trajectory. Late-time standard deviation (last 200) must be smaller
    than early-time standard deviation (first 200), demonstrating that V
    is settling toward its fixed point.
    """
    n_iterations: int = 3000  # INV-DA4: total convergence steps (slow due to lr*(1-gamma)~0.002)
    fixed_reward: float = 1.0  # INV-DA4: constant reward signal
    window: int = 200  # INV-DA4: window size for std comparison

    gamma: float = float(dopamine_controller.config["discount_gamma"])

    trajectory: List[float] = []
    for _ in range(n_iterations):
        v = dopamine_controller.value_estimate
        dopamine_controller.compute_rpe(
            reward=fixed_reward,
            value=v,
            next_value=v,
            discount_gamma=gamma,
        )
        dopamine_controller.update_value_estimate()
        trajectory.append(dopamine_controller.value_estimate)

    early_std = float(np.std(trajectory[:window]))
    late_std = float(np.std(trajectory[-window:]))

    assert late_std < early_std, (
        f"INV-DA4 VIOLATED: "
        f"observed late_std={late_std:.8f} >= early_std={early_std:.8f}. "
        f"Expected V to stabilise (decreasing variance over trajectory). "
        f"steps={n_iterations}, window={window}, "
        f"gamma={gamma}, V_final={trajectory[-1]:.6f}"
    )


# ── INV-DA5: E[delta] ~ 0 at equilibrium ────────────────────────────


def test_dopamine_mean_rpe_near_zero_at_equilibrium(
    dopamine_controller: DopamineController,
) -> None:
    """INV-DA5: E[delta] approx 0 at equilibrium.

    Warms up the controller for 3000 steps with fixed reward, then collects
    50 more RPEs. The mean of collected RPEs must be near zero, confirming
    the value estimate has converged and the prediction error is unbiased.
    """
    warmup_steps: int = 3000  # INV-DA5: warm-up for convergence (slow due to lr*(1-gamma)~0.002)
    collect_steps: int = 50  # INV-DA5: post-convergence sample size
    mean_tolerance: float = 0.1  # tolerance: |E[delta]| bound

    gamma: float = float(dopamine_controller.config["discount_gamma"])
    fixed_reward: float = 1.0  # INV-DA5: constant reward signal

    # Warm-up phase
    for _ in range(warmup_steps):
        v = dopamine_controller.value_estimate
        dopamine_controller.compute_rpe(
            reward=fixed_reward,
            value=v,
            next_value=v,
            discount_gamma=gamma,
        )
        dopamine_controller.update_value_estimate()

    # Collection phase
    rpes: List[float] = []
    for _ in range(collect_steps):
        v = dopamine_controller.value_estimate
        rpe = dopamine_controller.compute_rpe(
            reward=fixed_reward,
            value=v,
            next_value=v,
            discount_gamma=gamma,
        )
        dopamine_controller.update_value_estimate()
        rpes.append(rpe)

    mean_rpe = float(np.mean(rpes))
    assert abs(mean_rpe) < mean_tolerance, (
        f"INV-DA5 VIOLATED: "
        f"observed |mean(RPE)|={abs(mean_rpe):.6f} "
        f"exceeds tolerance={mean_tolerance:.4f}. "
        f"Expected E[delta] ~ 0 at equilibrium after {warmup_steps} warm-up steps. "
        f"steps={collect_steps}, gamma={gamma}, "
        f"V_final={dopamine_controller.value_estimate:.6f}"
    )
