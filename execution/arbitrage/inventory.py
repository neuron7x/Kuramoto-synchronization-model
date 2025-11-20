"""Inventory management utilities for cross-venue capital orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Mapping

from .liquidity import LiquidityLedger, LiquiditySnapshot
from .models import CapitalTransferPlan


class InventoryError(RuntimeError):
    """Raised when inventory state cannot be analysed or rebalanced."""


def _to_decimal(value: Decimal | int | str | float) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    raise TypeError(f"Unsupported numeric type {type(value)!r}")


@dataclass(slots=True, frozen=True)
class InventoryTarget:
    """Target weighting and buffers for a venue's inventory."""

    target_weight: Decimal
    min_base_buffer: Decimal = Decimal("0")
    min_quote_buffer: Decimal = Decimal("0")
    max_weight: Decimal | None = None

    def __post_init__(self) -> None:
        share = _to_decimal(self.target_weight)
        if share < Decimal("0"):
            raise ValueError("target_weight must be non-negative")
        object.__setattr__(self, "target_weight", share)
        base_buffer = _to_decimal(self.min_base_buffer)
        if base_buffer < Decimal("0"):
            raise ValueError("min_base_buffer must be non-negative")
        object.__setattr__(self, "min_base_buffer", base_buffer)
        quote_buffer = _to_decimal(self.min_quote_buffer)
        if quote_buffer < Decimal("0"):
            raise ValueError("min_quote_buffer must be non-negative")
        object.__setattr__(self, "min_quote_buffer", quote_buffer)
        if self.max_weight is not None:
            max_share = _to_decimal(self.max_weight)
            if max_share <= Decimal("0"):
                raise ValueError("max_weight must be positive when provided")
            object.__setattr__(self, "max_weight", max_share)


@dataclass(slots=True, frozen=True)
class VenueInventory:
    """Computed inventory statistics for a single venue."""

    exchange_id: str
    snapshot: LiquiditySnapshot
    target_weight: Decimal
    desired_base: Decimal
    surplus: Decimal
    deficit: Decimal


@dataclass(slots=True, frozen=True)
class InventorySnapshot:
    """Aggregated view of a symbol's inventory across venues."""

    symbol: str
    base_asset: str
    quote_asset: str
    total_base: Decimal
    total_quote: Decimal
    venues: tuple[VenueInventory, ...]

    def is_balanced(self, tolerance: Decimal, min_transfer: Decimal) -> bool:
        threshold = max(tolerance * self.total_base, min_transfer)
        for venue in self.venues:
            if venue.surplus > threshold or venue.deficit > threshold:
                return False
        return True


@dataclass(slots=True, frozen=True)
class RebalanceLeg:
    """Single transfer leg within a rebalance plan."""

    source_exchange: str
    target_exchange: str
    asset: str
    amount: Decimal
    unit_cost: Decimal


