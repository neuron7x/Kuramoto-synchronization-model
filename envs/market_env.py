"""Toy market environments exercising FHMC biomarker plumbing."""
from __future__ import annotations

import numpy as np
import networkx as nx

from core.indicators.multiscale_kuramoto import multiscale_kuramoto, fractal_gcl_novelty
from utils.change_point import cusum_score, vol_shock


class ToyMarketEnv:
    def __init__(self, dim_state: int = 128, dim_action: int = 8) -> None:
        self.dim_state = dim_state
        self.dim_action = dim_action
        self.timestep = 0
        self.latent = 0.0
        self.returns: list[float] = []

    def reset(self) -> np.ndarray:
        self.timestep = 0
        self.latent = 0.0
        self.returns.clear()
        return np.zeros(self.dim_state, dtype=np.float32)

    def step(self, action: np.ndarray) -> tuple[float, np.ndarray, dict[str, float]]:
        self.timestep += 1
        drift = 0.001 * np.sin(self.timestep / 200.0)
        noise = 0.01 * np.random.randn()
        reward = drift + noise + 0.001 * np.tanh(action.mean())
        self.returns.append(float(reward))

        self.latent = 0.95 * self.latent + 0.05 * reward * 100.0
        state = np.random.randn(self.dim_state).astype(np.float32)

        cumulative = np.cumsum(self.returns)
        peak = np.maximum.accumulate(np.append(0.0, cumulative))
        drawdowns = cumulative - peak[1:]
        max_drawdown = float(min(0.0, drawdowns.min()))

        volshock = vol_shock(np.array(self.returns), window=min(60, len(self.returns)))
        cp = cusum_score(np.array(self.returns[-300:])) if len(self.returns) > 100 else 0.0

        padded = np.array(self.returns[-128:], dtype=float)
        if padded.size < 128:
            padded = np.pad(padded, (128 - padded.size, 0))
        phases = np.angle(np.fft.rfft(padded))
        load = multiscale_kuramoto(phases.reshape(1, -1))

        embeddings_a = np.random.randn(32, 16)
        embeddings_b = np.random.randn(32, 16)
        novelty, fd = fractal_gcl_novelty(_toy_graph(32, 0.1), embeddings_a, embeddings_b)

        info = {
            "latent": float(self.latent),
            "maxdd": abs(max_drawdown),
            "volshock": float(volshock),
            "cp": float(cp),
            "exp_ret": float(reward),
            "novelty": float(novelty),
            "load": float(load),
            "fd": float(fd),
        }
        return float(reward), state, info


def _toy_graph(n: int, p: float) -> nx.Graph:
    graph = nx.erdos_renyi_graph(n, p)
    if graph.number_of_edges() == 0:
        graph.add_edges_from((i, i + 1) for i in range(n - 1))
    return graph


class RegimeShiftEnv(ToyMarketEnv):
    def __init__(self, dim_state: int = 128, dim_action: int = 8, T: int = 20_000) -> None:
        super().__init__(dim_state, dim_action)
        self.T = T

    def step(self, action: np.ndarray) -> tuple[float, np.ndarray, dict[str, float]]:
        base = 0.003 if (self.timestep // 2_000) % 2 == 0 else -0.003
        self.timestep += 1
        noise = 0.02 * np.random.randn()
        reward = base + noise + 0.001 * np.tanh(action.mean())
        self.returns.append(float(reward))

        self.latent = 0.9 * self.latent + 0.1 * reward * 100.0
        state = np.random.randn(self.dim_state).astype(np.float32)

        cumulative = np.cumsum(self.returns)
        peak = np.maximum.accumulate(np.append(0.0, cumulative))
        drawdowns = cumulative - peak[1:]
        max_drawdown = float(min(0.0, drawdowns.min()))

        volshock = vol_shock(np.array(self.returns), window=min(60, len(self.returns)))
        cp = cusum_score(np.array(self.returns[-300:])) if len(self.returns) > 100 else 0.0

        padded = np.array(self.returns[-128:], dtype=float)
        if padded.size < 128:
            padded = np.pad(padded, (128 - padded.size, 0))
        phases = np.angle(np.fft.rfft(padded))
        load = multiscale_kuramoto(phases.reshape(1, -1))

        embeddings_a = np.random.randn(32, 16)
        embeddings_b = np.random.randn(32, 16)
        novelty, fd = fractal_gcl_novelty(_toy_graph(32, 0.15), embeddings_a, embeddings_b)

        info = {
            "latent": float(self.latent),
            "maxdd": abs(max_drawdown),
            "volshock": float(volshock),
            "cp": float(cp),
            "exp_ret": float(reward),
            "novelty": float(novelty),
            "load": float(load),
            "fd": float(fd),
        }
        return float(reward), state, info
