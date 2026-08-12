# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Shared seed helper for benchmarks and examples."""

from __future__ import annotations

from core.utils.determinism import DEFAULT_SEED, apply_thread_determinism, seed_numpy


def set_global_seed(seed: int = DEFAULT_SEED) -> int:
    """Seed Python + NumPy and set deterministic thread defaults."""
    apply_thread_determinism()
    seed_numpy(seed)
    return seed


__all__ = ["set_global_seed"]
