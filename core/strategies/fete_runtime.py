# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Operational pipeline utilities for running the FETE strategy.

This module adapts the user-provided production trading scaffold to the
GeoSync codebase.  It plugs the existing :class:`~core.strategies.fete.FETE`
engine into a lightweight execution simulator with guardrails that mirror what
the CLI exposes.  The design goals are

* keep the components testable and dependency-light so the research toolchain
  can exercise them deterministically;
* integrate with existing domain aggregates (``domain.order``/``domain.position``);
* provide structured artefacts that higher layers – e.g. the CLI or notebooks –
  can consume without having to understand simulator internals.

The module intentionally focuses on realistic-yet-portable mechanics rather than
full exchange parity.  For instance, fills are immediate and assume a single
symbol, but we track cash, realised PnL, slippage and transaction costs the same
way the production execution adapters do.  Risk controls are modelled after the
user snippet, exposing position limits, stop-losses and drawdown based circuit
breakers.  The implementation favours clarity and defensive programming so the
behaviour is predictable during research and governance reviews.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import AsyncContextManager, Callable, Mapping, MutableSequence, Sequence

import numpy as np
import pandas as pd

from core.strategies.fete import FETE
from domain.order import OrderSide
from domain.position import Position

# ---------------------------------------------------------------------------
# Data acquisition helpers
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class HistoricalCandle:
    """Normalized OHLCV candle representation."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class YahooFinanceDataFetcher:
    """Download historical candles via ``yfinance`` if available.

    The fetcher accepts a dependency-injected downloader so unit tests can stub
    the behaviour without requiring the optional dependency.
    """

    def __init__(
        self,
        downloader: Callable[..., pd.DataFrame] | None = None,
    ) -> None:
        self._downloader = downloader

    def fetch(
        self,
        symbol: str,
        *,
        start: datetime,
        end: datetime,
    ) -> list[HistoricalCandle]:
        if not symbol:
            raise ValueError("symbol must be provided")
        if start >= end:
            raise ValueError("start must be earlier than end")

        downloader = self._downloader
        if downloader is None:
            try:
                import yfinance as yf
            except ImportError as exc:  # pragma: no cover - exercised in tests via stub
                raise RuntimeError(
                    "yfinance must be installed to use the default downloader"
                ) from exc
            downloader = yf.download

        frame = downloader(symbol, start=start, end=end, progress=False)
        if frame.empty:
            return []
        candles: list[HistoricalCandle] = []
        for ts, row in frame.iterrows():
            candles.append(
                HistoricalCandle(
                    timestamp=pd.Timestamp(ts).to_pydatetime(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume", 0.0)),
                )
            )
        return candles


class BinanceRESTFetcher:
    """Fetch recent klines from the Binance REST API.

    Parameters
    ----------
    session_factory:
        Optional callable returning an asynchronous context manager compatible
        with :class:`aiohttp.ClientSession`.  Supplying a custom factory allows
        unit tests to bypass the network.
    base_url:
        REST endpoint, overridable for testnet usage.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncContextManager[object]] | None = None,
        base_url: str = "https://api.binance.com/api/v3",
    ) -> None:
        self._session_factory = session_factory
        self._base_url = base_url.rstrip("/")

    async def fetch(
        self,
        symbol: str,
        *,
        interval: str = "1h",
        limit: int = 100,
    ) -> list[HistoricalCandle]:
        if not symbol:
            raise ValueError("symbol must be provided")
        if limit <= 0 or limit > 1000:
            raise ValueError("limit must be in (0, 1000]")

        factory = self._session_factory
        if factory is None:  # pragma: no cover - exercised via dependency injection in tests
            try:
                import aiohttp
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("aiohttp must be installed to use the default session") from exc

            def _factory() -> AsyncContextManager[aiohttp.ClientSession]:
                return aiohttp.ClientSession()

            factory = _factory

        session_ctx = factory()
        async with session_ctx as session:
            get = getattr(session, "get")
            async with get(
                f"{self._base_url}/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit},
            ) as resp:
                status = getattr(resp, "status", None)
                if status != 200:
                    raise RuntimeError(f"Binance API error: {status}")
                data = await resp.json()

        candles: list[HistoricalCandle] = []
        for candle in data:
            candles.append(
                HistoricalCandle(
                    timestamp=datetime.fromtimestamp(int(candle[0]) / 1000.0),
                    open=float(candle[1]),
                    high=float(candle[2]),
                    low=float(candle[3]),
                    close=float(candle[4]),
                    volume=float(candle[7]),
                )
            )
        return candles


