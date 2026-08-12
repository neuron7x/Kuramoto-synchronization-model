# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Signal bounded context within the domain layer."""

from .entity import Signal
from .value_objects import SignalAction

__all__ = ["Signal", "SignalAction"]
