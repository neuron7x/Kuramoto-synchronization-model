# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Limit order book simulator with microstructure aware extensions.

The module focuses on deterministic, testable components that can be used in
research pipelines or light–weight execution sandboxes.  The design embraces a
price–time priority queue, explicit level management and pluggable impact /
slippage adapters so additional realism can be layered without modifying the
matching logic.
"""
from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, Iterable, List, Optional, Protocol, Tuple


class Side(str, Enum):
    """Order directions supported by the simulator."""

    BUY = "buy"
    SELL = "sell"


@dataclass(slots=True)
class Order:
    """Representation of a limit order resting in the book."""

    order_id: str
    side: Side | str
    price: float
    quantity: float
    timestamp: int

    def __post_init__(self) -> None:
        if isinstance(self.side, str):
            self.side = Side(self.side.lower())
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.price <= 0:
            raise ValueError("price must be positive")


@dataclass(slots=True)
class Execution:
    """Result of matching a taker order against resting liquidity."""

    order_id: str
    price: float
    quantity: float
    level_index: int
    queue_position: int
    impacted_price: float
    slippage: float


class ImpactModel(Protocol):
    """Protocol for price impact models."""

    def adjusted_price(
        self, price: float, side: Side, executed_qty: float, level_index: int
    ) -> float:
        """Return the impacted price for the executed trade."""


class NullImpactModel:
    """No-op impact model used as default."""

    def adjusted_price(
        self, price: float, side: Side, executed_qty: float, level_index: int
    ) -> float:  # noqa: D401
        return price


class LinearImpactModel:
    """Linear impact model applying a coefficient per unit volume executed."""

    __slots__ = ("coefficient",)

    def __init__(self, coefficient: float) -> None:
        self.coefficient = float(max(coefficient, 0.0))

    def adjusted_price(
        self, price: float, side: Side, executed_qty: float, level_index: int
    ) -> float:  # noqa: D401
        if executed_qty <= 0:
            return price
        multiplier = self.coefficient * executed_qty
        if side is Side.BUY:
            return price * (1.0 + multiplier)
        return max(price * (1.0 - multiplier), 0.0)


class SlippageModule(Protocol):
    """Pluggable slippage estimators."""

    def compute(
        self,
        *,
        side: Side,
        base_price: float,
        impacted_price: float,
        level_index: int,
        queue_position: int,
        executed_qty: float,
    ) -> float:
        """Return the slippage (adverse price move) for a single fill."""


class PerUnitBpsSlippage:
    """Linear bps slippage applied to the impacted price."""

    __slots__ = ("bps",)

    def __init__(self, bps: float) -> None:
        self.bps = float(max(bps, 0.0))

    def compute(
        self,
        *,
        side: Side,
        base_price: float,
        impacted_price: float,
        level_index: int,
        queue_position: int,
        executed_qty: float,
    ) -> float:
        adjustment = impacted_price * self.bps * 1e-4
        return adjustment if side is Side.BUY else adjustment


class QueueAwareSlippage:
    """Simple queue position slippage model.

    Later positions in the queue incur proportionally larger slippage.
    """

    __slots__ = ("penalty",)

    def __init__(self, penalty: float) -> None:
        self.penalty = float(max(penalty, 0.0))

    def compute(
        self,
        *,
        side: Side,
        base_price: float,
        impacted_price: float,
        level_index: int,
        queue_position: int,
        executed_qty: float,
    ) -> float:
        if queue_position <= 0:
            return 0.0
        adverse = impacted_price * self.penalty * queue_position * 1e-4
        return adverse


@dataclass(slots=True)
class _Level:
    price: float
    side: Side
    orders: Deque[Order] = field(default_factory=deque)

    @property
    def total_quantity(self) -> float:
        return sum(order.quantity for order in self.orders)

    def append(self, order: Order) -> None:
        self.orders.append(order)

    def popleft(self) -> Order:
        return self.orders.popleft()

    def __len__(self) -> int:
        return len(self.orders)


class PriceTimeOrderBook:
    """Book implementation featuring price-time priority queues."""

    def __init__(
        self,
        *,
        impact_model: ImpactModel | None = None,
        slippage_modules: Optional[Iterable[SlippageModule]] = None,
    ) -> None:
        self._levels: Dict[Tuple[Side, float], _Level] = {}
        self._price_heaps: Dict[Side, List[float]] = {Side.BUY: [], Side.SELL: []}
        self._impact_model = impact_model or NullImpactModel()
        self._slippage_modules = tuple(slippage_modules or ())
        self._order_index: Dict[str, Tuple[Side, float]] = {}

    # ------------------------------------------------------------------
    # Order management
    # ------------------------------------------------------------------
    def add_limit_order(self, order: Order) -> None:
        """Insert a new limit order respecting price-time priority."""
        # order.side is converted to Side in Order.__post_init__
        side = order.side if isinstance(order.side, Side) else Side(order.side)
        key = (side, order.price)
        level = self._levels.get(key)
        if level is None:
            level = _Level(price=order.price, side=side)
            self._levels[key] = level
            heap = self._price_heaps[side]
            price = order.price if side is Side.SELL else -order.price
            heapq.heappush(heap, price)
        level.append(order)
        self._order_index[order.order_id] = key

    def cancel(self, order_id: str) -> bool:
        """Cancel an existing order if found."""

        key = self._order_index.pop(order_id, None)
        if key is None:
            return False
        level = self._levels.get(key)
        if level is None:
            return False

        new_queue = deque(o for o in level.orders if o.order_id != order_id)
        removed = len(level.orders) - len(new_queue)
        level.orders = new_queue
        if not level.orders:
            self._remove_level(level)
        return removed > 0

    def best_bid(self) -> Optional[float]:
        return self._best_price(Side.BUY)

    def best_ask(self) -> Optional[float]:
        return self._best_price(Side.SELL)

    def depth(self, side: Side) -> List[Tuple[float, float]]:
        """Return price levels and aggregate quantity for the given side."""

        heap = self._price_heaps[side]
        entries: List[Tuple[float, float]] = []
        for price_token in heap:
            price = -price_token if side is Side.BUY else price_token
            level = self._levels.get((side, price))
            if level is None:
                continue
            entries.append((price, level.total_quantity))
        entries.sort(reverse=side is Side.BUY)
        return entries

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------
    def match_market_order(self, side: Side, quantity: float) -> List[Execution]:
        """Match a market order against the book and return executions."""

        if quantity <= 0:
            raise ValueError("quantity must be positive")

        remaining = quantity
        executions: List[Execution] = []
        resting_side = Side.SELL if side is Side.BUY else Side.BUY

        while remaining > 0:
            level_info = self._top_level(resting_side)
            if level_info is None:
                break
            level_index, level = level_info
            queue_position = 0
            while remaining > 0 and level.orders:
                resting_order = level.orders[0]
                take = min(remaining, resting_order.quantity)
                impacted = self._impact_model.adjusted_price(
                    level.price, side, take, level_index
                )
                slippage = self._compute_slippage(
                    side=side,
                    base_price=level.price,
                    impacted_price=impacted,
                    level_index=level_index,
                    queue_position=queue_position,
                    executed_qty=take,
                )
                executions.append(
                    Execution(
                        order_id=resting_order.order_id,
                        price=level.price,
                        quantity=take,
                        level_index=level_index,
                        queue_position=queue_position,
                        impacted_price=impacted,
                        slippage=slippage,
                    )
                )
                remaining -= take
                resting_order.quantity -= take
                queue_position += 1
                if resting_order.quantity <= 0:
                    level.popleft()
                    self._order_index.pop(resting_order.order_id, None)
            if not level.orders:
                self._remove_level(level)

        return executions

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _compute_slippage(self, **kwargs: float | Side | int) -> float:
        total = 0.0
        for module in self._slippage_modules:
            total += module.compute(**kwargs)  # type: ignore[arg-type]
        return total

    def _top_level(self, side: Side) -> Optional[Tuple[int, _Level]]:
        price = self._best_price(side)
        if price is None:
            return None
        level = self._levels.get((side, price))
        if level is None or not level.orders:
            return None
        return 0, level

    def _best_price(self, side: Side) -> Optional[float]:
        heap = self._price_heaps[side]
        while heap:
            price_token = heap[0]
            price = -price_token if side is Side.BUY else price_token
            level = self._levels.get((side, price))
            if level and level.orders:
                return price
            heapq.heappop(heap)
        return None

    def _remove_level(self, level: _Level) -> None:
        key = (level.side, level.price)
        self._levels.pop(key, None)
        heap = self._price_heaps[level.side]
        token = level.price if level.side is Side.SELL else -level.price
        try:
            idx = heap.index(token)
        except ValueError:
            return
        # Remove element and restore heap property using public API
        heap[idx] = heap[-1]
        heap.pop()
        if idx < len(heap):
            # Re-heapify: simpler and more maintainable than using private methods
            heapq.heapify(heap)


__all__ = [
    "Execution",
    "ImpactModel",
    "LinearImpactModel",
    "NullImpactModel",
    "Order",
    "PerUnitBpsSlippage",
    "PriceTimeOrderBook",
    "QueueAwareSlippage",
    "Side",
]
