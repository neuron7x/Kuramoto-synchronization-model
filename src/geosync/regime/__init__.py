# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GeoSync regime detection module."""

__CANONICAL__ = True

from .ews import EWSAggregator, EWSConfig, EWSResult

__all__ = ["EWSAggregator", "EWSConfig", "EWSResult"]
