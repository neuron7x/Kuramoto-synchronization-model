# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Cognitive-core soundness: the falsification battery is a REALITY DETECTOR.

The cognitive core is the active invariant centre of the system — it holds the
goals, boundaries and admissible trajectories, routes prediction streams through
deterministic gates, and must preserve controllability when reality diverges
from the model. Academic verification states a law and checks it ONCE. A
cognitive core must additionally prove that its gates actually FIRE the instant
the measured world leaves the invariant — a gate that cannot fire is a rubber
stamp, not a compass.

This module is the hypothesis-destruction machine turned on the core itself.
For each EXACT law it forms the law's own predicate ``P(measured) -> {satisfied,
violated}`` over the REAL solver output, then injects a deterministic
perturbation beyond threshold and proves the predicate flips
``satisfied -> violated``. The structural soundness operator is

    gate_fires(P, real, perturbed) := P(real) AND NOT P(perturbed)

A SOUND gate fires (``True``); a vacuous always-satisfied gate does not. The
second test proves the soundness operator is itself not fooled by a rubber
stamp. Together: completeness (every law is witnessed — enforced by
``law_requires_positive_and_negative_witness``) PLUS soundness (every gate fires
on divergence — enforced here) = the core provably converts
"reality diverged" into "gate fired" for the exact-law spine.

All five solvers are REUSED, never reimplemented.
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import Callable

import networkx as nx
import numpy as np

from analytics.math_trading.kelly_criterion import kelly_from_edge_variance
from core.dro_ara.engine import derive_gamma
from core.indicators.gauss_bonnet import euler_characteristic, gauss_bonnet_residual
from core.kuramoto.ott_antonsen import OttAntonsenEngine
from core.physics.landauer import K_BOLTZMANN, bit_erasure_cost


def _gate_fires(
    predicate: Callable[[float], bool], real: float, perturbed: float
) -> bool:
    """Structural soundness operator: a gate fires iff it accepts reality and rejects divergence."""
    return predicate(real) and not predicate(perturbed)


def _exact_law_gates() -> list[tuple[str, Callable[[float], bool], float, float]]:
    """Build (name, predicate, real_measured, perturbed_measured) for the exact-law spine.

    ``real_measured`` is the residual/deviation produced by the REAL solver (sits
    at the invariant); ``perturbed_measured`` is that value pushed one
    deterministic step beyond the law's own threshold (a simulated
    reality-divergence). Each predicate is the SAME satisfaction test the law's
    production witness uses.
    """
    gates: list[tuple[str, Callable[[float], bool], float, float]] = []

    # 1. Gauss-Bonnet: residual Sum_x K(x) - chi(G) == 0 exactly (over Q).
    g = nx.cycle_graph(6)
    gb_residual = float(gauss_bonnet_residual(g))  # 0 for a valid clique complex
    assert euler_characteristic(g) == 0  # cycle chi = 0 (anchors the solver)
    gates.append(
        ("gauss_bonnet", lambda m: m == 0.0, gb_residual, gb_residual + 1.0)
    )

    # 2. Landauer: per-bit erasure cost >= k_B*T*ln2 (equality at the floor).
    temperature = 300.0
    floor = K_BOLTZMANN * temperature * math.log(2.0)
    cost = bit_erasure_cost(1.0, temperature)  # == floor exactly
    gates.append(
        ("landauer", lambda m: m >= floor * (1.0 - 1e-12), cost, 0.5 * floor)
    )

    # 3. Kelly: f* == mu / sigma^2 (small-edge log-optimal fraction).
    mu, sigma_sq = 0.002, 2.5e-3
    target = mu / sigma_sq
    f_star = kelly_from_edge_variance(mu, sigma_sq, fractional_kelly=1.0, max_fraction=10.0)
    gates.append(
        ("kelly", lambda m: abs(m - target) <= 1e-12, f_star, f_star + 0.1)
    )

    # 4. DRO-ARA: gamma == 2H + 1 (derived from the DFA Hurst, never assigned).
    series = np.cumsum(np.random.default_rng(7).normal(0.0, 1.0, 1024))
    gamma, hurst, _r2 = derive_gamma(series)
    expected_gamma = 2.0 * hurst + 1.0
    gates.append(
        ("dro_ara_gamma", lambda m: abs(m - expected_gamma) < 1e-5, gamma, gamma + 0.5)
    )

    # 5. Ott-Antonsen: supercritical R_inf == sqrt(1 - 2*delta/K).
    delta, coupling = 0.5, 2.0
    r_exact = math.sqrt(1.0 - (2.0 * delta) / coupling)
    r_inf = float(OttAntonsenEngine(K=coupling, delta=delta).integrate(T=200.0, dt=0.01, R0=0.05).R[-1])
    gates.append(
        ("ott_antonsen", lambda m: abs(m - r_exact) < 1e-6, r_inf, r_inf + 0.01)
    )

    return gates


