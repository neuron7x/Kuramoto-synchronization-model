"""NHS manifold-invariance regression pin (cycle #6).

`NeuroHomeostaticStabilizer.re_adaptation_to_baseline` uses naive
scalar subtraction `(base - node)` to compute phase_diffs, but the
downstream operations are `1 - cos(diff)` and `sin(diff)` — both
2π-periodic. Therefore NHS is *incidentally* manifold-correct: a node
near +π and a baseline near -π give the same energy and the same
correction signal as the shortest-arc form would.

Cycle #2 fixed a real manifold-bug in `run_reset_wave_async_resilient`
(which used `+= gain * (base - candidate)` — linear-phase add, which is
NOT 2π-periodic). NHS does not have that bug *because* every contact
between (base - node) and the rest of the system is mediated by
sin/cos.

This test pins that property: any future refactor that, for
"consistency", introduces a linear-phase combination of `phase_diffs`
in NHS will fail this test. The current code's safety is then visible
to maintainers, not implicit.
"""

from __future__ import annotations

import math

from geosync.neuroeconomics.homeostatic_stabilizer import NeuroHomeostaticStabilizer


def test_nhs_re_adaptation_invariant_to_2pi_shift_of_baseline() -> None:
    """Shifting baseline by 2π must not change the report's energy fields."""
    nhs = NeuroHomeostaticStabilizer()
    nodes = [0.4, -0.3, 0.2]
    base_a = [0.0, 0.0, 0.0]
    base_b = [2 * math.pi, -2 * math.pi, 4 * math.pi]
    cfg = dict(serotonin_gain=1.0, convergence_tol=0.05, max_phase_error=10.0)
    a = nhs.re_adaptation_to_baseline(node_phases=nodes, baseline_phases=base_a, **cfg)
    b = NeuroHomeostaticStabilizer().re_adaptation_to_baseline(
        node_phases=nodes, baseline_phases=base_b, **cfg
    )
    # 1 - cos(d) and sin(d) are 2π-periodic; the report fields must agree
    # to floating tolerance.
    assert math.isclose(a.pre_reset_energy, b.pre_reset_energy, abs_tol=1e-9)
    assert math.isclose(a.reset_energy, b.reset_energy, abs_tol=1e-9)
    assert math.isclose(a.post_reset_energy, b.post_reset_energy, abs_tol=1e-9)


def test_nhs_re_adaptation_at_pi_boundary_does_not_explode() -> None:
    """Near-±π phases must produce a well-bounded report.

    With shortest-distance ≈ 0.10 across the wraparound, the energy must
    stay near 1 - cos(0.10) ≈ 0.005, not in the absurd range that a
    long-arc reading would give if the rest of NHS were linear.
    """
    nhs = NeuroHomeostaticStabilizer()
    report = nhs.re_adaptation_to_baseline(
        node_phases=[math.pi - 0.05, -math.pi + 0.05],
        baseline_phases=[-math.pi + 0.05, math.pi - 0.05],
        serotonin_gain=1.0,
        convergence_tol=0.5,
        max_phase_error=2 * math.pi,
    )
    expected = 1.0 - math.cos(0.10)
    assert math.isclose(report.pre_reset_energy, expected, abs_tol=1e-6)
    assert math.isclose(report.post_reset_energy, expected, abs_tol=1e-6)
    assert not report.safety_lock
