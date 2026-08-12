# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""MLSDM (Multi-Level Stochastic Decision Model) public SDK.

This module provides a clean, user-friendly API for integrating MLSDM
decision-making capabilities into trading systems. It exposes:

- FHMC: Fracto-Hypothalamic Meta-Controller for adaptive decision timing
- ActorCriticFHMC: RL agent coupled with FHMC biomarker feedback
- SleepReplayEngine: Priority replay buffer with dream-like regeneration
- CFGWO: Chaotic Fractal Grey Wolf Optimizer for crisis adaptation

Example usage::

    from geosync.sdk.mlsdm import (
        create_fhmc,
        create_agent,
        create_optimizer,
        MLSDMConfig,
    )

    # Create FHMC controller from YAML configuration
    fhmc = create_fhmc("config/fhmc.yaml")

    # Create RL agent coupled to FHMC
    agent = create_agent(
        state_dim=10,
        action_dim=3,
        fhmc=fhmc,
    )

    # Train the agent
    state = agent.reset()
    action = agent.act(state)
    agent.learn(state, action, reward=0.1, next_state=new_state, done=False)

    # Use optimizer for crisis adaptation
    optimizer = create_optimizer(
        objective=loss_fn,
        dim=5,
        bounds=([0, 0, 0, 0, 0], [1, 1, 1, 1, 1]),
    )
    best_params, best_score = optimizer.optimize()
"""

from __future__ import annotations

__CANONICAL__ = True

from .config import AgentConfig, FHMCConfig, MLSDMConfig, OptimizerConfig
from .contracts import (
    BiomarkerState,
    DecisionState,
    OptimizationResult,
    ReplayTransition,
    TrainingStep,
)
from .facade import (
    MLSDM,
    create_agent,
    create_fhmc,
    create_optimizer,
    create_replay_engine,
)

__all__ = [
    # Configuration classes
    "MLSDMConfig",
    "FHMCConfig",
    "AgentConfig",
    "OptimizerConfig",
    # Factory functions
    "create_fhmc",
    "create_agent",
    "create_optimizer",
    "create_replay_engine",
    # Main facade
    "MLSDM",
    # Data contracts
    "BiomarkerState",
    "DecisionState",
    "OptimizationResult",
    "ReplayTransition",
    "TrainingStep",
]
