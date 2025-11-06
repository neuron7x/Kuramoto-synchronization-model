"""Multifractal optimisation utilities shared across RL components."""
from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
import torch


def levy_noise_like(param: torch.Tensor, alpha: float = 1.5) -> torch.Tensor:
    """Generate heavy-tailed noise aligned with ``param``'s shape."""

    if alpha <= 0:
        raise ValueError("alpha must be positive")
    shape = tuple(param.shape)
    samples = torch.from_numpy(np.random.standard_cauchy(size=shape)).to(param.device)
    samples = samples.type_as(param)
    if alpha < 1.5:
        samples = samples * (1.5 / alpha)
    return samples


def fractional_update(
    params: Sequence[torch.nn.Parameter],
    grads: Sequence[torch.Tensor | None],
    eta: float,
    *,
    eta_f: float = 0.1,
    alpha: float = 1.5,
    mask_states: Iterable[str] | None = None,
    current_state: str = "WAKE",
) -> None:
    """Perform Lévy-perturbed *descent* updates respecting FHMC state masks."""

    if eta < 0:
        raise ValueError("eta must be non-negative")

    if mask_states is not None and current_state not in set(mask_states):
        for param, grad in zip(params, grads):
            if grad is None:
                continue
            param.data.add_(-eta * grad)
        return

    for param, grad in zip(params, grads):
        if grad is None:
            continue
        update = -eta * grad
        if eta_f:
            noise = levy_noise_like(param, alpha=alpha)
            update = update + eta_f * noise
        param.data.add_(update)
