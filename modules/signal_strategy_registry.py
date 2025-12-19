"""
Signal Strategy Registry Module

Модуль для реєстрації, виявлення та валідації торгових стратегій.

Features:
- Автоматичне виявлення стратегій
- Валідація параметрів стратегій
- Управління життєвим циклом стратегій
- Версіювання та сумісність
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type

import numpy as np
import pandas as pd


class StrategyStatus(str, Enum):
    """Статус стратегії"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    TESTING = "testing"
    SUSPENDED = "suspended"


class StrategyCategory(str, Enum):
    """Категорія стратегії"""

    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    ARBITRAGE = "arbitrage"
    MARKET_MAKING = "market_making"
    STATISTICAL = "statistical"
    MACHINE_LEARNING = "machine_learning"
    HYBRID = "hybrid"


@dataclass
class StrategyMetadata:
    """Метадані стратегії"""

    name: str
    version: str
    category: StrategyCategory
    description: str
    author: str
    status: StrategyStatus = StrategyStatus.ACTIVE
    required_features: Set[str] = field(default_factory=set)
    supported_timeframes: Set[str] = field(default_factory=lambda: {"1d", "1h", "5m"})
    min_data_points: int = 100
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    tags: Set[str] = field(default_factory=set)


@dataclass
class StrategyParameter:
    """Параметр стратегії"""

    name: str
    param_type: Type
    default_value: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    description: str = ""
    required: bool = True


@dataclass
class StrategyValidationResult:
    """Результат валідації стратегії"""

    is_valid: bool
    errors: List[str]
    warnings: List[str]
    validated_at: datetime = field(default_factory=datetime.now)


