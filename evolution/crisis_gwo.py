"""Chaotic fractal Grey Wolf Optimiser used for crisis adaptation."""

from __future__ import annotations  # noqa: E402 - after module docstring

import numpy as np  # noqa: E402


def logistic_map(x: float, r: float = 3.99) -> float:
    return float(r * x * (1.0 - x))


class CFGWO:
    """Grey Wolf Optimiser enhanced with chaos and Lévy perturbations."""

    def __init__(
        self,
        objective,
        dim: int,
        lb,
        ub,
        *,
        pack: int = 20,
        iters: int = 200,
        chaos: bool = True,
        fractal_step: bool = True,
    ) -> None:
        self.objective = objective
        self.dim = int(dim)
        self.lb = np.array(lb, dtype=float)
        self.ub = np.array(ub, dtype=float)
        self.pack = int(pack)
        self.iters = int(iters)
        self.chaos = chaos
        self.fractal_step = fractal_step

    def optimize(self) -> tuple[np.ndarray, float]:
        rng = np.random.default_rng()
        wolves = rng.random((self.pack, self.dim))
        wolves = self.lb + wolves * (self.ub - self.lb)
        fitness = np.array([self.objective(wolf) for wolf in wolves], dtype=float)
        alpha, beta, delta = self._rank(wolves, fitness)
        chaos_state = rng.random()

        for t in range(self.iters):
            a = 2.0 - 2.0 * (t / self.iters)
            if self.chaos:
                chaos_state = logistic_map(chaos_state)
            for i in range(self.pack):
                A1 = 2 * a * rng.random(self.dim) - a
                C1 = 2 * rng.random(self.dim)
                A2 = 2 * a * rng.random(self.dim) - a
                C2 = 2 * rng.random(self.dim)
                A3 = 2 * a * rng.random(self.dim) - a
                C3 = 2 * rng.random(self.dim)

                D_alpha = np.abs(C1 * alpha - wolves[i])
                X1 = alpha - A1 * D_alpha
                D_beta = np.abs(C2 * beta - wolves[i])
                X2 = beta - A2 * D_beta
                D_delta = np.abs(C3 * delta - wolves[i])
                X3 = delta - A3 * D_delta

                wolves[i] = (X1 + X2 + X3) / 3.0
                if self.fractal_step:
                    step = rng.standard_cauchy(self.dim) * 0.01 * (1 + t / self.iters)
                    wolves[i] += step
                wolves[i] = np.clip(wolves[i], self.lb, self.ub)

            fitness = np.array([self.objective(wolf) for wolf in wolves], dtype=float)
            alpha, beta, delta = self._rank(wolves, fitness)

        best = alpha
        best_score = float(self.objective(best))
        return best, best_score

    def _rank(
        self, wolves: np.ndarray, fitness: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        indices = np.argsort(fitness)
        return wolves[indices[0]], wolves[indices[1]], wolves[indices[2]]
