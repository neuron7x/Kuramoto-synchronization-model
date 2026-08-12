# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""NaK v4.2: Bio-Inspired Homeostatic Controller for Trading."""

__CANONICAL__ = True

from .controller import NaKConfig, NaKControllerV4_2
from .controller import NaKControllerV4_2 as NaKController
from .desensitization import DesensitizationModule
from .integration import AdapterOutput, NaKAdapter
from .metrics import rolling_std

__all__ = [
    "NaKController",
    "NaKControllerV4_2",
    "NaKConfig",
    "DesensitizationModule",
    "NaKAdapter",
    "AdapterOutput",
    "rolling_std",
]
