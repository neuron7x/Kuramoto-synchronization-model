# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Multifractal optimisation utilities shared across RL components."""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
import torch


def levy_noise_like(param: torch.Tensor, alpha: float = 1.5) -> torch.Tensor:
    """Generate heavy-tailed noise aligned with ``param``'s shape."""

    if alpha <= 0:
        raise ValueError("alpha must be positive")

    samples = torch.from_numpy(np.random.standard_cauchy(size=tuple(param.shape))).to(param.device)
    samples = samples.to(dtype=param.dtype)

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
    """Perform Lévy-perturbed parameter updates respecting FHMC state masks."""

    if eta < 0:
        raise ValueError("eta must be non-negative")
    if eta_f < 0:
        raise ValueError("eta_f must be non-negative")

    allowed_states = set(mask_states) if mask_states is not None else None
    use_fractional = allowed_states is None or current_state in allowed_states

    with torch.no_grad():
        for param, grad in zip(params, grads):
            if grad is None:
                continue

            update = -eta * grad.to(dtype=param.dtype, device=param.device)
            if use_fractional and eta_f > 0:
                noise = levy_noise_like(param, alpha=alpha)
                update = update + eta_f * noise

            param.add_(update)
