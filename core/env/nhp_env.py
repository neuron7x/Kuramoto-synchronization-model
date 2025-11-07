"""Neural Hawkes process inspired environment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import torch
import torch.nn as nn


@dataclass
class NHPConfig:
    hidden_size: int
    num_steps: int
    baseline_intensity: float


class _IntensityModel(nn.Module):
    def __init__(self, hidden_size: int) -> None:
        super().__init__()
        self.gru = nn.GRU(1, hidden_size, batch_first=True)
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, seq: torch.Tensor) -> torch.Tensor:
        out, _ = self.gru(seq)
        last = out[:, -1]
        return torch.relu(self.head(last)) + 1e-3


class NHPEnv:
    def __init__(self, config: NHPConfig) -> None:
        self.config = config
        self.model = _IntensityModel(config.hidden_size)
        self.reset()

    def reset(self) -> Dict[str, float | np.ndarray]:
        self.t = 0
        self.price = 100.0
        self.inventory = 0.0
        self.history = [0.0]
        return self._state()

    def _state(self) -> Dict[str, float | np.ndarray]:
        seq = torch.tensor(self.history[-10:], dtype=torch.float32).view(1, -1, 1)
        intensity = float(self.model(seq).item())
        obs = np.array(
            [
                self.price,
                intensity,
                self.inventory,
                float(self.t) / self.config.num_steps,
                np.sin(self.t / 7.0),
                np.cos(self.t / 7.0),
            ],
            dtype=np.float32,
        )
        return {"state": obs}

    def step(self, action: int) -> Tuple[Dict[str, float | np.ndarray], float, bool]:
        seq = torch.tensor(self.history[-10:], dtype=torch.float32).view(1, -1, 1)
        intensity = float(self.model(seq).item())
        dt = np.random.exponential(1.0 / max(intensity, 1e-3))
        self.history.append(dt)
        price_change = 0.008 * (dt - 1.0)
        self.price += price_change
        reward = price_change * (action - 1) - 0.0015 * abs(action - 1)
        self.inventory += action - 1
        self.t += 1
        done = self.t >= self.config.num_steps
        return self._state(), float(reward), done


__all__ = ["NHPEnv", "NHPConfig"]
