from __future__ import annotations

from geosync.neuroeconomics.reset_wave_engine import (
    AsyncResilienceConfig,
    ResetWaveConfig,
    run_reset_wave_async_resilient,
)


def test_async_resilience_handles_jitter_and_dropout() -> None:
    out = run_reset_wave_async_resilient(
        [0.8, -0.7, 0.4],
        [0.0, 0.0, 0.0],
        ResetWaveConfig(coupling_gain=1.0, dt=0.05, steps=80, residual_potential_floor=1e-3),
        AsyncResilienceConfig(message_jitter=0.01, dropout_rate=0.2, reentry_gain=0.4, seed=7),
    )
    assert out.final_potential <= out.initial_potential


def test_async_resilience_can_lock_on_persistent_monotonicity_break() -> None:
    out = run_reset_wave_async_resilient(
        [1.2, -1.2, 1.1],
        [0.0, 0.0, 0.0],
        ResetWaveConfig(coupling_gain=6.0, dt=0.4, steps=30, residual_potential_floor=1e-3),
        AsyncResilienceConfig(
            message_jitter=0.3,
            dropout_rate=0.0,
            reentry_gain=0.3,
            monotonic_guard=True,
            seed=4,
        ),
    )
    assert out.locked or out.final_potential <= out.initial_potential


def test_async_resilience_rejects_bad_dropout_range() -> None:
    try:
        run_reset_wave_async_resilient(
            [0.1],
            [0.0],
            ResetWaveConfig(),
            AsyncResilienceConfig(dropout_rate=1.1),
        )
    except ValueError as exc:
        assert "dropout_rate must be in [0,1)" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid dropout rate")
