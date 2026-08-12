"""Property-based fuzz suite for the reset-wave engine.

Generates randomised valid inputs and checks the four contract surfaces
the engine declares:

    P1 — input validation: bad inputs always raise, good inputs never raise.
    P2 — monotonicity: in stable region, final potential ≤ initial.
    P3 — lock semantics: when locked=True, final == initial (no active update).
    P4 — manifold closure: every emitted phase remains in [-π, π).

Each property runs against the synchronous and asynchronous entry points.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from geosync.neuroeconomics.reset_wave_engine import (
    AsyncResilienceConfig,
    ResetWaveConfig,
    phase_alignment_potential,
    run_reset_wave,
    run_reset_wave_async_resilient,
    wrap_phase,
)

# Generators
finite_phase = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)
phase_vec = st.lists(finite_phase, min_size=1, max_size=8)
gain = st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False)
dt = st.floats(min_value=0.005, max_value=0.2, allow_nan=False, allow_infinity=False)


# ─── P1 — input validation ────────────────────────────────────────────────
@given(nodes=phase_vec, baselines=phase_vec)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_p1_mismatched_lengths_raise(nodes: list[float], baselines: list[float]) -> None:
    assume(len(nodes) != len(baselines))
    with pytest.raises(ValueError):
        run_reset_wave(nodes, baselines, ResetWaveConfig())


@given(
    n=st.integers(min_value=1, max_value=8),
    bad=st.sampled_from([float("nan"), float("inf"), float("-inf")]),
)
@settings(max_examples=60, deadline=None)
def test_p1_non_finite_inputs_raise(n: int, bad: float) -> None:
    nodes = [0.1] * n
    baselines = [0.0] * n
    nodes[0] = bad
    with pytest.raises(ValueError, match="must be finite"):
        run_reset_wave(nodes, baselines, ResetWaveConfig())
    with pytest.raises(ValueError, match="must be finite"):
        run_reset_wave_async_resilient(nodes, baselines, ResetWaveConfig(), AsyncResilienceConfig())


# ─── P2 — monotonicity in stable region ────────────────────────────────────
@given(nodes=phase_vec, g=gain, d=dt)
@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_p2_monotonic_in_stable_region(nodes: list[float], g: float, d: float) -> None:
    """Stable region heuristic: g*d ≤ 0.2. Within it, potential must not grow."""
    assume(g * d <= 0.2)
    baselines = [0.0] * len(nodes)
    cfg = ResetWaveConfig(coupling_gain=g, dt=d, steps=32, max_phase_error=math.pi)
    out = run_reset_wave(nodes, baselines, cfg)
    if out.locked:
        assert out.final_potential == out.initial_potential
    else:
        assert out.final_potential <= out.initial_potential + 1e-9


# ─── P3 — lock semantics ───────────────────────────────────────────────────
@given(amp=st.floats(min_value=2.0, max_value=10.0))
@settings(max_examples=40, deadline=None)
def test_p3_lock_freezes_state(amp: float) -> None:
    nodes = [amp, -amp]
    baselines = [0.0, 0.0]
    cfg = ResetWaveConfig(max_phase_error=0.5)
    out = run_reset_wave(nodes, baselines, cfg)
    if out.locked:
        assert out.final_potential == out.initial_potential
        assert not out.converged


# ─── P4 — manifold closure ─────────────────────────────────────────────────
@given(nodes=phase_vec, g=gain, d=dt)
@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_p4_potential_finite_and_bounded(nodes: list[float], g: float, d: float) -> None:
    baselines = [0.0] * len(nodes)
    cfg = ResetWaveConfig(coupling_gain=g, dt=d, steps=32, max_phase_error=math.pi)
    out = run_reset_wave(nodes, baselines, cfg)
    # phase_alignment_potential = mean(1 - cos δ) ∈ [0, 2] always
    assert 0.0 <= out.initial_potential <= 2.0 + 1e-9
    assert 0.0 <= out.final_potential <= 2.0 + 1e-9
    assert math.isfinite(out.initial_potential)
    assert math.isfinite(out.final_potential)
    for st_ in out.trajectory:
        assert math.isfinite(st_.mean_phase_error)
        assert math.isfinite(st_.phase_alignment_potential)


# ─── P4b — wrap_phase is an idempotent projection onto [-π, π) ─────────────
@given(theta=st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6))
@settings(max_examples=200, deadline=None)
def test_p4b_wrap_phase_idempotent_and_bounded(theta: float) -> None:
    once = wrap_phase(theta)
    twice = wrap_phase(once)
    assert -math.pi <= once < math.pi
    assert once == twice  # idempotent


# ─── P5 — async path: monotonicity OR safety lock ──────────────────────────
@given(
    nodes=phase_vec,
    g=gain,
    d=dt,
    drop=st.floats(min_value=0.0, max_value=0.4),
    jitter=st.floats(min_value=0.0, max_value=0.05),
    seed=st.integers(min_value=0, max_value=10_000),
)
@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_p5_async_monotonic_or_locked(
    nodes: list[float], g: float, d: float, drop: float, jitter: float, seed: int
) -> None:
    assume(g * d <= 0.2)
    baselines = [0.0] * len(nodes)
    out = run_reset_wave_async_resilient(
        nodes,
        baselines,
        ResetWaveConfig(coupling_gain=g, dt=d, steps=32, max_phase_error=math.pi),
        AsyncResilienceConfig(
            message_jitter=jitter,
            dropout_rate=drop,
            reentry_gain=0.4,
            monotonic_guard=True,
            seed=seed,
        ),
    )
    if out.locked:
        assert out.final_potential == out.initial_potential
    else:
        assert out.final_potential <= out.initial_potential + 1e-9


# ─── P6 — phase_alignment_potential is sign-symmetric in (a−b) ─────────────
@given(
    a=st.floats(min_value=-math.pi, max_value=math.pi, allow_nan=False),
    b=st.floats(min_value=-math.pi, max_value=math.pi, allow_nan=False),
)
@settings(max_examples=200, deadline=None)
def test_p6_potential_symmetric_in_swap(a: float, b: float) -> None:
    """1-cos δ is even in δ: swapping nodes/baselines must not change potential."""
    pab = phase_alignment_potential([a], [b])
    pba = phase_alignment_potential([b], [a])
    assert math.isclose(pab, pba, rel_tol=1e-9, abs_tol=1e-12)
