# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Data Quality Monitor Module

Модуль для моніторингу якості ринкових даних.

Features:
- Виявлення аномалій
- Перевірка повноти даних
- Валідація цінових даних
- Моніторинг затримок
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


class DataQualityIssue(str, Enum):
    """Типи проблем з якістю даних"""

    MISSING_DATA = "missing_data"
    STALE_DATA = "stale_data"
    PRICE_SPIKE = "price_spike"
    VOLUME_ANOMALY = "volume_anomaly"
    TIMESTAMP_GAP = "timestamp_gap"
    DUPLICATE_DATA = "duplicate_data"
    INVALID_VALUES = "invalid_values"
    OUT_OF_RANGE = "out_of_range"
    ZERO_VOLUME = "zero_volume"
    NEGATIVE_PRICE = "negative_price"


class IssueSeverity(str, Enum):
    """Рівень критичності проблеми"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class QualityIssue:
    """Проблема якості даних"""

    issue_id: str
    issue_type: DataQualityIssue
    severity: IssueSeverity
    symbol: str
    description: str
    detected_at: datetime = field(default_factory=datetime.now)
    affected_rows: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataQualityMetrics:
    """Метрики якості даних"""

    completeness: float  # Відсоток повних записів
    freshness: float  # Свіжість даних (1.0 = свіжі)
    validity: float  # Відсоток валідних значень
    consistency: float  # Відсоток консистентних записів
    uniqueness: float  # Відсоток унікальних записів
    overall_score: float  # Загальний скор якості


@dataclass
class SymbolHealthStatus:
    """Статус здоров'я символу"""

    symbol: str
    is_healthy: bool
    last_update: datetime
    issues_count: int
    quality_score: float
    staleness_seconds: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MonitorConfig:
    """Конфігурація монітора"""

    # Пороги для виявлення спайків
    price_spike_threshold: float = 0.1  # 10% зміна
    volume_spike_threshold: float = 5.0  # 5x від середнього

    # Пороги для свіжості
    stale_data_seconds: float = 60.0
    critical_stale_seconds: float = 300.0

    # Пороги для гепів
    max_gap_seconds: float = 120.0

    # Статистичні пороги
    z_score_threshold: float = 3.0

    # Мінімальні вимоги
    min_data_points: int = 10


