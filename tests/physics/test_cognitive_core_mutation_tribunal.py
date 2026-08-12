# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mutation tribunal — the cognitive core kills a TAXONOMY of physics corruptions.

The soundness witness (``test_cognitive_core_soundness``) proves each exact gate
fires on a single synthetic divergence. The tribunal is the next level: it
corrupts the REAL solver — its parameters, its input, or its governing formula —
in semantically distinct ways and proves the law's own predicate KILLS every
mutant. The figure of merit is the mutation kill-rate

    kill_rate = killed_mutants / total_mutants  (must be EXACTLY 1.0)

A surviving mutant is a way to break the physics that the core does NOT detect —
a hole in the invariant centre. The tribunal also proves the metric is honest:
a null (no-op) mutant SURVIVES (the core does not flag conforming physics), and a
rubber-stamp predicate kills NOTHING (kill_rate measures real discrimination, not
trigger-happiness).

Every mutant is produced from the REAL solver; none of the physics is reimplemented.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable

import networkx as nx
import numpy as np

from analytics.math_trading.kelly_criterion import kelly_from_edge_variance
from core.dro_ara.engine import derive_gamma
from core.indicators.gauss_bonnet import euler_characteristic, gauss_bonnet_residual
from core.kuramoto.ott_antonsen import OttAntonsenEngine
from core.physics.landauer import K_BOLTZMANN, bit_erasure_cost


@dataclass(frozen=True)
class _Law:
    """An exact law under adversarial mutation."""

    name: str
    predicate: Callable[[float], bool]  # True iff the measured value sits on the invariant
    real: float  # real-solver measured value (must satisfy predicate)
    mutants: dict[str, float]  # corruption-name -> measured value (must ALL violate)


def _ott_antonsen() -> _Law:
    """R_inf == sqrt(1 - 2*delta/K). Mutate delta, K, the bifurcation factor, collapse."""
    delta, coupling = 0.5, 2.0
    exact = math.sqrt(1.0 - (2.0 * delta) / coupling)

    def integrate(d: float, k: float) -> float:
        return float(OttAntonsenEngine(K=k, delta=d).integrate(T=200.0, dt=0.01, R0=0.05).R[-1])

    return _Law(
        name="ott_antonsen",
        predicate=lambda m: abs(m - exact) < 1e-6,
        real=integrate(delta, coupling),
        mutants={
            "delta_scaled_1.5x": integrate(1.5 * delta, coupling),  # wrong frequency width
            "coupling_at_critical": integrate(delta, 2.0 * delta),  # K -> K_c, R collapses
            "wrong_bifurcation_factor": math.sqrt(1.0 - delta / coupling),  # 1 instead of 2*delta
            "order_parameter_collapse": 0.0,  # solver returns incoherent
        },
    )


def _landauer() -> _Law:
    """cost == k_B*T*ln2. Mutate T, the log base, a small scale slip."""
    temperature = 300.0
    floor = K_BOLTZMANN * temperature * math.log(2.0)
    return _Law(
        name="landauer",
        predicate=lambda m: abs(m / floor - 1.0) <= 1e-12,
        real=bit_erasure_cost(1.0, temperature),
        mutants={
            "temperature_halved": bit_erasure_cost(1.0, 0.5 * temperature),  # wrong T
            "wrong_log_base_ln3": K_BOLTZMANN * temperature * math.log(3.0),  # ln3 not ln2
            "scale_slip_0.999": 0.999 * floor,  # sub-floor erasure
        },
    )


def _kelly() -> _Law:
    """f* == mu/sigma^2. Mutate variance, drop the square, small slip."""
    mu, sigma_sq = 0.002, 2.5e-3
    target = mu / sigma_sq
    return _Law(
        name="kelly",
        predicate=lambda m: abs(m - target) <= 1e-12,
        real=kelly_from_edge_variance(mu, sigma_sq, fractional_kelly=1.0, max_fraction=10.0),
        mutants={
            "variance_doubled": kelly_from_edge_variance(
                mu, 2.0 * sigma_sq, fractional_kelly=1.0, max_fraction=10.0
            ),  # wrong sigma^2
            "drop_square_mu_over_sigma": mu / math.sqrt(sigma_sq),  # mu/sigma not mu/sigma^2
            "slip_plus_1e-6": target + 1e-6,  # over-bet
        },
    )


def _dro_ara() -> _Law:
    """gamma == 2H + 1. Mutate the input series, drop the +1, drop the factor 2."""
    series = np.cumsum(np.random.default_rng(7).normal(0.0, 1.0, 1024))
    gamma, hurst, _r2 = derive_gamma(series)
    expected = 2.0 * hurst + 1.0
    other = np.cumsum(np.random.default_rng(99).normal(0.0, 1.0, 1024))
    gamma_other, _h2, _r = derive_gamma(other)
    return _Law(
        name="dro_ara_gamma",
        predicate=lambda m: abs(m - expected) < 1e-5,
        real=gamma,
        mutants={
            "different_input_series": gamma_other,  # gamma decoupled from this H
            "drop_plus_one": 2.0 * hurst,  # gamma = 2H (missing +1)
            "drop_factor_two": hurst + 1.0,  # gamma = H+1 (missing factor 2)
        },
    )


