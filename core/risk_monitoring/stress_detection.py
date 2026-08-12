# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Real-time Stress Detection for Risk Monitoring.

This module implements stress detection algorithms using market signals:
- Drawdown monitoring
- Volatility spikes
- Order book imbalances
- Liquidity stress indicators
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

__all__ = [
    "StressDetector",
    "StressLevel",
    "StressAssessment",
    "MarketSignals",
]

LOGGER = logging.getLogger(__name__)


class StressLevel(str, Enum):
    """Market stress levels.

    Attributes:
        NORMAL: Normal market conditions.
        ELEVATED: Elevated stress, caution advised.
        HIGH: High stress, reduce exposure.
        CRITICAL: Critical stress, halt trading.
    """

    NORMAL = "normal"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"

    # Order for comparison operations
    _ORDER = ["normal", "elevated", "high", "critical"]

    def _order_index(self) -> int:
        """Get the order index for comparison."""
        return self._ORDER.index(self.value)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, StressLevel):
            return NotImplemented
        return self._order_index() < other._order_index()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, StressLevel):
            return NotImplemented
        return self._order_index() <= other._order_index()


@dataclass(slots=True)
class MarketSignals:
    """Market signals for stress detection.

    Attributes:
        current_price: Current market price.
        peak_price: Peak price for drawdown calculation.
        current_volatility: Current realized volatility.
        baseline_volatility: Baseline volatility for comparison.
        bid_volume: Total bid volume in order book.
        ask_volume: Total ask volume in order book.
        spread_bps: Current bid-ask spread in basis points.
        recent_returns: Recent price returns.
        liquidity_score: Liquidity score (0-1, higher is better).
    """

    current_price: float = 0.0
    peak_price: float = 0.0
    current_volatility: float = 0.0
    baseline_volatility: float = 0.0
    bid_volume: float = 0.0
    ask_volume: float = 0.0
    spread_bps: float = 0.0
    recent_returns: list[float] = field(default_factory=list)
    liquidity_score: float = 1.0

    def get_drawdown(self) -> float:
        """Calculate current drawdown as fraction."""
        if self.peak_price <= 0:
            return 0.0
        return max(0.0, (self.peak_price - self.current_price) / self.peak_price)

    def get_volatility_ratio(self) -> float:
        """Calculate volatility ratio vs baseline."""
        if self.baseline_volatility <= 0:
            return 1.0
        return self.current_volatility / self.baseline_volatility

    def get_order_book_imbalance(self) -> float:
        """Calculate order book imbalance (-1 to 1).

        Positive values indicate more buying pressure (bid > ask).
        Negative values indicate more selling pressure (ask > bid).
        """
        total = self.bid_volume + self.ask_volume
        if total <= 0:
            return 0.0
        return (self.bid_volume - self.ask_volume) / total


