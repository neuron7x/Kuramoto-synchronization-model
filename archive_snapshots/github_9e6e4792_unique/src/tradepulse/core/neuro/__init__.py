"""Neuro-inspired adaptive controllers for core decision loops.

This package implements biologically-inspired neuromodulator controllers
for the TradePulse trading system. The architecture is based on the
neuroscience of decision-making and reward processing.

Module Structure
----------------
dopamine : Appetitive reward signaling and action invigoration
    - DopamineController: TD(0) RPE computation, temperature modulation
    - ActionGate: Go/Hold/No-Go decision fusion

serotonin : Chronic stress and hold-state management
    - SerotoninController: Hysteretic hold logic with desensitization

gaba : Inhibitory impulse control
    - GABAInhibitionGate: STDP-modulated impulse dampening

na_ach : Arousal and attention modulation
    - NAACHNeuromodulator: Risk and temperature scaling

nak : Homeostatic control
    - NaKController: Bio-inspired homeostatic trading controller

desensitization : Adaptive sensitivity management
    - DesensitizationManager: Reward, sensory, and threat modulation

neuro_orchestrator : High-level orchestration
    - NeuroOrchestrator: Scenario-to-module instruction mapping

Public API
----------
Core Types:
    NeuroOrchestrator, OrchestrationOutput, TradingScenario,
    ModuleInstruction, RiskContour, LearningLoop

Convenience Functions:
    create_orchestration_from_scenario

Submodules:
    dopamine, serotonin, gaba, na_ach, nak, desensitization

Examples
--------
>>> from tradepulse.core.neuro import NeuroOrchestrator, TradingScenario
>>> orchestrator = NeuroOrchestrator()
>>> scenario = TradingScenario(
...     market="BTC/USDT",
...     timeframe="1h",
...     risk_profile="moderate"
... )
>>> output = orchestrator.orchestrate(scenario)
>>> print(output.to_json())
"""

__CANONICAL__ = True

from . import desensitization, dopamine, gaba, na_ach, nak, serotonin
from .neuro_orchestrator import (
    LearningLoop,
    ModuleInstruction,
    NeuroOrchestrator,
    OrchestrationOutput,
    RiskContour,
    TradingScenario,
    create_orchestration_from_scenario,
)

__all__ = [
    # Submodules
    "dopamine",
    "serotonin",
    "gaba",
    "na_ach",
    "desensitization",
    "nak",
    # Core orchestrator types
    "NeuroOrchestrator",
    "OrchestrationOutput",
    "TradingScenario",
    "ModuleInstruction",
    "RiskContour",
    "LearningLoop",
    # Convenience functions
    "create_orchestration_from_scenario",
]
