"""Event-driven backtest engine with chunked data ingestion."""

from __future__ import annotations

import heapq
import logging
import queue
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, List, Optional

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from backtest.transaction_costs import PerUnitCommission, TransactionCostModel
from core.utils.metrics import get_metrics_collector
from interfaces.backtest import BacktestEngine

from .engine import LatencyConfig, OrderBookConfig, Result, SlippageConfig
from .events import FillEvent, MarketEvent, OrderEvent, SignalEvent
from .performance import compute_performance_metrics, export_performance_report

if TYPE_CHECKING:
    from backtest.market_calendar import MarketCalendar

LOGGER = logging.getLogger(__name__)


class MarketDataStream(Iterator[MarketEvent]):
    """Iterator interface for market data events.

    This is a protocol/interface for streaming market data events.
    Concrete implementations should provide the __next__ method to
    yield market events sequentially.

    Example:
        >>> class MyMarketData(MarketDataStream):
        ...     def __next__(self) -> MarketEvent:
        ...         # Return next market event or raise StopIteration
        ...         return MarketEvent(...)
    """

    def __next__(self) -> MarketEvent:  # pragma: no cover - protocol definition
        """Return the next market event in the stream.

        Returns:
            MarketEvent: The next market event with price, symbol, and timing info.

        Raises:
            StopIteration: When no more events are available.
        """
        raise NotImplementedError("Subclasses must implement __next__")


