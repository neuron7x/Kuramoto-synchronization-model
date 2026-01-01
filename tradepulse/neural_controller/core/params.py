from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .neuro_params import OBSERVATION_KEYS, PredictiveConfig, SensoryConfig


@dataclass(frozen=True)
class Params:
    alpha: float = 0.1
    beta: float = 0.05
    gamma: float = 0.05
    delta: float = 0.1
    theta: float = 0.0
    lambd: float = 0.2
    mu: float = 0.05
    phi: float = 0.6
    omega: float = 0.4
    kappa: float = 0.1
    psi: float = 1.0
    eps: float = 0.7
    eta: float = 0.2
    M0: float = 0.8
    prediction_gain: float = 0.08
    sensory_confidence_gain: float = 1.0


@dataclass(frozen=True)
class EKFConfig:
    q: float = 1e-3
    r: float = 1e-2


@dataclass(frozen=True)
class PolicyModeConfig:
    temp: float = 1.0
    gating: float = 0.0


@dataclass(frozen=True)
class PolicyConfig:
    temp: float = 1.0
    tau_E_amber: float = 0.3
    policy_modes: Mapping[str, PolicyModeConfig] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized: dict[str, PolicyModeConfig] = {}
        for mode, raw in self.policy_modes.items():
            key = str(mode).upper()
            if isinstance(raw, PolicyModeConfig):
                normalized[key] = raw
            elif isinstance(raw, Mapping):
                normalized[key] = PolicyModeConfig(**raw)
            else:
                raise TypeError(
                    "policy_modes values must be PolicyModeConfig or mapping"
                )
        object.__setattr__(self, "policy_modes", normalized)


@dataclass(frozen=True)
class RiskConfig:
    cvar_alpha: float = 0.95
    cvar_limit: float = 0.03
    lookback: int = 50


@dataclass(frozen=True)
class HomeoConfig:
    M_target: float = 0.8
    k_sigmoid: float = 5.0


@dataclass(frozen=True)
class MarketAdapterConfig:
    max_drawdown_limit: float = 0.20
    spread_threshold: float = 0.01
    regime_threshold: float = 0.05
    hist_max_vol: float = 1.0
    risk_free: float = 0.02
    eps: float = 1e-6


@dataclass(frozen=True)
class TemporalGatingConfig:
    sensory_frequency: float = 1.0
    predictive_frequency: float = 1.0
    sensory_period: int | None = None
    predictive_period: int | None = None
    cadence: str = "step"
    ema_alpha: float = 0.5

    def __post_init__(self) -> None:
        if self.sensory_period is not None:
            if self.sensory_period <= 0:
                raise ValueError("sensory_period must be positive")
            object.__setattr__(
                self, "sensory_frequency", 1.0 / float(self.sensory_period)
            )
        if self.predictive_period is not None:
            if self.predictive_period <= 0:
                raise ValueError("predictive_period must be positive")
            object.__setattr__(
                self,
                "predictive_frequency",
                1.0 / float(self.predictive_period),
            )
        if self.sensory_frequency <= 0 or self.predictive_frequency <= 0:
            raise ValueError("frequencies must be positive")
        cadence = self.cadence.lower()
        if cadence not in {"step", "ema"}:
            raise ValueError("cadence must be 'step' or 'ema'")
        object.__setattr__(self, "cadence", cadence)
        if not 0.0 < self.ema_alpha <= 1.0:
            raise ValueError("ema_alpha must be in (0, 1]")
