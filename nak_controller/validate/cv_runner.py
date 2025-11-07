"""Cross-validation helpers for the CLI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Sequence

import numpy as np

from ..integration.hook import NaKHook
from ..risk.cvar import conditional_value_at_risk
from .sim_env import SimulatedEnvironment


@dataclass(slots=True)
class CVConfig:
    """Configuration for a CV sweep."""

    config_path: str
    seeds: Sequence[int]
    steps: int
    base_risk_per_trade: float = 0.002
    base_max_position: float = 1.0
    base_cooldown_ms: float = 2000.0
    seed_base: int = 1234


def run_cross_validation(cfg: CVConfig) -> Dict[str, float]:
    """Run the controller for multiple seeds and return summary metrics."""

    hook = NaKHook(cfg.config_path)
    baseline_risks = []
    controller_risks = []
    controller_health = []

    for seed in cfg.seeds:
        env_seed = cfg.seed_base + seed
        env = SimulatedEnvironment(seed=env_seed, steps=cfg.steps)
        hook.reset()
        for local_obs, global_obs in env.iter_steps():
            out = hook.compute_limits(
                strategy_id=f"cv_{seed}",
                local_obs=local_obs,
                global_obs=global_obs,
                base_risk_per_trade=cfg.base_risk_per_trade,
                base_max_position=cfg.base_max_position,
                base_cooldown_ms=cfg.base_cooldown_ms,
            )
            controller_risks.append(out["risk_per_trade"])
            controller_health.append(out["health"])
            baseline_risks.append(cfg.base_risk_per_trade)

    baseline_risks_arr = np.asarray(baseline_risks, dtype=float)
    controller_risks_arr = np.asarray(controller_risks, dtype=float)
    controller_health_arr = np.asarray(controller_health, dtype=float)

    return {
        "baseline_mean_risk": float(baseline_risks_arr.mean()),
        "baseline_cvar": float(conditional_value_at_risk(baseline_risks_arr, alpha=0.95)),
        "nak_mean_risk": float(controller_risks_arr.mean()),
        "nak_cvar": float(conditional_value_at_risk(controller_risks_arr, alpha=0.95)),
        "nak_health_mean": float(controller_health_arr.mean()),
        "samples": int(controller_risks_arr.size),
    }


__all__ = ["CVConfig", "run_cross_validation"]