def test_exact_law_gates_fire_on_reality_divergence() -> None:
    """Soundness: each exact-law gate accepts the real value and FIRES on a planted divergence.

    This is the above-academic guarantee. A law that only ever sees conforming
    inputs is untested as a detector; here we prove the predicate returns
    SATISFIED on the real solver output and VIOLATED the instant the measured
    value leaves the invariant band. A gate that fails to fire would let
    reality-divergence pass silently — the core would lose controllability.
    """
    gates = _exact_law_gates()
    assert len(gates) >= 5, (
        f"COGNITIVE-CORE SOUNDNESS under-covered: only {len(gates)} exact-law "
        f"gates exercised; the exact spine must cover >= 5 independent laws."
    )
    for name, predicate, real, perturbed in gates:
        assert predicate(real), (
            f"COGNITIVE-CORE SOUNDNESS VIOLATED: gate '{name}' rejected the REAL "
            f"solver output (measured={real!r}); a sound gate must accept reality "
            f"that sits on the invariant. The compass points the wrong way."
        )
        assert not predicate(perturbed), (
            f"COGNITIVE-CORE SOUNDNESS VIOLATED: gate '{name}' did NOT fire on a "
            f"reality-divergence (perturbed={perturbed!r} beyond threshold from "
            f"real={real!r}). A gate that cannot fire is a rubber stamp, not an "
            f"invariant centre — reality-divergence would pass silently and the "
            f"core would lose controllability."
        )
        assert _gate_fires(predicate, real, perturbed), (
            f"COGNITIVE-CORE SOUNDNESS VIOLATED: gate '{name}' is not a "
            f"discriminator (gate_fires=False). real={real!r}, perturbed={perturbed!r}."
        )


def test_soundness_operator_rejects_rubber_stamp_gate() -> None:
    """Negative control: the soundness operator itself is not fooled by a vacuous gate.

    A rubber-stamp predicate that accepts everything must NOT be counted as a
    firing (sound) gate, while a genuine discriminating predicate must. If the
    soundness operator scored the rubber stamp as sound, the whole core-integrity
    proof would be vacuous.
    """
    def vacuous(_m: float) -> bool:
        return True  # rubber stamp: accepts everything

    def sound(m: float) -> bool:
        return abs(m) < 1e-9

    assert not _gate_fires(vacuous, 0.0, 999.0), (
        "COGNITIVE-CORE META VIOLATED: a vacuous always-satisfied gate was scored "
        "as sound; the soundness operator must reject rubber stamps or the "
        "core-integrity proof collapses."
    )
    assert _gate_fires(sound, 0.0, 1.0), (
        "COGNITIVE-CORE META VIOLATED: a genuine discriminating gate was scored as "
        "non-firing; the soundness operator must accept real detectors."
    )
    # A gate that rejects EVERYTHING (always-violated) is also not a detector:
    # it would reject reality itself, so it must not be counted sound either.
    def always_violated(_m: float) -> bool:
        return False  # rejects everything, including reality

    assert not _gate_fires(always_violated, 0.0, 1.0), (
        "COGNITIVE-CORE META VIOLATED: an always-reject gate was scored as sound; "
        "a gate that rejects reality is not a controllability-preserving detector."
    )