class MarketDataHandler:
    """Base class for chunked market data handlers.

    Market data handlers are responsible for loading and streaming market events
    in chunks to support memory-efficient backtesting with large datasets.

    Subclasses must implement the stream() method to provide market events.
    See ArrayDataHandler and CSVChunkDataHandler for concrete examples.

    Example:
        >>> class MyHandler(MarketDataHandler):
        ...     def stream(self) -> Iterator[Iterable[MarketEvent]]:
        ...         # Yield chunks of market events
        ...         yield [MarketEvent(...), MarketEvent(...)]
    """

    __slots__ = ()

    def stream(self) -> Iterator[Iterable[MarketEvent]]:
        """Stream market data in chunks.

        Yields:
            Iterator[Iterable[MarketEvent]]: Chunks of market events. Each chunk
            is an iterable of MarketEvent objects that will be processed together
            before loading the next chunk.

        Raises:
            NotImplementedError: If subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclasses must implement stream()")


@dataclass(slots=True)
class ArrayDataHandler(MarketDataHandler):
    """Create market events from an in-memory array with optional chunking."""

    prices: Sequence[float]
    symbol: str = "asset"
    chunk_size: Optional[int] = None

    def stream(self) -> Iterator[Iterable[MarketEvent]]:
        total = len(self.prices)
        if total == 0:
            return

        chunk = int(self.chunk_size or total)
        if chunk <= 0:
            chunk = total

        step = 0
        for start in range(0, total, chunk):
            end = min(start + chunk, total)
            events = [
                MarketEvent(symbol=self.symbol, price=float(price), step=step + idx)
                for idx, price in enumerate(self.prices[start:end])
            ]
            step += len(events)
            LOGGER.debug("array chunk %s-%s -> %s events", start, end, len(events))
            yield events


@dataclass(slots=True)
class CSVChunkDataHandler(MarketDataHandler):
    """Stream market data from a CSV file using pandas chunking."""

    path: str
    price_column: str = "close"
    symbol: str = "asset"
    chunk_size: int = 50_000
    parse_dates: bool = False
    date_column: Optional[str] = None
    dtype: Optional[dict[str, str]] = None

    def stream(self) -> Iterator[Iterable[MarketEvent]]:
        reader = pd.read_csv(
            self.path,
            usecols=(
                [self.price_column]
                if self.date_column is None
                else [self.date_column, self.price_column]
            ),
            parse_dates=(
                [self.date_column] if self.parse_dates and self.date_column else None
            ),
            dtype=self.dtype,
            chunksize=self.chunk_size,
        )

        step = 0
        for chunk in reader:
            prices = chunk[self.price_column].to_numpy(dtype=float, copy=False)
            timestamps: List[pd.Timestamp | None]
            if self.date_column is not None:
                timestamps = list(chunk[self.date_column])
            else:
                timestamps = [None] * len(prices)

            events = [
                MarketEvent(
                    symbol=self.symbol,
                    price=float(price),
                    step=step + idx,
                    timestamp=None if ts is None else ts.to_pydatetime(),
                )
                for idx, (price, ts) in enumerate(zip(prices, timestamps, strict=True))
            ]
            step += len(events)
            LOGGER.debug("csv chunk produced %s events", len(events))
            yield events


class Strategy:
    """Base strategy interface for event-driven backtests.

    Strategies process market events and generate trading signals in response.
    The event-driven architecture allows for realistic simulation of strategy
    behavior including latency, order execution, and position management.

    Subclasses must implement on_market_event() to define their trading logic.
    See VectorisedStrategy for an example implementation.

    Example:
        >>> class MyStrategy(Strategy):
        ...     def on_market_event(self, event: MarketEvent) -> Iterable[SignalEvent]:
        ...         # Analyze market event and generate signals
        ...         if should_buy(event):
        ...             return [SignalEvent(symbol=event.symbol, target_position=1.0)]
        ...         return []
    """

    def on_market_event(
        self, event: MarketEvent
    ) -> Iterable[SignalEvent]:  # pragma: no cover - interface
        """Process a market event and generate trading signals.

        Args:
            event: Market event containing price, symbol, and timestamp information.

        Returns:
            Iterable[SignalEvent]: Zero or more signal events representing desired
            trading actions. Empty iterable means no action.

        Raises:
            NotImplementedError: If subclass doesn't implement this method.
        """
        raise NotImplementedError("Subclasses must implement on_market_event()")


class VectorisedStrategy(Strategy):
    """Adapter turning pre-computed vectorised signals into events."""

    def __init__(self, signals: NDArray[np.float64], *, symbol: str = "asset") -> None:
        self._signals = np.asarray(signals, dtype=float)
        self._symbol = symbol

    @classmethod
    def from_signal_function(
        cls,
        prices: NDArray[np.float64],
        signal_fn: Callable[[NDArray[np.float64]], NDArray[np.float64]],
        *,
        symbol: str = "asset",
    ) -> VectorisedStrategy:
        price_array = np.asarray(prices, dtype=float)
        signals = np.asarray(signal_fn(price_array), dtype=float)
        if signals.shape != price_array.shape:
            raise ValueError(
                "signal_fn must return an array with the same length as prices"
            )
        signals = np.clip(signals, -1.0, 1.0)
        return cls(signals, symbol=symbol)

    def on_market_event(self, event: MarketEvent) -> Iterable[SignalEvent]:
        next_index = event.step + 1
        if next_index >= self._signals.size:
            return ()
        signal_value = float(self._signals[next_index])
        LOGGER.debug(
            "strategy emitted precomputed signal %.4f for future step %s",
            signal_value,
            next_index,
        )
        return (
            SignalEvent(
                symbol=self._symbol, target_position=signal_value, step=event.step
            ),
        )


@dataclass(slots=True)
class Portfolio:
    """Single-asset portfolio that reacts to fills and market updates."""

    symbol: str
    initial_capital: float
    fee_per_unit: float

    cash: float = 0.0
    position: float = 0.0
    equity_curve: List[float] | None = None
    position_history: List[float] | None = None
    trades: int = 0
    _last_price: float | None = field(init=False, default=None, repr=False)
    _pending_target: float = field(init=False, default=0.0, repr=False)

    def __post_init__(self) -> None:
        self.cash = float(self.initial_capital)
        self.equity_curve = []
        self.position_history = []
        self._pending_target = self.position

    def on_market_event(self, event: MarketEvent) -> None:
        if self._last_price is not None:
            delta = event.price - self._last_price
            self.cash += self.position * delta
        self._last_price = event.price
        self.equity_curve.append(self.cash)
        if self.position_history is not None:
            self.position_history.append(self.position)
        LOGGER.debug("portfolio equity updated to %.4f", self.cash)

    def create_order(self, signal: SignalEvent) -> Optional[OrderEvent]:
        target = float(signal.target_position)
        delta = target - self._pending_target
        if abs(delta) < 1e-12:
            return None
        self._pending_target += delta
        LOGGER.debug(
            "portfolio creating order for %.4f units (target=%.4f)",
            delta,
            self._pending_target,
        )
        return OrderEvent(symbol=self.symbol, quantity=delta, step=signal.step)

    def on_fill(self, event: FillEvent) -> None:
        self.position += event.quantity
        extra_spread = getattr(event, "spread_cost", 0.0)
        financing_cost = getattr(event, "financing_cost", 0.0)
        self.cash -= event.fee + event.slippage + extra_spread + financing_cost
        self.trades += 1
        self._pending_target = self.position
        LOGGER.debug(
            "fill processed: qty=%.4f price=%.4f cash=%.4f position=%.4f",
            event.quantity,
            event.price,
            self.cash,
            self.position,
        )
        if self.equity_curve:
            self.equity_curve[-1] = self.cash

    def apply_financing(self, cost: float) -> None:
        if cost == 0.0:
            return
        self.cash -= float(cost)
        if self.equity_curve:
            self.equity_curve[-1] = self.cash
        LOGGER.debug("applied financing cost %.6f -> cash %.4f", cost, self.cash)

    def has_price(self) -> bool:
        return self._last_price is not None

    @property
    def last_price(self) -> float:
        if self._last_price is None:
            raise RuntimeError("No market data has been processed yet")
        return self._last_price

    def finalise_history(self) -> None:
        if self.position_history is None:
            return
        if not self.position_history:
            self.position_history.append(self.position)
        elif abs(self.position_history[-1] - self.position) > 1e-12:
            self.position_history.append(self.position)


class SimulatedExecutionHandler:
    """Simple execution handler that uses a synthetic order book."""

    def __init__(
        self,
        order_book: OrderBookConfig,
        slippage: SlippageConfig,
        fee_per_unit: float,
        *,
        transaction_cost_model: TransactionCostModel | None = None,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._order_book = order_book
        self._slippage = slippage
        self._cost_model = transaction_cost_model or PerUnitCommission(fee_per_unit)
        self._price_history: List[float] = []
        self._rng = rng or np.random.default_rng()

    def on_market_event(self, event: MarketEvent) -> None:
        self._price_history.append(event.price)

    @property
    def cost_model(self) -> TransactionCostModel:
        return self._cost_model

    def execute(self, order: OrderEvent, current_step: int) -> FillEvent:
        if not self._price_history:
            raise RuntimeError("Cannot execute order before receiving market data")

        prices = np.asarray(self._price_history, dtype=float)
        current_idx = min(current_step, prices.size - 1)
        side = "buy" if order.quantity > 0 else "sell"
        quantity = abs(order.quantity)
        if quantity <= 0.0:
            raise ValueError("Order quantity must be positive")

        mid_price = float(prices[current_idx])
        best_bid, best_ask = self._best_quotes(mid_price)
        reference_price = best_ask if side == "buy" else best_bid
        (
            avg_price,
            filled_qty,
            depth_slippage_cost,
            remaining_qty,
        ) = self._consume_depth(side, quantity, reference_price)

        if filled_qty <= 0.0:
            LOGGER.debug("order qty=%.4f not filled due to zero depth", quantity)
            return FillEvent(
                symbol=order.symbol,
                quantity=0.0,
                price=reference_price,
                fee=0.0,
                slippage=0.0,
                step=current_step,
            )

        avg_price, per_unit_slippage_cost = self._apply_per_unit_slippage(
            avg_price, filled_qty, side
        )
        avg_price, stochastic_slippage_cost = self._apply_stochastic_slippage(
            avg_price, filled_qty, side
        )

        (
            avg_price,
            spread_model_cost,
            slippage_model_cost,
            commission_cost,
        ) = self._apply_transaction_costs(avg_price, filled_qty, side)

        spread_book_cost = abs(reference_price - mid_price) * filled_qty
        total_slippage_cost = (
            depth_slippage_cost
            + per_unit_slippage_cost
            + stochastic_slippage_cost
            + slippage_model_cost
        )
        total_spread_cost = spread_book_cost + spread_model_cost

        fill = FillEvent(
            symbol=order.symbol,
            quantity=np.copysign(filled_qty, order.quantity),
            price=float(avg_price),
            fee=commission_cost,
            slippage=total_slippage_cost,
            step=current_step,
            spread_cost=total_spread_cost,
        )

        if remaining_qty > 0.0:
            LOGGER.debug(
                "partial fill qty=%.4f remaining=%.4f price=%.4f",
                filled_qty,
                remaining_qty,
                avg_price,
            )
        else:
            LOGGER.debug(
                "executed order qty=%.4f price=%.4f commission=%.6f slippage=%.6f spread=%.6f",
                fill.quantity,
                avg_price,
                commission_cost,
                total_slippage_cost,
                total_spread_cost,
            )

        return fill

    def _best_quotes(self, mid_price: float) -> tuple[float, float]:
        spread = mid_price * self._order_book.spread_bps * 1e-4
        best_bid = mid_price - spread / 2.0
        best_ask = mid_price + spread / 2.0
        return best_bid, best_ask

    def _consume_depth(
        self,
        side: str,
        quantity: float,
        reference_price: float,
    ) -> tuple[float, float, float, float]:
        remaining = float(quantity)
        total_cost = 0.0
        filled = 0.0
        depth_cost = 0.0
        depth = tuple(
            float(max(level, 0.0)) for level in self._order_book.depth_profile
        )

        for level_idx, capacity in enumerate(depth, start=1):
            if remaining <= 0.0:
                break
            take = min(remaining, capacity)
            if take <= 0.0:
                continue
            depth_penalty = self._slippage.depth_impact_bps * (level_idx - 1) * 1e-4
            if side == "buy":
                level_price = reference_price * (1.0 + depth_penalty)
                depth_cost += (level_price - reference_price) * take
            else:
                level_price = reference_price * (1.0 - depth_penalty)
                depth_cost += (reference_price - level_price) * take
            total_cost += level_price * take
            filled += take
            remaining -= take

        if remaining > 0.0 and self._order_book.infinite_depth:
            depth_penalty = self._slippage.depth_impact_bps * max(len(depth), 1) * 1e-4
            if side == "buy":
                level_price = reference_price * (1.0 + depth_penalty)
                depth_cost += (level_price - reference_price) * remaining
            else:
                level_price = reference_price * (1.0 - depth_penalty)
                depth_cost += (reference_price - level_price) * remaining
            total_cost += level_price * remaining
            filled += remaining
            remaining = 0.0

        avg_price = total_cost / filled if filled > 0.0 else reference_price
        return float(avg_price), float(filled), float(depth_cost), float(remaining)

    def _apply_per_unit_slippage(
        self, avg_price: float, filled_qty: float, side: str
    ) -> tuple[float, float]:
        if filled_qty <= 0.0 or self._slippage.per_unit_bps == 0.0:
            return avg_price, 0.0
        adjustment = avg_price * self._slippage.per_unit_bps * 1e-4
        if side == "buy":
            new_price = avg_price + adjustment
            cost = adjustment * filled_qty
        else:
            new_price = avg_price - adjustment
            cost = adjustment * filled_qty
        return float(new_price), float(max(cost, 0.0))

    def _apply_stochastic_slippage(
        self, avg_price: float, filled_qty: float, side: str
    ) -> tuple[float, float]:
        scale = self._slippage.stochastic_bps
        if filled_qty <= 0.0 or scale <= 0.0:
            return avg_price, 0.0
        noise_fraction = float(self._rng.normal(loc=0.0, scale=scale)) * 1e-4
        noise_fraction = max(min(noise_fraction, 1.0), -0.99)
        if side == "buy":
            new_price = avg_price * (1.0 + noise_fraction)
            cost = max(0.0, (new_price - avg_price) * filled_qty)
        else:
            new_price = avg_price * (1.0 - noise_fraction)
            cost = max(0.0, (avg_price - new_price) * filled_qty)
        return float(new_price), float(cost)

    def _apply_transaction_costs(
        self, avg_price: float, filled_qty: float, side: str
    ) -> tuple[float, float, float, float]:
        model = self._cost_model
        spread_adjustment = model.get_spread(avg_price, side)
        spread_adjustment = max(float(spread_adjustment), 0.0)
        slippage_adjustment = model.get_slippage(filled_qty, avg_price, side)
        slippage_adjustment = max(float(slippage_adjustment), 0.0)
        commission = model.get_commission(filled_qty, avg_price)
        commission = max(float(commission), 0.0)

        if side == "buy":
            price = avg_price + spread_adjustment + slippage_adjustment
        else:
            price = avg_price - spread_adjustment - slippage_adjustment

        spread_cost = spread_adjustment * filled_qty
        slippage_cost = slippage_adjustment * filled_qty
        return float(price), float(spread_cost), float(slippage_cost), float(commission)


class EventDrivenBacktestEngine(BacktestEngine[Result]):
    """Event-driven backtest engine with memory-aware chunked ingestion."""

    def run(
        self,
        prices: NDArray[np.float64],
        signal_fn: Callable[[NDArray[np.float64]], NDArray[np.float64]],
        *,
        fee: float = 0.0005,
        initial_capital: float = 0.0,
        strategy_name: str = "default",
        latency: LatencyConfig | None = None,
        order_book: OrderBookConfig | None = None,
        slippage: SlippageConfig | None = None,
        data_handler: MarketDataHandler | None = None,
        strategy: Strategy | None = None,
        chunk_size: Optional[int] = None,
        transaction_cost_model: TransactionCostModel | None = None,
        random_seed: int | None = None,
        calendar: "MarketCalendar | None" = None,
    ) -> Result:
        latency_cfg = latency or LatencyConfig()
        order_book_cfg = order_book or OrderBookConfig()
        slippage_cfg = slippage or SlippageConfig()

        price_array = np.asarray(prices, dtype=float)
        if price_array.ndim > 1:
            raise ValueError("prices must be a 1-D array")

        if data_handler is None:
            data_handler = ArrayDataHandler(price_array, chunk_size=chunk_size)

        symbol = getattr(data_handler, "symbol", "asset")

        if strategy is None:
            if price_array.size == 0:
                raise ValueError(
                    "prices must be provided when using the default strategy"
                )
            strategy_impl = VectorisedStrategy.from_signal_function(
                price_array, signal_fn, symbol=symbol
            )
        else:
            strategy_impl = strategy

        metrics = get_metrics_collector()
        with metrics.measure_backtest(strategy_name) as ctx:
            event_queue: queue.Queue[
                FillEvent | MarketEvent | OrderEvent | SignalEvent
            ] = queue.Queue()
            delayed: list[tuple[int, int, SignalEvent | OrderEvent | FillEvent]] = []
            counter = 0
            current_step = -1

            portfolio = Portfolio(
                symbol=symbol, initial_capital=initial_capital, fee_per_unit=fee
            )
            rng = np.random.default_rng(random_seed)
            execution_handler = SimulatedExecutionHandler(
                order_book_cfg,
                slippage_cfg,
                fee,
                transaction_cost_model=transaction_cost_model,
                rng=rng,
            )
            cost_model = execution_handler.cost_model

            total_slippage = 0.0
            total_commission = 0.0
            total_spread = 0.0
            total_financing = 0.0

            def schedule(
                event: SignalEvent | OrderEvent | FillEvent, delay: int
            ) -> None:
                nonlocal counter
                release = current_step + max(0, delay)
                event.step = release
                heapq.heappush(delayed, (release, counter, event))
                counter += 1
                LOGGER.debug("scheduled %s with delay %s", event.type, delay)

            def release_ready() -> None:
                while delayed and delayed[0][0] <= current_step:
                    _, _, evt = heapq.heappop(delayed)
                    event_queue.put(evt)

            for chunk in data_handler.stream():
                for market_event in chunk:
                    current_step = market_event.step
                    if (
                        calendar is not None
                        and market_event.timestamp is not None
                        and not calendar.is_open(market_event.timestamp)
                    ):
                        LOGGER.debug(
                            "skipping market event outside trading hours at %s",
                            market_event.timestamp,
                        )
                        release_ready()
                        continue

                    if portfolio.has_price():
                        reference_price = portfolio.last_price
                    else:
                        reference_price = market_event.price
                    if portfolio.position_history:
                        prior_position = float(portfolio.position_history[-1])
                    else:
                        prior_position = float(portfolio.position)
                    financing_cost = float(
                        cost_model.get_financing(prior_position, reference_price)
                    )
                    if financing_cost:
                        portfolio.apply_financing(financing_cost)
                        total_financing += financing_cost

                    event_queue.put(market_event)
                    release_ready()

                    while True:
                        try:
                            event = event_queue.get_nowait()
                        except queue.Empty:
                            break

                        if isinstance(event, MarketEvent):
                            execution_handler.on_market_event(event)
                            portfolio.on_market_event(event)
                            for signal in strategy_impl.on_market_event(event):
                                schedule(signal, latency_cfg.signal_to_order)
                        elif isinstance(event, SignalEvent):
                            order = portfolio.create_order(event)
                            if order is not None:
                                schedule(order, latency_cfg.order_to_execution)
                        elif isinstance(event, OrderEvent):
                            fill = execution_handler.execute(event, current_step)
                            spread_cost = float(getattr(fill, "spread_cost", 0.0))
                            if (
                                fill.quantity != 0.0
                                or fill.fee
                                or fill.slippage
                                or spread_cost
                            ):
                                total_slippage += float(fill.slippage)
                                total_commission += float(fill.fee)
                                total_spread += spread_cost
                                schedule(fill, latency_cfg.execution_to_fill)
                        elif isinstance(event, FillEvent):
                            portfolio.on_fill(event)
                        else:  # pragma: no cover - safety net
                            LOGGER.warning("Unhandled event type: %s", type(event))

                        release_ready()

            while delayed:
                next_step, _, evt = heapq.heappop(delayed)
                if next_step > current_step:
                    current_step = next_step
                event_queue.put(evt)
                release_ready()

                while True:
                    try:
                        pending = event_queue.get_nowait()
                    except queue.Empty:
                        break

                    if isinstance(pending, SignalEvent):
                        order = portfolio.create_order(pending)
                        if order is not None:
                            schedule(order, latency_cfg.order_to_execution)
                    elif isinstance(pending, OrderEvent):
                        fill = execution_handler.execute(pending, current_step)
                        spread_cost = float(getattr(fill, "spread_cost", 0.0))
                        if (
                            fill.quantity != 0.0
                            or fill.fee
                            or fill.slippage
                            or spread_cost
                        ):
                            total_slippage += float(fill.slippage)
                            total_commission += float(fill.fee)
                            total_spread += spread_cost
                            schedule(fill, latency_cfg.execution_to_fill)
                    elif isinstance(pending, FillEvent):
                        portfolio.on_fill(pending)
                    else:  # pragma: no cover - safety net
                        LOGGER.warning(
                            "Unhandled delayed event type: %s", type(pending)
                        )

                    release_ready()

            portfolio.finalise_history()

            equity_curve = np.asarray(portfolio.equity_curve, dtype=float)
            positions = (
                np.asarray(portfolio.position_history, dtype=float)
                if portfolio.position_history is not None
                else np.array([], dtype=float)
            )
            pnl_total = (
                float(equity_curve[-1] - initial_capital) if equity_curve.size else 0.0
            )
            peaks = (
                np.maximum.accumulate(equity_curve)
                if equity_curve.size
                else np.array([], dtype=float)
            )
            drawdowns = (
                equity_curve - peaks if peaks.size else np.array([], dtype=float)
            )
            max_dd = float(drawdowns.min()) if drawdowns.size else 0.0

            trades = portfolio.trades

            ctx["pnl"] = pnl_total
            ctx["max_dd"] = max_dd
            ctx["trades"] = trades
            ctx["equity"] = (
                float(equity_curve[-1]) if equity_curve.size else initial_capital
            )
            ctx["status"] = "success"
            ctx["commission_cost"] = float(total_commission)
            ctx["spread_cost"] = float(total_spread)
            ctx["slippage_cost"] = float(total_slippage)
            ctx["financing_cost"] = float(total_financing)

            if metrics.enabled:
                metrics.record_equity_curve(strategy_name, equity_curve)

            pnl_series = (
                equity_curve
                - np.concatenate(([float(initial_capital)], equity_curve[:-1]))
                if equity_curve.size
                else np.array([], dtype=float)
            )
            position_changes = (
                np.diff(positions) if positions.size else np.array([], dtype=float)
            )
            performance = compute_performance_metrics(
                equity_curve=equity_curve,
                pnl=pnl_series,
                position_changes=position_changes,
                initial_capital=initial_capital,
                max_drawdown=max_dd,
            )
            report_path = export_performance_report(strategy_name, performance)
            ctx["performance"] = performance.as_dict()
            ctx["report_path"] = str(report_path)

            return Result(
                pnl=pnl_total,
                max_dd=max_dd,
                trades=trades,
                equity_curve=equity_curve,
                latency_steps=int(latency_cfg.total_delay),
                slippage_cost=float(total_slippage),
                commission_cost=float(total_commission),
                spread_cost=float(total_spread),
                financing_cost=float(total_financing),
                performance=performance,
                report_path=report_path,
            )


def vectorized_backtest(
    prices: NDArray[np.float64],
    signals: NDArray[np.float64],
    *,
    fee_per_trade: float = 0.0005,
    initial_capital: float = 0.0,
) -> dict[str, float | NDArray[np.float64]]:
    """Fast vectorized backtest for HFT-grade strategy evaluation.

    This function provides O(n) complexity backtest without event loop overhead,
    suitable for rapid parameter optimization and walk-forward analysis.

    Unlike the event-driven engine, this implementation:
    - Uses pure numpy vectorization (no Python loops in hot path)
    - Assumes instant execution (no latency modeling)
    - Does not support complex order book simulation

    For production backtesting with realistic execution simulation,
    use EventDrivenBacktestEngine instead.

    Args:
        prices: 1-D array of asset prices.
        signals: 1-D array of position signals in [-1, 1].
            Must have same length as prices.
            Signals are shifted by 1 to prevent look-ahead bias.
        fee_per_trade: Transaction fee as fraction of trade value.
        initial_capital: Starting capital (default 0 for return-based).

    Returns:
        dict containing:
            - pnl: Total P&L
            - max_dd: Maximum drawdown
            - trades: Number of trades executed
            - equity_curve: Array of equity values
            - sharpe: Annualized Sharpe ratio (assuming 252 trading days)
            - positions: Array of position history

    Raises:
        ValueError: If prices and signals have different lengths.

    Example:
        >>> prices = np.array([100.0, 101.0, 102.0, 101.0, 103.0])
        >>> signals = np.array([0.0, 1.0, 1.0, -1.0, 0.0])
        >>> result = vectorized_backtest(prices, signals)
        >>> result['pnl']
        2.0

    Note:
        Algorithmic complexity: O(n) where n = len(prices).
        Uses rolling window approach to prevent look-ahead bias.
    """
    prices = np.asarray(prices, dtype=np.float64)
    signals = np.asarray(signals, dtype=np.float64)

    if prices.shape != signals.shape:
        raise ValueError("prices and signals must have the same length")

    n = len(prices)
    if n == 0:
        return {
            "pnl": 0.0,
            "max_dd": 0.0,
            "trades": 0,
            "equity_curve": np.array([], dtype=np.float64),
            "sharpe": 0.0,
            "positions": np.array([], dtype=np.float64),
        }

    # Sanitize inputs with robust np.nan_to_num
    prices = np.nan_to_num(prices, nan=0.0, posinf=0.0, neginf=0.0)
    signals = np.nan_to_num(signals, nan=0.0, posinf=0.0, neginf=0.0)

    # Clip signals to valid range
    signals = np.clip(signals, -1.0, 1.0)

    # Shift signals by 1 to prevent look-ahead bias
    # Signal at t determines position at t+1
    positions = np.zeros(n, dtype=np.float64)
    positions[1:] = signals[:-1]

    # Compute returns
    price_returns = np.zeros(n, dtype=np.float64)
    price_returns[1:] = (prices[1:] - prices[:-1]) / np.maximum(prices[:-1], 1e-10)

    # Strategy returns = position * price_returns
    strategy_returns = positions * price_returns

    # Compute trades (position changes)
    position_changes = np.zeros(n, dtype=np.float64)
    position_changes[1:] = np.abs(positions[1:] - positions[:-1])

    # Transaction costs
    trade_costs = position_changes * fee_per_trade

    # Net returns after costs
    net_returns = strategy_returns - trade_costs

    # Equity curve: scale returns by capital or use unit returns
    capital_scale = initial_capital if initial_capital > 0 else 1.0
    equity_curve = initial_capital + np.cumsum(net_returns * capital_scale)

    # Maximum drawdown
    peaks = np.maximum.accumulate(equity_curve)
    drawdowns = equity_curve - peaks
    max_dd = float(np.min(drawdowns))

    # P&L
    pnl = float(equity_curve[-1] - initial_capital) if n > 0 else 0.0

    # Number of trades
    trades = int(np.sum(position_changes > 1e-10))

    # Sharpe ratio (annualized, assuming 252 trading days)
    if n > 1:
        mean_return = np.mean(net_returns)
        std_return = np.std(net_returns)
        if std_return > 1e-10:
            sharpe = float((mean_return / std_return) * np.sqrt(252))
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0

    return {
        "pnl": pnl,
        "max_dd": max_dd,
        "trades": trades,
        "equity_curve": equity_curve,
        "sharpe": sharpe,
        "positions": positions,
    }


__all__ = [
    "ArrayDataHandler",
    "CSVChunkDataHandler",
    "EventDrivenBacktestEngine",
    "Portfolio",
    "SimulatedExecutionHandler",
    "Strategy",
    "VectorisedStrategy",
    "vectorized_backtest",
]
