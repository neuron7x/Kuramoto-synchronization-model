from __future__ import annotations

import random

from geosync.neuroeconomics.reset_wave_engine import (
    ResetWaveConfig,
    audit_critical_centers,
    latent_interpretive_forecast_layer,
    run_reset_wave,
)


def test_reset_wave_engine_converges_and_decreases_potential() -> None:
    cfg = ResetWaveConfig(coupling_gain=1.0, dt=0.1, steps=64, convergence_tol=0.02)
    out = run_reset_wave([0.4, -0.3, 0.2], [0.0, 0.0, 0.0], cfg)
    assert not out.locked
    assert out.final_potential <= out.initial_potential
    assert out.converged


def test_reset_wave_engine_lock_on_extreme_drift() -> None:
    cfg = ResetWaveConfig(max_phase_error=0.5)
    out = run_reset_wave([2.0, -2.0], [0.0, 0.0], cfg)
    assert out.locked
    assert not out.converged
    assert out.final_potential == out.initial_potential


def test_reset_wave_engine_deterministic_trajectory() -> None:
    cfg = ResetWaveConfig(coupling_gain=0.8, dt=0.05, steps=20)
    a = run_reset_wave([0.1, -0.2], [0.0, 0.0], cfg)
    b = run_reset_wave([0.1, -0.2], [0.0, 0.0], cfg)
    assert a == b


def test_reset_wave_engine_rk4_fixed_and_euler_are_stable() -> None:
    base = [0.0, 0.0, 0.0]
    node = [0.4, -0.3, 0.2]
    rk = run_reset_wave(node, base, ResetWaveConfig(integrator="rk4_fixed", steps=50, dt=0.05))
    eu = run_reset_wave(node, base, ResetWaveConfig(integrator="euler", steps=50, dt=0.05))
    assert rk.final_potential <= rk.initial_potential
    assert eu.final_potential <= eu.initial_potential


def test_forecast_layer_outputs_supported_class() -> None:
    out = run_reset_wave([0.3, -0.2], [0.0, 0.0], ResetWaveConfig())
    cls, conf = latent_interpretive_forecast_layer(out)
    assert cls in {"CONVERGING", "LOCKED", "OSCILLATORY", "DIVERGING", "UNSTABLE", "UNKNOWN"}
    assert 0.0 <= conf <= 1.0


def test_forecast_layer_accuracy_on_labeled_simulations() -> None:
    rng = random.Random(9)
    total, correct = 0, 0
    for _ in range(120):
        cfg = ResetWaveConfig(
            coupling_gain=rng.choice([0.2, 0.5, 1.0, 1.5, 3.0]),
            dt=rng.choice([0.02, 0.05, 0.1, 0.3]),
            steps=48,
            max_phase_error=rng.choice([0.6, 1.0, 3.14]),
            convergence_tol=0.03,
        )
        base = [rng.uniform(-0.5, 0.5) for _ in range(5)]
        node = [b + rng.uniform(-1.2, 1.2) for b in base]
        out = run_reset_wave(node, base, cfg)
        pred, _ = latent_interpretive_forecast_layer(out)
        if out.locked:
            true = "LOCKED"
        elif out.converged:
            true = "CONVERGING"
        else:
            slope = out.final_potential - out.initial_potential
            true = (
                "DIVERGING"
                if slope > 1e-6
                else ("OSCILLATORY" if abs(slope) < 1e-4 else "UNSTABLE")
            )
        total += 1
        correct += int(pred == true)
    assert correct / total >= 0.95


def test_critical_center_audit_has_seven_passed_centers() -> None:
    audits = audit_critical_centers()
    assert len(audits) == 7
    assert all(a.passed for a in audits)


def test_residual_potential_floor_preserves_nonzero_residual_heat() -> None:
    cfg = ResetWaveConfig(
        coupling_gain=1.0,
        dt=0.05,
        steps=120,
        convergence_tol=0.01,
        residual_potential_floor=1e-3,
    )
    out = run_reset_wave([0.8, -0.6, 0.3], [0.0, 0.0, 0.0], cfg)
    assert out.final_potential > 0.0


def test_reject_negative_residual_potential_floor() -> None:
    try:
        run_reset_wave([0.1], [0.0], ResetWaveConfig(residual_potential_floor=-1e-6))
    except ValueError as exc:
        assert "residual_potential_floor must be >= 0" in str(exc)
    else:
        raise AssertionError("Expected ValueError for negative residual_potential_floor")
