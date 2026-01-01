from __future__ import annotations

from dataclasses import dataclass

OBSERVATION_KEYS = ("dd", "liq", "reg", "vol")


def _validate_keys(label: str, keys: tuple[str, ...]) -> None:
    if not keys:
        raise ValueError(f"{label} keys must be non-empty.")
    if any(not key for key in keys):
        raise ValueError(f"{label} keys must be non-empty strings.")
    if len(set(keys)) != len(keys):
        raise ValueError(f"{label} keys must be unique.")
    unexpected = set(keys) - set(OBSERVATION_KEYS)
    if unexpected:
        allowed = ", ".join(OBSERVATION_KEYS)
        raise ValueError(
            f"{label} keys contain unexpected values {sorted(unexpected)}. "
            f"Allowed keys: {allowed}."
        )


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


@dataclass(frozen=True)
class EKFConfig:
    q: float = 1e-3
    r: float = 1e-2


@dataclass(frozen=True)
class PolicyConfig:
    temp: float = 1.0
    tau_E_amber: float = 0.3


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
class SensoryConfig:
    spatial_lambda: float = 0.25
    temporal_lambda: float = 0.35
    contrast_gain: float = 0.6
    keys: tuple[str, ...] = ("dd", "liq", "reg", "vol")

    def __post_init__(self) -> None:
        normalized = tuple(self.keys)
        _validate_keys("SensoryConfig", normalized)
        object.__setattr__(self, "keys", normalized)


@dataclass(frozen=True)
class ThreatGainConfig:
    sensory_amber: float = 0.8
    sensory_red: float = 0.6


@dataclass(frozen=True)
class PredictiveConfig:
    decay: float = 0.8
    error_gain: float = 0.9
    keys: tuple[str, ...] = ("dd", "liq", "reg", "vol")

    def __post_init__(self) -> None:
        normalized = tuple(self.keys)
        _validate_keys("PredictiveConfig", normalized)
        object.__setattr__(self, "keys", normalized)
