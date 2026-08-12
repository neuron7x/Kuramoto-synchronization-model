# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Configuration classes for the MLSDM SDK.

This module provides validated configuration objects for all MLSDM
components. Configurations can be created programmatically or loaded
from YAML files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

__all__ = [
    "MLSDMConfig",
    "FHMCConfig",
    "AgentConfig",
    "OptimizerConfig",
]


def _default_orexin_params() -> dict[str, float]:
    return {"k1": 1.0, "k2": 0.7, "k3": 0.3}


def _default_threat_params() -> dict[str, float]:
    return {
        "w_dd": 0.5,
        "w_vol": 0.3,
        "w_cp": 0.2,
        "cp_threshold": 5.0,
        "vol_window": 60,
    }


def _default_flipflop_params() -> dict[str, float]:
    return {"theta_lo": 0.6, "theta_hi": 0.8, "omega_lo": 0.4, "omega_hi": 0.6}


def _default_mfs_params() -> dict[str, Any]:
    return {
        "depth": 12,
        "p": 0.6,
        "heavy_tail": 0.5,
        "base_dt_seconds": 60.0,
        "adapt_alpha": False,
    }


def _default_explore_params() -> dict[str, Any]:
    return {"ou_theta": 0.15, "ou_sigma": 0.3, "use_colored_noise_ppo": False}


def _default_fractional_params() -> dict[str, Any]:
    return {"eta_f": 0.5, "levy_alpha": 1.5, "on_states": None}


def _default_modulation_signal_params() -> dict[str, Any]:
    return {
        "base_scale": 1.0,
        "rpe_weight": 0.6,
        "threat_weight": 0.8,
        "orexin_weight": 0.3,
        "min_scale": 0.1,
        "max_scale": 1.5,
    }


@dataclass(slots=True)
class FHMCConfig:
    """Configuration for the Fracto-Hypothalamic Meta-Controller.

    Attributes:
        alpha_target: Target DFA alpha range [lo, hi] for action series.
        orexin: Orexin (arousal) computation parameters.
        threat: Threat detection parameters.
        flipflop: Wake/sleep state transition thresholds.
        mfs: Multi-fractal scaling cascade parameters.
        arousal: Arousal and slope-gate parameters.
        sleep: Sleep replay engine parameters.
        explore: Exploration noise parameters for RL agent.
        fractional_update: Fractional gradient update parameters.
        modulation_signal: Risk-weighted learning-rate modulation parameters.
    """

    alpha_target: tuple[float, float] = (0.5, 1.5)
    orexin: dict[str, float] = field(default_factory=_default_orexin_params)
    threat: dict[str, float] = field(default_factory=_default_threat_params)
    flipflop: dict[str, float] = field(default_factory=_default_flipflop_params)
    mfs: dict[str, Any] = field(default_factory=_default_mfs_params)
    arousal: dict[str, Any] = field(default_factory=lambda: {"slope_gate": False})
    sleep: dict[str, Any] = field(default_factory=lambda: {"dgr_ratio": 0.25})
    explore: dict[str, Any] = field(default_factory=_default_explore_params)
    fractional_update: dict[str, Any] = field(default_factory=_default_fractional_params)
    modulation_signal: dict[str, Any] = field(default_factory=_default_modulation_signal_params)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a dictionary suitable for FHMC initialization."""
        return {
            "alpha_target": list(self.alpha_target),
            "orexin": dict(self.orexin),
            "threat": dict(self.threat),
            "flipflop": dict(self.flipflop),
            "mfs": dict(self.mfs),
            "arousal": dict(self.arousal),
            "sleep": dict(self.sleep),
            "explore": dict(self.explore),
            "fractional_update": dict(self.fractional_update),
            "modulation_signal": dict(self.modulation_signal),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FHMCConfig:
        """Create configuration from a dictionary."""
        return cls(
            alpha_target=tuple(data.get("alpha_target", (0.5, 1.5))),
            orexin=dict(data.get("orexin", _default_orexin_params())),
            threat=dict(data.get("threat", _default_threat_params())),
            flipflop=dict(data.get("flipflop", _default_flipflop_params())),
            mfs=dict(data.get("mfs", _default_mfs_params())),
            arousal=dict(data.get("arousal", {"slope_gate": False})),
            sleep=dict(data.get("sleep", {"dgr_ratio": 0.25})),
            explore=dict(data.get("explore", _default_explore_params())),
            fractional_update=dict(data.get("fractional_update", _default_fractional_params())),
            modulation_signal=dict(
                data.get("modulation_signal", _default_modulation_signal_params())
            ),
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> FHMCConfig:
        """Load configuration from a YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        cfg_data = data.get("fhmc", data)
        return cls.from_dict(cfg_data)