@dataclass(slots=True)
class StressAssessment:
    """Result of stress assessment.

    Attributes:
        stress_level: Overall stress level.
        drawdown_stress: Stress contribution from drawdown.
        volatility_stress: Stress contribution from volatility.
        liquidity_stress: Stress contribution from liquidity.
        imbalance_stress: Stress contribution from order book imbalance.
        composite_score: Composite stress score (0-1).
        triggers: List of triggered stress indicators.
        recommendation: Recommended action.
        timestamp: Assessment timestamp.
    """

    stress_level: StressLevel
    drawdown_stress: float = 0.0
    volatility_stress: float = 0.0
    liquidity_stress: float = 0.0
    imbalance_stress: float = 0.0
    composite_score: float = 0.0
    triggers: tuple[str, ...] = ()
    recommendation: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert assessment to dictionary."""
        return {
            "stress_level": self.stress_level.value,
            "drawdown_stress": self.drawdown_stress,
            "volatility_stress": self.volatility_stress,
            "liquidity_stress": self.liquidity_stress,
            "imbalance_stress": self.imbalance_stress,
            "composite_score": self.composite_score,
            "triggers": list(self.triggers),
            "recommendation": self.recommendation,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(slots=True)
class StressDetectorConfig:
    """Configuration for stress detector.

    Attributes:
        drawdown_elevated_threshold: Drawdown threshold for elevated stress.
        drawdown_high_threshold: Drawdown threshold for high stress.
        drawdown_critical_threshold: Drawdown threshold for critical stress.
        volatility_elevated_ratio: Volatility ratio for elevated stress.
        volatility_high_ratio: Volatility ratio for high stress.
        volatility_critical_ratio: Volatility ratio for critical stress.
        imbalance_threshold: Order book imbalance threshold for stress.
        liquidity_threshold: Liquidity score threshold for stress.
        spread_threshold_bps: Spread threshold in bps for stress.
        lookback_periods: Number of periods for rolling calculations.
    """

    drawdown_elevated_threshold: float = 0.05  # 5%
    drawdown_high_threshold: float = 0.10  # 10%
    drawdown_critical_threshold: float = 0.15  # 15%
    volatility_elevated_ratio: float = 1.5
    volatility_high_ratio: float = 2.0
    volatility_critical_ratio: float = 3.0
    imbalance_threshold: float = 0.6  # 60% imbalance
    liquidity_threshold: float = 0.3  # Below 30% is stressed
    spread_threshold_bps: float = 50.0  # 50 bps
    lookback_periods: int = 20

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "drawdown_elevated_threshold": self.drawdown_elevated_threshold,
            "drawdown_high_threshold": self.drawdown_high_threshold,
            "drawdown_critical_threshold": self.drawdown_critical_threshold,
            "volatility_elevated_ratio": self.volatility_elevated_ratio,
            "volatility_high_ratio": self.volatility_high_ratio,
            "volatility_critical_ratio": self.volatility_critical_ratio,
            "imbalance_threshold": self.imbalance_threshold,
            "liquidity_threshold": self.liquidity_threshold,
            "spread_threshold_bps": self.spread_threshold_bps,
            "lookback_periods": self.lookback_periods,
        }


class StressDetector:
    """Real-time market stress detector.

    Monitors multiple market signals to detect stress conditions and
    provide early warning for risk mitigation.

    Example:
        >>> detector = StressDetector()
        >>> signals = MarketSignals(
        ...     current_price=95,
        ...     peak_price=100,
        ...     current_volatility=0.03,
        ...     baseline_volatility=0.01,
        ... )
        >>> assessment = detector.assess(signals)
        >>> print(f"Stress level: {assessment.stress_level.value}")
    """

    def __init__(
        self,
        config: StressDetectorConfig | None = None,
        *,
        time_source: Callable[[], datetime] | None = None,
    ) -> None:
        """Initialize the stress detector.

        Args:
            config: Detector configuration.
            time_source: Optional time source for testing.
        """
        self._config = config or StressDetectorConfig()
        self._time = time_source or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()

        # Historical tracking
        self._stress_history: deque[StressAssessment] = deque(maxlen=100)
        self._volatility_history: deque[float] = deque(maxlen=self._config.lookback_periods)

        # Escalation tracking
        self._consecutive_elevated: int = 0
        self._last_assessment: StressAssessment | None = None

        LOGGER.info(
            "Stress detector initialized",
            extra={"config": self._config.to_dict()},
        )

    @property
    def config(self) -> StressDetectorConfig:
        """Get current configuration."""
        return self._config

    def assess(self, signals: MarketSignals) -> StressAssessment:
        """Assess current market stress.

        Args:
            signals: Current market signals.

        Returns:
            Stress assessment with level and recommendations.
        """
        with self._lock:
            triggers: list[str] = []

            # Assess individual stress components
            drawdown_stress, dd_triggers = self._assess_drawdown(signals)
            triggers.extend(dd_triggers)

            volatility_stress, vol_triggers = self._assess_volatility(signals)
            triggers.extend(vol_triggers)

            liquidity_stress, liq_triggers = self._assess_liquidity(signals)
            triggers.extend(liq_triggers)

            imbalance_stress, imb_triggers = self._assess_imbalance(signals)
            triggers.extend(imb_triggers)

            # Calculate composite score (weighted average)
            composite_score = (
                0.35 * drawdown_stress
                + 0.30 * volatility_stress
                + 0.20 * liquidity_stress
                + 0.15 * imbalance_stress
            )

            # Determine overall stress level
            stress_level = self._determine_stress_level(
                composite_score, drawdown_stress, volatility_stress
            )

            # Generate recommendation
            recommendation = self._generate_recommendation(stress_level, triggers)

            # Track consecutive elevated readings
            if stress_level >= StressLevel.ELEVATED:
                self._consecutive_elevated += 1
            else:
                self._consecutive_elevated = 0

            assessment = StressAssessment(
                stress_level=stress_level,
                drawdown_stress=drawdown_stress,
                volatility_stress=volatility_stress,
                liquidity_stress=liquidity_stress,
                imbalance_stress=imbalance_stress,
                composite_score=composite_score,
                triggers=tuple(triggers),
                recommendation=recommendation,
                timestamp=self._time(),
            )

            self._stress_history.append(assessment)
            self._last_assessment = assessment

            if stress_level >= StressLevel.HIGH:
                LOGGER.warning(
                    "High stress detected",
                    extra={"assessment": assessment.to_dict()},
                )

            return assessment

    def get_last_assessment(self) -> StressAssessment | None:
        """Get the most recent stress assessment."""
        with self._lock:
            return self._last_assessment

    def get_stress_trend(self) -> str:
        """Analyze recent stress trend.

        Returns:
            Trend description: 'improving', 'stable', 'worsening'.
        """
        with self._lock:
            if len(self._stress_history) < 3:
                return "stable"

            recent = list(self._stress_history)[-5:]
            scores = [a.composite_score for a in recent]

            if len(scores) < 2:
                return "stable"

            trend = scores[-1] - scores[0]
            if trend > 0.1:
                return "worsening"
            elif trend < -0.1:
                return "improving"
            return "stable"

    def get_status(self) -> dict[str, Any]:
        """Get current detector status.

        Returns:
            Dictionary with status information.
        """
        with self._lock:
            last = self._last_assessment
            return {
                "last_assessment": last.to_dict() if last else None,
                "consecutive_elevated": self._consecutive_elevated,
                "trend": self.get_stress_trend(),
                "history_size": len(self._stress_history),
            }

    def reset(self) -> None:
        """Reset the detector state."""
        with self._lock:
            self._stress_history.clear()
            self._volatility_history.clear()
            self._consecutive_elevated = 0
            self._last_assessment = None
            LOGGER.info("Stress detector reset")

    def _assess_drawdown(self, signals: MarketSignals) -> tuple[float, list[str]]:
        """Assess drawdown stress component."""
        triggers: list[str] = []
        drawdown = signals.get_drawdown()

        if drawdown >= self._config.drawdown_critical_threshold:
            stress = 1.0
            triggers.append(f"critical_drawdown_{drawdown:.1%}")
        elif drawdown >= self._config.drawdown_high_threshold:
            # Scale from 0.6 to 1.0
            stress = 0.6 + 0.4 * (
                (drawdown - self._config.drawdown_high_threshold)
                / (self._config.drawdown_critical_threshold - self._config.drawdown_high_threshold)
            )
            triggers.append(f"high_drawdown_{drawdown:.1%}")
        elif drawdown >= self._config.drawdown_elevated_threshold:
            # Scale from 0.3 to 0.6
            stress = 0.3 + 0.3 * (
                (drawdown - self._config.drawdown_elevated_threshold)
                / (self._config.drawdown_high_threshold - self._config.drawdown_elevated_threshold)
            )
            triggers.append(f"elevated_drawdown_{drawdown:.1%}")
        else:
            stress = drawdown / self._config.drawdown_elevated_threshold * 0.3

        return min(1.0, stress), triggers

    def _assess_volatility(self, signals: MarketSignals) -> tuple[float, list[str]]:
        """Assess volatility stress component."""
        triggers: list[str] = []
        vol_ratio = signals.get_volatility_ratio()

        # Track volatility history
        if signals.current_volatility > 0:
            self._volatility_history.append(signals.current_volatility)

        if vol_ratio >= self._config.volatility_critical_ratio:
            stress = 1.0
            triggers.append(f"critical_volatility_{vol_ratio:.1f}x")
        elif vol_ratio >= self._config.volatility_high_ratio:
            stress = 0.6 + 0.4 * (
                (vol_ratio - self._config.volatility_high_ratio)
                / (self._config.volatility_critical_ratio - self._config.volatility_high_ratio)
            )
            triggers.append(f"high_volatility_{vol_ratio:.1f}x")
        elif vol_ratio >= self._config.volatility_elevated_ratio:
            stress = 0.3 + 0.3 * (
                (vol_ratio - self._config.volatility_elevated_ratio)
                / (self._config.volatility_high_ratio - self._config.volatility_elevated_ratio)
            )
            triggers.append(f"elevated_volatility_{vol_ratio:.1f}x")
        else:
            stress = max(
                0, (vol_ratio - 1.0) / (self._config.volatility_elevated_ratio - 1.0) * 0.3
            )

        return min(1.0, max(0, stress)), triggers

    def _assess_liquidity(self, signals: MarketSignals) -> tuple[float, list[str]]:
        """Assess liquidity stress component."""
        triggers: list[str] = []
        stress = 0.0

        # Check liquidity score
        if signals.liquidity_score < self._config.liquidity_threshold:
            stress = (
                self._config.liquidity_threshold - signals.liquidity_score
            ) / self._config.liquidity_threshold
            triggers.append(f"low_liquidity_{signals.liquidity_score:.2f}")

        # Check spread
        if signals.spread_bps > self._config.spread_threshold_bps:
            spread_stress = min(
                1.0,
                (signals.spread_bps - self._config.spread_threshold_bps)
                / self._config.spread_threshold_bps,
            )
            stress = max(stress, spread_stress)
            triggers.append(f"wide_spread_{signals.spread_bps:.0f}bps")

        return min(1.0, stress), triggers

    def _assess_imbalance(self, signals: MarketSignals) -> tuple[float, list[str]]:
        """Assess order book imbalance stress component."""
        triggers: list[str] = []
        imbalance = abs(signals.get_order_book_imbalance())

        if imbalance >= self._config.imbalance_threshold:
            stress = (imbalance - self._config.imbalance_threshold) / (
                1.0 - self._config.imbalance_threshold
            )
            direction = "bid" if signals.get_order_book_imbalance() > 0 else "ask"
            triggers.append(f"order_book_imbalance_{direction}_{imbalance:.1%}")
        else:
            stress = 0.0

        return min(1.0, stress), triggers

    def _determine_stress_level(
        self,
        composite_score: float,
        drawdown_stress: float,
        volatility_stress: float,
    ) -> StressLevel:
        """Determine overall stress level from component scores."""
        # Critical if any component is at critical level or composite is very high
        if composite_score >= 0.8 or drawdown_stress >= 0.9 or volatility_stress >= 0.9:
            return StressLevel.CRITICAL

        # High if composite is elevated or multiple components are high
        if composite_score >= 0.6:
            return StressLevel.HIGH

        # Elevated if composite shows early warning
        if composite_score >= 0.3:
            return StressLevel.ELEVATED

        # Also check for sustained elevated readings
        if self._consecutive_elevated >= 5:
            return StressLevel.ELEVATED

        return StressLevel.NORMAL

    def _generate_recommendation(self, stress_level: StressLevel, triggers: list[str]) -> str:
        """Generate action recommendation based on stress level."""
        if stress_level == StressLevel.CRITICAL:
            return "HALT: Immediately cease trading and reduce positions"
        elif stress_level == StressLevel.HIGH:
            return "REDUCE: Lower position sizes and tighten stops"
        elif stress_level == StressLevel.ELEVATED:
            return "CAUTION: Monitor closely and prepare to reduce exposure"
        else:
            return "NORMAL: Continue standard operations"
