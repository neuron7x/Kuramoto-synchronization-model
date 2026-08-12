# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Adaptive Risk Manager Module

Динамічний модуль управління ризиками, який адаптується до ринкових умов
та інтегрується з термодинамічною системою контролю (TACL).

Features:
- Адаптивні ліміти позицій на основі волатильності
- Динамічне управління ризиками на рівні портфеля
- Інтеграція з TACL для енергетичного менеджменту
- Моніторинг VaR та CVaR в реальному часі
- Автоматичне коригування експозиції
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
from pydantic import BaseModel, Field

from modules.types import MarketState


class RiskLevel(str, Enum):
    """Рівні ризику"""

    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"


class MarketCondition(str, Enum):
    """Стан ринку"""

    CALM = "calm"
    NORMAL = "normal"
    VOLATILE = "volatile"
    EXTREME = "extreme"


@dataclass
class RiskMetrics:
    """Метрики ризику"""

    var_95: float
    cvar_95: float
    var_99: float
    cvar_99: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    volatility: float
    timestamp: datetime


class PositionLimit(BaseModel):
    """Ліміти позицій"""

    symbol: str
    max_position_size: float = Field(gt=0, description="Максимальний розмір позиції")
    max_leverage: float = Field(gt=0, le=10, description="Максимальне плече")
    stop_loss_pct: float = Field(gt=0, lt=1, description="Відсоток стоп-лосу")
    take_profit_pct: Optional[float] = Field(
        default=None, gt=0, description="Відсоток тейк-профіту"
    )


class PortfolioRisk(BaseModel):
    """Ризик портфеля"""

    total_exposure: float
    max_exposure: float
    risk_level: RiskLevel
    market_condition: MarketCondition
    active_positions: int
    utilization_pct: float = Field(ge=0, le=100)


