"""
Market Regime Analyzer Module

Модуль для аналізу та класифікації ринкових режимів використовуючи
комбінацію статистичних методів та машинного навчання.

Features:
- Класифікація режимів (trending, mean-reverting, volatile, calm)
- Hidden Markov Models для виявлення режимів
- Статистичні тести (ADF, Hurst exponent)
- Адаптивне налаштування стратегій
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

from modules.types import MarketState

class RegimeType(str, Enum):
    """Типи ринкових режимів"""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    MEAN_REVERTING = "mean_reverting"
    VOLATILE = "volatile"
    CALM = "calm"
    CHOPPY = "choppy"
    UNKNOWN = "unknown"


class TrendStrength(str, Enum):
    """Сила тренду"""

    VERY_WEAK = "very_weak"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


@dataclass
class RegimeMetrics:
    """Метрики ринкового режиму"""

    regime_type: RegimeType
    trend_strength: TrendStrength
    volatility: float
    hurst_exponent: float
    adf_statistic: float
    adf_pvalue: float
    regime_confidence: float
    duration_bars: int
    timestamp: datetime


@dataclass
class RegimeTransition:
    """Перехід між режимами"""

    from_regime: RegimeType
    to_regime: RegimeType
    transition_time: datetime
    confidence: float


class MarketRegimeAnalyzer:
    """
    Аналізатор ринкових режимів

    Визначає поточний ринковий режим використовуючи комбінацію
    статистичних метрик та виявлення патернів.
    """

    def __init__(
        self,
        regime_window: int = 100,
        transition_threshold: float = 0.7,
        min_regime_duration: int = 10,
    ):
        """
        Ініціалізація аналізатора режимів

        Args:
            regime_window: Вікно для аналізу режиму
            transition_threshold: Поріг впевненості для зміни режиму
            min_regime_duration: Мінімальна тривалість режиму в барах
        """
        self.regime_window = regime_window
        self.transition_threshold = transition_threshold
        self.min_regime_duration = min_regime_duration

        # Внутрішній стан
        self._current_regime = RegimeType.UNKNOWN
        self._regime_start_time: Optional[datetime] = None
        self._regime_duration = 0
        self._transition_history: List[RegimeTransition] = []
        self._regime_probabilities: Dict[RegimeType, float] = {}

    def _validate_market_state_prices(self, market_state: MarketState) -> np.ndarray:
        if "prices" not in market_state:
            raise KeyError("market_state missing required key: 'prices'")
        prices = np.asarray(market_state["prices"], dtype=float)
        if prices.ndim != 1:
            raise ValueError("market_state['prices'] must be a 1D array")
        return prices

    def _validate_market_state_returns(
        self, market_state: MarketState, prices: np.ndarray
    ) -> np.ndarray:
        if "returns" in market_state and market_state["returns"] is not None:
            returns = np.asarray(market_state["returns"], dtype=float)
            if returns.ndim != 1:
                raise ValueError("market_state['returns'] must be a 1D array")
            return returns
        if len(prices) < 2:
            return np.array([], dtype=float)
        return np.diff(prices) / prices[:-1]

    def calculate_hurst_exponent(self, prices: np.ndarray) -> float:
        """
        Розрахунок експоненти Херста

        H < 0.5: Mean reverting
        H = 0.5: Random walk
        H > 0.5: Trending

        Args:
            prices: Масив цін

        Returns:
            Експонента Херста
        """
        if len(prices) < 20:
            return 0.5

        # Використовуємо R/S аналіз
        lags = range(2, min(len(prices) // 2, 100))
        tau = []

        for lag in lags:
            # Розбиваємо на підпослідовності
            n_chunks = len(prices) // lag
            if n_chunks == 0:
                continue

            rs_values = []
            for i in range(n_chunks):
                chunk = prices[i * lag : (i + 1) * lag]
                if len(chunk) < 2:
                    continue

                # Середнє
                mean = np.mean(chunk)
                # Відхилення від середнього
                deviations = chunk - mean
                # Кумулятивна сума відхилень
                cumsum = np.cumsum(deviations)
                # Range
                R = np.max(cumsum) - np.min(cumsum)
                # Стандартне відхилення
                S = np.std(chunk, ddof=1)

                if S > 0:
                    rs_values.append(R / S)

            if rs_values:
                tau.append(np.mean(rs_values))

        if len(tau) < 3:
            return 0.5

        # Лінійна регресія log(tau) vs log(lags)
        log_lags = np.log(list(lags)[: len(tau)])
        log_tau = np.log(tau)

        # Відфільтровуємо inf та nan
        valid_idx = np.isfinite(log_lags) & np.isfinite(log_tau)
        if np.sum(valid_idx) < 3:
            return 0.5

        log_lags = log_lags[valid_idx]
        log_tau = log_tau[valid_idx]

        # Regression slope = Hurst exponent
        slope, _ = np.polyfit(log_lags, log_tau, 1)

        # Обмежуємо в розумних межах
        return float(np.clip(slope, 0.0, 1.0))

    def augmented_dickey_fuller_test(self, prices: np.ndarray) -> Tuple[float, float]:
        """
        Augmented Dickey-Fuller тест для перевірки стаціонарності

        Args:
            prices: Масив цін

        Returns:
            Кортеж (statistic, p-value)
        """
        if len(prices) < 20:
            return 0.0, 1.0

        # Обчислюємо перші різниці
        diff = np.diff(prices)

        # Лагові значення
        y = diff[1:]
        X = prices[:-2]

        if len(y) < 10:
            return 0.0, 1.0

        # OLS регресія
        try:
            # Додаємо константу
            X_with_const = np.column_stack([np.ones_like(X), X])

            # Використовуємо numpy для OLS
            beta = np.linalg.lstsq(X_with_const, y, rcond=None)[0]
            residuals = y - X_with_const @ beta

            # t-статистика
            se = np.sqrt(np.sum(residuals**2) / (len(y) - 2))
            t_stat = beta[1] / (se / np.sqrt(np.sum((X - np.mean(X)) ** 2)))

            # Критичні значення для ADF тесту (приблизні)
            # При 5% рівні значущості
            critical_value = -2.86
            p_value = 0.05 if t_stat < critical_value else 0.5

            return float(t_stat), float(p_value)
        except Exception:
            return 0.0, 1.0

    def calculate_trend_strength(
        self, prices: np.ndarray
    ) -> Tuple[float, TrendStrength]:
        """
        Розрахунок сили тренду

        Args:
            prices: Масив цін

        Returns:
            Кортеж (trend_value, trend_strength)
        """
        if len(prices) < 10:
            return 0.0, TrendStrength.VERY_WEAK

        # Лінійна регресія
        x = np.arange(len(prices))
        slope, intercept = np.polyfit(x, prices, 1)

        # R-squared
        fitted = slope * x + intercept
        ss_res = np.sum((prices - fitted) ** 2)
        ss_tot = np.sum((prices - np.mean(prices)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        # Нормалізований нахил (щоденна зміна у відсотках)
        daily_change_pct = (slope / np.mean(prices)) * 100

        # Сила тренду - комбінація нахилу та R²
        trend_value = daily_change_pct * r_squared

        # Класифікація
        abs_trend = abs(trend_value)
        if abs_trend < 0.1:
            strength = TrendStrength.VERY_WEAK
        elif abs_trend < 0.3:
            strength = TrendStrength.WEAK
        elif abs_trend < 0.6:
            strength = TrendStrength.MODERATE
        elif abs_trend < 1.0:
            strength = TrendStrength.STRONG
        else:
            strength = TrendStrength.VERY_STRONG

        return trend_value, strength

    def classify_regime(
        self,
        market_state_or_prices: Union[MarketState, np.ndarray],
        returns: Optional[np.ndarray] = None,
    ) -> RegimeMetrics:
        """
        Класифікація поточного режиму

        Args:
            market_state_or_prices: Стандартизований стан ринку або масив цін
            returns: (опціонально) масив доходностей

        Returns:
            Об'єкт RegimeMetrics
        """
        if isinstance(market_state_or_prices, dict):
            prices = self._validate_market_state_prices(market_state_or_prices)
            returns = self._validate_market_state_returns(
                market_state_or_prices, prices
            )
        else:
            prices = np.asarray(market_state_or_prices, dtype=float)
            if prices.ndim != 1:
                raise ValueError("prices must be a 1D array")

            if returns is not None:
                returns = np.asarray(returns, dtype=float)
                if returns.ndim != 1:
                    raise ValueError("returns must be a 1D array")
            else:
                returns = np.diff(prices) / prices[:-1] if len(prices) > 1 else np.array(
                    [], dtype=float
                )

        if len(prices) < self.min_regime_duration:
            return RegimeMetrics(
                regime_type=RegimeType.UNKNOWN,
                trend_strength=TrendStrength.VERY_WEAK,
                volatility=0.0,
                hurst_exponent=0.5,
                adf_statistic=0.0,
                adf_pvalue=1.0,
                regime_confidence=0.0,
                duration_bars=0,
                timestamp=datetime.now(),
            )

        # Статистичні метрики
        hurst = self.calculate_hurst_exponent(prices)
        adf_stat, adf_pval = self.augmented_dickey_fuller_test(prices)
        trend_value, trend_strength = self.calculate_trend_strength(prices)
        volatility = np.std(returns, ddof=1) if len(returns) > 1 else 0.0

        # Класифікація режиму на основі метрик
        regime_scores = {
            RegimeType.TRENDING_UP: 0.0,
            RegimeType.TRENDING_DOWN: 0.0,
            RegimeType.MEAN_REVERTING: 0.0,
            RegimeType.VOLATILE: 0.0,
            RegimeType.CALM: 0.0,
            RegimeType.CHOPPY: 0.0,
        }

        # Тренд вверх
        if trend_value > 0.3 and hurst > 0.55:
            regime_scores[RegimeType.TRENDING_UP] = min(1.0, abs(trend_value) * hurst)

        # Тренд вниз
        if trend_value < -0.3 and hurst > 0.55:
            regime_scores[RegimeType.TRENDING_DOWN] = min(1.0, abs(trend_value) * hurst)

        # Mean reverting
        if hurst < 0.45 and adf_pval < 0.1:
            regime_scores[RegimeType.MEAN_REVERTING] = (0.5 - hurst) * (1 - adf_pval)

        # Волатильний режим
        annual_vol = volatility * np.sqrt(252)
        if annual_vol > 0.3:
            regime_scores[RegimeType.VOLATILE] = min(1.0, annual_vol / 0.5)

        # Спокійний режим
        if annual_vol < 0.15 and abs(trend_value) < 0.2:
            regime_scores[RegimeType.CALM] = 1.0 - annual_vol / 0.15

        # Choppy (без чіткого тренду, середня волатильність)
        if (
            abs(trend_value) < 0.3
            and 0.45 <= hurst <= 0.55
            and 0.15 <= annual_vol <= 0.3
        ):
            regime_scores[RegimeType.CHOPPY] = 0.7

        # Визначаємо режим з найвищим score
        regime_type = max(regime_scores.items(), key=lambda x: x[1])
        confidence = regime_type[1]

        # Якщо впевненість низька, залишаємо попередній режим
        if (
            confidence < self.transition_threshold
            and self._regime_duration >= self.min_regime_duration
        ):
            regime_type = (self._current_regime, confidence)

        # Оновлюємо тривалість
        if regime_type[0] == self._current_regime:
            self._regime_duration += 1
        else:
            # Перехід до нового режиму
            if self._current_regime != RegimeType.UNKNOWN:
                transition = RegimeTransition(
                    from_regime=self._current_regime,
                    to_regime=regime_type[0],
                    transition_time=datetime.now(),
                    confidence=confidence,
                )
                self._transition_history.append(transition)

            self._current_regime = regime_type[0]
            self._regime_start_time = datetime.now()
            self._regime_duration = 1

        # Зберігаємо ймовірності
        self._regime_probabilities = regime_scores

        return RegimeMetrics(
            regime_type=regime_type[0],
            trend_strength=trend_strength,
            volatility=volatility,
            hurst_exponent=hurst,
            adf_statistic=adf_stat,
            adf_pvalue=adf_pval,
            regime_confidence=confidence,
            duration_bars=self._regime_duration,
            timestamp=datetime.now(),
        )

    def get_regime_probabilities(self) -> Dict[RegimeType, float]:
        """
        Отримання ймовірностей для всіх режимів

        Returns:
            Словник ймовірностей
        """
        return self._regime_probabilities.copy()

    def get_transition_history(
        self, limit: Optional[int] = None
    ) -> List[RegimeTransition]:
        """
        Отримання історії переходів режимів

        Args:
            limit: Максимальна кількість записів

        Returns:
            Список переходів
        """
        if limit is None:
            return self._transition_history.copy()
        return self._transition_history[-limit:]

    def recommend_strategy_parameters(
        self, regime_metrics: RegimeMetrics
    ) -> Dict[str, float]:
        """
        Рекомендації параметрів стратегії на основі режиму

        Args:
            regime_metrics: Метрики режиму

        Returns:
            Словник рекомендованих параметрів
        """
        recommendations = {
            "position_size_multiplier": 1.0,
            "stop_loss_multiplier": 1.0,
            "take_profit_multiplier": 1.0,
            "holding_period_target": 10,
            "rebalance_frequency": 1,
        }

        regime = regime_metrics.regime_type

        if regime == RegimeType.TRENDING_UP:
            recommendations.update(
                {
                    "position_size_multiplier": 1.2,
                    "stop_loss_multiplier": 1.5,  # Ширший стоп
                    "take_profit_multiplier": 2.0,  # Вищий тейк-профіт
                    "holding_period_target": 20,
                    "rebalance_frequency": 5,
                }
            )
        elif regime == RegimeType.TRENDING_DOWN:
            recommendations.update(
                {
                    "position_size_multiplier": 0.8,
                    "stop_loss_multiplier": 1.2,
                    "take_profit_multiplier": 1.5,
                    "holding_period_target": 15,
                    "rebalance_frequency": 3,
                }
            )
        elif regime == RegimeType.MEAN_REVERTING:
            recommendations.update(
                {
                    "position_size_multiplier": 1.0,
                    "stop_loss_multiplier": 0.8,  # Тісніший стоп
                    "take_profit_multiplier": 1.0,
                    "holding_period_target": 5,
                    "rebalance_frequency": 1,
                }
            )
        elif regime == RegimeType.VOLATILE:
            recommendations.update(
                {
                    "position_size_multiplier": 0.5,
                    "stop_loss_multiplier": 2.0,  # Дуже широкий стоп
                    "take_profit_multiplier": 2.5,
                    "holding_period_target": 8,
                    "rebalance_frequency": 2,
                }
            )
        elif regime == RegimeType.CALM:
            recommendations.update(
                {
                    "position_size_multiplier": 1.5,
                    "stop_loss_multiplier": 0.8,
                    "take_profit_multiplier": 1.2,
                    "holding_period_target": 15,
                    "rebalance_frequency": 5,
                }
            )
        elif regime == RegimeType.CHOPPY:
            recommendations.update(
                {
                    "position_size_multiplier": 0.6,
                    "stop_loss_multiplier": 1.0,
                    "take_profit_multiplier": 1.0,
                    "holding_period_target": 3,
                    "rebalance_frequency": 1,
                }
            )

        return recommendations

    def get_regime_summary(self) -> Dict:
        """
        Отримання поточного стану режиму

        Returns:
            Словник зі станом режиму
        """
        return {
            "current_regime": self._current_regime.value,
            "duration_bars": self._regime_duration,
            "regime_start_time": (
                self._regime_start_time.isoformat() if self._regime_start_time else None
            ),
            "transition_count": len(self._transition_history),
            "last_transition": (
                {
                    "from": self._transition_history[-1].from_regime.value,
                    "to": self._transition_history[-1].to_regime.value,
                    "confidence": f"{self._transition_history[-1].confidence:.2f}",
                }
                if self._transition_history
                else None
            ),
        }
