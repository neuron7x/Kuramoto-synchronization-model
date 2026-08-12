# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Compatibility layer for signal domain entity.

The canonical implementation lives under :mod:`domain.signals`.
"""

from __future__ import annotations

from .signals import Signal, SignalAction

__all__ = ["Signal", "SignalAction"]
