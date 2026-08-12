# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""NA/ACh neuromodulation package.

This package implements noradrenaline (NA) and acetylcholine (ACh)
neuromodulation utilities that model arousal and attention dynamics
for the trading system.

Public API
----------
NAACHConfig : Configuration dataclass for the neuromodulator
NAACHNeuromodulator : Main neuromodulator class with update() interface

The NA component models arousal and affects risk tolerance.
The ACh component models attention and affects exploration temperature.

Examples
--------
>>> from geosync.core.neuro.na_ach import NAACHNeuromodulator
>>> mod = NAACHNeuromodulator(config_path="configs/na_ach.yaml")
>>> result = mod.update(volatility=0.03, novelty=0.5)
>>> print(f"Arousal: {result['arousal']:.3f}, Attention: {result['attention']:.3f}")
"""

__CANONICAL__ = True

from .neuromods import NAACHConfig, NAACHNeuromodulator

__all__ = [
    "NAACHConfig",
    "NAACHNeuromodulator",
]
