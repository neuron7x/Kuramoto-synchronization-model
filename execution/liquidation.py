# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Margin-aware liquidation engine for automated deleveraging.

The liquidation flow is inspired by the operational guidance in
``docs/execution.md`` where margin shortfalls must result in immediate and
observable deleveraging.  The module models an account snapshot, estimates the
margin deficit, constructs a deterministic liquidation plan, and optionally
hands it to an execution adapter.  The design emphasises testability and
clarity so that safety-critical logic can be audited easily.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from core.utils.logging import StructuredLogger, get_logger
from domain.order import OrderSide

__all__ = [
    "LiquidationAction",
    "LiquidationEngine",
    "LiquidationEngineConfig",
    "LiquidationError",
    "LiquidationPlan",
    "MarginAccountState",
    "PositionExposure",
]


class LiquidationError(RuntimeError):
    """Raised when liquidation execution fails."""


@dataclass(frozen=True, slots=True)
class PositionExposure:
    """Snapshot of a single position with margin metadata."""

    symbol: str
    quantity: float
    mark_price: float
    maintenance_margin_rate: float
    initial_margin_rate: float | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must be provided")
        if not isinstance(self.quantity, (int, float)):
            raise TypeError("quantity must be numeric")
        if self.mark_price <= 0:
            raise ValueError("mark_price must be positive")
        if self.maintenance_margin_rate <= 0:
            raise ValueError("maintenance_margin_rate must be positive")
        if self.initial_margin_rate is not None and self.initial_margin_rate <= 0:
            raise ValueError("initial_margin_rate must be positive when provided")

    @property
    def abs_quantity(self) -> float:
        return abs(self.quantity)

    @property
    def notional(self) -> float:
        return self.abs_quantity * self.mark_price

    @property
    def maintenance_margin(self) -> float:
        return self.notional * self.maintenance_margin_rate

    @property
    def initial_margin(self) -> float:
        rate = self.initial_margin_rate or self.maintenance_margin_rate
        return self.notional * rate

    @property
    def liquidation_side(self) -> OrderSide:
        if self.quantity > 0:
            return OrderSide.SELL
        if self.quantity < 0:
            return OrderSide.BUY
        raise ValueError("cannot liquidate a flat position")


@dataclass(slots=True)
class MarginAccountState:
    """Aggregate account snapshot used by the liquidation engine."""

    equity: float
    positions: Sequence[PositionExposure] = ()
    maintenance_margin: float | None = None
    initial_margin: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.equity, (int, float)):
            raise TypeError("equity must be numeric")
        if not isinstance(self.positions, Sequence):
            raise TypeError("positions must be a sequence")

    @property
    def maintenance_requirement(self) -> float:
        if self.maintenance_margin is not None:
            return max(float(self.maintenance_margin), 0.0)
        return sum(position.maintenance_margin for position in self.positions)

    @property
    def initial_requirement(self) -> float:
        if self.initial_margin is not None:
            return max(float(self.initial_margin), 0.0)
        return sum(position.initial_margin for position in self.positions)

    @property
    def margin_ratio(self) -> float:
        requirement = self.maintenance_requirement
        if requirement <= 0:
            return float("inf")
        return float(self.equity) / requirement

    @property
    def maintenance_deficit(self) -> float:
        return max(0.0, self.maintenance_requirement - float(self.equity))


@dataclass(frozen=True, slots=True)
class LiquidationEngineConfig:
    """Tunable parameters for :class:`LiquidationEngine`."""

    target_margin_ratio: float = 1.05
    max_position_fraction: float = 1.0
    min_order_quantity: float = 0.0
    precision: float = 1e-9

    def __post_init__(self) -> None:
        if self.target_margin_ratio <= 0:
            raise ValueError("target_margin_ratio must be positive")
        if not 0 < self.max_position_fraction <= 1:
            raise ValueError("max_position_fraction must be in (0, 1]")
        if self.min_order_quantity < 0:
            raise ValueError("min_order_quantity must be non-negative")
        if self.precision <= 0:
            raise ValueError("precision must be positive")


@dataclass(frozen=True, slots=True)
class LiquidationAction:
    """Single liquidation order recommendation."""

    symbol: str
    side: OrderSide
    quantity: float
    maintenance_reduction: float
    notional_reduction: float

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.maintenance_reduction < 0:
            raise ValueError("maintenance_reduction cannot be negative")
        if self.notional_reduction < 0:
            raise ValueError("notional_reduction cannot be negative")