class AdaptiveRiskManager:
    """
    Адаптивний менеджер ризиків

    Управляє ризиками на основі поточних ринкових умов,
    волатильності та термодинамічного стану системи.
    """

    def __init__(
        self,
        base_capital: float,
        risk_tolerance: float = 0.02,
        var_window: int = 252,
        volatility_window: int = 20,
        enable_tacl_integration: bool = True,
    ):
        """
        Ініціалізація менеджера ризиків

        Args:
            base_capital: Базовий капітал
            risk_tolerance: Толерантність до ризику (0.01 = 1%)
            var_window: Вікно для розрахунку VaR
            volatility_window: Вікно для розрахунку волатильності
            enable_tacl_integration: Увімкнути інтеграцію з TACL
        """
        self.base_capital = base_capital
        self.risk_tolerance = risk_tolerance
        self.var_window = var_window
        self.volatility_window = volatility_window
        self.enable_tacl_integration = enable_tacl_integration

        # Внутрішній стан
        self._position_limits: Dict[str, PositionLimit] = {}
        self._returns_history: List[float] = []
        self._volatility_multiplier = 1.0
        self._current_market_condition = MarketCondition.NORMAL

    def _validate_market_state_returns(self, market_state: MarketState) -> np.ndarray:
        if "returns" not in market_state:
            raise KeyError("market_state missing required key: 'returns'")
        returns = np.asarray(market_state["returns"], dtype=float)
        if returns.ndim != 1:
            raise ValueError("market_state['returns'] must be a 1D array")
        return returns

    def _validate_market_state_symbol(self, market_state: MarketState) -> str:
        symbol = market_state.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("market_state['symbol'] must be a non-empty string")
        return symbol

    def _validate_market_state_price(self, market_state: MarketState) -> float:
        if "price" not in market_state:
            raise KeyError("market_state missing required key: 'price'")
        price = float(market_state["price"])
        if price <= 0:
            raise ValueError("market_state['price'] must be positive")
        return price

    def _validate_market_state_volatility(
        self, market_state: MarketState, returns: np.ndarray
    ) -> float:
        if "volatility" in market_state and market_state["volatility"] is not None:
            volatility = float(market_state["volatility"])
            if volatility < 0:
                raise ValueError("market_state['volatility'] must be non-negative")
            return volatility
        if len(returns) > 1:
            return float(np.std(returns, ddof=1))
        return 0.0

    def calculate_var_cvar(
        self, returns: np.ndarray, confidence_level: float = 0.95
    ) -> Tuple[float, float]:
        """
        Розрахунок VaR та CVaR

        Args:
            returns: Масив повернень
            confidence_level: Рівень довіри

        Returns:
            Кортеж (VaR, CVaR)
        """
        if len(returns) < 10:
            return 0.0, 0.0

        sorted_returns = np.sort(returns)
        index = int((1 - confidence_level) * len(sorted_returns))

        var = -sorted_returns[index] if index < len(sorted_returns) else 0.0
        cvar = -sorted_returns[:index].mean() if index > 0 else var

        return var, cvar

    def assess_market_condition(self, volatility: float) -> MarketCondition:
        """
        Оцінка ринкових умов на основі волатильності

        Args:
            volatility: Поточна волатильність

        Returns:
            Стан ринку
        """
        # Нормалізована волатильність (річна)
        annual_vol = volatility * np.sqrt(252)

        if annual_vol < 0.15:
            return MarketCondition.CALM
        elif annual_vol < 0.25:
            return MarketCondition.NORMAL
        elif annual_vol < 0.40:
            return MarketCondition.VOLATILE
        else:
            return MarketCondition.EXTREME

    def _calculate_risk_metrics_from_returns(self, returns: np.ndarray) -> RiskMetrics:
        """
        Розрахунок всіх метрик ризику

        Args:
            returns: Масив повернень

        Returns:
            Об'єкт RiskMetrics
        """
        if len(returns) < 2:
            return RiskMetrics(
                var_95=0.0,
                cvar_95=0.0,
                var_99=0.0,
                cvar_99=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                max_drawdown=0.0,
                volatility=0.0,
                timestamp=datetime.now(),
            )

        # VaR та CVaR
        var_95, cvar_95 = self.calculate_var_cvar(returns, 0.95)
        var_99, cvar_99 = self.calculate_var_cvar(returns, 0.99)

        # Волатильність
        volatility = np.std(returns, ddof=1)

        # Sharpe Ratio
        mean_return = np.mean(returns)
        sharpe_ratio = mean_return / volatility if volatility > 0 else 0.0

        # Sortino Ratio
        downside_returns = returns[returns < 0]
        downside_std = np.std(downside_returns, ddof=1) if len(downside_returns) > 1 else volatility
        sortino_ratio = mean_return / downside_std if downside_std > 0 else 0.0

        # Maximum Drawdown
        cumulative = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = np.abs(np.min(drawdown))

        return RiskMetrics(
            var_95=var_95,
            cvar_95=cvar_95,
            var_99=var_99,
            cvar_99=cvar_99,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            volatility=volatility,
            timestamp=datetime.now(),
        )

    def calculate_risk_metrics(
        self, market_state_or_returns: Union[MarketState, np.ndarray]
    ) -> RiskMetrics:
        """
        Розрахунок всіх метрик ризику зі стандартного market_state.

        Args:
            market_state_or_returns: Стандартизований стан ринку або масив доходностей

        Returns:
            Об'єкт RiskMetrics
        """
        if isinstance(market_state_or_returns, dict):
            returns = self._validate_market_state_returns(market_state_or_returns)
        else:
            returns = np.asarray(market_state_or_returns, dtype=float)
            if returns.ndim != 1:
                raise ValueError("returns must be a 1D array")

        return self._calculate_risk_metrics_from_returns(returns)

    def update_position_limits(
        self,
        market_state_or_symbol: Union[MarketState, str],
        volatility: Optional[float] = None,
        market_condition: Optional[MarketCondition] = None,
    ) -> PositionLimit:
        """
        Оновлення лімітів позицій на основі волатильності

        Args:
            market_state_or_symbol: Стандартизований стан ринку або символ
            volatility: (опційно) волатильність для спрощеного виклику
            market_condition: Стан ринку (опційно)

        Returns:
            Оновлені ліміти позицій
        """
        if isinstance(market_state_or_symbol, dict):
            market_state = market_state_or_symbol
            symbol = self._validate_market_state_symbol(market_state)
            returns = self._validate_market_state_returns(market_state)
            volatility_value = self._validate_market_state_volatility(market_state, returns)
        else:
            symbol = str(market_state_or_symbol)
            if not symbol:
                raise ValueError("symbol must be a non-empty string")
            if volatility is None:
                raise ValueError("volatility must be provided when market_state is not supplied")
            volatility_value = float(volatility)
            if volatility_value < 0:
                raise ValueError("volatility must be non-negative")
            returns = np.array([], dtype=float)

        if market_condition is None:
            market_condition = self.assess_market_condition(volatility_value)

        # Базові ліміти
        base_position_size = self.base_capital * self.risk_tolerance

        # Коригування на основі ринкових умов
        condition_multipliers = {
            MarketCondition.CALM: 1.5,
            MarketCondition.NORMAL: 1.0,
            MarketCondition.VOLATILE: 0.6,
            MarketCondition.EXTREME: 0.3,
        }

        multiplier = condition_multipliers.get(market_condition, 1.0)

        # Динамічний розрахунок стоп-лосу
        # Більша волатильність = ширший стоп-лос
        annual_vol = volatility_value * np.sqrt(252)
        stop_loss_pct = min(0.05, max(0.01, annual_vol * 0.15))

        position_limit = PositionLimit(
            symbol=symbol,
            max_position_size=base_position_size * multiplier,
            max_leverage=2.0 / (1.0 + annual_vol),  # Менше плече при високій волатильності
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=stop_loss_pct * 2.0,  # 2:1 reward-to-risk
        )

        self._position_limits[symbol] = position_limit
        return position_limit

    def calculate_position_size(
        self,
        market_state_or_symbol: Union[MarketState, str],
        *,
        price: Optional[float] = None,
        volatility: Optional[float] = None,
        confidence: float = 1.0,
    ) -> float:
        """
        Розрахунок розміру позиції

        Args:
            market_state_or_symbol: Стандартизований стан ринку або символ
            price: Поточна ціна (потрібна для спрощеного виклику)
            volatility: Волатильність (опційно для спрощеного виклику)
            confidence: Рівень впевненості сигналу (0-1)

        Returns:
            Розмір позиції в базовій валюті
        """
        if isinstance(market_state_or_symbol, dict):
            market_state = market_state_or_symbol
            symbol = self._validate_market_state_symbol(market_state)
            price = self._validate_market_state_price(market_state)
            returns = self._validate_market_state_returns(market_state)
            volatility_value = self._validate_market_state_volatility(market_state, returns)
        else:
            symbol = str(market_state_or_symbol)
            if not symbol:
                raise ValueError("symbol must be a non-empty string")
            if price is None:
                raise ValueError("price must be provided when market_state is not supplied")
            price = float(price)
            if price <= 0:
                raise ValueError("price must be positive")
            volatility_value = float(volatility) if volatility is not None else 0.0
            if volatility_value < 0:
                raise ValueError("volatility must be non-negative")
            returns = np.array([], dtype=float)

        # Оновлюємо ліміти якщо необхідно
        if symbol not in self._position_limits:
            self.update_position_limits(symbol, volatility_value)

        limit = self._position_limits[symbol]

        # Базовий розмір з урахуванням впевненості
        base_size = limit.max_position_size * confidence

        # Коригування на основі волатільності
        vol_adjusted_size = base_size * self._volatility_multiplier

        # Перевірка лімітів
        max_allowed = min(
            vol_adjusted_size,
            limit.max_position_size,
            self.base_capital * 0.2,  # Максимум 20% капіталу в одній позиції
        )

        return max_allowed

    def update_from_market_state(self, market_state: MarketState) -> None:
        """
        Оновлення внутрішнього стану на основі standard market_state.

        Args:
            market_state: Стандартизований стан ринку
        """
        returns = self._validate_market_state_returns(market_state)
        self.update_from_returns(returns)

    def assess_portfolio_risk(
        self, positions: Dict[str, float], prices: Dict[str, float]
    ) -> PortfolioRisk:
        """
        Оцінка ризику портфеля

        Args:
            positions: Словник позицій {symbol: quantity}
            prices: Словник цін {symbol: price}

        Returns:
            Об'єкт PortfolioRisk
        """
        # Розрахунок загальної експозиції
        total_exposure = sum(abs(qty * prices.get(sym, 0.0)) for sym, qty in positions.items())

        # Максимальна дозволена експозиція
        max_exposure = self.base_capital * 2.0  # 200% з урахуванням плеча

        # Відсоток використання
        utilization_pct = (total_exposure / max_exposure) * 100 if max_exposure > 0 else 0.0

        # Визначення рівня ризику
        if utilization_pct < 30:
            risk_level = RiskLevel.LOW
        elif utilization_pct < 50:
            risk_level = RiskLevel.MODERATE
        elif utilization_pct < 70:
            risk_level = RiskLevel.ELEVATED
        elif utilization_pct < 90:
            risk_level = RiskLevel.HIGH
        else:
            risk_level = RiskLevel.CRITICAL

        return PortfolioRisk(
            total_exposure=total_exposure,
            max_exposure=max_exposure,
            risk_level=risk_level,
            market_condition=self._current_market_condition,
            active_positions=len(positions),
            utilization_pct=utilization_pct,
        )

    def should_reduce_risk(self, portfolio_risk: PortfolioRisk) -> bool:
        """
        Перевірка чи потрібно зменшити ризик

        Args:
            portfolio_risk: Ризик портфеля

        Returns:
            True якщо потрібно зменшити ризик
        """
        return (
            portfolio_risk.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
            or portfolio_risk.market_condition == MarketCondition.EXTREME
            or portfolio_risk.utilization_pct > 85
        )

    def update_from_returns(self, returns: np.ndarray) -> None:
        """
        Оновлення внутрішнього стану на основі повернень

        Args:
            returns: Масив нових повернень
        """
        self._returns_history.extend(returns.tolist())

        # Обмеження історії
        max_history = self.var_window * 2
        if len(self._returns_history) > max_history:
            self._returns_history = self._returns_history[-max_history:]

        # Оновлення волатільності
        if len(self._returns_history) >= self.volatility_window:
            recent_returns = np.array(self._returns_history[-self.volatility_window :])
            volatility = np.std(recent_returns, ddof=1)

            # Оновлення стану ринку
            self._current_market_condition = self.assess_market_condition(volatility)

            # Динамічна адаптація мультиплікатора волатильності
            # При високій волатильності зменшуємо розмір позицій
            base_vol = 0.01  # 1% денна волатільність як базова
            self._volatility_multiplier = min(1.5, max(0.5, base_vol / (volatility + 1e-8)))

    def get_risk_summary(self) -> Dict:
        """
        Отримання поточного стану ризику

        Returns:
            Словник з метриками ризику
        """
        if len(self._returns_history) < 10:
            return {
                "status": "insufficient_data",
                "market_condition": self._current_market_condition.value,
                "volatility_multiplier": self._volatility_multiplier,
                "position_limits_count": len(self._position_limits),
            }

        returns_array = np.array(self._returns_history)
        metrics = self._calculate_risk_metrics_from_returns(returns_array)

        return {
            "status": "active",
            "market_condition": self._current_market_condition.value,
            "volatility_multiplier": self._volatility_multiplier,
            "var_95": f"{metrics.var_95:.4f}",
            "cvar_95": f"{metrics.cvar_95:.4f}",
            "sharpe_ratio": f"{metrics.sharpe_ratio:.2f}",
            "max_drawdown": f"{metrics.max_drawdown:.2%}",
            "position_limits_count": len(self._position_limits),
        }