# ---------------------------------------------------------------------------
# Execution simulator
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class ExecutedTrade:
    """Immutable record of a simulated fill."""

    symbol: str
    side: OrderSide
    quantity: float
    price: float
    timestamp: datetime
    realized_pnl: float
    cash_after: float

    def to_dict(self) -> dict[str, object]:  # pragma: no cover - convenience wrapper
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "timestamp": self.timestamp.isoformat(),
            "realized_pnl": self.realized_pnl,
            "cash_after": self.cash_after,
        }


@dataclass(slots=True)
class PaperTradingAccount:
    """Single-asset paper account with deterministic fills."""

    initial_cash: float = 10_000.0
    transaction_cost: float = 0.0002
    slippage: float = 0.0005
    cash: float = field(init=False)
    positions: dict[str, Position] = field(init=False, default_factory=dict)
    trades: MutableSequence[ExecutedTrade] = field(init=False, default_factory=list)
    equity_history: MutableSequence[tuple[datetime, float]] = field(
        init=False, default_factory=list
    )

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.transaction_cost < 0:
            raise ValueError("transaction_cost must be non-negative")
        if self.slippage < 0:
            raise ValueError("slippage must be non-negative")
        self.cash = float(self.initial_cash)

    def reset(self) -> None:
        """Clear state so the account can be reused across scenarios."""

        self.cash = float(self.initial_cash)
        self.positions.clear()
        self.trades.clear()
        self.equity_history.clear()

    # ------------------------------------------------------------------ utils

    def _position(self, symbol: str) -> Position:
        position = self.positions.get(symbol)
        if position is None:
            position = Position(symbol=symbol)
            self.positions[symbol] = position
        return position

    def _execute(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        timestamp: datetime,
    ) -> ExecutedTrade | None:
        if quantity <= 0:
            return None
        if price <= 0:
            raise ValueError("price must be positive")

        fill_price = (
            price * (1.0 + self.slippage)
            if side is OrderSide.BUY
            else price * (1.0 - self.slippage)
        )
        transaction_multiplier = (
            1.0 + self.transaction_cost if side is OrderSide.BUY else 1.0 - self.transaction_cost
        )

        notional = quantity * fill_price
        if side is OrderSide.BUY:
            total_cost = notional * transaction_multiplier
            if total_cost > self.cash + 1e-9:
                quantity = (self.cash / transaction_multiplier) / fill_price
                if quantity <= 1e-9:
                    return None
                notional = quantity * fill_price
                total_cost = notional * transaction_multiplier
            self.cash -= total_cost
        else:
            proceeds = notional * transaction_multiplier
            self.cash += proceeds

        position = self._position(symbol)
        realized_before = position.realized_pnl
        position.apply_fill(side, quantity, fill_price)
        realized_delta = position.realized_pnl - realized_before

        trade = ExecutedTrade(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=fill_price,
            timestamp=timestamp,
            realized_pnl=realized_delta,
            cash_after=self.cash,
        )
        self.trades.append(trade)
        return trade

    def rebalance_to_fraction(
        self,
        symbol: str,
        target_fraction: float,
        *,
        reference_price: float,
        equity: float,
        timestamp: datetime,
    ) -> ExecutedTrade | None:
        if equity <= 0:
            return None
        if reference_price <= 0:
            raise ValueError("reference_price must be positive")
        position = self._position(symbol)
        current_qty = position.quantity
        target_value = target_fraction * equity
        target_qty = target_value / reference_price
        delta = target_qty - current_qty
        if abs(delta) < 1e-9:
            return None
        side = OrderSide.BUY if delta > 0 else OrderSide.SELL
        return self._execute(symbol, side, abs(delta), reference_price, timestamp)

    def equity(
        self,
        price_map: Mapping[str, float],
        *,
        timestamp: datetime | None = None,
        record: bool = True,
    ) -> float:
        total = float(self.cash)
        for symbol, position in self.positions.items():
            price = price_map.get(symbol, position.current_price)
            if price is None or price <= 0:
                continue
            position.mark_to_market(price)
            total += position.quantity * price
        if record and timestamp is not None:
            self.equity_history.append((timestamp, total))
        return total

    def portfolio_snapshot(self, price_map: Mapping[str, float]) -> dict[str, object]:
        equity = self.equity(price_map, record=False)
        return {
            "cash": self.cash,
            "equity": equity,
            "positions": [position.to_dict() for position in self.positions.values()],
            "num_positions": len(self.positions),
            "num_trades": len(self.trades),
        }