class StrategyInterface:
    """Базовий інтерфейс для стратегій"""

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Генерація торгових сигналів"""
        raise NotImplementedError("Subclasses must implement generate_signals()")

    def validate_data(self, data: pd.DataFrame) -> bool:
        """Валідація вхідних даних"""
        return True

    def get_parameters(self) -> Dict[str, Any]:
        """Отримання параметрів стратегії"""
        return {}

    def update_parameters(self, params: Dict[str, Any]) -> None:
        """Оновлення параметрів стратегії"""
        pass


class SignalStrategyRegistry:
    """
    Реєстр торгових стратегій

    Централізований реєстр для управління стратегіями,
    їх валідації та виявлення.
    """

    def __init__(
        self,
        enable_auto_discovery: bool = True,
        strict_validation: bool = True,
    ):
        """
        Ініціалізація реєстру

        Args:
            enable_auto_discovery: Увімкнути автоматичне виявлення
            strict_validation: Строга валідація стратегій
        """
        self.enable_auto_discovery = enable_auto_discovery
        self.strict_validation = strict_validation

        # Реєстр стратегій
        self._strategies: Dict[str, Type[StrategyInterface]] = {}
        self._metadata: Dict[str, StrategyMetadata] = {}
        self._parameters: Dict[str, List[StrategyParameter]] = {}
        self._instances: Dict[str, StrategyInterface] = {}

        # Фабрики стратегій
        self._factories: Dict[str, Callable[..., StrategyInterface]] = {}

        # Валідатори
        self._validators: List[Callable[[Type[StrategyInterface]], bool]] = []

    def register(
        self,
        strategy_class: Type[StrategyInterface],
        metadata: StrategyMetadata,
        parameters: Optional[List[StrategyParameter]] = None,
        factory: Optional[Callable[..., StrategyInterface]] = None,
    ) -> bool:
        """
        Реєстрація стратегії

        Args:
            strategy_class: Клас стратегії
            metadata: Метадані стратегії
            parameters: Параметри стратегії
            factory: Фабрика для створення екземплярів

        Returns:
            True якщо успішно зареєстровано
        """
        strategy_name = metadata.name

        if strategy_name in self._strategies:
            raise ValueError(f"Strategy '{strategy_name}' is already registered")

        # Валідація стратегії
        if self.strict_validation:
            validation = self._validate_strategy_class(strategy_class)
            if not validation.is_valid:
                raise ValueError(
                    f"Strategy validation failed: {', '.join(validation.errors)}"
                )

        # Реєстрація
        self._strategies[strategy_name] = strategy_class
        self._metadata[strategy_name] = metadata
        self._parameters[strategy_name] = parameters or []

        if factory:
            self._factories[strategy_name] = factory
        else:
            self._factories[strategy_name] = lambda **kwargs: strategy_class(**kwargs)

        return True

    def unregister(self, strategy_name: str) -> bool:
        """
        Видалення стратегії з реєстру

        Args:
            strategy_name: Назва стратегії

        Returns:
            True якщо успішно видалено
        """
        if strategy_name not in self._strategies:
            return False

        del self._strategies[strategy_name]
        del self._metadata[strategy_name]
        del self._parameters[strategy_name]
        del self._factories[strategy_name]

        if strategy_name in self._instances:
            del self._instances[strategy_name]

        return True

    def get_strategy(
        self, strategy_name: str, **kwargs: Any
    ) -> Optional[StrategyInterface]:
        """
        Отримання екземпляра стратегії

        Args:
            strategy_name: Назва стратегії
            **kwargs: Параметри для ініціалізації

        Returns:
            Екземпляр стратегії або None
        """
        if strategy_name not in self._strategies:
            return None

        # Перевірка статусу
        metadata = self._metadata[strategy_name]
        if metadata.status == StrategyStatus.SUSPENDED:
            raise RuntimeError(f"Strategy '{strategy_name}' is suspended")

        # Створення екземпляра
        factory = self._factories[strategy_name]
        instance = factory(**kwargs)

        self._instances[strategy_name] = instance
        return instance

    def get_metadata(self, strategy_name: str) -> Optional[StrategyMetadata]:
        """
        Отримання метаданих стратегії

        Args:
            strategy_name: Назва стратегії

        Returns:
            Метадані або None
        """
        return self._metadata.get(strategy_name)

    def get_parameters(self, strategy_name: str) -> List[StrategyParameter]:
        """
        Отримання параметрів стратегії

        Args:
            strategy_name: Назва стратегії

        Returns:
            Список параметрів
        """
        return self._parameters.get(strategy_name, [])

    def list_strategies(
        self,
        category: Optional[StrategyCategory] = None,
        status: Optional[StrategyStatus] = None,
        tags: Optional[Set[str]] = None,
    ) -> List[str]:
        """
        Список зареєстрованих стратегій

        Args:
            category: Фільтр за категорією
            status: Фільтр за статусом
            tags: Фільтр за тегами

        Returns:
            Список назв стратегій
        """
        result = []

        for name, metadata in self._metadata.items():
            if category and metadata.category != category:
                continue
            if status and metadata.status != status:
                continue
            if tags and not tags.issubset(metadata.tags):
                continue
            result.append(name)

        return sorted(result)

    def update_status(
        self, strategy_name: str, status: StrategyStatus
    ) -> bool:
        """
        Оновлення статусу стратегії

        Args:
            strategy_name: Назва стратегії
            status: Новий статус

        Returns:
            True якщо успішно оновлено
        """
        if strategy_name not in self._metadata:
            return False

        self._metadata[strategy_name].status = status
        self._metadata[strategy_name].updated_at = datetime.now()

        return True

    def validate_strategy(
        self, strategy_name: str, data: pd.DataFrame
    ) -> StrategyValidationResult:
        """
        Валідація стратегії з тестовими даними

        Args:
            strategy_name: Назва стратегії
            data: Тестові дані

        Returns:
            Результат валідації
        """
        errors = []
        warnings = []

        if strategy_name not in self._strategies:
            errors.append(f"Strategy '{strategy_name}' not found")
            return StrategyValidationResult(
                is_valid=False, errors=errors, warnings=warnings
            )

        metadata = self._metadata[strategy_name]

        # Перевірка мінімальної кількості даних
        if len(data) < metadata.min_data_points:
            warnings.append(
                f"Data has {len(data)} points, "
                f"recommended minimum is {metadata.min_data_points}"
            )

        # Перевірка необхідних колонок
        required_cols = metadata.required_features
        missing_cols = required_cols - set(data.columns)
        if missing_cols:
            errors.append(f"Missing required columns: {missing_cols}")

        # Спроба генерації сигналів
        try:
            strategy = self.get_strategy(strategy_name)
            if strategy:
                signals = strategy.generate_signals(data)
                if signals.empty:
                    warnings.append("Strategy generated no signals")
        except Exception as e:
            errors.append(f"Signal generation failed: {str(e)}")

        return StrategyValidationResult(
            is_valid=len(errors) == 0, errors=errors, warnings=warnings
        )

    def _validate_strategy_class(
        self, strategy_class: Type[StrategyInterface]
    ) -> StrategyValidationResult:
        """
        Валідація класу стратегії

        Args:
            strategy_class: Клас стратегії

        Returns:
            Результат валідації
        """
        errors = []
        warnings = []

        # Перевірка базового класу
        if not issubclass(strategy_class, StrategyInterface):
            errors.append("Strategy must inherit from StrategyInterface")

        # Перевірка наявності методу generate_signals
        if not hasattr(strategy_class, "generate_signals"):
            errors.append("Strategy must implement generate_signals method")

        # Перевірка callable методів
        generate_signals = getattr(strategy_class, "generate_signals", None)
        if generate_signals and not callable(generate_signals):
            errors.append("generate_signals must be callable")

        # Додаткова валідація через зареєстровані валідатори
        for validator in self._validators:
            try:
                if not validator(strategy_class):
                    warnings.append(f"Custom validator failed: {validator.__name__}")
            except Exception as e:
                warnings.append(f"Validator error: {str(e)}")

        return StrategyValidationResult(
            is_valid=len(errors) == 0, errors=errors, warnings=warnings
        )

    def add_validator(
        self, validator: Callable[[Type[StrategyInterface]], bool]
    ) -> None:
        """
        Додавання валідатора стратегій

        Args:
            validator: Функція валідації
        """
        self._validators.append(validator)

    def get_summary(self) -> Dict:
        """
        Отримання загальної статистики реєстру

        Returns:
            Словник зі статистикою
        """
        status_counts = {}
        category_counts = {}

        for metadata in self._metadata.values():
            status = metadata.status.value
            category = metadata.category.value

            status_counts[status] = status_counts.get(status, 0) + 1
            category_counts[category] = category_counts.get(category, 0) + 1

        return {
            "total_strategies": len(self._strategies),
            "active_instances": len(self._instances),
            "by_status": status_counts,
            "by_category": category_counts,
            "validators_count": len(self._validators),
        }


# Приклад реалізації стратегії для демонстрації
class MomentumStrategy(StrategyInterface):
    """
    Momentum стратегія на основі ковзних середніх
    """

    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 30,
        signal_threshold: float = 0.02,
    ):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_threshold = signal_threshold

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Генерація сигналів на основі перетину MA"""
        if "close" not in data.columns:
            raise ValueError("Data must contain 'close' column")

        prices = data["close"].astype(float)

        fast_ma = prices.rolling(window=self.fast_period).mean()
        slow_ma = prices.rolling(window=self.slow_period).mean()

        # Розрахунок momentum
        momentum = (fast_ma - slow_ma) / slow_ma

        signals = np.where(
            momentum > self.signal_threshold,
            "Buy",
            np.where(momentum < -self.signal_threshold, "Sell", "Hold"),
        )

        return pd.DataFrame(
            {
                "timestamp": data.index,
                "signal": signals,
                "momentum": momentum,
                "confidence": np.abs(momentum),
            }
        )

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "signal_threshold": self.signal_threshold,
        }

    def update_parameters(self, params: Dict[str, Any]) -> None:
        if "fast_period" in params:
            self.fast_period = int(params["fast_period"])
        if "slow_period" in params:
            self.slow_period = int(params["slow_period"])
        if "signal_threshold" in params:
            self.signal_threshold = float(params["signal_threshold"])


