"""Simple deep ensembles for uncertainty quantification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim


def _build_head(state_dim: int) -> nn.Module:
    return nn.Sequential(nn.Linear(state_dim, state_dim), nn.ReLU(), nn.Linear(state_dim, 1))


@dataclass
class _EnsembleMember:
    model: nn.Module
    optimizer: optim.Optimizer


class DeepEnsembles:
    def __init__(self, state_dim: int, k: int = 5, lr: float = 1e-3, bootstrap: bool = True) -> None:
        self.state_dim = state_dim
        self.k = int(k)
        self.bootstrap = bootstrap
        self.members: List[_EnsembleMember] = []
        for _ in range(self.k):
            model = _build_head(state_dim)
            optimizer = optim.Adam(model.parameters(), lr=lr)
            self.members.append(_EnsembleMember(model=model, optimizer=optimizer))
        self.loss = nn.MSELoss()

    def update_batch(self, X: np.ndarray, y: np.ndarray) -> None:
        if len(X) == 0:
            return
        x_tensor = torch.as_tensor(X, dtype=torch.float32)
        y_tensor = torch.as_tensor(y, dtype=torch.float32).view(-1, 1)
        for member in self.members:
            member.model.train(True)
            member.optimizer.zero_grad(set_to_none=True)
            if self.bootstrap:
                idx = np.random.choice(len(X), len(X))
                pred = member.model(x_tensor[idx])
                loss = self.loss(pred, y_tensor[idx])
            else:
                pred = member.model(x_tensor)
                loss = self.loss(pred, y_tensor)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(member.model.parameters(), 1.0)
            member.optimizer.step()

    def predict_var(self, x: np.ndarray) -> float:
        x_tensor = torch.as_tensor(x, dtype=torch.float32).view(1, -1)
        preds = []
        for member in self.members:
            was_training = member.model.training
            member.model.eval()
            with torch.no_grad():
                preds.append(float(member.model(x_tensor).item()))
            member.model.train(was_training)
        return float(np.var(preds))


__all__ = ["DeepEnsembles"]
