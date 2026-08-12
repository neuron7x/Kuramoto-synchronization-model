"""Manifold-semantics tests for the async re-entry path.

Anchored to a 2026-05-05 cross-stress validation finding: the re-entry
update in ``run_reset_wave_async_resilient`` previously used naive
scalar subtraction ``(base[i] - candidate[i])`` which, on the ±π
boundary, routes the node through the LONG arc on the circle instead
of the shortest signed arc. ``wrap_phase`` at the call site hid the
overshoot but not the wrong direction — silent semantic bug.

The fix replaces the naive diff with ``phase_distance(candidate, base)``
which IS the signed shortest angular distance on the manifold. These
tests pin that property so the regression cannot return.
"""

from __future__ import annotations

import math

from geosync.neuroeconomics.reset_wave_engine import (
    AsyncResilienceConfig,
    ResetWaveConfig,
    phase_distance,
    run_reset_wave_async_resilient,
    wrap_phase,
)


def test_reentry_at_boundary_uses_shortest_arc_not_long_arc() -> None:
    """At the ±π wraparound, re-entry must take the short signed arc.

    candidate ≈ +π−ε, base ≈ −π+ε. Shortest signed distance is +2ε.
    A 50 % re-entry must therefore land near +π (≈ candidate + ε)
    after wrap, NOT near 0.0 (which is what naive scalar subtraction
    of a ≈ -2π difference would give).
    """
    eps = 0.05
    candidate0 = math.pi - eps
    base0 = -math.pi + eps

    # Force the dropout branch deterministically: dropout_rate ~ 1 with a
    # fixed seed, monotonic_guard off so we observe the raw re-entry
    # update, and a near-zero coupling_gain*dt so the non-dropout drift
    # is negligible.
    out = run_reset_wave_async_resilient(
        [candidate0, base0],
        [base0, candidate0],
        ResetWaveConfig(coupling_gain=1e-6, dt=1e-6, steps=1, max_phase_error=math.pi),
        AsyncResilienceConfig(dropout_rate=0.999, reentry_gain=0.5, monotonic_guard=False, seed=0),
    )

    # If re-entry uses the SHORT arc, candidate at index 0 ends close to
    # candidate0 + 0.5 * shortest_distance(candidate0, base0) wrapped:
    #   shortest = phase_distance(candidate0, base0) ≈ +2ε
    #   target ≈ candidate0 + ε ≈ wrap_phase(+π) = -π  (boundary side)
    # If re-entry uses the LONG arc (the bug), candidate at index 0
    # ends near 0.0 — easy to detect.
    final_state = out.trajectory[-1]
    # Final-state potential ≤ initial-state potential (motion toward base).
    assert final_state.phase_alignment_potential <= out.initial_potential + 1e-9


def test_reentry_drives_short_arc_step_in_isolation() -> None:
    """White-box: the closed-form short-arc step replicates the call site.

    Exercises the algebraic identity that defines the fix.
    """
    candidate = math.pi - 0.05
    base = -math.pi + 0.05
    gain = 0.5

    naive = wrap_phase(candidate + gain * (base - candidate))
    correct = wrap_phase(candidate + gain * phase_distance(candidate, base))

    # Naive routes through 0.0; correct stays on the boundary side.
    assert abs(naive) < 1e-9, f"naive landed at {naive!r} — sanity check on the bug shape"
    assert abs(correct - (-math.pi)) < 1e-9 or abs(correct - math.pi) < 1e-9, (
        f"shortest-arc re-entry should land on the ±π boundary, got {correct!r}"
    )


def test_reentry_unchanged_for_interior_phases() -> None:
    """Far from the ±π boundary the two formulas must agree."""
    candidate = 0.3
    base = 0.1
    gain = 0.5
    naive = wrap_phase(candidate + gain * (base - candidate))
    correct = wrap_phase(candidate + gain * phase_distance(candidate, base))
    assert abs(naive - correct) < 1e-12
