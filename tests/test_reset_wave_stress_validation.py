from __future__ import annotations

import math
import random

from geosync.neuroeconomics.reset_wave_engine import ResetWaveConfig, run_reset_wave


def test_stress_surface_potential_and_lock_invariants() -> None:
    rng = random.Random(20260503)
    gains = [0.2, 0.5, 1.0, 1.5]
    dts = [0.02, 0.05, 0.1]
    tolerances = [0.01, 0.03, 0.05]
    max_errors = [0.4, 1.0, 3.14]

    for gain in gains:
        for dt in dts:
            for tol in tolerances:
                for max_err in max_errors:
                    cfg = ResetWaveConfig(
                        coupling_gain=gain,
                        dt=dt,
                        steps=48,
                        convergence_tol=tol,
                        max_phase_error=max_err,
                    )
                    for _ in range(20):
                        baseline = [rng.uniform(-0.5, 0.5) for _ in range(6)]
                        nodes = [b + rng.uniform(-1.2, 1.2) for b in baseline]
                        out = run_reset_wave(nodes, baseline, cfg)
                        if out.locked:
                            assert out.final_potential == out.initial_potential
                        else:
                            assert out.final_potential <= out.initial_potential + 1e-12


def test_negative_nonconvergence_large_dt_gain() -> None:
    cfg = ResetWaveConfig(coupling_gain=8.0, dt=1.5, steps=8, max_phase_error=math.pi)
    out = run_reset_wave([0.9, -1.1, 0.6], [0.0, 0.0, 0.0], cfg)
    assert not out.converged
