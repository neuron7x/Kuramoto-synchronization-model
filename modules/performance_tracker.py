# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Performance Tracker Module

Модуль для відстеження продуктивності торгової системи в реальному часі.

Features:
- Відстеження PnL
- Розрахунок метрик в реальному часі
- Benchmarking
- Атрибуція продуктивності
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


class TimeFrame(str, Enum):
    """Часові рамки"""

    INTRADAY = "intraday"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    ALL_TIME = "all_time"


@dataclass
class PositionSnapshot:
    """Знімок позиції"""

    symbol: str
    quantity: float
    average_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    weight: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class PerformanceSnapshot:
    """Знімок продуктивності"""

    timestamp: datetime
    equity: float
    cash: float
    positions_value: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    daily_return: float
    cumulative_return: float


@dataclass
class PerformanceMetrics:
    """Метрики продуктивності"""

    total_return: float = 0.0
    annualized_return: float = 0.0
    daily_return: float = 0.0
    volatility: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    current_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    calmar_ratio: float = 0.0


@dataclass
class AttributionResult:
    """Результат атрибуції"""

    symbol: str
    contribution: float
    weight: float
    return_value: float
    attribution_type: str


class PerformanceTracker:
    """
    Трекер продуктивності

    Відстежує продуктивність торгової системи в реальному часі.
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        risk_free_rate: float = 0.02,
        benchmark_returns: Optional[pd.Series] = None,
        annualization_factor: int = 252,
    ):
        """
        Ініціалізація трекера

        Args:
            initial_capital: Початковий капітал
            risk_free_rate: Безризикова ставка
            benchmark_returns: Повернення бенчмарку
            annualization_factor: Фактор аналізації
        """
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate
        self.benchmark_returns = benchmark_returns
        self.annualization_factor = annualization_factor

        # Поточний стан
        self._current_equity = initial_capital
        self._current_cash = initial_capital
        self._peak_equity = initial_capital

        # Позиції
        self._positions: Dict[str, PositionSnapshot] = {}

        # Історія
        self._equity_history: List[PerformanceSnapshot] = []
        self._trade_history: List[Dict[str, Any]] = []

        # Статистика
        self._realized_pnl = 0.0
        self._unrealized_pnl = 0.0
        self._winning_trades = 0
        self._losing_trades = 0
        self._total_profit = 0.0
        self._total_loss = 0.0

        # Часові мітки
        self._start_time = datetime.now()
        self._last_update = datetime.now()

    def update_position(
        self,
        symbol: str,
        quantity: float,
        average_price: float,
        current_price: float,
    ) -> None:
        """
        Оновлення позиції

        Args:
            symbol: Символ
            quantity: Кількість
            average_price: Середня ціна
            current_price: Поточна ціна
        """
        if quantity == 0:
            if symbol in self._positions:
                del self._positions[symbol]
            return

        market_value = quantity * current_price
        cost_basis = quantity * average_price
        unrealized_pnl = market_value - cost_basis
        unrealized_pnl_pct = unrealized_pnl / cost_basis if cost_basis != 0 else 0.0

        # Розрахунок ваги
        total_positions_value = sum(p.market_value for p in self._positions.values())
        total_positions_value += market_value  # Включаємо поточну позицію

        weight = market_value / self._current_equity if self._current_equity > 0 else 0.0

        self._positions[symbol] = PositionSnapshot(
            symbol=symbol,
            quantity=quantity,
            average_price=average_price,
            current_price=current_price,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            weight=weight,
        )

        self._update_unrealized_pnl()

    def record_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        pnl: float = 0.0,
    ) -> None:
        """
        Запис торгової операції

        Args:
            symbol: Символ
            side: Сторона (buy/sell)
            quantity: Кількість
            price: Ціна
            pnl: PnL (для закриття позиції)
        """
        trade = {
            "timestamp": datetime.now(),
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "pnl": pnl,
        }

        self._trade_history.append(trade)

        # Оновлення статистики
        if pnl != 0:
            self._realized_pnl += pnl

            if pnl > 0:
                self._winning_trades += 1
                self._total_profit += pnl
            else:
                self._losing_trades += 1
                self._total_loss += abs(pnl)

        # Оновлення кешу
        notional = quantity * price
        if side.lower() == "buy":
            self._current_cash -= notional
        else:
            self._current_cash += notional

    def update_equity(
        self,
        equity: Optional[float] = None,
        cash: Optional[float] = None,
    ) -> PerformanceSnapshot:
        """
        Оновлення equity

        Args:
            equity: Загальний equity (якщо None - розрахувати)
            cash: Готівка (якщо None - використати поточну)

        Returns:
            Знімок продуктивності
        """
        if cash is not None:
            self._current_cash = cash

        positions_value = sum(p.market_value for p in self._positions.values())

        if equity is not None:
            self._current_equity = equity
        else:
            self._current_equity = self._current_cash + positions_value

        # Оновлення peak equity
        if self._current_equity > self._peak_equity:
            self._peak_equity = self._current_equity

        # Розрахунок повернень
        total_pnl = self._current_equity - self.initial_capital
        cumulative_return = total_pnl / self.initial_capital if self.initial_capital > 0 else 0.0

        # Денне повернення
        daily_return = 0.0
        if self._equity_history:
            last_equity = self._equity_history[-1].equity
            if last_equity > 0:
                daily_return = (self._current_equity - last_equity) / last_equity

        snapshot = PerformanceSnapshot(
            timestamp=datetime.now(),
            equity=self._current_equity,
            cash=self._current_cash,
            positions_value=positions_value,
            realized_pnl=self._realized_pnl,
            unrealized_pnl=self._unrealized_pnl,
            total_pnl=total_pnl,
            daily_return=daily_return,
            cumulative_return=cumulative_return,
        )

        self._equity_history.append(snapshot)
        self._last_update = datetime.now()

        return snapshot

    def get_metrics(self, timeframe: TimeFrame = TimeFrame.ALL_TIME) -> PerformanceMetrics:
        """
        Отримання метрик продуктивності

        Args:
            timeframe: Часові рамки

        Returns:
            Метрики продуктивності
        """
        # Фільтрація історії за timeframe
        history = self._filter_history(timeframe)

        if len(history) < 2:
            return PerformanceMetrics()

        # Підготовка даних
        equities = np.array([h.equity for h in history])
        returns = np.diff(equities) / equities[:-1]

        # Базові метрики
        total_return = (equities[-1] - equities[0]) / equities[0] if equities[0] > 0 else 0.0

        # Аналізовані метрики
        periods = len(returns)
        scaling = self.annualization_factor / periods if periods > 0 else 1.0

        annualized_return = (1 + total_return) ** scaling - 1
        daily_return = np.mean(returns) if len(returns) > 0 else 0.0
        volatility = (
            np.std(returns) * np.sqrt(self.annualization_factor) if len(returns) > 1 else 0.0
        )

        # Sharpe Ratio
        excess_return = annualized_return - self.risk_free_rate
        sharpe_ratio = excess_return / volatility if volatility > 0 else 0.0

        # Sortino Ratio
        downside_returns = returns[returns < 0]
        downside_std = (
            np.std(downside_returns) * np.sqrt(self.annualization_factor)
            if len(downside_returns) > 0
            else volatility
        )
        sortino_ratio = excess_return / downside_std if downside_std > 0 else 0.0

        # Drawdown
        running_max = np.maximum.accumulate(equities)
        drawdowns = (equities - running_max) / running_max
        max_drawdown = abs(np.min(drawdowns))
        current_drawdown = abs(drawdowns[-1])

        # Calmar Ratio
        calmar_ratio = annualized_return / max_drawdown if max_drawdown > 0 else 0.0

        # Win rate та Profit factor
        total_trades = self._winning_trades + self._losing_trades
        win_rate = self._winning_trades / total_trades if total_trades > 0 else 0.0
        profit_factor = (
            self._total_profit / self._total_loss if self._total_loss > 0 else float("inf")
        )

        return PerformanceMetrics(
            total_return=float(total_return),
            annualized_return=float(annualized_return),
            daily_return=float(daily_return),
            volatility=float(volatility),
            sharpe_ratio=float(sharpe_ratio),
            sortino_ratio=float(sortino_ratio),
            max_drawdown=float(max_drawdown),
            current_drawdown=float(current_drawdown),
            win_rate=float(win_rate),
            profit_factor=float(min(profit_factor, 100.0)),
            calmar_ratio=float(calmar_ratio),
        )

    def get_positions(self) -> List[PositionSnapshot]:
        """
        Отримання поточних позицій

        Returns:
            Список позицій
        """
        return list(self._positions.values())

    def get_attribution(self) -> List[AttributionResult]:
        """
        Атрибуція продуктивності

        Returns:
            Список результатів атрибуції
        """
        results = []

        total_pnl = self._realized_pnl + self._unrealized_pnl

        # Атрибуція за позиціями
        for symbol, position in self._positions.items():
            contribution = position.unrealized_pnl / total_pnl if total_pnl != 0 else 0.0

            results.append(
                AttributionResult(
                    symbol=symbol,
                    contribution=float(contribution),
                    weight=float(position.weight),
                    return_value=float(position.unrealized_pnl_pct),
                    attribution_type="position",
                )
            )

        # Атрибуція за трейдами
        trade_pnl_by_symbol: Dict[str, float] = {}
        for trade in self._trade_history:
            if trade["pnl"] != 0:
                symbol = trade["symbol"]
                trade_pnl_by_symbol[symbol] = trade_pnl_by_symbol.get(symbol, 0.0) + trade["pnl"]

        for symbol, pnl in trade_pnl_by_symbol.items():
            contribution = pnl / total_pnl if total_pnl != 0 else 0.0

            results.append(
                AttributionResult(
                    symbol=symbol,
                    contribution=float(contribution),
                    weight=0.0,
                    return_value=float(pnl),
                    attribution_type="realized",
                )
            )

        return results

    def get_equity_curve(self, timeframe: TimeFrame = TimeFrame.ALL_TIME) -> pd.DataFrame:
        """
        Отримання equity curve

        Args:
            timeframe: Часові рамки

        Returns:
            DataFrame з equity curve
        """
        history = self._filter_history(timeframe)

        if not history:
            return pd.DataFrame()

        data = {
            "timestamp": [h.timestamp for h in history],
            "equity": [h.equity for h in history],
            "cash": [h.cash for h in history],
            "positions_value": [h.positions_value for h in history],
            "realized_pnl": [h.realized_pnl for h in history],
            "unrealized_pnl": [h.unrealized_pnl for h in history],
            "total_pnl": [h.total_pnl for h in history],
            "daily_return": [h.daily_return for h in history],
            "cumulative_return": [h.cumulative_return for h in history],
        }

        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)

        return df

    def get_trade_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Отримання історії трейдів

        Args:
            symbol: Фільтр за символом
            limit: Максимальна кількість

        Returns:
            Список трейдів
        """
        trades = self._trade_history.copy()

        if symbol:
            trades = [t for t in trades if t["symbol"] == symbol]

        trades = sorted(trades, key=lambda x: x["timestamp"], reverse=True)
        return trades[:limit]

    def get_drawdown_analysis(self) -> Dict[str, Any]:
        """
        Аналіз drawdown

        Returns:
            Словник з аналізом
        """
        if len(self._equity_history) < 2:
            return {
                "current_drawdown": 0.0,
                "max_drawdown": 0.0,
                "drawdown_periods": 0,
                "max_drawdown_duration": timedelta(),
                "time_to_recovery": None,
            }

        equities = np.array([h.equity for h in self._equity_history])
        timestamps = [h.timestamp for h in self._equity_history]

        running_max = np.maximum.accumulate(equities)
        drawdowns = (equities - running_max) / running_max

        current_drawdown = abs(drawdowns[-1])
        max_drawdown = abs(np.min(drawdowns))

        # Аналіз періодів drawdown
        in_drawdown = drawdowns < 0
        drawdown_periods = 0
        max_duration = timedelta()
        current_duration = timedelta()
        drawdown_start = None

        for i, is_dd in enumerate(in_drawdown):
            if is_dd:
                if drawdown_start is None:
                    drawdown_start = timestamps[i]
                    drawdown_periods += 1
            else:
                if drawdown_start is not None:
                    duration = timestamps[i] - drawdown_start
                    if duration > max_duration:
                        max_duration = duration
                    drawdown_start = None

        # Поточна тривалість drawdown
        if drawdown_start is not None:
            current_duration = timestamps[-1] - drawdown_start

        return {
            "current_drawdown": float(current_drawdown),
            "max_drawdown": float(max_drawdown),
            "drawdown_periods": drawdown_periods,
            "max_drawdown_duration": max_duration,
            "current_drawdown_duration": current_duration,
            "peak_equity": float(self._peak_equity),
        }

    def reset(self) -> None:
        """Скидання трекера"""
        self._current_equity = self.initial_capital
        self._current_cash = self.initial_capital
        self._peak_equity = self.initial_capital
        self._positions.clear()
        self._equity_history.clear()
        self._trade_history.clear()
        self._realized_pnl = 0.0
        self._unrealized_pnl = 0.0
        self._winning_trades = 0
        self._losing_trades = 0
        self._total_profit = 0.0
        self._total_loss = 0.0
        self._start_time = datetime.now()
        self._last_update = datetime.now()

    def _update_unrealized_pnl(self) -> None:
        """Оновлення нереалізованого PnL"""
        self._unrealized_pnl = sum(p.unrealized_pnl for p in self._positions.values())

    def _filter_history(self, timeframe: TimeFrame) -> List[PerformanceSnapshot]:
        """Фільтрація історії за timeframe"""
        if timeframe == TimeFrame.ALL_TIME:
            return self._equity_history

        now = datetime.now()
        cutoff_map = {
            TimeFrame.INTRADAY: now.replace(hour=0, minute=0, second=0, microsecond=0),
            TimeFrame.DAILY: now - timedelta(days=1),
            TimeFrame.WEEKLY: now - timedelta(weeks=1),
            TimeFrame.MONTHLY: now - timedelta(days=30),
            TimeFrame.YEARLY: now - timedelta(days=365),
        }

        cutoff = cutoff_map.get(timeframe, datetime.min)
        return [h for h in self._equity_history if h.timestamp >= cutoff]

    def get_summary(self) -> Dict:
        """
        Отримання саммарі

        Returns:
            Словник зі статистикою
        """
        metrics = self.get_metrics()
        drawdown = self.get_drawdown_analysis()

        return {
            "current_equity": f"${self._current_equity:,.2f}",
            "initial_capital": f"${self.initial_capital:,.2f}",
            "total_return": f"{metrics.total_return:.2%}",
            "realized_pnl": f"${self._realized_pnl:,.2f}",
            "unrealized_pnl": f"${self._unrealized_pnl:,.2f}",
            "sharpe_ratio": f"{metrics.sharpe_ratio:.2f}",
            "max_drawdown": f"{drawdown['max_drawdown']:.2%}",
            "current_drawdown": f"{drawdown['current_drawdown']:.2%}",
            "win_rate": f"{metrics.win_rate:.2%}",
            "profit_factor": f"{metrics.profit_factor:.2f}",
            "total_trades": self._winning_trades + self._losing_trades,
            "winning_trades": self._winning_trades,
            "losing_trades": self._losing_trades,
            "positions_count": len(self._positions),
            "history_size": len(self._equity_history),
            "tracking_since": self._start_time.isoformat(),
        }
