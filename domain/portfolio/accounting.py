"""Portfolio accounting primitives for multi-asset trading."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping, MutableMapping

from domain.orders import OrderSide

DecimalInput = Decimal | float | int | str


def _to_decimal(value: DecimalInput) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass(slots=True, frozen=True)
class CorporateActionRecord:
    """Immutable record of a corporate action affecting a symbol."""

    symbol: str
    action_type: str
    timestamp: datetime
    details: Mapping[str, Any]

    def __post_init__(self) -> None:  # pragma: no cover - trivial
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


@dataclass(slots=True, frozen=True)
class PositionSnapshot:
    """Snapshot of a single position expressed in both local and base currency."""

    symbol: str
    quantity: Decimal
    average_price: Decimal
    market_price: Decimal
    currency: str
    market_value: Decimal
    market_value_base: Decimal
    unrealized_pnl_base: Decimal
    realized_pnl_base: Decimal


@dataclass(slots=True, frozen=True)
class CurrencyExposureSnapshot:
    """Aggregate currency exposure across cash and positions."""

    currency: str
    cash: Decimal
    positions: Decimal
    net: Decimal
    cash_base: Decimal
    positions_base: Decimal
    net_base: Decimal


@dataclass(slots=True, frozen=True)
class PortfolioSnapshot:
    """Point-in-time view of the portfolio accounting state."""

    base_currency: str
    timestamp: datetime
    total_equity: Decimal
    cash_value_base: Decimal
    net_exposure_base: Decimal
    gross_exposure_base: Decimal
    realized_pnl_base: Decimal
    unrealized_pnl_base: Decimal
    fees_paid_base: Decimal
    cash_balances: Mapping[str, Decimal]
    fees_paid: Mapping[str, Decimal]
    positions: tuple[PositionSnapshot, ...]
    currency_exposures: tuple[CurrencyExposureSnapshot, ...]
    corporate_actions: tuple[CorporateActionRecord, ...]

    def __post_init__(self) -> None:  # pragma: no cover - defensive
        object.__setattr__(
            self, "cash_balances", MappingProxyType(dict(self.cash_balances))
        )
        object.__setattr__(self, "fees_paid", MappingProxyType(dict(self.fees_paid)))


class FXRates:
    """Utility converting monetary amounts between currencies via a base."""

    __slots__ = ("base_currency", "_base_rates")

    def __init__(
        self, base_currency: str, rates: Mapping[str, DecimalInput] | None = None
    ) -> None:
        self.base_currency = base_currency.upper()
        self._base_rates: MutableMapping[str, Decimal] = {
            self.base_currency: Decimal("1")
        }
        if rates:
            for currency, rate in rates.items():
                self.set_rate(currency, rate)

    def set_rate(self, currency: str, rate: DecimalInput) -> None:
        currency = currency.upper()
        if currency == self.base_currency:
            self._base_rates[self.base_currency] = Decimal("1")
            return
        decimal_rate = _to_decimal(rate)
        if decimal_rate <= 0:
            raise ValueError("FX rates must be positive")
        self._base_rates[currency] = decimal_rate

    def get_rate(self, currency: str) -> Decimal:
        currency = currency.upper()
        try:
            return self._base_rates[currency]
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise ValueError(f"Missing FX rate for {currency}") from exc

    def convert(
        self, amount: DecimalInput, from_currency: str, to_currency: str
    ) -> Decimal:
        decimal_amount = _to_decimal(amount)
        source = from_currency.upper()
        target = to_currency.upper()
        if source == target:
            return decimal_amount
        if target == self.base_currency:
            return decimal_amount * self.get_rate(source)
        if source == self.base_currency:
            return decimal_amount / self.get_rate(target)
        base_amount = decimal_amount * self.get_rate(source)
        return base_amount / self.get_rate(target)


@dataclass(slots=True)
class _PositionState:
    symbol: str
    currency: str
    quantity: Decimal = Decimal("0")
    average_price: Decimal = Decimal("0")
    market_price: Decimal = Decimal("0")
    unrealized_pnl_base: Decimal = Decimal("0")
    realized_pnl_base: Decimal = Decimal("0")


@dataclass(slots=True)
class _CurrencyExposureState:
    currency: str
    cash: Decimal = Decimal("0")
    positions: Decimal = Decimal("0")
    cash_base: Decimal = Decimal("0")
    positions_base: Decimal = Decimal("0")

    def to_snapshot(self) -> CurrencyExposureSnapshot:
        net = self.cash + self.positions
        net_base = self.cash_base + self.positions_base
        return CurrencyExposureSnapshot(
            currency=self.currency,
            cash=self.cash,
            positions=self.positions,
            net=net,
            cash_base=self.cash_base,
            positions_base=self.positions_base,
            net_base=net_base,
        )


class PortfolioAccounting:
    """Manage multi-currency positions, PnL, fees, and corporate actions."""

    __slots__ = (
        "base_currency",
        "fx_rates",
        "_positions",
        "_cash",
        "_fees",
        "_corporate_actions",
        "_realized_pnl_base",
        "_fees_paid_base",
    )

    def __init__(self, base_currency: str, fx_rates: FXRates | None = None) -> None:
        self.base_currency = base_currency.upper()
        self.fx_rates = fx_rates or FXRates(self.base_currency)
        if self.fx_rates.base_currency != self.base_currency:
            raise ValueError("FXRates base currency must match portfolio base currency")
        self._positions: dict[str, _PositionState] = {}
        self._cash: MutableMapping[str, Decimal] = {}
        self._fees: MutableMapping[str, Decimal] = {}
        self._corporate_actions: list[CorporateActionRecord] = []
        self._realized_pnl_base = Decimal("0")
        self._fees_paid_base = Decimal("0")

    def update_fx_rate(self, currency: str, rate: DecimalInput) -> None:
        """Update the FX rate and refresh unrealised PnL for affected positions."""

        self.fx_rates.set_rate(currency, rate)
        currency = currency.upper()
        for position in self._positions.values():
            if position.currency == currency:
                self._refresh_unrealized(position)

    def apply_fill(
        self,
        *,
        symbol: str,
        side: OrderSide | str,
        quantity: DecimalInput,
        price: DecimalInput,
        currency: str,
        fee: DecimalInput = Decimal("0"),
        fee_currency: str | None = None,
        fx_rate: DecimalInput | None = None,
    ) -> None:
        """Apply a trade fill to the portfolio."""

        side = OrderSide(side)
        qty = _to_decimal(quantity)
        fill_price = _to_decimal(price)
        if qty <= 0:
            raise ValueError("quantity must be positive")
        if fill_price <= 0:
            raise ValueError("price must be positive")
        currency = currency.upper()
        if fx_rate is not None:
            self.update_fx_rate(currency, fx_rate)
        else:
            if currency != self.base_currency:
                # ensure we have a conversion rate available
                self.fx_rates.get_rate(currency)
        position = self._ensure_position(symbol, currency)
        signed_qty = qty if side is OrderSide.BUY else -qty
        previous_qty = position.quantity
        if (
            previous_qty == 0
            or (previous_qty > 0 and signed_qty > 0)
            or (previous_qty < 0 and signed_qty < 0)
        ):
            total_abs = abs(previous_qty) + qty
            if total_abs == 0:
                position.average_price = fill_price
            else:
                position.average_price = (
                    (position.average_price * abs(previous_qty) + fill_price * qty)
                    / total_abs
                    if abs(previous_qty) > 0
                    else fill_price
                )
            position.quantity = previous_qty + signed_qty
        else:
            closing_qty = min(abs(previous_qty), qty)
            direction = Decimal("1") if previous_qty > 0 else Decimal("-1")
            realized_local = (
                closing_qty * (fill_price - position.average_price) * direction
            )
            realized_base = self.fx_rates.convert(
                realized_local, currency, self.base_currency
            )
            position.realized_pnl_base += realized_base
            self._realized_pnl_base += realized_base
            net_qty = previous_qty + signed_qty
            position.quantity = net_qty
            if net_qty == 0:
                position.average_price = Decimal("0")
                position.market_price = Decimal("0")
                position.unrealized_pnl_base = Decimal("0")
            elif abs(net_qty) < abs(previous_qty):
                # Partial reduction retains prior average cost.
                pass
            else:
                residual = qty - closing_qty
                if residual > 0:
                    position.average_price = fill_price
        trade_value = fill_price * qty
        cash_delta = -trade_value if side is OrderSide.BUY else trade_value
        self._adjust_cash(currency, cash_delta)
        fee_currency = currency if fee_currency is None else fee_currency.upper()
        fee_amount = _to_decimal(fee)
        if fee_amount < 0:
            raise ValueError("fee must be non-negative")
        if fee_amount:
            if fee_currency != self.base_currency:
                if fx_rate is not None and fee_currency == currency:
                    # rate already refreshed above
                    pass
                elif fee_currency != self.base_currency:
                    self.fx_rates.get_rate(fee_currency)
            self._record_fee(fee_currency, fee_amount, position)
        position.market_price = fill_price
        self._refresh_unrealized(position)
        self._prune_position_if_flat(position)

    def mark_to_market(
        self, symbol: str, price: DecimalInput, currency: str | None = None
    ) -> None:
        """Refresh the market price and unrealised PnL for a position."""

        position = self._positions.get(symbol)
        if position is None:
            raise KeyError(f"unknown position {symbol}")
        market_price = _to_decimal(price)
        if market_price <= 0:
            raise ValueError("price must be positive")
        if currency is not None and currency.upper() != position.currency:
            raise ValueError("currency mismatch for mark-to-market")
        position.market_price = market_price
        self._refresh_unrealized(position)

    def record_dividend(
        self,
        *,
        symbol: str,
        amount: DecimalInput,
        currency: str,
        timestamp: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Record a dividend cash flow and update realised PnL."""

        amount_decimal = _to_decimal(amount)
        if amount_decimal <= 0:
            raise ValueError("dividend amount must be positive")
        currency = currency.upper()
        if currency != self.base_currency:
            self.fx_rates.get_rate(currency)
        self._adjust_cash(currency, amount_decimal)
        base_amount = self.fx_rates.convert(
            amount_decimal, currency, self.base_currency
        )
        self._realized_pnl_base += base_amount
        position = self._positions.get(symbol)
        if position is not None:
            position.realized_pnl_base += base_amount
        record = self._build_action_record(
            symbol,
            "dividend",
            timestamp,
            {
                "amount": amount_decimal,
                "currency": currency,
                **(dict(metadata) if metadata else {}),
            },
        )
        self._corporate_actions.append(record)

    def apply_split(
        self,
        *,
        symbol: str,
        ratio: DecimalInput,
        timestamp: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Apply a stock split adjusting quantity and average price."""

        position = self._positions.get(symbol)
        if position is None:
            raise KeyError(f"unknown position {symbol}")
        split_ratio = _to_decimal(ratio)
        if split_ratio <= 0:
            raise ValueError("split ratio must be positive")
        position.quantity *= split_ratio
        if position.average_price != 0:
            position.average_price /= split_ratio
        if position.market_price != 0:
            position.market_price /= split_ratio
        self._refresh_unrealized(position)
        record = self._build_action_record(
            symbol,
            "split",
            timestamp,
            {
                "ratio": split_ratio,
                **(dict(metadata) if metadata else {}),
            },
        )
        self._corporate_actions.append(record)

    def record_custom_action(
        self,
        *,
        symbol: str,
        action_type: str,
        details: Mapping[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Persist an arbitrary corporate action for downstream consumers."""

        record = self._build_action_record(
            symbol,
            action_type,
            timestamp,
            dict(details) if details else {},
        )
        self._corporate_actions.append(record)

    def snapshot(self, *, timestamp: datetime | None = None) -> PortfolioSnapshot:
        """Return an immutable snapshot suitable for risk reporting."""

        ts = timestamp or datetime.now(timezone.utc)
        position_snapshots: list[PositionSnapshot] = []
        exposures: dict[str, _CurrencyExposureState] = {}
        gross_exposure = Decimal("0")
        net_exposure = Decimal("0")
        unrealized_total = Decimal("0")
        for state in sorted(self._positions.values(), key=lambda p: p.symbol):
            market_value_local = state.quantity * state.market_price
            market_value_base = self.fx_rates.convert(
                market_value_local, state.currency, self.base_currency
            )
            position_snapshots.append(
                PositionSnapshot(
                    symbol=state.symbol,
                    quantity=state.quantity,
                    average_price=state.average_price,
                    market_price=state.market_price,
                    currency=state.currency,
                    market_value=market_value_local,
                    market_value_base=market_value_base,
                    unrealized_pnl_base=state.unrealized_pnl_base,
                    realized_pnl_base=state.realized_pnl_base,
                )
            )
            unrealized_total += state.unrealized_pnl_base
            gross_exposure += abs(market_value_base)
            net_exposure += market_value_base
            exposure_state = exposures.setdefault(
                state.currency, _CurrencyExposureState(currency=state.currency)
            )
            exposure_state.positions += market_value_local
            exposure_state.positions_base += market_value_base
        cash_value_base = Decimal("0")
        for currency, balance in self._cash.items():
            exposure_state = exposures.setdefault(
                currency, _CurrencyExposureState(currency=currency)
            )
            exposure_state.cash += balance
            cash_base = self.fx_rates.convert(balance, currency, self.base_currency)
            exposure_state.cash_base += cash_base
            cash_value_base += cash_base
        exposure_snapshots = tuple(
            exposures[currency].to_snapshot() for currency in sorted(exposures)
        )
        total_equity = cash_value_base + net_exposure
        return PortfolioSnapshot(
            base_currency=self.base_currency,
            timestamp=ts,
            total_equity=total_equity,
            cash_value_base=cash_value_base,
            net_exposure_base=net_exposure,
            gross_exposure_base=gross_exposure,
            realized_pnl_base=self._realized_pnl_base,
            unrealized_pnl_base=unrealized_total,
            fees_paid_base=self._fees_paid_base,
            cash_balances=dict(self._cash),
            fees_paid=dict(self._fees),
            positions=tuple(position_snapshots),
            currency_exposures=exposure_snapshots,
            corporate_actions=tuple(self._corporate_actions),
        )

    def _ensure_position(self, symbol: str, currency: str) -> _PositionState:
        position = self._positions.get(symbol)
        if position is None:
            position = _PositionState(symbol=symbol, currency=currency)
            self._positions[symbol] = position
        elif position.currency != currency:
            raise ValueError("currency mismatch for existing position")
        return position

    def _adjust_cash(self, currency: str, delta: Decimal) -> None:
        currency = currency.upper()
        self._cash[currency] = self._cash.get(currency, Decimal("0")) + delta

    def _record_fee(
        self, currency: str, amount: Decimal, position: _PositionState | None
    ) -> None:
        self._adjust_cash(currency, -amount)
        self._fees[currency] = self._fees.get(currency, Decimal("0")) + amount
        fee_base = self.fx_rates.convert(amount, currency, self.base_currency)
        self._fees_paid_base += fee_base
        self._realized_pnl_base -= fee_base
        if position is not None:
            position.realized_pnl_base -= fee_base

    def _refresh_unrealized(self, position: _PositionState) -> None:
        if position.quantity == 0 or position.market_price == 0:
            position.unrealized_pnl_base = Decimal("0")
            return
        direction = Decimal("1") if position.quantity > 0 else Decimal("-1")
        raw = (
            direction
            * abs(position.quantity)
            * (position.market_price - position.average_price)
        )
        position.unrealized_pnl_base = self.fx_rates.convert(
            raw, position.currency, self.base_currency
        )

    def _prune_position_if_flat(self, position: _PositionState) -> None:
        if position.quantity != 0:
            return
        if position.realized_pnl_base != 0:
            return
        if position.unrealized_pnl_base != 0:
            return
        self._positions.pop(position.symbol, None)

    def _build_action_record(
        self,
        symbol: str,
        action_type: str,
        timestamp: datetime | None,
        details: Mapping[str, Any],
    ) -> CorporateActionRecord:
        ts = timestamp or datetime.now(timezone.utc)
        return CorporateActionRecord(
            symbol=symbol,
            action_type=action_type,
            timestamp=ts,
            details=dict(details),
        )


__all__ = [
    "CorporateActionRecord",
    "CurrencyExposureSnapshot",
    "FXRates",
    "PortfolioAccounting",
    "PortfolioSnapshot",
    "PositionSnapshot",
]
