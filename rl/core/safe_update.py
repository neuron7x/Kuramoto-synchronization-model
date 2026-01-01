"""Safe update gating aligned with TACL risk filters."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
import logging
from typing import Mapping

from tacl.risk_gating import PreActionDecision, RiskGatingConfig, RiskGatingEngine

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SafeUpdateDecision:
    """Decision payload for safe update scaling."""

    allowed: bool
    scale: float
    reasons: tuple[str, ...]
    safe_mode: bool
    rollback: bool
    policy_override: str | None = None


@dataclass(slots=True)
class SafeUpdateConfig:
    """Configuration for safe update gating."""

    rpe_scale: float = 1.0
    safe_scale: float = 0.5
    min_scale: float = 0.0
    policy_deviation_cap: float = 1.0
    risk_gating: RiskGatingConfig = field(default_factory=RiskGatingConfig)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object] | None) -> "SafeUpdateConfig":
        if not payload:
            return cls()
        risk_payload = payload.get("risk_gating") if isinstance(payload, Mapping) else None
        risk_cfg = _risk_config_from_mapping(risk_payload)
        return cls(
            rpe_scale=float(payload.get("rpe_scale", cls.rpe_scale)),
            safe_scale=float(payload.get("safe_scale", cls.safe_scale)),
            min_scale=float(payload.get("min_scale", cls.min_scale)),
            policy_deviation_cap=float(
                payload.get("policy_deviation_cap", cls.policy_deviation_cap)
            ),
            risk_gating=risk_cfg,
        )


def _risk_config_from_mapping(payload: Mapping[str, object] | None) -> RiskGatingConfig:
    if not payload:
        return RiskGatingConfig()
    default_cfg = RiskGatingConfig()
    kwargs = {
        f.name: payload.get(f.name, getattr(default_cfg, f.name))
        for f in fields(default_cfg)
    }
    return RiskGatingConfig(**kwargs)


class SafeUpdateGate:
    """Risk-gated safe update controller."""

    def __init__(self, config: SafeUpdateConfig | None = None) -> None:
        cfg = config or SafeUpdateConfig()
        self._config = cfg
        self._risk_gate = RiskGatingEngine(cfg.risk_gating)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object] | None) -> "SafeUpdateGate":
        return cls(SafeUpdateConfig.from_mapping(payload))

    def evaluate(
        self,
        rpe_metrics: Mapping[str, float],
        *,
        volatility: float | None = None,
        liquidity: float | None = None,
        latency_ms: float | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> SafeUpdateDecision:
        rpe_abs = float(rpe_metrics.get("rpe_abs", 0.0))
        policy_deviation = min(
            rpe_abs * self._config.rpe_scale, self._config.policy_deviation_cap
        )
        context = {
            "venue": "rl_update",
            "symbol": "rpe",
            "side": "learn",
            "quantity": 0.0,
            "policy_deviation": policy_deviation,
            "volatility": volatility,
            "liquidity": liquidity,
            "latency_ms": latency_ms,
            "metadata": dict(metadata or {}),
        }
        decision: PreActionDecision = self._risk_gate.check(context)
        scale = 0.0
        if decision.allowed:
            scale = self._config.safe_scale if decision.safe_mode else 1.0
            scale = max(scale, self._config.min_scale)

        metrics = {
            "policy_deviation": policy_deviation,
            "update_scale": scale,
            "safe_mode": 1.0 if decision.safe_mode else 0.0,
            "allowed": 1.0 if decision.allowed else 0.0,
        }
        logger.info("Safe update gating decision: %s", metrics)
        return SafeUpdateDecision(
            allowed=decision.allowed,
            scale=scale,
            reasons=decision.reasons,
            safe_mode=decision.safe_mode,
            rollback=decision.rollback,
            policy_override=decision.policy_override,
        )
