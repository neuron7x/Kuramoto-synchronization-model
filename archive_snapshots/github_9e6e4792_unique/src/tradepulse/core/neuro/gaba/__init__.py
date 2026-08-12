"""GABA neuromodulation package.

This package implements GABAergic inhibition mechanisms that moderate
impulsive trading decisions under high-stress or high-volatility conditions.

Public API
----------
GABAConfig : Configuration dataclass for the inhibition gate
GABAInhibitionGate : Main inhibition gate class with update() interface

The GABA gate computes inhibition coefficients that dampen Go drives when
impulse activity exceeds threshold levels, with STDP-like plasticity for
adaptation based on prediction errors.

Examples
--------
>>> from tradepulse.core.neuro.gaba import GABAInhibitionGate
>>> gate = GABAInhibitionGate(config_path="configs/gaba.yaml")
>>> result = gate.update(sequence_intensity=0.8, rpe=-0.1, stress=0.5)
>>> print(f"Inhibition: {result['inhibition']:.3f}")
"""

__CANONICAL__ = True

from .gaba_inhibition_gate import GABAConfig, GABAInhibitionGate

__all__ = [
    "GABAConfig",
    "GABAInhibitionGate",
]
