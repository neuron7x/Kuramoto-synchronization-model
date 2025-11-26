"""Simple data generator replay utility used in FHMC tests."""

from __future__ import annotations

import numpy as np


class SimpleDGR:
    def __init__(self, dim_state: int, dim_action: int) -> None:
        self.dim_state = dim_state
        self.dim_action = dim_action

    def sample(self, m: int) -> list[tuple[np.ndarray, np.ndarray, float, np.ndarray]]:
        batch = []
        for _ in range(m):
            state = np.random.randn(self.dim_state).astype(np.float32)
            action = np.random.randn(self.dim_action).astype(np.float32)
            reward = float(np.random.randn() * 0.01)
            next_state = state + 0.01 * np.random.randn(self.dim_state).astype(
                np.float32
            )
            batch.append((state, action, reward, next_state))
        return batch
