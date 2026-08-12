# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Memory manager for MLSDM simulations.

This module provides the MemoryManager class which orchestrates
MLSDM components for simulation runs.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import numpy as np

from ..config import MLSDMConfig
from ..facade import MLSDM

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages MLSDM simulations with memory components.

    The MemoryManager coordinates FHMC, agent, and replay engine
    for running multi-step simulations of trading decisions.

    Attributes:
        mlsdm: The MLSDM facade instance.
        config: Configuration dictionary.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize MemoryManager with configuration.

        Args:
            config: Configuration dictionary containing MLSDM setup.
        """
        self.config = config
        logger.info("Initializing MemoryManager", extra={"config": config})

        # Convert dict config to MLSDMConfig if needed
        if isinstance(config, dict):
            mlsdm_config = MLSDMConfig.from_dict(config)
        else:
            mlsdm_config = config

        self.mlsdm = MLSDM.from_config(mlsdm_config)
        logger.info("MemoryManager initialized successfully")

    def run_simulation(self, steps: int) -> None:
        """Run a simulation for the specified number of steps.

        Args:
            steps: Number of simulation steps to execute.
        """
        logger.info(f"Starting simulation for {steps} steps")

        # Get state dimension from config or use default
        state_dim = 8
        if self.mlsdm.agent is not None and hasattr(self.mlsdm.agent, "state_dim"):
            state_dim = self.mlsdm.agent.state_dim
        elif isinstance(self.config, dict) and "agent" in self.config:
            state_dim = self.config["agent"].get("state_dim", 8)

        for step in range(steps):
            # Generate synthetic state for demonstration
            state = np.random.randn(state_dim)

            # Update biomarkers with synthetic market conditions
            exp_return = np.random.uniform(-0.05, 0.05)
            novelty = np.random.uniform(0, 1)
            load = np.random.uniform(0, 1)
            maxdd = np.random.uniform(0, 0.2)
            volshock = np.random.uniform(0, 1)
            cp_score = np.random.uniform(0, 1)

            biomarkers = self.mlsdm.compute_drive(
                exp_return=exp_return,
                novelty=novelty,
                load=load,
                maxdd=maxdd,
                volshock=volshock,
                cp_score=cp_score,
            )

            # Get decision state
            decision = self.mlsdm.get_decision_state()

            # Take action if agent is available
            if self.mlsdm.agent is not None:
                _ = self.mlsdm.act(state)  # Action computed but not used in demo

            # Log progress periodically
            if (step + 1) % 10 == 0:
                logger.info(
                    f"Step {step + 1}/{steps}",
                    extra={
                        "orexin": biomarkers.orexin,
                        "threat": biomarkers.threat,
                        "state": biomarkers.state,
                        "window_seconds": decision.window_seconds,
                    },
                )

        logger.info(f"Simulation completed: {steps} steps")