@dataclass(slots=True, frozen=True)
class RebalancePlan:
    """Recommended sequence of transfers to restore balance."""

    symbol: str
    asset: str
    transfers: tuple[RebalanceLeg, ...]
    estimated_cost: Decimal

    def to_transfer_plan(
        self,
        transfer_id: str,
        *,
        initiated_at: datetime | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> CapitalTransferPlan:
        if not self.transfers:
            raise InventoryError("Cannot materialise a transfer plan without legs")
        if initiated_at is None:
            initiated_at = datetime.now(timezone.utc)
        legs: Dict[tuple[str, str], Decimal] = {}
        for leg in self.transfers:
            legs[(leg.source_exchange, self.asset)] = (
                legs.get((leg.source_exchange, self.asset), Decimal("0")) + leg.amount
            )
            legs[(leg.target_exchange, self.asset)] = (
                legs.get((leg.target_exchange, self.asset), Decimal("0")) + leg.amount
            )
        meta: Dict[str, str] = {
            "symbol": self.symbol,
            "asset": self.asset,
            "estimated_cost": str(self.estimated_cost),
        }
        if metadata:
            meta.update(metadata)
        return CapitalTransferPlan(
            transfer_id=transfer_id,
            legs=legs,
            initiated_at=initiated_at,
            metadata=meta,
        )


class InventoryManager:
    """Orchestrates inventory monitoring and rebalance suggestions."""

    def __init__(
        self,
        ledger: LiquidityLedger,
        pair_config: Mapping[str, tuple[str, str]],
        *,
        rebalance_tolerance: Decimal = Decimal("0.02"),
        min_transfer: Decimal = Decimal("0"),
        transfer_costs: Mapping[tuple[str, str], Decimal] | None = None,
    ) -> None:
        if rebalance_tolerance < Decimal("0"):
            raise ValueError("rebalance_tolerance must be non-negative")
        if min_transfer < Decimal("0"):
            raise ValueError("min_transfer must be non-negative")
        self._ledger = ledger
        self._pair_config = dict(pair_config)
        self._tolerance = rebalance_tolerance
        self._min_transfer = min_transfer
        self._transfer_costs: Dict[tuple[str, str], Decimal] = {}
        if transfer_costs:
            for key, cost in transfer_costs.items():
                self._transfer_costs[key] = _to_decimal(cost)

    def snapshot(
        self,
        symbol: str,
        targets: Mapping[str, InventoryTarget],
    ) -> InventorySnapshot:
        if symbol not in self._pair_config:
            raise InventoryError(f"Unknown symbol {symbol}")
        base_asset, quote_asset = self._pair_config[symbol]
        if not targets:
            raise InventoryError("At least one target must be specified")
        weights = self._normalise_weights(targets)
        venues: list[VenueInventory] = []
        total_base = Decimal("0")
        total_quote = Decimal("0")
        for exchange_id, target in targets.items():
            snapshot = self._ledger.get_snapshot(exchange_id, symbol)
            if snapshot is None:
                raise InventoryError(
                    f"No liquidity snapshot available for {exchange_id}:{symbol}"
                )
            weight = weights[exchange_id]
            base_available = snapshot.base_available
            quote_available = snapshot.quote_available
            total_base += base_available
            total_quote += quote_available
            desired_base = Decimal("0")
            surplus = Decimal("0")
            deficit = Decimal("0")
            venue = VenueInventory(
                exchange_id=exchange_id,
                snapshot=snapshot,
                target_weight=weight,
                desired_base=desired_base,
                surplus=surplus,
                deficit=deficit,
            )
            venues.append(venue)

        venues_with_targets = self._compute_targets(
            venues, targets, weights, total_base
        )
        return InventorySnapshot(
            symbol=symbol,
            base_asset=base_asset,
            quote_asset=quote_asset,
            total_base=total_base,
            total_quote=total_quote,
            venues=tuple(venues_with_targets),
        )

    def propose_rebalance(
        self,
        symbol: str,
        targets: Mapping[str, InventoryTarget],
    ) -> tuple[InventorySnapshot, RebalancePlan | None]:
        snapshot = self.snapshot(symbol, targets)
        if snapshot.total_base <= Decimal("0"):
            return snapshot, None
        threshold = max(self._tolerance * snapshot.total_base, self._min_transfer)
        if snapshot.is_balanced(self._tolerance, self._min_transfer):
            return snapshot, None
        surplus_map: Dict[str, Decimal] = {}
        deficit_map: Dict[str, Decimal] = {}
        for venue in snapshot.venues:
            if venue.surplus > threshold:
                surplus_map[venue.exchange_id] = venue.surplus
            if venue.deficit > threshold:
                deficit_map[venue.exchange_id] = venue.deficit
        if not surplus_map or not deficit_map:
            return snapshot, None

        transfers = self._allocate_transfers(
            snapshot.base_asset,
            surplus_map,
            deficit_map,
            threshold,
        )
        if not transfers:
            return snapshot, None
        estimated_cost = sum(
            (leg.amount * leg.unit_cost for leg in transfers), Decimal("0")
        )
        plan = RebalancePlan(
            symbol=symbol,
            asset=snapshot.base_asset,
            transfers=tuple(transfers),
            estimated_cost=estimated_cost,
        )
        return snapshot, plan

    def _normalise_weights(
        self, targets: Mapping[str, InventoryTarget]
    ) -> Dict[str, Decimal]:
        weights: Dict[str, Decimal] = {}
        total = Decimal("0")
        for exchange_id, target in targets.items():
            weight = target.target_weight
            total += weight
            weights[exchange_id] = weight
        if total <= Decimal("0"):
            raise InventoryError("Target weights must sum to a positive value")
        for exchange_id, value in list(weights.items()):
            weights[exchange_id] = value / total
        return weights

    def _compute_targets(
        self,
        venues: list[VenueInventory],
        targets: Mapping[str, InventoryTarget],
        weights: Mapping[str, Decimal],
        total_base: Decimal,
    ) -> list[VenueInventory]:
        if total_base <= Decimal("0"):
            return venues
        updated: list[VenueInventory] = []
        for venue in venues:
            target = targets[venue.exchange_id]
            normalised_weight = weights[venue.exchange_id]
            desired = total_base * normalised_weight
            min_base = target.min_base_buffer
            max_cap = target.max_weight
            if max_cap is not None:
                cap_amount = total_base * max_cap
                if desired > cap_amount:
                    desired = cap_amount
            available = venue.snapshot.base_available
            surplus = Decimal("0")
            deficit = Decimal("0")
            if available > desired:
                transferable = max(available - desired, Decimal("0"))
                spare_after_buffer = max(available - min_base, Decimal("0"))
                surplus = min(transferable, spare_after_buffer)
                if venue.snapshot.quote_available < target.min_quote_buffer:
                    surplus = Decimal("0")
            else:
                target_amount = max(desired, min_base)
                if available < target_amount:
                    deficit = target_amount - available
            updated.append(
                VenueInventory(
                    exchange_id=venue.exchange_id,
                    snapshot=venue.snapshot,
                    target_weight=normalised_weight,
                    desired_base=desired,
                    surplus=surplus,
                    deficit=deficit,
                )
            )
        return updated

    def _allocate_transfers(
        self,
        asset: str,
        surplus_map: Dict[str, Decimal],
        deficit_map: Dict[str, Decimal],
        threshold: Decimal,
    ) -> list[RebalanceLeg]:
        transfers: list[RebalanceLeg] = []
        while surplus_map and deficit_map:
            best_pair = None
            best_cost = None
            for source, surplus in surplus_map.items():
                for target, deficit in deficit_map.items():
                    if source == target:
                        continue
                    amount = min(surplus, deficit)
                    if amount <= threshold:
                        continue
                    cost = self._transfer_costs.get((source, target), Decimal("0"))
                    if best_cost is None or cost < best_cost:
                        best_cost = cost
                        best_pair = (source, target, amount)
            if best_pair is None:
                break
            source, target, amount = best_pair
            transfers.append(
                RebalanceLeg(
                    source_exchange=source,
                    target_exchange=target,
                    asset=asset,
                    amount=amount,
                    unit_cost=best_cost or Decimal("0"),
                )
            )
            surplus_map[source] -= amount
            deficit_map[target] -= amount
            if surplus_map[source] <= threshold:
                surplus_map.pop(source)
            if deficit_map[target] <= threshold:
                deficit_map.pop(target)
        return transfers
