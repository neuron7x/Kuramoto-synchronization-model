"""Habitual policy head and adaptation utilities."""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class HabitHead(nn.Module):
    """Value-free head for action preference encoding."""

    def __init__(self, state_dim: int, action_dim: int) -> None:
        super().__init__()
        self.head = nn.Linear(state_dim, action_dim)

    def forward(self, state: torch.Tensor) -> torch.Tensor:  # type: ignore[override]
        logits = self.head(state)
        return F.softmax(logits, dim=-1)


def ape_update(
    habit_head: HabitHead,
    state: torch.Tensor,
    action_one_hot: torch.Tensor,
    optimizer: torch.optim.Optimizer,
) -> float:
    """Perform the action prediction error update step."""

    probs = habit_head(state)
    delta = action_one_hot - probs
    loss = -(delta.detach() * torch.log(probs + 1e-8)).sum(dim=-1).mean()
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
    return float(loss.item())