class MeanReversionStrategy(StrategyInterface):
    """
    Mean Reversion стратегія на основі Bollinger Bands
    """

    def __init__(
        self,
        period: int = 20,
        std_dev: float = 2.0,
    ):
        self.period = period
        self.std_dev = std_dev

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Генерація сигналів на основі Bollinger Bands"""
        if "close" not in data.columns:
            raise ValueError("Data must contain 'close' column")

        prices = data["close"].astype(float)

        sma = prices.rolling(window=self.period).mean()
        std = prices.rolling(window=self.period).std()

        upper_band = sma + (std * self.std_dev)
        lower_band = sma - (std * self.std_dev)

        # Нормалізована позиція в каналі
        position = (prices - lower_band) / (upper_band - lower_band)

        signals = np.where(
            position > 0.95,
            "Sell",
            np.where(position < 0.05, "Buy", "Hold"),
        )

        confidence = np.where(
            signals == "Buy",
            1.0 - position,
            np.where(signals == "Sell", position, 0.5),
        )

        return pd.DataFrame(
            {
                "timestamp": data.index,
                "signal": signals,
                "band_position": position,
                "confidence": confidence,
            }
        )

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "period": self.period,
            "std_dev": self.std_dev,
        }

    def update_parameters(self, params: Dict[str, Any]) -> None:
        if "period" in params:
            self.period = int(params["period"])
        if "std_dev" in params:
            self.std_dev = float(params["std_dev"])


# Фабрика для створення глобального реєстру
_global_registry: Optional[SignalStrategyRegistry] = None


def get_strategy_registry() -> SignalStrategyRegistry:
    """
    Отримання глобального реєстру стратегій

    Returns:
        Глобальний екземпляр реєстру
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = SignalStrategyRegistry()

        # Реєстрація вбудованих стратегій
        _global_registry.register(
            MomentumStrategy,
            StrategyMetadata(
                name="momentum",
                version="1.0.0",
                category=StrategyCategory.MOMENTUM,
                description="Momentum strategy based on moving average crossover",
                author="TradePulse",
                required_features={"close"},
                tags={"trend", "momentum", "ma"},
            ),
            parameters=[
                StrategyParameter(
                    name="fast_period",
                    param_type=int,
                    default_value=10,
                    min_value=1,
                    max_value=100,
                    description="Fast moving average period",
                ),
                StrategyParameter(
                    name="slow_period",
                    param_type=int,
                    default_value=30,
                    min_value=2,
                    max_value=200,
                    description="Slow moving average period",
                ),
                StrategyParameter(
                    name="signal_threshold",
                    param_type=float,
                    default_value=0.02,
                    min_value=0.001,
                    max_value=0.2,
                    description="Threshold for signal generation",
                ),
            ],
        )

        _global_registry.register(
            MeanReversionStrategy,
            StrategyMetadata(
                name="mean_reversion",
                version="1.0.0",
                category=StrategyCategory.MEAN_REVERSION,
                description="Mean reversion strategy based on Bollinger Bands",
                author="TradePulse",
                required_features={"close"},
                tags={"reversion", "bollinger", "volatility"},
            ),
            parameters=[
                StrategyParameter(
                    name="period",
                    param_type=int,
                    default_value=20,
                    min_value=5,
                    max_value=100,
                    description="Lookback period for calculations",
                ),
                StrategyParameter(
                    name="std_dev",
                    param_type=float,
                    default_value=2.0,
                    min_value=0.5,
                    max_value=4.0,
                    description="Standard deviation multiplier for bands",
                ),
            ],
        )

    return _global_registry
