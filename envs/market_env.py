"""Toy market environments exercising FHMC biomarker plumbing."""

from __future__ import annotations

import networkx as nx
import numpy as np

from core.indicators.multiscale_kuramoto import fractal_gcl_novelty, multiscale_kuramoto
from utils.change_point import cusum_score, vol_shock


def _max_drawdown(returns: np.ndarray) -> float:
    """Return the maximum drawdown of ``returns`` as a positive scalar."""

    values = np.asarray(returns, dtype=float)
    if values.size == 0:
        return 0.0

    cumulative = np.cumsum(values)
    peaks = np.maximum.accumulate(np.concatenate(([0.0], cumulative)))
    drawdowns = peaks[1:] - cumulative
    return float(np.max(drawdowns))


class ToyMarketEnv:
    def __init__(
        self,
        dim_state: int = 128,
        dim_action: int = 8,
        *,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.dim_state = dim_state
        self.dim_action = dim_action
        self.timestep = 0
        self.latent = 0.0
        self.returns: list[float] = []
        self._rng = rng or np.random.default_rng()

    def reset(self) -> np.ndarray:
        self.timestep = 0
        self.latent = 0.0
        self.returns.clear()
        return np.zeros(self.dim_state, dtype=np.float32)

    def step(self, action: np.ndarray) -> tuple[float, np.ndarray, dict[str, float]]:
        self.timestep += 1
        action_arr = np.asarray(action, dtype=float)
        drift = 0.001 * np.sin(self.timestep / 200.0)
        noise = 0.01 * self._rng.standard_normal()
        reward = drift + noise + 0.001 * np.tanh(float(action_arr.mean()))
        self.returns.append(float(reward))

        self.latent = 0.95 * self.latent + 0.05 * reward * 100.0
        state = self._rng.standard_normal(self.dim_state).astype(np.float32)

        max_drawdown = _max_drawdown(np.array(self.returns, dtype=float))

        volshock = vol_shock(np.array(self.returns), window=min(60, len(self.returns)))
        cp = (
            cusum_score(np.array(self.returns[-300:]))
            if len(self.returns) > 100
            else 0.0
        )

        padded = np.array(self.returns[-128:], dtype=float)
        if padded.size < 128:
            padded = np.pad(padded, (128 - padded.size, 0))
        phases = np.angle(np.fft.rfft(padded))
        load = multiscale_kuramoto(phases.reshape(1, -1))

        embeddings_a = self._rng.standard_normal((32, 16))
        embeddings_b = self._rng.standard_normal((32, 16))
        novelty, fd = fractal_gcl_novelty(
            _toy_graph(32, 0.1, self._rng), embeddings_a, embeddings_b
        )

        info = {
            "latent": float(self.latent),
            "maxdd": float(max_drawdown),
            "volshock": float(volshock),
            "cp": float(cp),
            "exp_ret": float(reward),
            "novelty": float(novelty),
            "load": float(load),
            "fd": float(fd),
        }
        return float(reward), state, info


def _toy_graph(n: int, p: float, rng: np.random.Generator) -> nx.Graph:
    seed = int(rng.integers(0, 2**32 - 1))
    graph = nx.erdos_renyi_graph(n, p, seed=seed)
    if graph.number_of_edges() == 0:
        graph.add_edges_from((i, i + 1) for i in range(n - 1))
    return graph


class RegimeShiftEnv(ToyMarketEnv):
    def __init__(
        self,
        dim_state: int = 128,
        dim_action: int = 8,
        T: int = 20_000,
        *,
        rng: np.random.Generator | None = None,
    ) -> None:
        super().__init__(dim_state, dim_action, rng=rng)
        self.T = T

    def step(self, action: np.ndarray) -> tuple[float, np.ndarray, dict[str, float]]:
        base = 0.003 if (self.timestep // 2_000) % 2 == 0 else -0.003
        self.timestep += 1
        action_arr = np.asarray(action, dtype=float)
        noise = 0.02 * self._rng.standard_normal()
        reward = base + noise + 0.001 * np.tanh(float(action_arr.mean()))
        self.returns.append(float(reward))

        self.latent = 0.9 * self.latent + 0.1 * reward * 100.0
        state = self._rng.standard_normal(self.dim_state).astype(np.float32)

        max_drawdown = _max_drawdown(np.array(self.returns, dtype=float))

        volshock = vol_shock(np.array(self.returns), window=min(60, len(self.returns)))
        cp = (
            cusum_score(np.array(self.returns[-300:]))
            if len(self.returns) > 100
            else 0.0
        )

        padded = np.array(self.returns[-128:], dtype=float)
        if padded.size < 128:
            padded = np.pad(padded, (128 - padded.size, 0))
        phases = np.angle(np.fft.rfft(padded))
        load = multiscale_kuramoto(phases.reshape(1, -1))

        embeddings_a = self._rng.standard_normal((32, 16))
        embeddings_b = self._rng.standard_normal((32, 16))
        novelty, fd = fractal_gcl_novelty(
            _toy_graph(32, 0.15, self._rng), embeddings_a, embeddings_b
        )

        info = {
            "latent": float(self.latent),
            "maxdd": float(max_drawdown),
            "volshock": float(volshock),
            "cp": float(cp),
            "exp_ret": float(reward),
            "novelty": float(novelty),
            "load": float(load),
            "fd": float(fd),
        }
        return float(reward), state, info
