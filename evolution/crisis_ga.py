# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Crisis-aware genetic algorithm for topology optimisation."""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

Topology = List[Tuple[str, str, str]]


@dataclass(slots=True)
class GAConfig:
    population_size: int
    mutation_rate: float
    num_generations: int
    elite_size: int = 2
    tournament_size: int = 3


class CrisisMode:
    NORMAL = "normal"
    ELEVATED = "elevated"
    CRITICAL = "critical"

    @staticmethod
    def detect(F_current: float, F_baseline: float, threshold: float = 0.1) -> str:
        if F_baseline <= 0:
            return CrisisMode.NORMAL
        deviation = (F_current - F_baseline) / F_baseline
        if deviation >= threshold * 2:
            return CrisisMode.CRITICAL
        if deviation >= threshold:
            return CrisisMode.ELEVATED
        return CrisisMode.NORMAL


class CrisisAwareGA:
    """Genetic algorithm that adapts parameters based on crisis level."""

    CONFIGS: Dict[str, GAConfig] = {
        CrisisMode.NORMAL: GAConfig(population_size=5, mutation_rate=0.1, num_generations=10),
        CrisisMode.ELEVATED: GAConfig(population_size=15, mutation_rate=0.3, num_generations=30),
        CrisisMode.CRITICAL: GAConfig(population_size=30, mutation_rate=0.5, num_generations=50),
    }

    def __init__(
        self,
        *,
        fitness_func: Callable[[Topology], float],
        F_baseline: float,
        crisis_threshold: float = 0.1,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.fitness_func = fitness_func
        self.F_baseline = F_baseline
        self.crisis_threshold = crisis_threshold
        self._rng = rng or np.random.default_rng()

        self.generation_count = 0
        self.crisis_history: List[Dict[str, float | str]] = []
        self.homeostasis_penalty = 0.0

        logger.debug(
            "CrisisAwareGA initialised baseline=%.6f threshold=%.2f",
            F_baseline,
            crisis_threshold,
        )

    def evolve(self, initial_topology: Topology, current_F: float) -> Tuple[Topology, float, str]:
        crisis_mode = CrisisMode.detect(current_F, self.F_baseline, self.crisis_threshold)
        config = self.CONFIGS[crisis_mode]

        self.crisis_history.append(
            {
                "generation": self.generation_count,
                "crisis_mode": crisis_mode,
                "current_F": current_F,
                "baseline_F": self.F_baseline,
            }
        )

        population = self._initialise_population(initial_topology, config.population_size)
        best: Topology = deepcopy(initial_topology)
        best_fitness = self.fitness_func(best) + self.homeostasis_penalty

        for _ in range(config.num_generations):
            fitnesses = np.array([self.fitness_func(ind) for ind in population])
            fitnesses = fitnesses + self.homeostasis_penalty
            idx_best = int(np.argmin(fitnesses))
            if fitnesses[idx_best] < best_fitness:
                best_fitness = float(fitnesses[idx_best])
                best = deepcopy(population[idx_best])

            population = self._next_generation(population, fitnesses, config)

        self.generation_count += 1
        return best, best_fitness, crisis_mode

    def apply_homeostasis_feedback(self, delta_score: float) -> None:
        """Integrate CNS stability rewards/penalties into GA fitness."""

        self.homeostasis_penalty = float(delta_score)

    def get_crisis_statistics(self) -> Dict[str, object]:
        if not self.crisis_history:
            return {
                "total_generations": self.generation_count,
                "crisis_counts": {},
                "crisis_rate": 0.0,
                "history": [],
            }

        counts: Dict[str, int] = {}
        for record in self.crisis_history:
            mode = str(record["crisis_mode"])
            counts[mode] = counts.get(mode, 0) + 1

        critical_rate = counts.get(CrisisMode.CRITICAL, 0) / max(self.generation_count, 1)
        return {
            "total_generations": self.generation_count,
            "crisis_counts": counts,
            "crisis_rate": critical_rate,
            "history": self.crisis_history[-10:],
        }

    # Internal helpers ---------------------------------------------------
    def _initialise_population(self, base: Topology, size: int) -> List[Topology]:
        population = [deepcopy(base)]
        choices: Sequence[str] = ("metallic", "ionic", "covalent", "hydrogen", "vdw")
        for _ in range(max(size - 1, 0)):
            mutant = deepcopy(base)
            if not mutant:
                population.append(mutant)
                continue
            idx = self._rng.integers(0, len(mutant))
            new_type = self._rng.choice(choices)
            src, dst, _ = mutant[idx]
            mutant[idx] = (src, dst, str(new_type))
            population.append(mutant)
        return population

    def _next_generation(
        self,
        population: List[Topology],
        fitnesses: np.ndarray,
        config: GAConfig,
    ) -> List[Topology]:
        new_population: List[Topology] = []
        elite_indices = np.argsort(fitnesses)[: config.elite_size]
        for idx in elite_indices:
            new_population.append(deepcopy(population[int(idx)]))

        choices: Sequence[str] = ("metallic", "ionic", "covalent", "hydrogen", "vdw")
        while len(new_population) < config.population_size:
            candidate_indices = self._rng.choice(
                len(population), size=config.tournament_size, replace=False
            )
            candidate_fitness = fitnesses[candidate_indices]
            winner_idx = int(candidate_indices[int(np.argmin(candidate_fitness))])
            child = deepcopy(population[winner_idx])

            if child and self._rng.random() < config.mutation_rate:
                pos = self._rng.integers(0, len(child))
                src, dst, _ = child[pos]
                child[pos] = (src, dst, str(self._rng.choice(choices)))

            new_population.append(child)

        return new_population[: config.population_size]


__all__ = ["CrisisAwareGA", "CrisisMode", "GAConfig", "Topology"]
