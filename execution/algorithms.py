# SPDX-License-Identifier: MIT
"""Execution algorithms for slicing large parent orders."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List, Sequence

from domain import Order, OrderType


@dataclass(slots=True)
class ChildOrder:
    """A scheduled child order produced by an execution algorithm."""

    order: Order
    scheduled_time: datetime


class ExecutionAlgorithm(ABC):
    """Base class for execution algorithms."""

    @abstractmethod
    def schedule(self, parent: Order) -> List[ChildOrder]:
        """Return the child order schedule for ``parent``."""


class TWAPAlgorithm(ExecutionAlgorithm):
    """Slice orders evenly across a specified horizon."""

    def __init__(self, *, duration: timedelta, slices: int) -> None:
        if slices <= 0:
            raise ValueError("slices must be positive")
        if duration.total_seconds() <= 0:
            raise ValueError("duration must be positive")
        self.duration = duration
        self.slices = slices

    def schedule(self, parent: Order) -> List[ChildOrder]:
        slice_qty = parent.quantity / self.slices
        now = datetime.now(parent.created_at.tzinfo)
        interval = self.duration / self.slices
        return [
            ChildOrder(
                order=Order(
                    symbol=parent.symbol,
                    side=parent.side,
                    quantity=slice_qty,
                    price=parent.price,
                    order_type=OrderType.LIMIT if parent.price else OrderType.MARKET,
                ),
                scheduled_time=now + i * interval,
            )
            for i in range(self.slices)
        ]


class VWAPAlgorithm(ExecutionAlgorithm):
    """Slice orders according to volume weights."""

    def __init__(self, volume_profile: Sequence[float], *, duration: timedelta) -> None:
        if not volume_profile:
            raise ValueError("volume_profile must not be empty")
        total = float(sum(volume_profile))
        if total <= 0:
            raise ValueError("volume_profile must sum to positive value")
        self.weights = [v / total for v in volume_profile]
        self.duration = duration

    def schedule(self, parent: Order) -> List[ChildOrder]:
        now = datetime.now(parent.created_at.tzinfo)
        interval = self.duration / len(self.weights)
        cumulative = 0.0
        children: List[ChildOrder] = []
        for idx, weight in enumerate(self.weights):
            cumulative += weight
            qty = parent.quantity * weight
            child = Order(
                symbol=parent.symbol,
                side=parent.side,
                quantity=qty,
                price=parent.price,
                order_type=OrderType.LIMIT if parent.price else OrderType.MARKET,
            )
            children.append(
                ChildOrder(order=child, scheduled_time=now + idx * interval)
            )
        # Numerical guard to ensure total quantity matches parent
        diff = parent.quantity - sum(child.order.quantity for child in children)
        if abs(diff) > 1e-9:
            children[-1].order.quantity += diff
        return children


class POVAlgorithm(ExecutionAlgorithm):
    """Participation of volume algorithm."""

    def __init__(
        self,
        *,
        participation: float,
        forecast_volume: Sequence[float],
        duration: timedelta,
    ) -> None:
        if not 0 < participation <= 1:
            raise ValueError("participation must be between 0 and 1")
        if not forecast_volume:
            raise ValueError("forecast_volume must not be empty")
        self.participation = participation
        self.forecast = list(forecast_volume)
        self.duration = duration

    def schedule(self, parent: Order) -> List[ChildOrder]:
        now = datetime.now(parent.created_at.tzinfo)
        interval = self.duration / len(self.forecast)
        total_forecast = sum(self.forecast)
        if total_forecast <= 0:
            raise ValueError("forecast_volume must sum to positive value")
        target_qty = parent.quantity
        allocations = [
            min(target_qty, self.participation * bucket) for bucket in self.forecast
        ]
        # Normalize allocations to ensure full quantity is sent if possible
        allocated = sum(allocations)
        if allocated < target_qty:
            shortfall = target_qty - allocated
            allocations[-1] += shortfall
        children: List[ChildOrder] = []
        for idx, qty in enumerate(allocations):
            child = Order(
                symbol=parent.symbol,
                side=parent.side,
                quantity=qty,
                price=parent.price,
                order_type=OrderType.LIMIT if parent.price else OrderType.MARKET,
            )
            children.append(
                ChildOrder(order=child, scheduled_time=now + idx * interval)
            )
        return children


def aggregate_fills(children: Iterable[ChildOrder]) -> float:
    """Compute the total quantity filled across child orders."""

    return sum(item.order.filled_quantity for item in children)


__all__ = [
    "ChildOrder",
    "ExecutionAlgorithm",
    "TWAPAlgorithm",
    "VWAPAlgorithm",
    "POVAlgorithm",
    "aggregate_fills",
]
