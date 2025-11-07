"""Coherent risk measures for distributional RL."""

from __future__ import annotations

import torch


def cvar_from_quantiles(q: torch.Tensor, alpha: float) -> torch.Tensor:
    """Approximate the CVaR from a batch of quantile samples."""

    if q.ndim < 2:
        raise ValueError("Quantiles tensor must be at least 2-D")
    sorted_q, _ = torch.sort(q, dim=-1)
    num = sorted_q.shape[-1]
    tail_count = max(int(num * alpha), 1)
    tail = sorted_q[..., :tail_count]
    return tail.mean(dim=-1)


__all__ = ["cvar_from_quantiles"]
