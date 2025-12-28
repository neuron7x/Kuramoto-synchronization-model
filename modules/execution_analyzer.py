"""
Execution Analyzer Module

Модуль для аналізу якості виконання торгових ордерів.

Features:
- Аналіз slippage
- Вимірювання latency
- Fill rate analysis
- Market impact estimation
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np

from modules.types import MarketState

class ExecutionSide(str, Enum):
    """Сторона виконання"""

    BUY = "buy"
    SELL = "sell"


class ExecutionQuality(str, Enum):
    """Якість виконання"""

    EXCELLENT = "excellent"
    GOOD = "good"
    AVERAGE = "average"
    POOR = "poor"
    VERY_POOR = "very_poor"


@dataclass
class ExecutionRecord:
    """Запис виконання"""

    execution_id: str
    order_id: str
    symbol: str
    side: ExecutionSide
    quantity: float
    expected_price: float
    executed_price: float
    order_created_at: datetime
    execution_time: datetime
    venue: str = "default"
    fees: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SlippageMetrics:
    """Метрики slippage"""

    absolute_slippage: float  # В одиницях ціни
    relative_slippage: float  # У відсотках
    slippage_bps: float  # В базисних пунктах
    direction: str  # "favorable" або "adverse"


@dataclass
class LatencyMetrics:
    """Метрики затримки"""

    order_to_execution_ms: float
    market_data_latency_ms: float
    total_latency_ms: float


@dataclass
class FillMetrics:
    """Метрики заповнення"""

    fill_rate: float  # Відсоток заповнення
    partial_fills: int
    average_fill_size: float
    time_to_fill_seconds: float


@dataclass
class MarketImpactMetrics:
    """Метрики впливу на ринок"""

    temporary_impact: float
    permanent_impact: float
    realized_impact: float
    participation_rate: float


@dataclass
class ExecutionAnalysis:
    """Повний аналіз виконання"""

    execution_id: str
    symbol: str
    slippage: SlippageMetrics
    latency: LatencyMetrics
    quality: ExecutionQuality
    quality_score: float  # 0-100
    cost_analysis: Dict[str, float]
    recommendations: List[str]
    analyzed_at: datetime = field(default_factory=datetime.now)


@dataclass
class VenueStatistics:
    """Статистика venue"""

    venue: str
    total_executions: int
    average_slippage_bps: float
    average_latency_ms: float
    fill_rate: float
    quality_score: float


@dataclass
class SymbolStatistics:
    """Статистика по символу"""

    symbol: str
    total_executions: int
    total_volume: float
    average_slippage_bps: float
    buy_slippage_bps: float
    sell_slippage_bps: float
    average_latency_ms: float


class ExecutionAnalyzer:
    """
    Аналізатор виконання ордерів

    Аналізує якість виконання та надає рекомендації.
    """

    def __init__(
        self,
        slippage_threshold_bps: float = 10.0,
        latency_threshold_ms: float = 100.0,
        market_data_provider: Optional[Any] = None,
    ):
        """
        Ініціалізація аналізатора

        Args:
            slippage_threshold_bps: Поріг slippage в бп
            latency_threshold_ms: Поріг latency в мс
            market_data_provider: Провайдер ринкових даних
        """
        self.slippage_threshold_bps = slippage_threshold_bps
        self.latency_threshold_ms = latency_threshold_ms
        self.market_data_provider = market_data_provider

        # Історія виконань
        self._executions: List[ExecutionRecord] = []

        # Статистика по venue
        self._venue_stats: Dict[str, Dict[str, Any]] = {}

        # Статистика по символам
        self._symbol_stats: Dict[str, Dict[str, Any]] = {}

    def _validate_market_state_latency(self, market_state: MarketState) -> float:
        if "market_data_latency_ms" not in market_state:
            raise KeyError(
                "market_state missing required key: 'market_data_latency_ms'"
            )
        market_data_latency_ms = float(market_state["market_data_latency_ms"])
        if market_data_latency_ms < 0:
            raise ValueError("market_state['market_data_latency_ms'] must be >= 0")
        return market_data_latency_ms

    def record_execution(
        self,
        execution: ExecutionRecord,
        market_state: Optional[MarketState] = None,
    ) -> ExecutionAnalysis:
        """
        Запис та аналіз виконання

        Args:
            execution: Запис виконання
            market_state: Стандартизований стан ринку (опційно)

        Returns:
            Аналіз виконання
        """
        self._executions.append(execution)

        # Аналіз
        analysis = self.analyze_execution(execution, market_state=market_state)

        # Оновлення статистики
        self._update_venue_stats(execution, analysis)
        self._update_symbol_stats(execution, analysis)

        return analysis

    def analyze_execution(
        self, execution: ExecutionRecord, market_state: Optional[MarketState] = None
    ) -> ExecutionAnalysis:
        """
        Аналіз окремого виконання

        Args:
            execution: Запис виконання
            market_state: Стандартизований стан ринку (опційно)

        Returns:
            Аналіз виконання
        """
        # Slippage
        slippage = self._calculate_slippage(execution)

        # Latency
        latency = self._calculate_latency(execution, market_state=market_state)

        # Якість
        quality_score = self._calculate_quality_score(slippage, latency)
        quality = self._classify_quality(quality_score)

        # Аналіз витрат
        cost_analysis = self._analyze_costs(execution, slippage)

        # Рекомендації
        recommendations = self._generate_recommendations(
            execution, slippage, latency, quality_score
        )

        return ExecutionAnalysis(
            execution_id=execution.execution_id,
            symbol=execution.symbol,
            slippage=slippage,
            latency=latency,
            quality=quality,
            quality_score=quality_score,
            cost_analysis=cost_analysis,
            recommendations=recommendations,
        )

    def analyze_batch(
        self,
        executions: List[ExecutionRecord],
    ) -> Dict[str, Any]:
        """
        Аналіз пакету виконань

        Args:
            executions: Список виконань

        Returns:
            Агрегований аналіз
        """
        if not executions:
            return {"error": "No executions to analyze"}

        analyses = [self.analyze_execution(e) for e in executions]

        # Агрегація
        slippages_bps = [a.slippage.slippage_bps for a in analyses]
        latencies_ms = [a.latency.total_latency_ms for a in analyses]
        quality_scores = [a.quality_score for a in analyses]

        # Статистика по стороні
        buy_slippages = [
            a.slippage.slippage_bps
            for a, e in zip(analyses, executions)
            if e.side == ExecutionSide.BUY
        ]
        sell_slippages = [
            a.slippage.slippage_bps
            for a, e in zip(analyses, executions)
            if e.side == ExecutionSide.SELL
        ]

        # Загальна вартість slippage
        total_slippage_cost = sum(
            a.cost_analysis.get("slippage_cost", 0) for a in analyses
        )

        return {
            "total_executions": len(executions),
            "slippage": {
                "mean_bps": float(np.mean(slippages_bps)),
                "median_bps": float(np.median(slippages_bps)),
                "std_bps": float(np.std(slippages_bps)),
                "max_bps": float(np.max(slippages_bps)),
                "min_bps": float(np.min(slippages_bps)),
                "buy_mean_bps": float(np.mean(buy_slippages)) if buy_slippages else 0.0,
                "sell_mean_bps": float(np.mean(sell_slippages)) if sell_slippages else 0.0,
            },
            "latency": {
                "mean_ms": float(np.mean(latencies_ms)),
                "median_ms": float(np.median(latencies_ms)),
                "p95_ms": float(np.percentile(latencies_ms, 95)),
                "p99_ms": float(np.percentile(latencies_ms, 99)),
                "max_ms": float(np.max(latencies_ms)),
            },
            "quality": {
                "mean_score": float(np.mean(quality_scores)),
                "excellent_count": sum(1 for a in analyses if a.quality == ExecutionQuality.EXCELLENT),
                "good_count": sum(1 for a in analyses if a.quality == ExecutionQuality.GOOD),
                "average_count": sum(1 for a in analyses if a.quality == ExecutionQuality.AVERAGE),
                "poor_count": sum(1 for a in analyses if a.quality == ExecutionQuality.POOR),
                "very_poor_count": sum(1 for a in analyses if a.quality == ExecutionQuality.VERY_POOR),
            },
            "costs": {
                "total_slippage_cost": total_slippage_cost,
                "total_fees": sum(e.fees for e in executions),
            },
        }

    def get_venue_statistics(self) -> List[VenueStatistics]:
        """
        Отримання статистики по venue

        Returns:
            Список статистик
        """
        result = []

        for venue, stats in self._venue_stats.items():
            if stats["count"] == 0:
                continue

            result.append(
                VenueStatistics(
                    venue=venue,
                    total_executions=stats["count"],
                    average_slippage_bps=stats["total_slippage_bps"] / stats["count"],
                    average_latency_ms=stats["total_latency_ms"] / stats["count"],
                    fill_rate=stats.get("fill_rate", 1.0),
                    quality_score=stats["total_quality_score"] / stats["count"],
                )
            )

        return sorted(result, key=lambda x: x.quality_score, reverse=True)

    def get_symbol_statistics(self) -> List[SymbolStatistics]:
        """
        Отримання статистики по символам

        Returns:
            Список статистик
        """
        result = []

        for symbol, stats in self._symbol_stats.items():
            if stats["count"] == 0:
                continue

            result.append(
                SymbolStatistics(
                    symbol=symbol,
                    total_executions=stats["count"],
                    total_volume=stats["total_volume"],
                    average_slippage_bps=stats["total_slippage_bps"] / stats["count"],
                    buy_slippage_bps=(
                        stats["buy_slippage_bps"] / stats["buy_count"]
                        if stats["buy_count"] > 0
                        else 0.0
                    ),
                    sell_slippage_bps=(
                        stats["sell_slippage_bps"] / stats["sell_count"]
                        if stats["sell_count"] > 0
                        else 0.0
                    ),
                    average_latency_ms=stats["total_latency_ms"] / stats["count"],
                )
            )

        return sorted(result, key=lambda x: x.total_volume, reverse=True)

    def estimate_market_impact(
        self,
        symbol: str,
        quantity: float,
        side: ExecutionSide,
        average_daily_volume: Optional[float] = None,
        volatility: Optional[float] = None,
    ) -> MarketImpactMetrics:
        """
        Оцінка впливу на ринок

        Args:
            symbol: Символ
            quantity: Кількість
            side: Сторона
            average_daily_volume: Середній денний об'єм
            volatility: Волатильність

        Returns:
            Метрики впливу на ринок
        """
        # Якщо немає ADV, використовуємо історичні дані
        if average_daily_volume is None:
            symbol_stats = self._symbol_stats.get(symbol, {})
            average_daily_volume = symbol_stats.get("average_volume", quantity * 100)

        if average_daily_volume <= 0:
            average_daily_volume = quantity * 100

        # Participation rate
        participation_rate = quantity / average_daily_volume

        # Волатильність за замовчуванням
        if volatility is None:
            volatility = 0.02  # 2% за замовчуванням

        # Модель впливу на ринок (спрощена квадратична модель)
        # Temporary impact = volatility * sqrt(participation_rate)
        temporary_impact = volatility * np.sqrt(participation_rate)

        # Permanent impact = 0.5 * temporary_impact (типово)
        permanent_impact = 0.5 * temporary_impact

        # Realized impact - на основі історичних даних
        symbol_stats = self._symbol_stats.get(symbol, {})
        historical_slippage = symbol_stats.get("total_slippage_bps", 0) / max(
            symbol_stats.get("count", 1), 1
        )
        realized_impact = historical_slippage / 10000  # Конвертація з bps

        return MarketImpactMetrics(
            temporary_impact=float(temporary_impact),
            permanent_impact=float(permanent_impact),
            realized_impact=float(realized_impact),
            participation_rate=float(participation_rate),
        )

    def get_execution_history(
        self,
        symbol: Optional[str] = None,
        venue: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[ExecutionRecord]:
        """
        Отримання історії виконань

        Args:
            symbol: Фільтр за символом
            venue: Фільтр за venue
            start_time: Початок періоду
            end_time: Кінець періоду
            limit: Максимальна кількість

        Returns:
            Список виконань
        """
        executions = self._executions.copy()

        if symbol:
            executions = [e for e in executions if e.symbol == symbol]
        if venue:
            executions = [e for e in executions if e.venue == venue]
        if start_time:
            executions = [e for e in executions if e.execution_time >= start_time]
        if end_time:
            executions = [e for e in executions if e.execution_time <= end_time]

        executions = sorted(executions, key=lambda e: e.execution_time, reverse=True)
        return executions[:limit]

    def get_daily_report(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Отримання денного звіту

        Args:
            date: Дата (за замовчуванням - сьогодні)

        Returns:
            Денний звіт
        """
        if date is None:
            date = datetime.now()

        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        daily_executions = [
            e
            for e in self._executions
            if start_of_day <= e.execution_time < end_of_day
        ]

        if not daily_executions:
            return {
                "date": date.date().isoformat(),
                "total_executions": 0,
                "message": "No executions for this day",
            }

        batch_analysis = self.analyze_batch(daily_executions)

        # Топ символів
        symbol_volumes: Dict[str, float] = {}
        for e in daily_executions:
            volume = e.quantity * e.executed_price
            symbol_volumes[e.symbol] = symbol_volumes.get(e.symbol, 0) + volume

        top_symbols = sorted(
            symbol_volumes.items(), key=lambda x: x[1], reverse=True
        )[:5]

        return {
            "date": date.date().isoformat(),
            "total_executions": len(daily_executions),
            "total_volume": sum(
                e.quantity * e.executed_price for e in daily_executions
            ),
            "analysis": batch_analysis,
            "top_symbols": [
                {"symbol": s, "volume": v} for s, v in top_symbols
            ],
        }

    def _calculate_slippage(self, execution: ExecutionRecord) -> SlippageMetrics:
        """Розрахунок slippage"""
        price_diff = execution.executed_price - execution.expected_price

        # Для покупки позитивний slippage = погано
        # Для продажу негативний slippage = погано
        if execution.side == ExecutionSide.BUY:
            adverse_slippage = price_diff
        else:
            adverse_slippage = -price_diff

        absolute_slippage = abs(price_diff)
        relative_slippage = (
            absolute_slippage / execution.expected_price
            if execution.expected_price > 0
            else 0.0
        )
        slippage_bps = relative_slippage * 10000

        direction = "adverse" if adverse_slippage > 0 else "favorable"

        return SlippageMetrics(
            absolute_slippage=float(absolute_slippage),
            relative_slippage=float(relative_slippage),
            slippage_bps=float(slippage_bps) if adverse_slippage > 0 else float(-slippage_bps),
            direction=direction,
        )

    def _calculate_latency(
        self,
        execution: ExecutionRecord,
        market_state: Optional[MarketState] = None,
    ) -> LatencyMetrics:
        """Розрахунок затримки"""
        order_to_execution_ms = (
            execution.execution_time - execution.order_created_at
        ).total_seconds() * 1000

        # Market data latency (якщо є в metadata)
        if market_state is not None:
            market_data_latency_ms = self._validate_market_state_latency(market_state)
        else:
            market_data_latency_ms = execution.metadata.get("market_data_latency_ms", 0.0)

        total_latency_ms = order_to_execution_ms

        return LatencyMetrics(
            order_to_execution_ms=float(order_to_execution_ms),
            market_data_latency_ms=float(market_data_latency_ms),
            total_latency_ms=float(total_latency_ms),
        )

    def _calculate_quality_score(
        self, slippage: SlippageMetrics, latency: LatencyMetrics
    ) -> float:
        """Розрахунок якості виконання (0-100)"""
        # Slippage score (50% ваги)
        slippage_penalty = min(abs(slippage.slippage_bps) / self.slippage_threshold_bps, 1.0)
        slippage_score = (1 - slippage_penalty) * 50

        # Latency score (50% ваги)
        latency_penalty = min(latency.total_latency_ms / self.latency_threshold_ms, 1.0)
        latency_score = (1 - latency_penalty) * 50

        # Бонус за favorable slippage
        if slippage.direction == "favorable":
            slippage_score = min(slippage_score + 10, 50)

        return max(0, min(100, slippage_score + latency_score))

    def _classify_quality(self, score: float) -> ExecutionQuality:
        """Класифікація якості"""
        if score >= 90:
            return ExecutionQuality.EXCELLENT
        elif score >= 75:
            return ExecutionQuality.GOOD
        elif score >= 50:
            return ExecutionQuality.AVERAGE
        elif score >= 25:
            return ExecutionQuality.POOR
        else:
            return ExecutionQuality.VERY_POOR

    def _analyze_costs(
        self, execution: ExecutionRecord, slippage: SlippageMetrics
    ) -> Dict[str, float]:
        """Аналіз витрат"""
        notional = execution.quantity * execution.expected_price

        slippage_cost = (
            slippage.absolute_slippage * execution.quantity
            if slippage.direction == "adverse"
            else -slippage.absolute_slippage * execution.quantity
        )

        total_cost = slippage_cost + execution.fees

        return {
            "notional": float(notional),
            "slippage_cost": float(slippage_cost),
            "fees": float(execution.fees),
            "total_cost": float(total_cost),
            "cost_bps": float(total_cost / notional * 10000) if notional > 0 else 0.0,
        }

    def _generate_recommendations(
        self,
        execution: ExecutionRecord,
        slippage: SlippageMetrics,
        latency: LatencyMetrics,
        quality_score: float,
    ) -> List[str]:
        """Генерація рекомендацій"""
        recommendations = []

        # Рекомендації по slippage
        if abs(slippage.slippage_bps) > self.slippage_threshold_bps:
            recommendations.append(
                f"High slippage detected ({slippage.slippage_bps:.1f} bps). "
                "Consider using limit orders or splitting the order."
            )

        if abs(slippage.slippage_bps) > self.slippage_threshold_bps * 2:
            recommendations.append(
                "Consider using TWAP or VWAP algorithms for large orders."
            )

        # Рекомендації по latency
        if latency.total_latency_ms > self.latency_threshold_ms:
            recommendations.append(
                f"High latency detected ({latency.total_latency_ms:.0f} ms). "
                "Check network connection and venue responsiveness."
            )

        # Рекомендації по venue
        venue_stats = self._venue_stats.get(execution.venue, {})
        if venue_stats.get("count", 0) > 10:
            avg_slippage = venue_stats.get("total_slippage_bps", 0) / venue_stats.get("count", 1)
            if avg_slippage > self.slippage_threshold_bps:
                recommendations.append(
                    f"Venue '{execution.venue}' shows consistently high slippage. "
                    "Consider alternative venues."
                )

        # Загальні рекомендації по якості
        if quality_score < 50:
            recommendations.append(
                "Overall execution quality is below average. "
                "Review order timing and venue selection."
            )

        if not recommendations:
            recommendations.append("Execution quality is acceptable. No immediate actions needed.")

        return recommendations

    def _update_venue_stats(
        self, execution: ExecutionRecord, analysis: ExecutionAnalysis
    ) -> None:
        """Оновлення статистики venue"""
        venue = execution.venue

        if venue not in self._venue_stats:
            self._venue_stats[venue] = {
                "count": 0,
                "total_slippage_bps": 0.0,
                "total_latency_ms": 0.0,
                "total_quality_score": 0.0,
            }

        stats = self._venue_stats[venue]
        stats["count"] += 1
        stats["total_slippage_bps"] += abs(analysis.slippage.slippage_bps)
        stats["total_latency_ms"] += analysis.latency.total_latency_ms
        stats["total_quality_score"] += analysis.quality_score

    def _update_symbol_stats(
        self, execution: ExecutionRecord, analysis: ExecutionAnalysis
    ) -> None:
        """Оновлення статистики символу"""
        symbol = execution.symbol

        if symbol not in self._symbol_stats:
            self._symbol_stats[symbol] = {
                "count": 0,
                "total_volume": 0.0,
                "total_slippage_bps": 0.0,
                "total_latency_ms": 0.0,
                "buy_count": 0,
                "sell_count": 0,
                "buy_slippage_bps": 0.0,
                "sell_slippage_bps": 0.0,
            }

        stats = self._symbol_stats[symbol]
        stats["count"] += 1
        stats["total_volume"] += execution.quantity * execution.executed_price
        stats["total_slippage_bps"] += abs(analysis.slippage.slippage_bps)
        stats["total_latency_ms"] += analysis.latency.total_latency_ms

        if execution.side == ExecutionSide.BUY:
            stats["buy_count"] += 1
            stats["buy_slippage_bps"] += analysis.slippage.slippage_bps
        else:
            stats["sell_count"] += 1
            stats["sell_slippage_bps"] += analysis.slippage.slippage_bps

    def get_summary(self) -> Dict:
        """
        Отримання саммарі

        Returns:
            Словник зі статистикою
        """
        if not self._executions:
            return {
                "total_executions": 0,
                "message": "No executions recorded",
            }

        batch_analysis = self.analyze_batch(self._executions)

        return {
            "total_executions": len(self._executions),
            "venues_tracked": len(self._venue_stats),
            "symbols_tracked": len(self._symbol_stats),
            "average_slippage_bps": f"{batch_analysis['slippage']['mean_bps']:.2f}",
            "average_latency_ms": f"{batch_analysis['latency']['mean_ms']:.0f}",
            "average_quality_score": f"{batch_analysis['quality']['mean_score']:.1f}",
            "total_slippage_cost": f"${batch_analysis['costs']['total_slippage_cost']:,.2f}",
            "quality_distribution": {
                "excellent": batch_analysis["quality"]["excellent_count"],
                "good": batch_analysis["quality"]["good_count"],
                "average": batch_analysis["quality"]["average_count"],
                "poor": batch_analysis["quality"]["poor_count"],
                "very_poor": batch_analysis["quality"]["very_poor_count"],
            },
        }
