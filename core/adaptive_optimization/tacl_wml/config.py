"""WML configuration with business-aware weights and risk controls."""

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass(slots=True)
class WMLConfig:
    """Configuration for WML adaptive optimization system."""

    # Latency and jitter thresholds
    latency_p99_ms: float = 8.0
    jitter_p99_ms: float = 4.0

    # Free energy function weights
    mfe_alpha: float = 0.5  # Weight for jitter
    mfe_beta: float = 0.3  # Weight for resource cost
    mfe_margin: float = 0.05  # Absolute threshold for backwards compatibility

    # NEW: Relative threshold and IS penalty
    eps_rel: float = 0.03  # Relative threshold: F_try < F_now*(1-ε)
    gamma_is: float = 0.02  # Penalty weight for implementation shortfall (basis points)

    # Rollback settings
    rollback_deadline_ms: int = 1000

    # Myelin bounds
    bounds: Dict[str, float] = field(
        default_factory=lambda: {"m_min": 0.0, "m_max": 1.0}
    )

    # Plasticity schedule by regime
    plasticity_schedule: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: {
            "CALM": {"eta": 0.04, "lambda_decay": 0.002},
            "TREND": {"eta": 0.03, "lambda_decay": 0.003},
            "VOLATILE": {"eta": 0.01, "lambda_decay": 0.01},
            "SHOCK": {"eta": 0.00, "lambda_decay": 0.05},
        }
    )

    # Regime detection thresholds
    regime_thresholds: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: {
            "CALM": {"vol_index_max": 0.3},
            "TREND": {"vol_index_min": 0.3, "vol_index_max": 0.6},
            "VOLATILE": {"vol_index_min": 0.6},
            "SHOCK": {"latency_p99_max": 20.0, "jitter_p99_max": 10.0},
        }
    )

    hysteresis_vol: float = 0.03

    # NEW: Risk freeze controls
    min_apply_interval_s: float = 0.2
    risk_freeze_enabled: bool = True
    auto_freeze_fails: int = 2

    @staticmethod
    def from_json(d: Dict[str, Any]) -> "WMLConfig":
        """Create config from dictionary."""
        cfg = WMLConfig()
        for k, v in d.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg

    def validate(self) -> None:
        """Validate configuration parameters."""
        assert 0.0 <= self.bounds.get("m_min", 0.0) <= self.bounds.get("m_max", 1.0)
        assert self.mfe_margin >= 0.0
        assert 0.0 <= self.eps_rel < 1.0
        assert self.gamma_is >= 0.0
