"""NaK Neuro-Energetic Controller package."""

from .control.neuromods import (
    NeuromodulatorState,
    acetylcholine,
    cross_modulator_interaction,
    dopamine,
    dopamine_enhanced,
    glutamate_gaba_balance,
    homeostatic_compensation,
    modulate_activity_ach,
    modulate_activity_integrated,
    modulate_risk_da,
    modulate_risk_integrated,
    noradrenaline,
    noradrenaline_enhanced,
    serotonin,
    serotonin_enhanced,
)
from .integration.hook import NaKHook
from .runtime.controller import NaKController
from .version import __version__

__all__ = [
    # Version
    "__version__",
    # Main controller classes
    "NaKController",
    "NaKHook",
    # Core neuromodulator functions
    "dopamine",
    "noradrenaline",
    "serotonin",
    "acetylcholine",
    # Enhanced neuromodulator functions
    "dopamine_enhanced",
    "noradrenaline_enhanced",
    "serotonin_enhanced",
    # Cross-modulator dynamics
    "glutamate_gaba_balance",
    "cross_modulator_interaction",
    "homeostatic_compensation",
    # Modulation functions
    "modulate_risk_da",
    "modulate_risk_integrated",
    "modulate_activity_ach",
    "modulate_activity_integrated",
    # State container
    "NeuromodulatorState",
]
