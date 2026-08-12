# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Acceleration utilities bridging Python and Rust implementations."""

from .numeric import convolve, quantiles, sliding_windows

__all__ = ["convolve", "quantiles", "sliding_windows"]