# ---------------------------------------------------------------------------
# Risk controls
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class RiskEvent:
    """Risk management incident captured during a backtest."""

    timestamp: datetime
    code: str
    message: str


@dataclass(slots=True)
class RiskGuard:
    """Risk controls inspired by the user-provided production system."""

    max_position_fraction: float = 0.1
    max_daily_loss: float = 0.05
    max_drawdown: float = 0.2
    stop_loss_pct: float = 0.05
    start_equity: float = field(init=False, default=1.0)
    peak_equity: float = field(init=False, default=1.0)
    current_drawdown: float = field(init=False, default=0.0)
    max_observed_drawdown: float = field(init=False, default=0.0)
    circuit_breaker_active: bool = field(init=False, default=False)
    circuit_reason: str | None = field(init=False, default=None)
    events: MutableSequence[RiskEvent] = field(init=False, default_factory=list)

    def reset(self, equity: float, *, timestamp: datetime | None = None) -> None:
        if equity <= 0:
            raise ValueError("equity must be positive when resetting risk guard")
        self.start_equity = float(equity)
        self.peak_equity = float(equity)
        self.current_drawdown = 0.0
        self.max_observed_drawdown = 0.0
        self.circuit_breaker_active = False
        self.circuit_reason = None
        self.events.clear()
        if timestamp is not None:
            self.events.append(RiskEvent(timestamp, "reset", "Risk guard reset"))

    def _record_event(self, timestamp: datetime, code: str, message: str) -> None:
        self.events.append(RiskEvent(timestamp, code, message))

    def _trigger_circuit(self, timestamp: datetime, message: str) -> None:
        if not self.circuit_breaker_active:
            self.circuit_breaker_active = True
            self.circuit_reason = message
            self._record_event(timestamp, "circuit", message)

    def check_equity(self, equity: float, *, timestamp: datetime) -> tuple[bool, str | None]:
        if equity <= 0:
            self._trigger_circuit(timestamp, "Equity dropped to non-positive value")
            return False, "equity_non_positive"

        if equity > self.peak_equity:
            self.peak_equity = float(equity)

        drawdown = 0.0 if self.peak_equity <= 0 else (self.peak_equity - equity) / self.peak_equity
        self.current_drawdown = float(max(drawdown, 0.0))
        self.max_observed_drawdown = max(self.max_observed_drawdown, self.current_drawdown)

        daily_loss = (self.start_equity - equity) / self.start_equity
        if daily_loss > self.max_daily_loss:
            self._trigger_circuit(
                timestamp,
                f"Daily loss {daily_loss:.2%} exceeded threshold {self.max_daily_loss:.2%}",
            )
            return False, "daily_loss"

        if self.current_drawdown > self.max_drawdown:
            self._trigger_circuit(
                timestamp,
                f"Drawdown {self.current_drawdown:.2%} exceeded threshold {self.max_drawdown:.2%}",
            )
            return False, "drawdown"

        return True, None

    def check_position_size(
        self, value: float, equity: float, *, timestamp: datetime
    ) -> tuple[bool, str | None]:
        limit = equity * self.max_position_fraction
        if value > limit + 1e-9:
            self._record_event(
                timestamp,
                "position_limit",
                f"Position value {value:.2f} exceeds limit {limit:.2f}",
            )
            return False, "position_limit"
        return True, None

    def stop_loss_triggered(
        self, position: Position | None, price: float, *, timestamp: datetime
    ) -> bool:
        if position is None or position.quantity == 0:
            return False
        if position.entry_price <= 0:
            return False
        if position.quantity > 0:
            threshold = position.entry_price * (1.0 - self.stop_loss_pct)
            triggered = price <= threshold
        else:
            threshold = position.entry_price * (1.0 + self.stop_loss_pct)
            triggered = price >= threshold
        if triggered:
            direction = "long" if position.quantity > 0 else "short"
            self._record_event(
                timestamp,
                "stop_loss",
                f"Stop loss breached for {direction} position at {price:.4f}",
            )
        return triggered