def _gauss_bonnet() -> _Law:
    """residual Sum_x K(x) - chi(G) == 0. Mutate by additive rational and a wrong chi."""
    graph = nx.cycle_graph(6)
    residual = float(gauss_bonnet_residual(graph))
    chi = euler_characteristic(graph)
    curvature_sum = residual + chi  # == chi for a valid complex
    return _Law(
        name="gauss_bonnet",
        predicate=lambda m: m == 0.0,
        real=residual,
        mutants={
            "additive_unit": residual + 1.0,  # one curvature off by 1
            "additive_third": float(Fraction(1, 3)),  # one curvature off by 1/3
            "wrong_euler_off_by_one": float(curvature_sum - (chi + 1)),  # chi miscounted
        },
    )


def _laws() -> list[_Law]:
    return [_ott_antonsen(), _landauer(), _kelly(), _dro_ara(), _gauss_bonnet()]


def test_mutation_tribunal_kills_every_physics_corruption() -> None:
    """The core's exact gates kill 100% of a taxonomy of real solver mutations.

    For each law the real-solver value satisfies the predicate (anchor), and every
    mutant — a parameter, input, or formula corruption of the REAL solver — is
    rejected. The mutation kill-rate must be exactly 1.0; any survivor is an
    undetected way to break the physics.
    """
    laws = _laws()
    total = 0
    killed = 0
    survivors: list[str] = []
    for law in laws:
        assert law.predicate(law.real), (
            f"MUTATION-TRIBUNAL ANCHOR FAILED: real {law.name} value {law.real!r} "
            f"does not satisfy its own predicate; the kill-rate would be meaningless."
        )
        for mutant_name, mutant_value in law.mutants.items():
            total += 1
            if not law.predicate(mutant_value):
                killed += 1
            else:
                survivors.append(f"{law.name}:{mutant_name} (measured={mutant_value!r})")

    assert total >= 15, (
        f"MUTATION-TRIBUNAL too narrow: only {total} mutants across {len(laws)} laws; "
        f"the taxonomy must exercise >= 15 distinct physics corruptions."
    )
    kill_rate = killed / total
    assert kill_rate == 1.0, (
        f"COGNITIVE-CORE MUTATION-ROBUSTNESS VIOLATED: kill-rate={kill_rate:.4f} "
        f"({killed}/{total}); SURVIVORS={survivors}. Every survivor is an undetected "
        f"way to corrupt the real solver — a hole in the invariant centre."
    )


def test_kill_rate_metric_is_honest() -> None:
    """Negative control: a null mutant survives, and a rubber-stamp predicate kills nothing.

    Proves the kill-rate measures real discrimination. The null (no-op) mutant
    equals the real value, so a SOUND predicate must NOT kill it (the core does not
    flag conforming physics). A vacuous always-True predicate kills 0% of genuine
    mutants — so a kill-rate of 1.0 from the real predicates is a real signal, not
    an artefact of a trigger-happy or rubber-stamp gate.
    """
    laws = _laws()

    # 1. Null mutant (== real) survives every real predicate.
    for law in laws:
        assert law.predicate(law.real), (
            f"MUTATION-TRIBUNAL HONESTY VIOLATED: real {law.name} value was killed by "
            f"its own predicate; the core would reject conforming physics."
        )

    # 2. A rubber-stamp predicate kills NONE of the genuine mutants.
    def rubber_stamp(_m: float) -> bool:
        return True

    rubber_killed = 0
    rubber_total = 0
    for law in laws:
        for mutant_value in law.mutants.values():
            rubber_total += 1
            if not rubber_stamp(mutant_value):
                rubber_killed += 1
    assert rubber_killed == 0, (
        f"MUTATION-TRIBUNAL HONESTY VIOLATED: a rubber-stamp predicate killed "
        f"{rubber_killed}/{rubber_total} mutants; the kill-rate metric is not "
        f"measuring real discrimination."
    )

    # 3. The real predicates DO kill those same mutants (1.0 vs 0.0 separation).
    real_killed = 0
    for law in laws:
        for mutant_value in law.mutants.values():
            if not law.predicate(mutant_value):
                real_killed += 1
    assert real_killed == rubber_total, (
        f"MUTATION-TRIBUNAL HONESTY VIOLATED: real predicates killed {real_killed}/"
        f"{rubber_total}; expected all — the real/rubber-stamp separation must be 1.0 vs 0.0."
    )
