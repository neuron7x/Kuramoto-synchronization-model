"""Validation routines for the NaK controller."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from statistics import mean
from typing import Dict, Iterable, List

from ..integration.hook import NaKHook
from .sim_env import SimulationEnvironment


@dataclass(slots=True)
class ValidationResult:
    """Aggregated validation metrics."""

    avg_risk_per_trade: float
    avg_max_position: float
    avg_cooldown_ms: float
    avg_health: float

    def as_dict(self) -> Dict[str, float]:
        return {
            "avg_risk_per_trade": self.avg_risk_per_trade,
            "avg_max_position": self.avg_max_position,
            "avg_cooldown_ms": self.avg_cooldown_ms,
            "avg_health": self.avg_health,
        }


def _aggregate(samples: Iterable[Dict[str, float]]) -> ValidationResult:
    risks = [sample["risk_per_trade"] for sample in samples]
    max_positions = [sample["max_position"] for sample in samples]
    cooldowns = [sample["cooldown_ms"] for sample in samples]
    health = [sample["health"] for sample in samples]
    return ValidationResult(
        avg_risk_per_trade=mean(risks),
        avg_max_position=mean(max_positions),
        avg_cooldown_ms=mean(cooldowns),
        avg_health=mean(health),
    )


def _ensure_float(value: object, key: str) -> float:
    if isinstance(value, Real):
        return float(value)
    raise TypeError(
        f"Expected numeric value for {key!r}, received {type(value).__name__}"
    )


def run_validation(
    config_path: str,
    *,
    steps: int = 200,
    seeds: int = 3,
    seed: int | None = None,
) -> Dict[str, Dict[str, float]]:
    """Run synthetic validation using ``seeds`` random seeds."""
    if steps <= 0:
        raise ValueError("steps must be positive")
    if seeds <= 0:
        raise ValueError("seeds must be positive")

    hook = NaKHook(config_path, seed=seed)
    if seed is not None:
        base_seed = seed
    else:
        base_seed = hook.seed if hook.seed is not None else 0

    baseline_samples: List[Dict[str, float]] = []
    nak_samples: List[Dict[str, float]] = []

    for offset in range(seeds):
        iteration_seed = base_seed + offset
        env = SimulationEnvironment(seed=iteration_seed)
        hook.reset(seed=iteration_seed)
        for _ in range(steps):
            local, global_obs, bases = env.step()
            baseline_samples.append(
                {
                    "risk_per_trade": bases["risk_per_trade"],
                    "max_position": bases["max_position"],
                    "cooldown_ms": bases["cooldown_ms_base"],
                    "health": 0.5,
                }
            )
            limits = hook.compute_limits(
                "sim-strategy",
                local,
                global_obs,
                bases["risk_per_trade"],
                bases["max_position"],
                bases["cooldown_ms_base"],
            )
            nak_samples.append(
                {
                    "risk_per_trade": _ensure_float(
                        limits["risk_per_trade"], "risk_per_trade"
                    ),
                    "max_position": _ensure_float(
                        limits["max_position"], "max_position"
                    ),
                    "cooldown_ms": _ensure_float(limits["cooldown_ms"], "cooldown_ms"),
                    "health": _ensure_float(limits["health"], "health"),
                }
            )

    baseline_result = _aggregate(baseline_samples)
    nak_result = _aggregate(nak_samples)

    return {"baseline": baseline_result.as_dict(), "nak": nak_result.as_dict()}


__all__ = ["run_validation", "ValidationResult"]
