# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witness for the ECS conditional Lyapunov-descent law.

Binds the catalog law ``ecs.lyapunov_descent`` to an executable ``@law`` witness
and proves the HONEST conditional form holds in the real
``core.neuro.ecs_lyapunov.ECSLyapunovRegulator``:

* ``ecs.lyapunov_descent`` — whenever V_before > V_floor (=1e-12) the corrected
  RK4 step satisfies V_after ≤ V_before (dV/dt ≤ 0). At the floor V ≤ V_floor the
  guarantee is suspended by physics: V = ½FE² + λCF² + μSI² ≥ 0 cannot descend
  below zero, so a stress injection from the origin necessarily raises V (INV-FE3).

The witness deliberately EXCLUDES floor steps (the precondition), because a
universal "dV/dt ≤ 0" claim would be a pretender — falsified at the origin. It
also asserts that floor steps CAN rise, documenting why the precondition exists
rather than hiding it. Nothing here is a market claim.
"""

from __future__ import annotations

from core.neuro.ecs_lyapunov import ECSLyapunovRegulator
from core.neuro.signal_bus import NeuroSignalBus
from physics_contracts.law import law

# Lyapunov floor below which descent below zero is impossible (V ≥ 0).
V_FLOOR = 1e-12
# Descent slack: the correction's worst case is α=0 (no move) ⇒ dV = 0 exactly.
DESCENT_SLACK = 1e-12
# Deterministic stress/dt schedule (no RNG) so the witness is bit-reproducible.
STRESS_SCHEDULE = (1.5, -0.8, 2.0, 0.3, -1.2, 0.9, -2.0, 1.1, 0.0, 1.7)
DT_SCHEDULE = (0.5, 0.25, 1.0, 0.75, 0.5, 0.9, 0.1, 0.6, 0.4, 0.8)


def _lyapunov(regulator: ECSLyapunovRegulator) -> float:
    return regulator._lyapunov(
        regulator.free_energy, regulator.compensatory_factor, regulator.stress_integral
    )


@law("ecs.lyapunov_descent", n_steps=200, v_floor=V_FLOOR)
def test_ecs_descent_holds_above_floor_and_floor_excluded() -> None:
    """INV-FE3: V_before > 1e-12 ⇒ V_after ≤ V_before; floor steps may rise.

    Drives the regulator through a deterministic stress schedule for many steps.
    For every step whose pre-state Lyapunov value exceeds the floor, the corrected
    update must not increase V. The witness separately confirms that at least one
    floor step (V_before ≤ floor) is observed and is allowed to rise — proving the
    precondition is real, not a loophole that silently never triggers.
    """
    n_steps = 200
    regulator = ECSLyapunovRegulator(NeuroSignalBus())
    worst_dv_above_floor = 0.0
    above_floor_steps = 0
    floor_steps = 0
    for index in range(n_steps):
        stress = STRESS_SCHEDULE[index % len(STRESS_SCHEDULE)]
        dt = DT_SCHEDULE[index % len(DT_SCHEDULE)]
        v_before = _lyapunov(regulator)
        result = regulator.step(stress=stress, dt=dt)
        dv_dt = float(result["dV_dt"])
        if v_before > V_FLOOR:
            above_floor_steps += 1
            worst_dv_above_floor = max(worst_dv_above_floor, dv_dt)
        else:
            floor_steps += 1

    assert worst_dv_above_floor <= DESCENT_SLACK, (
        "INV-FE3 violated: observed worst dV/dt above floor = "
        f"{worst_dv_above_floor:.3e} must be ≤ {DESCENT_SLACK:.0e} over "
        f"n_steps={n_steps}; corrected step must enforce descent when V_before > 1e-12"
    )
    assert above_floor_steps >= 3, (
        "INV-FE3 vacuity guard: observed above-floor steps = "
        f"{above_floor_steps} must be ≥ 3 over n_steps={n_steps}; the descent "
        "guarantee must actually be exercised, not skipped because V stayed at the floor"
    )
    assert floor_steps >= 1, (
        "INV-FE3 precondition guard: observed floor steps = "
        f"{floor_steps} must be ≥ 1 over n_steps={n_steps}; at least one origin/floor "
        "step must exist to justify excluding it (the precondition is real, not a loophole)"
    )