@dataclass(frozen=True, slots=True)
class LiquidationPlan:
    """Result of evaluating an account for liquidation."""

    actions: tuple[LiquidationAction, ...]
    pre_margin_ratio: float
    post_margin_ratio: float
    maintenance_deficit: float
    required_reduction: float

    @property
    def should_liquidate(self) -> bool:
        return bool(self.actions)


class LiquidationEngine:
    """Coordinate liquidation planning and optional order dispatch."""

    def __init__(
        self,
        submit_order: Callable[[str, OrderSide, float], None],
        *,
        config: LiquidationEngineConfig | None = None,
        logger: StructuredLogger | None = None,
    ) -> None:
        self._submit_order = submit_order
        self._config = config or LiquidationEngineConfig()
        self._logger = logger or get_logger(__name__)

    @property
    def config(self) -> LiquidationEngineConfig:
        return self._config

    def plan(self, account: MarginAccountState) -> LiquidationPlan:
        """Compute a liquidation plan for ``account`` without executing it."""

        maintenance_requirement = account.maintenance_requirement
        margin_ratio = account.margin_ratio
        target_ratio = self._config.target_margin_ratio

        if maintenance_requirement <= self._config.precision:
            return LiquidationPlan(
                actions=(),
                pre_margin_ratio=margin_ratio,
                post_margin_ratio=float("inf"),
                maintenance_deficit=0.0,
                required_reduction=0.0,
            )

        if margin_ratio >= target_ratio:
            return LiquidationPlan(
                actions=(),
                pre_margin_ratio=margin_ratio,
                post_margin_ratio=margin_ratio,
                maintenance_deficit=account.maintenance_deficit,
                required_reduction=0.0,
            )

        target_maintenance = float(account.equity) / target_ratio
        required_reduction = max(0.0, maintenance_requirement - target_maintenance)

        actions: list[LiquidationAction] = []
        reduction_accumulated = 0.0

        positions = sorted(
            account.positions,
            key=lambda position: (position.maintenance_margin, position.notional),
            reverse=True,
        )

        for position in positions:
            if reduction_accumulated >= required_reduction - self._config.precision:
                break
            if position.abs_quantity <= self._config.precision:
                continue

            maintenance_contribution = position.maintenance_margin
            if maintenance_contribution <= 0:
                continue

            remaining_reduction = required_reduction - reduction_accumulated
            fraction = min(
                1.0,
                self._config.max_position_fraction,
                remaining_reduction / maintenance_contribution,
            )
            if fraction <= 0:
                continue

            qty = position.abs_quantity * fraction
            if fraction >= 1.0:
                qty = position.abs_quantity

            if qty < self._config.min_order_quantity - self._config.precision:
                continue

            maintenance_reduction = maintenance_contribution * fraction
            notional_reduction = position.notional * fraction

            actions.append(
                LiquidationAction(
                    symbol=position.symbol,
                    side=position.liquidation_side,
                    quantity=qty,
                    maintenance_reduction=maintenance_reduction,
                    notional_reduction=notional_reduction,
                )
            )
            reduction_accumulated += maintenance_reduction

        post_maintenance = max(maintenance_requirement - reduction_accumulated, 0.0)
        post_margin_ratio = (
            float(account.equity) / post_maintenance
            if post_maintenance > self._config.precision
            else float("inf")
        )

        return LiquidationPlan(
            actions=tuple(actions),
            pre_margin_ratio=margin_ratio,
            post_margin_ratio=post_margin_ratio,
            maintenance_deficit=account.maintenance_deficit,
            required_reduction=required_reduction,
        )

    def liquidate(self, account: MarginAccountState) -> LiquidationPlan:
        """Execute the liquidation plan for ``account`` if required."""

        plan = self.plan(account)
        if not plan.should_liquidate:
            return plan

        for action in plan.actions:
            try:
                self._submit_order(action.symbol, action.side, action.quantity)
            except Exception as exc:  # pragma: no cover - defensive guard
                raise LiquidationError(str(exc)) from exc
            self._logger.info(
                "submitted_liquidation_order",
                symbol=action.symbol,
                side=action.side.value,
                quantity=action.quantity,
                maintenance_reduction=action.maintenance_reduction,
            )

        return plan

    def simulate(self, accounts: Iterable[MarginAccountState]) -> list[LiquidationPlan]:
        """Utility helper to plan liquidations across multiple accounts."""

        plans: list[LiquidationPlan] = []
        for account in accounts:
            plans.append(self.plan(account))
        return plans
