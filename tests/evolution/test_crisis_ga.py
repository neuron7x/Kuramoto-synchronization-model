# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import numpy as np

from evolution.crisis_ga import CrisisAwareGA


def _dummy_fitness(_: list) -> float:
    return 0.0


def test_homeostasis_feedback_overwrites_penalty():
    ga = CrisisAwareGA(fitness_func=_dummy_fitness, F_baseline=1.0)

    ga.apply_homeostasis_feedback(-0.25)
    assert ga.homeostasis_penalty == -0.25

    ga.apply_homeostasis_feedback(-0.25)
    assert ga.homeostasis_penalty == -0.25

    ga.apply_homeostasis_feedback(0.1)
    assert ga.homeostasis_penalty == 0.1


def test_homeostasis_penalty_influences_best_fitness():
    ga = CrisisAwareGA(fitness_func=_dummy_fitness, F_baseline=1.0)
    topology = [("a", "b", "vdw")]

    best, fitness, _ = ga.evolve(topology, current_F=1.0)
    assert best == topology
    assert np.isclose(fitness, 0.0)

    ga.apply_homeostasis_feedback(0.5)
    _, adjusted_fitness, _ = ga.evolve(topology, current_F=1.0)
    assert np.isclose(adjusted_fitness, 0.5)