class DataQualityMonitor:
    """
    Монітор якості даних

    Відстежує якість ринкових даних та виявляє аномалії.
    """

    def __init__(
        self,
        config: Optional[MonitorConfig] = None,
    ):
        """
        Ініціалізація монітора

        Args:
            config: Конфігурація монітора
        """
        self.config = config or MonitorConfig()

        # Історія даних для кожного символу
        self._data_history: Dict[str, pd.DataFrame] = {}

        # Останні оновлення
        self._last_updates: Dict[str, datetime] = {}

        # Статистика
        self._rolling_stats: Dict[str, Dict[str, float]] = {}

        # Виявлені проблеми
        self._issues: List[QualityIssue] = []
        self._issue_counter = 0

        # Конфігурація символів
        self._symbol_configs: Dict[str, Dict[str, Any]] = {}

    def check_data_point(
        self,
        symbol: str,
        timestamp: datetime,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        volume: float,
    ) -> List[QualityIssue]:
        """
        Перевірка окремої точки даних

        Args:
            symbol: Символ
            timestamp: Мітка часу
            open_price: Ціна відкриття
            high_price: Максимальна ціна
            low_price: Мінімальна ціна
            close_price: Ціна закриття
            volume: Об'єм

        Returns:
            Список виявлених проблем
        """
        issues = []

        # Валідація базових значень
        issues.extend(
            self._validate_basic_values(
                symbol, timestamp, open_price, high_price, low_price, close_price, volume
            )
        )

        # Перевірка OHLC логіки
        issues.extend(
            self._validate_ohlc_logic(symbol, open_price, high_price, low_price, close_price)
        )

        # Оновлення історії
        self._update_history(
            symbol, timestamp, open_price, high_price, low_price, close_price, volume
        )

        # Перевірка спайків ціни
        issues.extend(self._check_price_spikes(symbol, close_price))

        # Перевірка аномалій об'єму
        issues.extend(self._check_volume_anomalies(symbol, volume))

        # Перевірка гепів часу
        issues.extend(self._check_timestamp_gaps(symbol, timestamp))

        # Оновлення останнього часу
        self._last_updates[symbol] = timestamp

        # Збереження проблем
        self._issues.extend(issues)

        return issues

    def check_dataframe(
        self,
        symbol: str,
        data: pd.DataFrame,
    ) -> Tuple[DataQualityMetrics, List[QualityIssue]]:
        """
        Перевірка DataFrame з даними

        Args:
            symbol: Символ
            data: DataFrame з колонками open, high, low, close, volume

        Returns:
            Кортеж (метрики, список проблем)
        """
        issues = []

        if data.empty:
            issues.append(
                self._create_issue(
                    DataQualityIssue.MISSING_DATA,
                    IssueSeverity.CRITICAL,
                    symbol,
                    "Empty dataframe provided",
                )
            )
            return DataQualityMetrics(0, 0, 0, 0, 0, 0), issues

        # Перевірка необхідних колонок
        required_cols = {"open", "high", "low", "close", "volume"}
        available_cols = set(data.columns.str.lower())
        missing_cols = required_cols - available_cols

        if missing_cols:
            issues.append(
                self._create_issue(
                    DataQualityIssue.MISSING_DATA,
                    IssueSeverity.HIGH,
                    symbol,
                    f"Missing columns: {missing_cols}",
                )
            )

        # Нормалізація імен колонок
        data.columns = data.columns.str.lower()

        # Метрики якості
        completeness = self._calculate_completeness(data)
        freshness = self._calculate_freshness(data, symbol)
        validity = self._calculate_validity(data, symbol, issues)
        consistency = self._calculate_consistency(data, symbol, issues)
        uniqueness = self._calculate_uniqueness(data, symbol, issues)

        # Загальний скор
        weights = [0.25, 0.2, 0.25, 0.15, 0.15]
        overall_score = (
            completeness * weights[0]
            + freshness * weights[1]
            + validity * weights[2]
            + consistency * weights[3]
            + uniqueness * weights[4]
        )

        metrics = DataQualityMetrics(
            completeness=completeness,
            freshness=freshness,
            validity=validity,
            consistency=consistency,
            uniqueness=uniqueness,
            overall_score=overall_score,
        )

        # Збереження проблем
        self._issues.extend(issues)

        return metrics, issues

    def get_symbol_health(self, symbol: str) -> SymbolHealthStatus:
        """
        Отримання статусу здоров'я символу

        Args:
            symbol: Символ

        Returns:
            Статус здоров'я
        """
        last_update = self._last_updates.get(symbol, datetime.now())
        staleness = (datetime.now() - last_update).total_seconds()

        # Підрахунок проблем за останню годину
        recent_issues = [
            i
            for i in self._issues
            if i.symbol == symbol and (datetime.now() - i.detected_at).total_seconds() < 3600
        ]

        # Розрахунок якості
        quality_score = 1.0
        for issue in recent_issues:
            severity_penalty = {
                IssueSeverity.LOW: 0.05,
                IssueSeverity.MEDIUM: 0.1,
                IssueSeverity.HIGH: 0.2,
                IssueSeverity.CRITICAL: 0.4,
            }
            quality_score -= severity_penalty.get(issue.severity, 0.1)

        quality_score = max(0.0, quality_score)

        is_healthy = (
            staleness < self.config.stale_data_seconds
            and quality_score > 0.7
            and len(recent_issues) < 5
        )

        return SymbolHealthStatus(
            symbol=symbol,
            is_healthy=is_healthy,
            last_update=last_update,
            issues_count=len(recent_issues),
            quality_score=quality_score,
            staleness_seconds=staleness,
            metadata={
                "history_size": len(self._data_history.get(symbol, [])),
                "has_rolling_stats": symbol in self._rolling_stats,
            },
        )

    def check_staleness(self) -> Dict[str, float]:
        """
        Перевірка свіжості даних для всіх символів

        Returns:
            Словник {symbol: seconds_since_update}
        """
        now = datetime.now()
        staleness = {}

        for symbol, last_update in self._last_updates.items():
            staleness[symbol] = (now - last_update).total_seconds()

        return staleness

    def get_stale_symbols(self) -> List[str]:
        """
        Отримання списку символів зі застарілими даними

        Returns:
            Список символів
        """
        staleness = self.check_staleness()
        threshold = self.config.stale_data_seconds

        return [symbol for symbol, seconds in staleness.items() if seconds > threshold]

    def get_recent_issues(
        self,
        symbol: Optional[str] = None,
        severity: Optional[IssueSeverity] = None,
        limit: int = 100,
    ) -> List[QualityIssue]:
        """
        Отримання останніх проблем

        Args:
            symbol: Фільтр за символом
            severity: Фільтр за критичністю
            limit: Максимальна кількість

        Returns:
            Список проблем
        """
        issues = self._issues.copy()

        if symbol:
            issues = [i for i in issues if i.symbol == symbol]
        if severity:
            issues = [i for i in issues if i.severity == severity]

        issues = sorted(issues, key=lambda x: x.detected_at, reverse=True)
        return issues[:limit]

    def _validate_basic_values(
        self,
        symbol: str,
        timestamp: datetime,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        volume: float,
    ) -> List[QualityIssue]:
        """Валідація базових значень"""
        issues = []

        # Негативні ціни
        prices = {"open": open_price, "high": high_price, "low": low_price, "close": close_price}
        for name, price in prices.items():
            if price < 0:
                issues.append(
                    self._create_issue(
                        DataQualityIssue.NEGATIVE_PRICE,
                        IssueSeverity.CRITICAL,
                        symbol,
                        f"Negative {name} price: {price}",
                        metadata={"price_type": name, "value": price},
                    )
                )

        # Нульовий об'єм
        if volume == 0:
            issues.append(
                self._create_issue(
                    DataQualityIssue.ZERO_VOLUME,
                    IssueSeverity.LOW,
                    symbol,
                    "Zero volume detected",
                )
            )

        # Від'ємний об'єм
        if volume < 0:
            issues.append(
                self._create_issue(
                    DataQualityIssue.INVALID_VALUES,
                    IssueSeverity.CRITICAL,
                    symbol,
                    f"Negative volume: {volume}",
                )
            )

        # NaN/Inf значення
        all_values = [open_price, high_price, low_price, close_price, volume]
        if any(np.isnan(v) or np.isinf(v) for v in all_values):
            issues.append(
                self._create_issue(
                    DataQualityIssue.INVALID_VALUES,
                    IssueSeverity.HIGH,
                    symbol,
                    "NaN or Inf values detected",
                )
            )

        return issues

    def _validate_ohlc_logic(
        self,
        symbol: str,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
    ) -> List[QualityIssue]:
        """Валідація логіки OHLC"""
        issues = []

        # High повинен бути >= всіх інших
        if high_price < max(open_price, low_price, close_price):
            issues.append(
                self._create_issue(
                    DataQualityIssue.INVALID_VALUES,
                    IssueSeverity.MEDIUM,
                    symbol,
                    f"High ({high_price}) is not the highest value",
                    metadata={
                        "open": open_price,
                        "high": high_price,
                        "low": low_price,
                        "close": close_price,
                    },
                )
            )

        # Low повинен бути <= всіх інших
        if low_price > min(open_price, high_price, close_price):
            issues.append(
                self._create_issue(
                    DataQualityIssue.INVALID_VALUES,
                    IssueSeverity.MEDIUM,
                    symbol,
                    f"Low ({low_price}) is not the lowest value",
                )
            )

        return issues

    def _update_history(
        self,
        symbol: str,
        timestamp: datetime,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        volume: float,
    ) -> None:
        """Оновлення історії даних"""
        new_row = pd.DataFrame(
            {
                "timestamp": [timestamp],
                "open": [open_price],
                "high": [high_price],
                "low": [low_price],
                "close": [close_price],
                "volume": [volume],
            }
        )

        if symbol not in self._data_history:
            self._data_history[symbol] = new_row
        else:
            self._data_history[symbol] = pd.concat(
                [self._data_history[symbol], new_row], ignore_index=True
            )

            # Обмеження розміру історії
            max_history = 1000
            if len(self._data_history[symbol]) > max_history:
                self._data_history[symbol] = self._data_history[symbol].tail(max_history)

        # Оновлення статистики
        self._update_rolling_stats(symbol)

    def _update_rolling_stats(self, symbol: str) -> None:
        """Оновлення ковзної статистики"""
        if symbol not in self._data_history:
            return

        data = self._data_history[symbol]
        if len(data) < self.config.min_data_points:
            return

        self._rolling_stats[symbol] = {
            "price_mean": data["close"].mean(),
            "price_std": data["close"].std(),
            "volume_mean": data["volume"].mean(),
            "volume_std": data["volume"].std(),
        }

    def _check_price_spikes(self, symbol: str, current_price: float) -> List[QualityIssue]:
        """Перевірка спайків ціни"""
        issues = []

        if symbol not in self._rolling_stats:
            return issues

        stats = self._rolling_stats[symbol]
        if stats["price_std"] == 0:
            return issues

        z_score = abs(current_price - stats["price_mean"]) / stats["price_std"]

        if z_score > self.config.z_score_threshold:
            severity = IssueSeverity.HIGH if z_score > 5 else IssueSeverity.MEDIUM
            issues.append(
                self._create_issue(
                    DataQualityIssue.PRICE_SPIKE,
                    severity,
                    symbol,
                    f"Price spike detected: z-score={z_score:.2f}",
                    metadata={
                        "current_price": current_price,
                        "mean": stats["price_mean"],
                        "std": stats["price_std"],
                        "z_score": z_score,
                    },
                )
            )

        return issues

    def _check_volume_anomalies(self, symbol: str, current_volume: float) -> List[QualityIssue]:
        """Перевірка аномалій об'єму"""
        issues = []

        if symbol not in self._rolling_stats:
            return issues

        stats = self._rolling_stats[symbol]
        if stats["volume_mean"] == 0:
            return issues

        volume_ratio = current_volume / stats["volume_mean"]

        if volume_ratio > self.config.volume_spike_threshold:
            issues.append(
                self._create_issue(
                    DataQualityIssue.VOLUME_ANOMALY,
                    IssueSeverity.MEDIUM,
                    symbol,
                    f"Volume anomaly: {volume_ratio:.1f}x average",
                    metadata={
                        "current_volume": current_volume,
                        "mean_volume": stats["volume_mean"],
                        "ratio": volume_ratio,
                    },
                )
            )

        return issues

    def _check_timestamp_gaps(self, symbol: str, current_timestamp: datetime) -> List[QualityIssue]:
        """Перевірка гепів у часі"""
        issues = []

        if symbol not in self._last_updates:
            return issues

        last_update = self._last_updates[symbol]
        gap_seconds = (current_timestamp - last_update).total_seconds()

        if gap_seconds > self.config.max_gap_seconds:
            severity = (
                IssueSeverity.HIGH
                if gap_seconds > self.config.max_gap_seconds * 2
                else IssueSeverity.MEDIUM
            )
            issues.append(
                self._create_issue(
                    DataQualityIssue.TIMESTAMP_GAP,
                    severity,
                    symbol,
                    f"Timestamp gap: {gap_seconds:.0f} seconds",
                    metadata={
                        "gap_seconds": gap_seconds,
                        "last_update": last_update.isoformat(),
                        "current": current_timestamp.isoformat(),
                    },
                )
            )

        return issues

    def _calculate_completeness(self, data: pd.DataFrame) -> float:
        """Розрахунок повноти даних"""
        if data.empty:
            return 0.0

        total_cells = data.size
        non_null_cells = data.notna().sum().sum()

        return non_null_cells / total_cells if total_cells > 0 else 0.0

    def _calculate_freshness(self, data: pd.DataFrame, symbol: str) -> float:
        """Розрахунок свіжості даних"""
        if "timestamp" not in data.columns and data.index.name != "timestamp":
            return 1.0

        try:
            if "timestamp" in data.columns:
                last_timestamp = pd.to_datetime(data["timestamp"]).max()
            else:
                last_timestamp = data.index.max()

            staleness = (datetime.now() - last_timestamp).total_seconds()

            if staleness <= self.config.stale_data_seconds:
                return 1.0
            elif staleness >= self.config.critical_stale_seconds:
                return 0.0
            else:
                return 1.0 - (
                    (staleness - self.config.stale_data_seconds)
                    / (self.config.critical_stale_seconds - self.config.stale_data_seconds)
                )
        except Exception:
            return 1.0

    def _calculate_validity(
        self, data: pd.DataFrame, symbol: str, issues: List[QualityIssue]
    ) -> float:
        """Розрахунок валідності даних"""
        if data.empty:
            return 0.0

        total_rows = len(data)
        invalid_rows = 0

        # Перевірка негативних цін
        for col in ["open", "high", "low", "close"]:
            if col in data.columns:
                negatives = (data[col] < 0).sum()
                if negatives > 0:
                    invalid_rows += negatives
                    issues.append(
                        self._create_issue(
                            DataQualityIssue.NEGATIVE_PRICE,
                            IssueSeverity.CRITICAL,
                            symbol,
                            f"Found {negatives} negative {col} prices",
                            affected_rows=int(negatives),
                        )
                    )

        # Перевірка OHLC логіки
        if all(c in data.columns for c in ["open", "high", "low", "close"]):
            invalid_ohlc = (
                (data["high"] < data["low"])
                | (data["high"] < data["open"])
                | (data["high"] < data["close"])
                | (data["low"] > data["open"])
                | (data["low"] > data["close"])
            ).sum()

            if invalid_ohlc > 0:
                invalid_rows += invalid_ohlc
                issues.append(
                    self._create_issue(
                        DataQualityIssue.INVALID_VALUES,
                        IssueSeverity.HIGH,
                        symbol,
                        f"Found {invalid_ohlc} rows with invalid OHLC logic",
                        affected_rows=int(invalid_ohlc),
                    )
                )

        valid_rows = total_rows - invalid_rows
        return max(0.0, valid_rows / total_rows)

    def _calculate_consistency(
        self, data: pd.DataFrame, symbol: str, issues: List[QualityIssue]
    ) -> float:
        """Розрахунок консистентності даних"""
        if data.empty or "close" not in data.columns:
            return 1.0

        # Перевірка спайків
        if len(data) > 1:
            returns = data["close"].pct_change().dropna()
            extreme_returns = (returns.abs() > self.config.price_spike_threshold).sum()

            if extreme_returns > 0:
                issues.append(
                    self._create_issue(
                        DataQualityIssue.PRICE_SPIKE,
                        IssueSeverity.MEDIUM,
                        symbol,
                        f"Found {extreme_returns} price spikes",
                        affected_rows=int(extreme_returns),
                    )
                )

            return max(0.0, 1.0 - extreme_returns / len(returns))

        return 1.0

    def _calculate_uniqueness(
        self, data: pd.DataFrame, symbol: str, issues: List[QualityIssue]
    ) -> float:
        """Розрахунок унікальності даних"""
        if data.empty:
            return 1.0

        total_rows = len(data)
        duplicates = data.duplicated().sum()

        if duplicates > 0:
            issues.append(
                self._create_issue(
                    DataQualityIssue.DUPLICATE_DATA,
                    IssueSeverity.MEDIUM,
                    symbol,
                    f"Found {duplicates} duplicate rows",
                    affected_rows=int(duplicates),
                )
            )

        return max(0.0, (total_rows - duplicates) / total_rows)

    def _create_issue(
        self,
        issue_type: DataQualityIssue,
        severity: IssueSeverity,
        symbol: str,
        description: str,
        affected_rows: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> QualityIssue:
        """Створення нової проблеми"""
        self._issue_counter += 1
        return QualityIssue(
            issue_id=f"DQ_{self._issue_counter}",
            issue_type=issue_type,
            severity=severity,
            symbol=symbol,
            description=description,
            affected_rows=affected_rows,
            metadata=metadata or {},
        )

    def get_summary(self) -> Dict:
        """
        Отримання саммарі

        Returns:
            Словник зі статистикою
        """
        staleness = self.check_staleness()
        stale_count = len([s for s in staleness.values() if s > self.config.stale_data_seconds])

        recent_issues = self.get_recent_issues(limit=100)
        severity_counts = {}
        for issue in recent_issues:
            severity_counts[issue.severity.value] = severity_counts.get(issue.severity.value, 0) + 1

        return {
            "symbols_monitored": len(self._last_updates),
            "stale_symbols": stale_count,
            "total_issues": len(self._issues),
            "recent_issues": len(recent_issues),
            "issues_by_severity": severity_counts,
            "symbols_with_history": len(self._data_history),
            "symbols_with_stats": len(self._rolling_stats),
        }
