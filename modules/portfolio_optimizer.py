"""
Portfolio Optimizer Module

Модуль для оптимізації портфеля з різними методами оптимізації.

Features:
- Mean-Variance Optimization (Markowitz)
- Risk Parity
- Maximum Sharpe Ratio
- Minimum Variance
- Black-Litterman Model
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


class OptimizationMethod(str, Enum):
    """Методи оптимізації"""

    MEAN_VARIANCE = "mean_variance"
    RISK_PARITY = "risk_parity"
    MAX_SHARPE = "max_sharpe"
    MIN_VARIANCE = "min_variance"
    EQUAL_WEIGHT = "equal_weight"
    HIERARCHICAL_RISK_PARITY = "hierarchical_risk_parity"


class RebalanceFrequency(str, Enum):
    """Частота ребалансування"""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUALLY = "annually"


@dataclass
class OptimizationConstraints:
    """Обмеження оптимізації"""

    min_weight: float = 0.0
    max_weight: float = 1.0
    max_sector_weight: float = 0.4
    min_assets: int = 5
    max_assets: int = 50
    max_turnover: float = 0.5
    allow_short: bool = False


@dataclass
class AssetAllocation:
    """Алокація активу"""

    symbol: str
    weight: float
    expected_return: float
    volatility: float
    contribution_to_risk: float


@dataclass
class PortfolioResult:
    """Результат оптимізації портфеля"""

    allocations: List[AssetAllocation]
    expected_return: float
    volatility: float
    sharpe_ratio: float
    diversification_ratio: float
    effective_n: float
    optimization_method: OptimizationMethod
    optimized_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskContribution:
    """Внесок у ризик"""

    symbol: str
    marginal_contribution: float
    percentage_contribution: float
    standalone_risk: float


class PortfolioOptimizer:
    """
    Оптимізатор портфеля

    Реалізує різні методи оптимізації для побудови
    ефективних портфелів.
    """

    def __init__(
        self,
        risk_free_rate: float = 0.02,
        constraints: Optional[OptimizationConstraints] = None,
        annualization_factor: int = 252,
    ):
        """
        Ініціалізація оптимізатора

        Args:
            risk_free_rate: Безризикова ставка
            constraints: Обмеження оптимізації
            annualization_factor: Фактор анналізації (252 для денних даних)
        """
        self.risk_free_rate = risk_free_rate
        self.constraints = constraints or OptimizationConstraints()
        self.annualization_factor = annualization_factor

        self._last_result: Optional[PortfolioResult] = None
        self._covariance_matrix: Optional[np.ndarray] = None
        self._expected_returns: Optional[np.ndarray] = None

    def optimize(
        self,
        returns: pd.DataFrame,
        method: OptimizationMethod = OptimizationMethod.MAX_SHARPE,
        expected_returns: Optional[np.ndarray] = None,
    ) -> PortfolioResult:
        """
        Оптимізація портфеля

        Args:
            returns: DataFrame з поверненнями активів
            method: Метод оптимізації
            expected_returns: Очікувані повернення (опціонально)

        Returns:
            Результат оптимізації
        """
        # Розрахунок ковариаційної матриці
        self._covariance_matrix = returns.cov().values * self.annualization_factor

        # Розрахунок очікуваних повернень
        if expected_returns is None:
            self._expected_returns = (
                returns.mean().values * self.annualization_factor
            )
        else:
            self._expected_returns = expected_returns

        assets = returns.columns.tolist()
        n_assets = len(assets)

        # Вибір методу оптимізації
        if method == OptimizationMethod.EQUAL_WEIGHT:
            weights = self._equal_weight(n_assets)
        elif method == OptimizationMethod.MIN_VARIANCE:
            weights = self._minimum_variance()
        elif method == OptimizationMethod.MAX_SHARPE:
            weights = self._maximum_sharpe()
        elif method == OptimizationMethod.RISK_PARITY:
            weights = self._risk_parity()
        elif method == OptimizationMethod.MEAN_VARIANCE:
            weights = self._mean_variance(target_return=None)
        else:
            weights = self._equal_weight(n_assets)

        # Застосування обмежень
        weights = self._apply_constraints(weights)

        # Розрахунок характеристик портфеля
        portfolio_return = np.dot(weights, self._expected_returns)
        portfolio_volatility = np.sqrt(
            np.dot(weights.T, np.dot(self._covariance_matrix, weights))
        )
        sharpe_ratio = (
            (portfolio_return - self.risk_free_rate) / portfolio_volatility
            if portfolio_volatility > 0
            else 0.0
        )

        # Розрахунок диверсифікації
        asset_volatilities = np.sqrt(np.diag(self._covariance_matrix))
        weighted_avg_volatility = np.dot(weights, asset_volatilities)
        diversification_ratio = (
            weighted_avg_volatility / portfolio_volatility
            if portfolio_volatility > 0
            else 1.0
        )

        # Effective N
        effective_n = 1.0 / np.sum(weights**2) if np.sum(weights**2) > 0 else 0.0

        # Внесок кожного активу у ризик
        risk_contributions = self._calculate_risk_contributions(weights)

        # Створення алокацій
        allocations = []
        for i, asset in enumerate(assets):
            allocations.append(
                AssetAllocation(
                    symbol=asset,
                    weight=float(weights[i]),
                    expected_return=float(self._expected_returns[i]),
                    volatility=float(asset_volatilities[i]),
                    contribution_to_risk=float(risk_contributions[i]),
                )
            )

        result = PortfolioResult(
            allocations=allocations,
            expected_return=float(portfolio_return),
            volatility=float(portfolio_volatility),
            sharpe_ratio=float(sharpe_ratio),
            diversification_ratio=float(diversification_ratio),
            effective_n=float(effective_n),
            optimization_method=method,
            metadata={
                "n_assets": n_assets,
                "risk_free_rate": self.risk_free_rate,
                "annualization_factor": self.annualization_factor,
            },
        )

        self._last_result = result
        return result

    def _equal_weight(self, n_assets: int) -> np.ndarray:
        """Рівномірні ваги"""
        return np.ones(n_assets) / n_assets

    def _minimum_variance(self) -> np.ndarray:
        """Мінімальна дисперсія"""
        cov_inv = np.linalg.pinv(self._covariance_matrix)
        ones = np.ones(len(cov_inv))
        weights = cov_inv @ ones
        weights = weights / np.sum(weights)
        return weights

    def _maximum_sharpe(self) -> np.ndarray:
        """Максимальний коефіцієнт Шарпа"""
        excess_returns = self._expected_returns - self.risk_free_rate

        # Проста реалізація через аналітичне рішення
        try:
            cov_inv = np.linalg.pinv(self._covariance_matrix)
            weights = cov_inv @ excess_returns
            weights_sum = np.sum(weights)
            if weights_sum > 0:
                weights = weights / weights_sum
            else:
                weights = self._minimum_variance()
        except Exception:
            weights = self._minimum_variance()

        return weights

    def _risk_parity(self) -> np.ndarray:
        """
        Risk Parity - рівний внесок у ризик

        Кожен актив вносить однаковий відсоток у загальний ризик портфеля.
        """
        n = len(self._covariance_matrix)

        # Ітеративний алгоритм
        weights = np.ones(n) / n
        max_iterations = 1000
        tolerance = 1e-8

        for _ in range(max_iterations):
            # Розрахунок marginal risk contributions
            portfolio_vol = np.sqrt(
                np.dot(weights.T, np.dot(self._covariance_matrix, weights))
            )
            if portfolio_vol < 1e-10:
                break

            marginal_risk = np.dot(self._covariance_matrix, weights) / portfolio_vol

            # Цільовий внесок (рівний для всіх)
            target_contribution = portfolio_vol / n

            # Оновлення ваг
            new_weights = target_contribution / (marginal_risk + 1e-10)
            new_weights = new_weights / np.sum(new_weights)

            # Перевірка збіжності
            if np.max(np.abs(new_weights - weights)) < tolerance:
                weights = new_weights
                break

            weights = new_weights

        return weights

    def _mean_variance(
        self, target_return: Optional[float] = None
    ) -> np.ndarray:
        """
        Mean-Variance Optimization (Markowitz)

        Args:
            target_return: Цільове повернення (якщо None - максимальний Sharpe)

        Returns:
            Оптимальні ваги
        """
        if target_return is None:
            return self._maximum_sharpe()

        n = len(self._expected_returns)

        try:
            cov_inv = np.linalg.pinv(self._covariance_matrix)
            ones = np.ones(n)

            # Розрахунок констант
            A = np.dot(ones.T, np.dot(cov_inv, ones))
            B = np.dot(ones.T, np.dot(cov_inv, self._expected_returns))
            C = np.dot(
                self._expected_returns.T,
                np.dot(cov_inv, self._expected_returns),
            )

            # Лагранжевські мультиплікатори
            D = A * C - B * B
            if abs(D) < 1e-10:
                return self._minimum_variance()

            lambda1 = (C - B * target_return) / D
            lambda2 = (A * target_return - B) / D

            # Оптимальні ваги
            weights = np.dot(cov_inv, lambda1 * ones + lambda2 * self._expected_returns)
        except Exception:
            weights = self._minimum_variance()

        return weights

    def _calculate_risk_contributions(self, weights: np.ndarray) -> np.ndarray:
        """
        Розрахунок внеску кожного активу у ризик

        Args:
            weights: Ваги активів

        Returns:
            Масив внесків у ризик
        """
        portfolio_vol = np.sqrt(
            np.dot(weights.T, np.dot(self._covariance_matrix, weights))
        )

        if portfolio_vol < 1e-10:
            return np.zeros_like(weights)

        marginal_risk = np.dot(self._covariance_matrix, weights) / portfolio_vol
        risk_contributions = weights * marginal_risk

        # Нормалізація до відсотків
        total_contribution = np.sum(risk_contributions)
        if total_contribution > 0:
            risk_contributions = risk_contributions / total_contribution

        return risk_contributions

    def _apply_constraints(self, weights: np.ndarray) -> np.ndarray:
        """
        Застосування обмежень до ваг

        Args:
            weights: Початкові ваги

        Returns:
            Ваги після застосування обмежень
        """
        constraints = self.constraints

        # Мінімальні та максимальні ваги
        if not constraints.allow_short:
            weights = np.maximum(weights, 0.0)

        weights = np.clip(weights, constraints.min_weight, constraints.max_weight)

        # Нормалізація до 100%
        weight_sum = np.sum(weights)
        if weight_sum > 0:
            weights = weights / weight_sum
        else:
            weights = np.ones_like(weights) / len(weights)

        return weights

    def efficient_frontier(
        self,
        returns: pd.DataFrame,
        n_points: int = 50,
    ) -> pd.DataFrame:
        """
        Побудова ефективної границі

        Args:
            returns: DataFrame з поверненнями
            n_points: Кількість точок

        Returns:
            DataFrame з точками ефективної границі
        """
        # Розрахунок ковариаційної матриці
        self._covariance_matrix = returns.cov().values * self.annualization_factor
        self._expected_returns = returns.mean().values * self.annualization_factor

        # Діапазон цільових повернень
        min_return = np.min(self._expected_returns)
        max_return = np.max(self._expected_returns)
        target_returns = np.linspace(min_return, max_return, n_points)

        frontier_points = []

        for target in target_returns:
            try:
                weights = self._mean_variance(target_return=target)
                weights = self._apply_constraints(weights)

                portfolio_return = np.dot(weights, self._expected_returns)
                portfolio_vol = np.sqrt(
                    np.dot(weights.T, np.dot(self._covariance_matrix, weights))
                )
                sharpe = (
                    (portfolio_return - self.risk_free_rate) / portfolio_vol
                    if portfolio_vol > 0
                    else 0.0
                )

                frontier_points.append(
                    {
                        "target_return": target,
                        "expected_return": portfolio_return,
                        "volatility": portfolio_vol,
                        "sharpe_ratio": sharpe,
                    }
                )
            except Exception:
                continue

        return pd.DataFrame(frontier_points)

    def backtest_allocation(
        self,
        returns: pd.DataFrame,
        allocation: PortfolioResult,
    ) -> Dict[str, float]:
        """
        Бектест алокації

        Args:
            returns: Історичні повернення
            allocation: Результат оптимізації

        Returns:
            Словник з метриками
        """
        # Ваги з алокації
        weights = np.array([a.weight for a in allocation.allocations])
        symbols = [a.symbol for a in allocation.allocations]

        # Фільтрація колонок
        available_symbols = [s for s in symbols if s in returns.columns]
        if not available_symbols:
            return {"error": "No matching symbols"}

        filtered_returns = returns[available_symbols]
        filtered_weights = np.array(
            [weights[symbols.index(s)] for s in available_symbols]
        )
        filtered_weights = filtered_weights / np.sum(filtered_weights)

        # Портфельні повернення
        portfolio_returns = filtered_returns @ filtered_weights

        # Метрики
        total_return = (1 + portfolio_returns).prod() - 1
        annualized_return = (
            (1 + total_return) ** (self.annualization_factor / len(portfolio_returns))
            - 1
        )
        volatility = portfolio_returns.std() * np.sqrt(self.annualization_factor)
        sharpe = (
            (annualized_return - self.risk_free_rate) / volatility
            if volatility > 0
            else 0.0
        )

        # Maximum Drawdown
        cumulative = (1 + portfolio_returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()

        # Sortino Ratio
        downside_returns = portfolio_returns[portfolio_returns < 0]
        downside_std = (
            downside_returns.std() * np.sqrt(self.annualization_factor)
            if len(downside_returns) > 0
            else volatility
        )
        sortino = (
            (annualized_return - self.risk_free_rate) / downside_std
            if downside_std > 0
            else 0.0
        )

        return {
            "total_return": float(total_return),
            "annualized_return": float(annualized_return),
            "volatility": float(volatility),
            "sharpe_ratio": float(sharpe),
            "sortino_ratio": float(sortino),
            "max_drawdown": float(max_drawdown),
            "calmar_ratio": float(
                annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0.0
            ),
        }

    def get_rebalancing_trades(
        self,
        current_allocation: Dict[str, float],
        target_allocation: PortfolioResult,
        portfolio_value: float,
    ) -> Dict[str, float]:
        """
        Розрахунок ребалансувальних угод

        Args:
            current_allocation: Поточна алокація {symbol: weight}
            target_allocation: Цільова алокація
            portfolio_value: Вартість портфеля

        Returns:
            Словник {symbol: trade_value} (позитивні - купити, негативні - продати)
        """
        trades = {}

        # Цільові ваги
        target_weights = {a.symbol: a.weight for a in target_allocation.allocations}

        # Всі символи
        all_symbols = set(current_allocation.keys()) | set(target_weights.keys())

        for symbol in all_symbols:
            current_weight = current_allocation.get(symbol, 0.0)
            target_weight = target_weights.get(symbol, 0.0)

            weight_diff = target_weight - current_weight
            trade_value = weight_diff * portfolio_value

            if abs(trade_value) > 1.0:  # Мінімальний розмір угоди
                trades[symbol] = float(trade_value)

        return trades

    def get_summary(self) -> Dict:
        """
        Отримання поточного стану оптимізатора

        Returns:
            Словник зі станом
        """
        summary = {
            "risk_free_rate": self.risk_free_rate,
            "annualization_factor": self.annualization_factor,
            "constraints": {
                "min_weight": self.constraints.min_weight,
                "max_weight": self.constraints.max_weight,
                "allow_short": self.constraints.allow_short,
            },
        }

        if self._last_result:
            summary["last_optimization"] = {
                "method": self._last_result.optimization_method.value,
                "n_assets": len(self._last_result.allocations),
                "expected_return": f"{self._last_result.expected_return:.2%}",
                "volatility": f"{self._last_result.volatility:.2%}",
                "sharpe_ratio": f"{self._last_result.sharpe_ratio:.2f}",
                "optimized_at": self._last_result.optimized_at.isoformat(),
            }

        return summary
