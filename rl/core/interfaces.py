# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Interface contracts for policy and value modules."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import torch


@runtime_checkable
class PolicyContract(Protocol):
    """Contract for policy networks returning distribution parameters."""

    def forward(self, state: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Return distribution parameters for the given state."""


@runtime_checkable
class ValueContract(Protocol):
    """Contract for value networks estimating state value."""

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """Return the scalar state value estimate."""