# ---------------------------------------------------------------------------
# Backtest engine
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BacktestReport:
    """Summary of a FETE paper-trading run."""

    symbol: str
    start: datetime
    end: datetime
    start_equity: float
    final_equity: float
    total_return: float
    annual_return: float
    volatility: float
    sharpe: float
    max_drawdown: float
    num_trades: int
    win_trades: int
    win_rate: float
    profit_factor: float
    audit: dict[str, object]
    equity_curve: list[tuple[datetime, float]]
    trades: list[ExecutedTrade]
    risk_events: list[RiskEvent]
    portfolio: dict[str, object]

    def to_dict(
        self,
    ) -> dict[str, object]:  # pragma: no cover - convenience for callers
        return {
            "symbol": self.symbol,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "start_equity": self.start_equity,
            "final_equity": self.final_equity,
            "total_return": self.total_return,
            "annual_return": self.annual_return,
            "volatility": self.volatility,
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown,
            "num_trades": self.num_trades,
            "win_trades": self.win_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "audit": self.audit,
            "equity_curve": [(ts.isoformat(), value) for ts, value in self.equity_curve],
            "trades": [trade.to_dict() for trade in self.trades],
            "risk_events": [event.__dict__ for event in self.risk_events],
            "portfolio": self.portfolio,
        }


