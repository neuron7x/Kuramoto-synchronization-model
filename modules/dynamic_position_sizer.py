"""
Dynamic Position Sizer Module

Модуль для динамічного розрахунку розміру позицій з урахуванням
ризику, волатильності, впевненості сигналу та Kelly Criterion.

Features:
- Kelly Criterion з fractional Kelly
- Адаптивний розмір на основі волатильності
- Інтеграція з ризик-менеджером
- Врахування кореляцій портфеля
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Optional

import numpy as np


class SizingMethod(str, Enum):
    """Методи визначення розміру позиції"""

    FIXED = "fixed"
    KELLY = "kelly"
    FRACTIONAL_KELLY = "fractional_kelly"
    VOLATILITY_ADJUSTED = "volatility_adjusted"
    RISK_PARITY = "risk_parity"
    ADAPTIVE = "adaptive"


@dataclass
class PositionSizeResult:
    """Результат розрахунку розміру позиції"""

    symbol: str
    recommended_size: float
    max_size: float
    min_size: float
    sizing_method: SizingMethod
    confidence: float
    risk_adjusted_size: float
    kelly_fraction: float
    volatility_adjustment: float
    timestamp: datetime


class DynamicPositionSizer:
    """
    Динамічний розрахунок розміру позицій

    Використовує комбінацію методів для оптимального
    визначення розміру позиції з урахуванням ризику.
    """

    def __init__(
        self,
        base_capital: float,
        default_method: SizingMethod = SizingMethod.ADAPTIVE,
        kelly_fraction: float = 0.25,
        max_position_pct: float = 0.1,
        min_position_pct: float = 0.01,
        volatility_target: float = 0.15,
    ):
        """
        Ініціалізація position sizer

        Args:
            base_capital: Базовий капітал
            default_method: Метод за замовчуванням
            kelly_fraction: Фракція Kelly (0.25 = 25% від повного Kelly)
            max_position_pct: Максимальний розмір позиції (% від капіталу)
            min_position_pct: Мінімальний розмір позиції (% від капіталу)
            volatility_target: Цільова волатільність портфеля
        """
        self.base_capital = base_capital
        self.default_method = default_method
        self.kelly_fraction = kelly_fraction
        self.max_position_pct = max_position_pct
        self.min_position_pct = min_position_pct
        self.volatility_target = volatility_target

        # Статистика для адаптації
        self._win_rate: Dict[str, float] = {}
        self._avg_win: Dict[str, float] = {}
        self._avg_loss: Dict[str, float] = {}
        self._trade_count: Dict[str, int] = {}

    def calculate_kelly_size(
        self, win_rate: float, avg_win: float, avg_loss: float, fractional: bool = True
    ) -> float:
        """
        Розрахунок Kelly Criterion

        f* = (p * b - q) / b
        де:
        p = ймовірність виграшу
        q = ймовірність програшу = 1 - p
        b = avg_win / avg_loss

        Args:
            win_rate: Ймовірність виграшу (0-1)
            avg_win: Середній виграш
            avg_loss: Середній програш (позитивне число)
            fractional: Використовувати fractional Kelly

        Returns:
            Рекомендована фракція капіталу
        """
        if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
            return 0.0

        p = win_rate
        q = 1 - p
        b = avg_win / avg_loss

        # Kelly criterion
        kelly = (p * b - q) / b

        # Обмежуємо в розумних межах
        kelly = max(0.0, min(kelly, 0.5))  # Максимум 50% капіталу

        # Fractional Kelly для зменшення ризику
        if fractional:
            kelly *= self.kelly_fraction

        return kelly

    def calculate_volatility_adjusted_size(
        self, volatility: float, base_size: float
    ) -> float:
        """
        Коригування розміру на основі волатільності

        Args:
            volatility: Поточна волатільність активу
            base_size: Базовий розмір позиції

        Returns:
            Скоригований розмір
        """
        if volatility <= 0:
            return base_size

        # Розрахунок adjustment factor
        # Вища волатільність = менший розмір
        vol_adjustment = self.volatility_target / (volatility * np.sqrt(252))
        vol_adjustment = np.clip(vol_adjustment, 0.3, 2.0)

        return float(base_size * vol_adjustment)

    def calculate_risk_parity_size(
        self, symbol: str, volatility: float, portfolio_volatilities: Dict[str, float]
    ) -> float:
        """
        Risk Parity - рівний ризик для всіх позицій

        Args:
            symbol: Символ інструменту
            volatility: Волатільність активу
            portfolio_volatilities: Волатільності всіх активів у портфелі

        Returns:
            Розмір позиції
        """
        if not portfolio_volatilities or volatility <= 0:
            return self.base_capital * self.max_position_pct

        # Інверсна волатільність
        inv_vol = 1.0 / volatility
        total_inv_vol = sum(1.0 / v for v in portfolio_volatilities.values() if v > 0)

        if total_inv_vol <= 0:
            return self.base_capital * self.max_position_pct

        # Ваги пропорційні інверсній волатільності
        weight = inv_vol / total_inv_vol

        # Розмір позиції
        size = self.base_capital * weight

        # Обмеження
        max_size = self.base_capital * self.max_position_pct
        min_size = self.base_capital * self.min_position_pct

        return float(np.clip(size, min_size, max_size))

    def calculate_adaptive_size(
        self,
        symbol: str,
        price: float,
        volatility: float,
        confidence: float,
        win_rate: Optional[float] = None,
        avg_win: Optional[float] = None,
        avg_loss: Optional[float] = None,
    ) -> PositionSizeResult:
        """
        Адаптивний розрахунок розміру - комбінація всіх методів

        Args:
            symbol: Символ інструменту
            price: Поточна ціна
            volatility: Волатільність
            confidence: Впевненість сигналу (0-1)
            win_rate: Історичний win rate (опційно)
            avg_win: Середній виграш (опційно)
            avg_loss: Середній програш (опційно)

        Returns:
            PositionSizeResult з деталями розрахунку
        """
        # Базовий розмір
        base_size = self.base_capital * self.max_position_pct

        # 1. Kelly criterion якщо є історичні дані
        kelly_size = base_size
        kelly_frac = 0.0
        if win_rate is not None and avg_win is not None and avg_loss is not None:
            kelly_frac = self.calculate_kelly_size(
                win_rate, avg_win, avg_loss, fractional=True
            )
            kelly_size = self.base_capital * kelly_frac
        elif (
            symbol in self._win_rate
            and symbol in self._avg_win
            and symbol in self._avg_loss
        ):
            # Використовуємо накопичену статистику
            kelly_frac = self.calculate_kelly_size(
                self._win_rate[symbol],
                self._avg_win[symbol],
                self._avg_loss[symbol],
                fractional=True,
            )
            kelly_size = self.base_capital * kelly_frac

        # 2. Коригування на волатільність
        vol_adjusted_size = self.calculate_volatility_adjusted_size(
            volatility, base_size
        )

        # 3. Коригування на впевненість сигналу
        confidence_adjusted = vol_adjusted_size * confidence

        # 4. Комбінуємо Kelly та volatility-adjusted
        # Беремо мінімум для консервативності
        if kelly_frac > 0:
            combined_size = min(kelly_size, confidence_adjusted)
        else:
            combined_size = confidence_adjusted

        # 5. Застосовуємо обмеження
        max_size = self.base_capital * self.max_position_pct
        min_size = self.base_capital * self.min_position_pct

        recommended_size = np.clip(combined_size, min_size, max_size)

        # Розрахунок volatility adjustment factor
        vol_adjustment = vol_adjusted_size / base_size if base_size > 0 else 1.0

        return PositionSizeResult(
            symbol=symbol,
            recommended_size=recommended_size,
            max_size=max_size,
            min_size=min_size,
            sizing_method=SizingMethod.ADAPTIVE,
            confidence=confidence,
            risk_adjusted_size=confidence_adjusted,
            kelly_fraction=kelly_frac,
            volatility_adjustment=vol_adjustment,
            timestamp=datetime.now(),
        )

    def calculate_size(
        self,
        symbol: str,
        price: float,
        volatility: float,
        confidence: float = 1.0,
        method: Optional[SizingMethod] = None,
        **kwargs,
    ) -> PositionSizeResult:
        """
        Основний метод розрахунку розміру позиції

        Args:
            symbol: Символ інструменту
            price: Поточна ціна
            volatility: Волатільність
            confidence: Впевненість сигналу (0-1)
            method: Метод розрахунку (якщо None, використовується default)
            **kwargs: Додаткові параметри для специфічних методів

        Returns:
            PositionSizeResult
        """
        if method is None:
            method = self.default_method

        if method == SizingMethod.ADAPTIVE:
            return self.calculate_adaptive_size(
                symbol,
                price,
                volatility,
                confidence,
                kwargs.get("win_rate"),
                kwargs.get("avg_win"),
                kwargs.get("avg_loss"),
            )

        # Інші методи
        base_size = self.base_capital * self.max_position_pct

        if method == SizingMethod.FIXED:
            recommended_size = base_size * confidence

        elif method == SizingMethod.VOLATILITY_ADJUSTED:
            recommended_size = (
                self.calculate_volatility_adjusted_size(volatility, base_size)
                * confidence
            )

        elif method == SizingMethod.KELLY or method == SizingMethod.FRACTIONAL_KELLY:
            win_rate = kwargs.get("win_rate", self._win_rate.get(symbol, 0.5))
            avg_win = kwargs.get("avg_win", self._avg_win.get(symbol, 0.02))
            avg_loss = kwargs.get("avg_loss", self._avg_loss.get(symbol, 0.01))

            kelly_frac = self.calculate_kelly_size(
                win_rate,
                avg_win,
                avg_loss,
                fractional=(method == SizingMethod.FRACTIONAL_KELLY),
            )
            recommended_size = self.base_capital * kelly_frac * confidence

        elif method == SizingMethod.RISK_PARITY:
            portfolio_vols = kwargs.get("portfolio_volatilities", {})
            recommended_size = (
                self.calculate_risk_parity_size(symbol, volatility, portfolio_vols)
                * confidence
            )

        else:
            recommended_size = base_size * confidence

        # Обмеження
        max_size = self.base_capital * self.max_position_pct
        min_size = self.base_capital * self.min_position_pct
        recommended_size = np.clip(recommended_size, min_size, max_size)

        return PositionSizeResult(
            symbol=symbol,
            recommended_size=recommended_size,
            max_size=max_size,
            min_size=min_size,
            sizing_method=method,
            confidence=confidence,
            risk_adjusted_size=recommended_size,
            kelly_fraction=0.0,
            volatility_adjustment=1.0,
            timestamp=datetime.now(),
        )

    def update_statistics(self, symbol: str, trade_result: float, is_win: bool) -> None:
        """
        Оновлення статистики для адаптивного розрахунку

        Args:
            symbol: Символ інструменту
            trade_result: Результат трейду (% return)
            is_win: Чи був трейд прибутковим
        """
        # Ініціалізація якщо потрібно
        if symbol not in self._trade_count:
            self._trade_count[symbol] = 0
            self._win_rate[symbol] = 0.5
            self._avg_win[symbol] = 0.0
            self._avg_loss[symbol] = 0.0

        # Оновлення count
        self._trade_count[symbol] += 1
        n = self._trade_count[symbol]

        # Оновлення win rate (експоненційна ковзна середня)
        alpha = 2.0 / (n + 1) if n < 100 else 0.1
        current_win = 1.0 if is_win else 0.0
        self._win_rate[symbol] = (
            alpha * current_win + (1 - alpha) * self._win_rate[symbol]
        )

        # Оновлення середніх виграшів/програшів
        if is_win:
            if self._avg_win[symbol] == 0:
                self._avg_win[symbol] = abs(trade_result)
            else:
                self._avg_win[symbol] = (
                    alpha * abs(trade_result) + (1 - alpha) * self._avg_win[symbol]
                )
        else:
            if self._avg_loss[symbol] == 0:
                self._avg_loss[symbol] = abs(trade_result)
            else:
                self._avg_loss[symbol] = (
                    alpha * abs(trade_result) + (1 - alpha) * self._avg_loss[symbol]
                )

    def get_statistics(self, symbol: str) -> Dict:
        """
        Отримання статистики для символу

        Args:
            symbol: Символ інструменту

        Returns:
            Словник зі статистикою
        """
        if symbol not in self._trade_count:
            return {
                "trade_count": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "expectancy": 0.0,
            }

        win_rate = self._win_rate[symbol]
        avg_win = self._avg_win[symbol]
        avg_loss = self._avg_loss[symbol]

        # Математичне очікування
        expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss

        return {
            "trade_count": self._trade_count[symbol],
            "win_rate": f"{win_rate:.2%}",
            "avg_win": f"{avg_win:.4f}",
            "avg_loss": f"{avg_loss:.4f}",
            "expectancy": f"{expectancy:.4f}",
        }

    def update_capital(self, new_capital: float) -> None:
        """
        Оновлення базового капіталу

        Args:
            new_capital: Новий базовий капітал
        """
        self.base_capital = max(0.0, new_capital)

    def get_summary(self) -> Dict:
        """
        Отримання загальної інформації

        Returns:
            Словник з інформацією про sizer
        """
        return {
            "base_capital": f"${self.base_capital:,.2f}",
            "default_method": self.default_method.value,
            "kelly_fraction": f"{self.kelly_fraction:.2%}",
            "max_position_pct": f"{self.max_position_pct:.2%}",
            "min_position_pct": f"{self.min_position_pct:.2%}",
            "volatility_target": f"{self.volatility_target:.2%}",
            "tracked_symbols": len(self._trade_count),
            "total_trades": sum(self._trade_count.values()),
        }