@dataclass(slots=True)
class AgentConfig:
    """Configuration for the ActorCriticFHMC agent.

    Attributes:
        state_dim: Dimension of the observation state vector.
        action_dim: Dimension of the action vector.
        lr: Learning rate for optimizer.
        device: Torch device ("cpu" or "cuda").
    """

    state_dim: int
    action_dim: int
    lr: float = 3e-4
    device: str = "cpu"


@dataclass(slots=True)
class OptimizerConfig:
    """Configuration for the CFGWO optimizer.

    Attributes:
        dim: Dimension of the search space.
        lb: Lower bounds for each dimension.
        ub: Upper bounds for each dimension.
        pack: Wolf pack size (population).
        iters: Number of optimization iterations.
        chaos: Enable chaotic exploration via logistic map.
        fractal_step: Enable Lévy-flight fractal perturbations.
    """

    dim: int
    lb: Sequence[float]
    ub: Sequence[float]
    pack: int = 20
    iters: int = 200
    chaos: bool = True
    fractal_step: bool = True


@dataclass(slots=True)
class MLSDMConfig:
    """Top-level configuration for the MLSDM system.

    This aggregates all component configurations and provides convenience
    methods for loading from files and creating default configurations.

    Attributes:
        fhmc: FHMC controller configuration.
        agent: RL agent configuration (optional).
        optimizer: Optimizer configuration (optional).
    """

    fhmc: FHMCConfig = field(default_factory=FHMCConfig)
    agent: AgentConfig | None = None
    optimizer: OptimizerConfig | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MLSDMConfig:
        """Create configuration from a dictionary.

        Args:
            data: Dictionary with configuration data.

        Returns:
            MLSDMConfig instance.
        """
        fhmc_data = data.get("fhmc", data)
        fhmc = FHMCConfig.from_dict(fhmc_data)

        agent = None
        if "agent" in data:
            agent_data = data["agent"]
            agent = AgentConfig(
                state_dim=agent_data.get("state_dim", 10),
                action_dim=agent_data.get("action_dim", 3),
                lr=agent_data.get("lr", 3e-4),
                device=agent_data.get("device", "cpu"),
            )

        optimizer = None
        if "optimizer" in data:
            opt_data = data["optimizer"]
            optimizer = OptimizerConfig(
                dim=opt_data.get("dim", 5),
                lb=opt_data.get("lb", [0.0] * opt_data.get("dim", 5)),
                ub=opt_data.get("ub", [1.0] * opt_data.get("dim", 5)),
                pack=opt_data.get("pack", 20),
                iters=opt_data.get("iters", 200),
                chaos=opt_data.get("chaos", True),
                fractal_step=opt_data.get("fractal_step", True),
            )

        return cls(fhmc=fhmc, agent=agent, optimizer=optimizer)

    @classmethod
    def from_yaml(cls, path: str | Path) -> MLSDMConfig:
        """Load full MLSDM configuration from a YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls.from_dict(data)

    @classmethod
    def default(cls) -> MLSDMConfig:
        """Create a default configuration with sensible values."""
        return cls(fhmc=FHMCConfig())