class FETEBacktestEngine:
    """Run the FETE strategy through the :class:`PaperTradingAccount` simulator."""

    def __init__(
        self,
        fete: FETE,
        account: PaperTradingAccount,
        risk_guard: RiskGuard,
    ) -> None:
        self._fete = fete
        self._account = account
        self._risk = risk_guard

    def run(
        self,
        prices: Sequence[float],
        probs: Sequence[float],
        *,
        symbol: str,
        timestamps: Sequence[datetime] | None = None,
    ) -> BacktestReport:
        price_array = np.asarray(prices, dtype=float)
        prob_array = np.asarray(probs, dtype=float)
        if price_array.ndim != 1:
            raise ValueError("prices must be a 1-D sequence")
        if prob_array.ndim != 1:
            raise ValueError("probs must be a 1-D sequence")
        if price_array.size == 0:
            raise ValueError("prices must contain at least one element")
        if prob_array.size != price_array.size:
            raise ValueError("prices and probs must have the same length")
        if np.any(price_array <= 0):
            raise ValueError("prices must be strictly positive")

        if timestamps is None:
            timestamps = [
                datetime.now() - timedelta(minutes=price_array.size - idx)
                for idx in range(price_array.size)
            ]
        elif len(timestamps) != price_array.size:
            raise ValueError("timestamps length must match prices")

        self._account.reset()
        initial_equity = self._account.equity(
            {symbol: float(price_array[0])}, timestamp=timestamps[0], record=False
        )
        self._risk.reset(initial_equity, timestamp=timestamps[0])

        returns = np.zeros_like(price_array)
        returns[1:] = np.diff(price_array) / price_array[:-1]

        diagnostics: list[dict[str, float]] = []

        for idx, price in enumerate(price_array):
            ts = timestamps[idx]
            equity_before = self._account.equity({symbol: float(price)}, timestamp=ts, record=False)

            realized_return = float(returns[idx]) if idx > 0 else None
            position_fraction, diag = self._fete.decide(
                prob_up=float(prob_array[idx]),
                price=float(price),
                equity=float(equity_before),
                realized_return=realized_return,
            )
            diagnostics.append(diag)

            ok_equity, equity_reason = self._risk.check_equity(float(equity_before), timestamp=ts)
            target_fraction = float(position_fraction)

            if not ok_equity or self._risk.circuit_breaker_active:
                target_fraction = 0.0
                if equity_reason is not None:
                    self._risk._record_event(ts, equity_reason, "Circuit breaker engaged")

            if not self._risk.circuit_breaker_active:
                pos_value = abs(target_fraction) * float(equity_before)
                ok_size, size_reason = self._risk.check_position_size(
                    pos_value, float(equity_before), timestamp=ts
                )
                if not ok_size:
                    # Clamp to the allowed band instead of flat rejection.
                    target_fraction = float(
                        np.clip(
                            target_fraction,
                            -self._risk.max_position_fraction,
                            self._risk.max_position_fraction,
                        )
                    )
                position = self._account.positions.get(symbol)
                if self._risk.stop_loss_triggered(position, float(price), timestamp=ts):
                    target_fraction = 0.0

            target_fraction = float(
                np.clip(
                    target_fraction,
                    -self._risk.max_position_fraction,
                    self._risk.max_position_fraction,
                )
            )

            trade = self._account.rebalance_to_fraction(
                symbol,
                target_fraction,
                reference_price=float(price),
                equity=float(equity_before),
                timestamp=ts,
            )

            self._account.equity({symbol: float(price)}, timestamp=ts, record=True)

            equity_after = self._account.equity({symbol: float(price)}, timestamp=ts, record=False)
            self._risk.check_equity(float(equity_after), timestamp=ts)

            if trade is not None:
                diagnostics[-1]["executed_fraction"] = target_fraction

        equity_curve = list(self._account.equity_history)
        final_equity = equity_curve[-1][1] if equity_curve else initial_equity
        equity_values = np.array([value for _, value in equity_curve], dtype=float)
        if equity_values.size > 1:
            equity_returns = np.diff(equity_values) / equity_values[:-1]
        else:
            equity_returns = np.zeros(1, dtype=float)

        avg_return = float(np.mean(equity_returns)) if equity_returns.size else 0.0
        volatility = float(np.std(equity_returns, ddof=1)) if equity_returns.size > 1 else 0.0
        annual_return = avg_return * 252.0
        sharpe = 0.0
        if volatility > 0:
            sharpe = (avg_return / volatility) * np.sqrt(252.0)

        trades = list(self._account.trades)
        num_trades = len(trades)
        win_trades = sum(trade.realized_pnl > 0 for trade in trades)
        win_rate = win_trades / num_trades if num_trades > 0 else 0.0
        realized_pnls = [trade.realized_pnl for trade in trades]
        wins = [pnl for pnl in realized_pnls if pnl > 0]
        losses = [pnl for pnl in realized_pnls if pnl < 0]
        profit_factor = sum(wins) / abs(sum(losses)) if losses else float("inf") if wins else 0.0

        report = BacktestReport(
            symbol=symbol,
            start=timestamps[0],
            end=timestamps[-1],
            start_equity=float(initial_equity),
            final_equity=float(final_equity),
            total_return=(float(final_equity) - float(initial_equity)) / float(initial_equity),
            annual_return=float(annual_return),
            volatility=volatility,
            sharpe=float(sharpe),
            max_drawdown=float(self._risk.max_observed_drawdown),
            num_trades=num_trades,
            win_trades=win_trades,
            win_rate=float(win_rate),
            profit_factor=float(profit_factor),
            audit=self._fete.sigma.audit(),
            equity_curve=equity_curve,
            trades=trades,
            risk_events=list(self._risk.events),
            portfolio=self._account.portfolio_snapshot({symbol: float(price_array[-1])}),
        )
        return report


__all__ = [
    "HistoricalCandle",
    "YahooFinanceDataFetcher",
    "BinanceRESTFetcher",
    "ExecutedTrade",
    "PaperTradingAccount",
    "RiskEvent",
    "RiskGuard",
    "BacktestReport",
    "FETEBacktestEngine",
]
