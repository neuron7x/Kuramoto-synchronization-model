# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""MLSDM facade providing simplified entry-points to core components.

This module is the primary interface for users integrating MLSDM
functionality into their trading systems. It provides factory functions
and a unified facade class for coordinating all MLSDM components.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np

from .config import AgentConfig, FHMCConfig, MLSDMConfig, OptimizerConfig
from .contracts import (
    BiomarkerState,
    DecisionState,
    OptimizationResult,
    ReplayTransition,
    TrainingStep,
)

__all__ = [
    "create_fhmc",
    "create_agent",
    "create_optimizer",
    "create_replay_engine",
    "MLSDM",
]


def create_fhmc(
    config: FHMCConfig | str | Path | None = None,
) -> Any:
    """Create an FHMC controller from configuration.

    The Fracto-Hypothalamic Meta-Controller (FHMC) manages adaptive
    decision timing using biomarkers inspired by neuroscience. It provides:

    - Wake/sleep state transitions for trading activity
    - Orexin (arousal) and threat biomarker computation
    - Multi-fractal time window sampling

    Args:
        config: Configuration object, path to YAML file, or None for defaults.

    Returns:
        FHMC instance ready for use.

    Example::

        fhmc = create_fhmc("config/fhmc.yaml")
        fhmc.compute_orexin(exp_return=0.05, novelty=0.3, load=0.2)
        fhmc.compute_threat(maxdd=0.1, volshock=0.5, cp_score=0.2)
        state = fhmc.flipflop_step()  # "WAKE" or "SLEEP"
        window = fhmc.next_window_seconds()  # adaptive time window
    """
    from runtime.thermo_controller import FHMC

    if config is None:
        config = FHMCConfig()

    if isinstance(config, (str, Path)):
        config = FHMCConfig.from_yaml(config)

    cfg_dict = config.to_dict()
    return FHMC(cfg_dict)


def create_agent(
    state_dim: int,
    action_dim: int,
    fhmc: Any,
    *,
    config: AgentConfig | None = None,
) -> Any:
    """Create an ActorCriticFHMC agent for RL-based trading.

    The agent uses an actor-critic architecture informed by FHMC biomarker
    feedback. Key features:

    - Policy network with Gaussian exploration
    - Value network for advantage estimation
    - Habit head for learned action priors
    - Fractional gradient updates during specific FHMC states
    - Ornstein-Uhlenbeck and colored noise for exploration

    Args:
        state_dim: Dimension of the observation state vector.
        action_dim: Dimension of the action vector.
        fhmc: FHMC controller instance (from create_fhmc).
        config: Optional agent configuration. If not provided, uses defaults.

    Returns:
        ActorCriticFHMC agent ready for training.

    Example::

        fhmc = create_fhmc()
        agent = create_agent(state_dim=10, action_dim=3, fhmc=fhmc)

        state = agent.reset()
        action = agent.act(state)
        agent.learn(
            state=state,
            action=action,
            reward=0.1,
            next_state=new_state,
            done=False,
        )
    """
    from rl.core.actor_critic import ActorCriticFHMC

    if config is None:
        config = AgentConfig(state_dim=state_dim, action_dim=action_dim)

    return ActorCriticFHMC(
        state_dim=config.state_dim,
        action_dim=config.action_dim,
        fhmc=fhmc,
        lr=config.lr,
        device=config.device,
    )


def create_optimizer(
    objective: Callable[[np.ndarray], float],
    dim: int,
    bounds: tuple[Sequence[float], Sequence[float]],
    *,
    config: OptimizerConfig | None = None,
) -> Any:
    """Create a CFGWO optimizer for parameter search.

    The Chaotic Fractal Grey Wolf Optimizer (CFGWO) enhances the standard
    GWO algorithm with:

    - Logistic map chaos for exploration
    - Lévy flight fractal steps for escaping local minima
    - Crisis-aware adaptation for trading strategy optimization

    Args:
        objective: Function to minimize, takes parameter vector, returns scalar.
        dim: Dimension of the search space.
        bounds: Tuple of (lower_bounds, upper_bounds) for each dimension.
        config: Optional optimizer configuration. If not provided, uses defaults.

    Returns:
        CFGWO optimizer ready to run.

    Example::

        def loss_fn(params: np.ndarray) -> float:
            return np.sum((params - target) ** 2)

        optimizer = create_optimizer(
            objective=loss_fn,
            dim=5,
            bounds=([0, 0, 0, 0, 0], [1, 1, 1, 1, 1]),
        )
        result = optimizer.optimize()  # (best_params, best_score)
    """
    from evolution.crisis_gwo import CFGWO

    lb, ub = bounds

    if config is None:
        config = OptimizerConfig(dim=dim, lb=lb, ub=ub)

    return CFGWO(
        objective=objective,
        dim=config.dim,
        lb=config.lb,
        ub=config.ub,
        pack=config.pack,
        iters=config.iters,
        chaos=config.chaos,
        fractal_step=config.fractal_step,
    )


