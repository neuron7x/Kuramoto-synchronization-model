"""Reward prediction error utilities for RL learning loops."""

from __future__ import annotations

from dataclasses import dataclass
import logging

import torch

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RewardPredictionErrorResult:
    """Container for RPE outputs and metrics."""

    delta: torch.Tensor
    metrics: dict[str, float]


@dataclass(slots=True)
class RewardPredictionError:
    """Compute reward prediction error with logging and metrics."""

    gamma: float = 0.99
    clip_value: float | None = None

    def compute(
        self,
        reward: torch.Tensor,
        value: torch.Tensor,
        next_value: torch.Tensor,
        done: bool,
    ) -> RewardPredictionErrorResult:
        """Return the reward prediction error and metric payload."""

        gamma = 0.0 if done else self.gamma
        delta = reward + gamma * next_value - value
        if self.clip_value is not None:
            delta = torch.clamp(delta, -self.clip_value, self.clip_value)

        delta_detached = delta.detach()
        metrics = {
            "rpe": float(delta_detached.mean().item()),
            "rpe_abs": float(delta_detached.abs().mean().item()),
            "rpe_squared": float((delta_detached**2).mean().item()),
            "gamma": float(gamma),
        }
        logger.debug("Reward prediction error computed: %s", metrics)
        return RewardPredictionErrorResult(delta=delta, metrics=metrics)
