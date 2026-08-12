# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Risk-gating pre-action filter for live execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Mapping, Protocol

if TYPE_CHECKING:
    from .degradation import DegradationPolicy, DegradationReport


@dataclass(slots=True)
class PreActionContext:
    """Context payload evaluated before an execution action."""

    venue: str
    symbol: str
    side: str
    quantity: float
    price: float | None = None
    volatility: float | None = None
    liquidity: float | None = None
    latency_ms: float | None = None
    policy_deviation: float | None = None
    policy_mode: str | None = None
    timestamp: float | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "PreActionContext":
        return cls(
            venue=str(payload.get("venue", "")),
            symbol=str(payload.get("symbol", "")),
            side=str(payload.get("side", "")),
            quantity=float(payload.get("quantity", 0.0)),
            price=payload.get("price"),
            volatility=payload.get("volatility"),
            liquidity=payload.get("liquidity"),
            latency_ms=payload.get("latency_ms"),
            policy_deviation=payload.get("policy_deviation"),
            policy_mode=payload.get("policy_mode"),
            timestamp=payload.get("timestamp"),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(slots=True)
class PreActionDecision:
    """Decision outcome for pre-action filters."""

    allowed: bool
    reasons: tuple[str, ...] = ()
    safe_mode: bool = False
    rollback: bool = False
    policy_override: str | None = None


class PreActionFilter(Protocol):
    """Callable interface for pre-action gating."""

    def check(self, context: PreActionContext | Mapping[str, object]) -> PreActionDecision:
        raise NotImplementedError


@dataclass(slots=True)
class RiskGatingConfig:
    """Thresholds for threat-model gating."""

    max_volatility: float = 0.05
    min_liquidity: float = 1_000_000.0
    max_latency_ms: float = 250.0
    max_policy_deviation: float = 0.2
    hard_volatility: float = 0.1
    hard_liquidity: float = 500_000.0
    hard_latency_ms: float = 750.0
    hard_policy_deviation: float = 0.35
    safe_policy: str = "conservative"


class RiskGatingEngine:
    """Pre-action filter implementing volatility/liquidity/latency gating."""

    def __init__(self, config: RiskGatingConfig | None = None) -> None:
        self._config = config or RiskGatingConfig()

    def check(self, context: PreActionContext | Mapping[str, object]) -> PreActionDecision:
        ctx = (
            context
            if isinstance(context, PreActionContext)
            else PreActionContext.from_mapping(context)
        )
        cfg = self._config
        reasons: list[str] = []
        safe_mode = False
        rollback = False
        allowed = True

        def _soft_breach(reason: str) -> None:
            nonlocal safe_mode
            safe_mode = True
            reasons.append(reason)

        def _hard_breach(reason: str) -> None:
            nonlocal allowed, rollback
            allowed = False
            rollback = True
            reasons.append(reason)

        if ctx.volatility is not None:
            if ctx.volatility >= cfg.hard_volatility:
                _hard_breach("volatility_hard_breach")
            elif ctx.volatility >= cfg.max_volatility:
                _soft_breach("volatility_soft_breach")

        if ctx.liquidity is not None:
            if ctx.liquidity <= cfg.hard_liquidity:
                _hard_breach("liquidity_dryup")
            elif ctx.liquidity <= cfg.min_liquidity:
                _soft_breach("liquidity_thin")

        if ctx.latency_ms is not None:
            if ctx.latency_ms >= cfg.hard_latency_ms:
                _hard_breach("latency_spike")
            elif ctx.latency_ms >= cfg.max_latency_ms:
                _soft_breach("latency_degraded")

        if ctx.policy_deviation is not None:
            if ctx.policy_deviation >= cfg.hard_policy_deviation:
                _hard_breach("policy_deviation_hard")
            elif ctx.policy_deviation >= cfg.max_policy_deviation:
                _soft_breach("policy_deviation_soft")

        policy_override = cfg.safe_policy if safe_mode else None
        reasons_tuple: tuple[str, ...] = tuple(reasons) or ("clear",)
        return PreActionDecision(
            allowed=allowed,
            reasons=reasons_tuple,
            safe_mode=safe_mode,
            rollback=rollback,
            policy_override=policy_override,
        )

    def check_with_degradation(
        self,
        context: PreActionContext | Mapping[str, object],
        *,
        policy: "DegradationPolicy" | None = None,
    ) -> tuple[PreActionDecision, "DegradationReport"]:
        """Run the risk gate with standard timeout and fallback handling."""

        from .degradation import apply_degradation

        return apply_degradation(self, context, policy=policy)


__all__ = [
    "PreActionContext",
    "PreActionDecision",
    "PreActionFilter",
    "RiskGatingConfig",
    "RiskGatingEngine",
]