def create_replay_engine(
    capacity: int = 100_000,
    psi: float = 0.5,
    phi: float = 0.3,
    dgr_ratio: float = 0.25,
) -> Any:
    """Create a SleepReplayEngine for experience replay.

    The sleep replay engine uses novelty-aware prioritization inspired
    by sleep consolidation in biological systems. Features:

    - Priority sampling based on TD-error and change-point scores
    - Configurable capacity with automatic eviction
    - Dream-like generative replay (DGR) support

    Args:
        capacity: Maximum number of transitions to store.
        psi: Weight for change-point score in priority computation.
        phi: Weight for imminence jump in priority computation.
        dgr_ratio: Ratio of synthetic samples in DGR batches.

    Returns:
        SleepReplayEngine ready for use.

    Example::

        engine = create_replay_engine(capacity=50_000)
        priority = engine.observe_transition(
            state=obs,
            action=action,
            reward=reward,
            next_state=next_obs,
            td_error=td_error,
            cp_score=0.3,
        )
        batch = engine.sample(batch_size=64)
    """
    from rl.replay.sleep_engine import SleepReplayEngine

    return SleepReplayEngine(
        capacity=capacity,
        psi=psi,
        phi=phi,
        dgr_ratio=dgr_ratio,
    )


class MLSDM:
    """Unified facade for the Multi-Level Stochastic Decision Model.

    This class provides a high-level interface for using MLSDM components
    together. It coordinates the FHMC controller, RL agent, replay engine,
    and optimizer in a coherent workflow.

    Attributes:
        fhmc: The FHMC controller instance.
        agent: The ActorCriticFHMC agent (if created).
        replay_engine: The SleepReplayEngine (if created).

    Example::

        mlsdm = MLSDM.from_config("config/mlsdm.yaml")

        # Get biomarker state
        biomarkers = mlsdm.get_biomarkers()
        print(f"Orexin: {biomarkers.orexin}, Threat: {biomarkers.threat}")

        # Make a decision
        action = mlsdm.act(observation)

        # Update with experience
        mlsdm.observe(
            state=observation,
            action=action,
            reward=reward,
            next_state=next_observation,
            td_error=td_error,
        )

        # Optimize strategy parameters
        result = mlsdm.optimize(objective=loss_fn, dim=5, bounds=bounds)
    """

    def __init__(
        self,
        fhmc: Any,
        agent: Any | None = None,
        replay_engine: Any | None = None,
    ) -> None:
        """Initialize MLSDM with components.

        Args:
            fhmc: FHMC controller instance.
            agent: Optional ActorCriticFHMC agent.
            replay_engine: Optional SleepReplayEngine.
        """
        self.fhmc = fhmc
        self.agent = agent
        self.replay_engine = replay_engine

    @classmethod
    def from_config(cls, config: MLSDMConfig | str | Path) -> MLSDM:
        """Create MLSDM from configuration.

        Args:
            config: MLSDMConfig object or path to YAML file.

        Returns:
            Fully configured MLSDM instance.
        """
        if isinstance(config, (str, Path)):
            config = MLSDMConfig.from_yaml(config)

        fhmc = create_fhmc(config.fhmc)

        agent = None
        if config.agent is not None:
            agent = create_agent(
                state_dim=config.agent.state_dim,
                action_dim=config.agent.action_dim,
                fhmc=fhmc,
                config=config.agent,
            )

        replay_engine = create_replay_engine(dgr_ratio=config.fhmc.sleep.get("dgr_ratio", 0.25))

        return cls(fhmc=fhmc, agent=agent, replay_engine=replay_engine)

    @classmethod
    def default(cls) -> MLSDM:
        """Create MLSDM with default configuration."""
        return cls.from_config(MLSDMConfig.default())

    def get_biomarkers(self) -> BiomarkerState:
        """Get current biomarker state from FHMC.

        Returns:
            BiomarkerState with orexin, threat, and state values.
        """
        return BiomarkerState(
            orexin=self.fhmc.orexin_value(),
            threat=self.fhmc.threat_value(),
            state=self.fhmc.state,
            alpha_history=tuple(self.fhmc._alpha_hist),
            slope_history=tuple(self.fhmc._slope_hist),
        )

    def get_decision_state(self) -> DecisionState:
        """Get current decision state.

        Returns:
            DecisionState with FHMC-derived values.
        """
        window = self.fhmc.next_window_seconds()
        return DecisionState(
            free_energy=0.0,  # Requires ThermoController integration
            baseline_free_energy=0.0,
            latency_spike=1.0,
            steps_in_crisis=0,
            window_seconds=window,
        )

    def update_biomarkers(
        self,
        actions: Iterable[float],
        latents: Iterable[float],
        *,
        fs_latents: int = 50,
    ) -> BiomarkerState:
        """Update biomarkers with new action and latent series.

        Args:
            actions: Recent action scalar series.
            latents: Recent internal latent signals.
            fs_latents: Sampling frequency for latent signals.

        Returns:
            Updated BiomarkerState.
        """
        self.fhmc.update_biomarkers(actions, latents, fs_latents=fs_latents)
        return self.get_biomarkers()

    def compute_drive(
        self,
        exp_return: float,
        novelty: float,
        load: float,
        maxdd: float,
        volshock: float,
        cp_score: float,
    ) -> BiomarkerState:
        """Compute orexin and threat from market conditions.

        Args:
            exp_return: Expected return signal.
            novelty: Novelty/surprise signal.
            load: Cognitive/computational load.
            maxdd: Maximum drawdown.
            volshock: Volatility shock indicator.
            cp_score: Change-point detection score.

        Returns:
            Updated BiomarkerState after computing orexin and threat.
        """
        self.fhmc.compute_orexin(exp_return, novelty, load)
        self.fhmc.compute_threat(maxdd, volshock, cp_score)
        self.fhmc.flipflop_step()
        return self.get_biomarkers()

    def act(self, state: np.ndarray) -> np.ndarray:
        """Select action using the RL agent.

        Args:
            state: Observation state vector.

        Returns:
            Action vector.

        Raises:
            RuntimeError: If agent was not initialized.
        """
        if self.agent is None:
            raise RuntimeError("Agent not initialized. Create MLSDM with agent configuration.")
        return self.agent.act(state)

    def learn(
        self,
        state: np.ndarray,
        action: np.ndarray,
        reward: float,
        next_state: np.ndarray,
        done: bool,
    ) -> TrainingStep:
        """Update agent with a single transition.

        Args:
            state: Observation state before action.
            action: Action taken.
            reward: Reward received.
            next_state: Observation state after action.
            done: Whether episode terminated.

        Returns:
            TrainingStep with update metrics.

        Raises:
            RuntimeError: If agent was not initialized.
        """
        if self.agent is None:
            raise RuntimeError("Agent not initialized. Create MLSDM with agent configuration.")
        self.agent.learn(state, action, reward, next_state, done)

        return TrainingStep(
            td_error=0.0,  # Could be extracted from agent internals
            orexin=self.fhmc.orexin_value(),
            threat=self.fhmc.threat_value(),
            state=self.fhmc.state,
            timestamp=datetime.now(timezone.utc),
        )

    def observe(
        self,
        state: np.ndarray,
        action: np.ndarray,
        reward: float,
        next_state: np.ndarray,
        td_error: float,
        *,
        cp_score: float = 0.0,
        imminence_jump: float = 0.0,
    ) -> float:
        """Store a transition in the replay buffer.

        Args:
            state: Observation state before action.
            action: Action taken.
            reward: Reward received.
            next_state: Observation state after action.
            td_error: TD-error for priority calculation.
            cp_score: Change-point score for priority.
            imminence_jump: Imminence jump for priority.

        Returns:
            Computed priority for the transition.

        Raises:
            RuntimeError: If replay engine was not initialized.
        """
        if self.replay_engine is None:
            raise RuntimeError("Replay engine not initialized.")

        return self.replay_engine.observe_transition(
            state=state,
            action=action,
            reward=reward,
            next_state=next_state,
            td_error=td_error,
            cp_score=cp_score,
            imminence_jump=imminence_jump,
        )

    def sample(self, batch_size: int = 64) -> list[ReplayTransition]:
        """Sample a batch of transitions from replay buffer.

        Args:
            batch_size: Number of transitions to sample.

        Returns:
            List of ReplayTransition objects.

        Raises:
            RuntimeError: If replay engine was not initialized.
        """
        if self.replay_engine is None:
            raise RuntimeError("Replay engine not initialized.")

        raw = self.replay_engine.sample(batch_size)
        return [
            ReplayTransition(
                state=t.state,
                action=t.action,
                reward=t.reward,
                next_state=t.next_state,
                priority=t.priority,
                cp_score=t.cp_score,
            )
            for t in raw
        ]

    def optimize(
        self,
        objective: Callable[[np.ndarray], float],
        dim: int,
        bounds: tuple[Sequence[float], Sequence[float]],
        *,
        config: OptimizerConfig | None = None,
    ) -> OptimizationResult:
        """Run CFGWO optimization.

        Args:
            objective: Function to minimize.
            dim: Search space dimension.
            bounds: (lower_bounds, upper_bounds) for each dimension.
            config: Optional optimizer configuration.

        Returns:
            OptimizationResult with best parameters and score.
        """
        lb, ub = bounds

        if config is None:
            config = OptimizerConfig(dim=dim, lb=lb, ub=ub)

        optimizer = create_optimizer(objective=objective, dim=dim, bounds=bounds, config=config)
        best_params, best_score = optimizer.optimize()

        return OptimizationResult(
            best_params=best_params,
            best_score=best_score,
            iterations=config.iters,
            pack_size=config.pack,
        )

    def next_window(self) -> float:
        """Get the recommended window size for next decision.

        Returns:
            Window size in seconds from FHMC fractal cascade.
        """
        return self.fhmc.next_window_seconds()
