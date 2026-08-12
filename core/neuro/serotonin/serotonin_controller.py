# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Shim for canonical serotonin controller located under ``geosync.core``."""

from geosync.core.neuro.serotonin import serotonin_controller as _canonical

__CANONICAL__ = False

_generate_config_table = _canonical._generate_config_table

__all__ = [name for name in dir(_canonical) if not name.startswith("_")]
__all__.append("_generate_config_table")
globals().update({name: getattr(_canonical, name) for name in __all__})
