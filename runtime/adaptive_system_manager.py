"""Adaptive system manager for self-diagnosis and automatic optimization.

This module implements autonomous adaptation capabilities including self-diagnosis,
auto-tuning, self-healing, and adaptive load management.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """System health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    RECOVERING = "recovering"


class AdaptationStrategy(Enum):
    """Available adaptation strategies."""

    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    ADJUST_TIMEOUT = "adjust_timeout"
    ENABLE_CIRCUIT_BREAKER = "enable_circuit_breaker"
    INCREASE_BATCH_SIZE = "increase_batch_size"
    DECREASE_BATCH_SIZE = "decrease_batch_size"
    ADJUST_RATE_LIMIT = "adjust_rate_limit"
    RESTART_COMPONENT = "restart_component"


@dataclass
class SystemHealth:
    """System health assessment."""

    status: HealthStatus
    cpu_utilization: float
    memory_utilization: float
    error_rate: float
    latency_p99: float
    throughput: float
    timestamp: float = field(default_factory=time.time)
    issues: List[str] = field(default_factory=list)

    def health_score(self) -> float:
        """Calculate overall health score (0-100).

        Returns:
            Health score where 100 is perfect health
        """
        score = 100.0

        # Deduct points for issues
        if self.cpu_utilization > 80:
            score -= 15
        elif self.cpu_utilization > 60:
            score -= 5

        if self.memory_utilization > 85:
            score -= 15
        elif self.memory_utilization > 70:
            score -= 5

        if self.error_rate > 0.05:  # 5%
            score -= 25
        elif self.error_rate > 0.01:  # 1%
            score -= 10

        if self.latency_p99 > 1000:  # 1 second
            score -= 20
        elif self.latency_p99 > 500:  # 500ms
            score -= 10

        return max(0.0, score)


@dataclass
class AdaptationAction:
    """Action to adapt system configuration."""

    strategy: AdaptationStrategy
    parameter: str
    old_value: any
    new_value: any
    reason: str
    timestamp: float = field(default_factory=time.time)
    applied: bool = False
    rollback_available: bool = True


class AdaptiveSystemManager:
    """Manager for autonomous system adaptation and optimization."""

    def __init__(
        self, health_check_interval: float = 60.0, adaptation_cooldown: float = 300.0
    ):
        """Initialize adaptive system manager.

        Args:
            health_check_interval: Seconds between health checks
            adaptation_cooldown: Seconds to wait between adaptations
        """
        self.health_check_interval = health_check_interval
        self.adaptation_cooldown = adaptation_cooldown
        self.health_history: List[SystemHealth] = []
        self.adaptations: List[AdaptationAction] = []
        self.last_adaptation_time = 0.0
        self.configuration: Dict[str, any] = self._default_configuration()
        self._adaptation_handlers: Dict[AdaptationStrategy, Callable] = {}

    def _default_configuration(self) -> Dict[str, any]:
        """Get default system configuration.

        Returns:
            Default configuration dictionary
        """
        return {
            "worker_threads": 4,
            "batch_size": 100,
            "timeout_ms": 5000,
            "max_connections": 1000,
            "rate_limit_rps": 1000,
            "circuit_breaker_enabled": False,
            "circuit_breaker_threshold": 0.5,
        }

    def register_adaptation_handler(
        self, strategy: AdaptationStrategy, handler: Callable[[str, any], bool]
    ) -> None:
        """Register a handler for an adaptation strategy.

        Args:
            strategy: Adaptation strategy
            handler: Handler function that applies the adaptation
        """
        self._adaptation_handlers[strategy] = handler

    def assess_health(
        self,
        cpu_utilization: float,
        memory_utilization: float,
        error_rate: float,
        latency_p99: float,
        throughput: float,
    ) -> SystemHealth:
        """Assess current system health.

        Args:
            cpu_utilization: CPU usage percentage (0-100)
            memory_utilization: Memory usage percentage (0-100)
            error_rate: Error rate (0.0-1.0)
            latency_p99: 99th percentile latency in ms
            throughput: Operations per second

        Returns:
            SystemHealth assessment
        """
        issues = []

        # Check thresholds
        if cpu_utilization > 80:
            issues.append("High CPU utilization")
        if memory_utilization > 85:
            issues.append("High memory utilization")
        if error_rate > 0.05:
            issues.append("High error rate")
        if latency_p99 > 1000:
            issues.append("High latency")
        if throughput < 100:
            issues.append("Low throughput")

        # Determine status
        if not issues:
            status = HealthStatus.HEALTHY
        elif len(issues) >= 3 or error_rate > 0.15:
            status = HealthStatus.CRITICAL
        else:
            status = HealthStatus.DEGRADED

        health = SystemHealth(
            status=status,
            cpu_utilization=cpu_utilization,
            memory_utilization=memory_utilization,
            error_rate=error_rate,
            latency_p99=latency_p99,
            throughput=throughput,
            issues=issues,
        )

        self.health_history.append(health)

        # Keep last 1000 health checks
        if len(self.health_history) > 1000:
            self.health_history = self.health_history[-1000:]

        return health

    def detect_degradation(self, window_size: int = 10) -> bool:
        """Detect gradual system degradation.

        Args:
            window_size: Number of recent health checks to analyze

        Returns:
            True if degradation detected
        """
        if len(self.health_history) < window_size:
            return False

        recent = self.health_history[-window_size:]
        scores = [h.health_score() for h in recent]

        # Check if scores are declining
        import numpy as np

        x = np.arange(len(scores))
        y = np.array(scores)

        # Simple linear regression
        slope = np.polyfit(x, y, 1)[0]

        # Negative slope indicates degradation
        return slope < -2.0  # Losing > 2 points per check

    def recommend_adaptations(self, health: SystemHealth) -> List[AdaptationAction]:
        """Recommend adaptations based on health assessment.

        Args:
            health: Current system health

        Returns:
            List of recommended adaptation actions
        """
        recommendations = []

        # CPU overload - scale up or optimize
        if health.cpu_utilization > 80:
            recommendations.append(
                AdaptationAction(
                    strategy=AdaptationStrategy.SCALE_UP,
                    parameter="worker_threads",
                    old_value=self.configuration["worker_threads"],
                    new_value=min(self.configuration["worker_threads"] + 2, 16),
                    reason="High CPU utilization",
                )
            )

        # Memory pressure
        if health.memory_utilization > 85:
            recommendations.append(
                AdaptationAction(
                    strategy=AdaptationStrategy.DECREASE_BATCH_SIZE,
                    parameter="batch_size",
                    old_value=self.configuration["batch_size"],
                    new_value=max(self.configuration["batch_size"] // 2, 10),
                    reason="High memory utilization",
                )
            )

        # High error rate
        if health.error_rate > 0.05:
            recommendations.append(
                AdaptationAction(
                    strategy=AdaptationStrategy.ENABLE_CIRCUIT_BREAKER,
                    parameter="circuit_breaker_enabled",
                    old_value=False,
                    new_value=True,
                    reason="High error rate detected",
                )
            )

        # High latency
        if health.latency_p99 > 1000:
            recommendations.append(
                AdaptationAction(
                    strategy=AdaptationStrategy.ADJUST_TIMEOUT,
                    parameter="timeout_ms",
                    old_value=self.configuration["timeout_ms"],
                    new_value=self.configuration["timeout_ms"] + 2000,
                    reason="High latency detected",
                )
            )

        # Low throughput
        if health.throughput < 100:
            recommendations.append(
                AdaptationAction(
                    strategy=AdaptationStrategy.INCREASE_BATCH_SIZE,
                    parameter="batch_size",
                    old_value=self.configuration["batch_size"],
                    new_value=min(self.configuration["batch_size"] * 2, 1000),
                    reason="Low throughput",
                )
            )

        return recommendations

    def apply_adaptation(self, action: AdaptationAction) -> bool:
        """Apply an adaptation action.

        Args:
            action: Adaptation action to apply

        Returns:
            True if successfully applied
        """
        # Check cooldown
        if time.time() - self.last_adaptation_time < self.adaptation_cooldown:
            logger.info("Adaptation in cooldown period, skipping")
            return False

        # Check if handler registered
        if action.strategy not in self._adaptation_handlers:
            logger.warning(f"No handler registered for {action.strategy}")
            # Apply to configuration anyway for tracking
            self.configuration[action.parameter] = action.new_value
            action.applied = True
            self.adaptations.append(action)
            self.last_adaptation_time = time.time()
            return True

        # Call handler
        handler = self._adaptation_handlers[action.strategy]
        success = handler(action.parameter, action.new_value)

        if success:
            self.configuration[action.parameter] = action.new_value
            action.applied = True
            self.adaptations.append(action)
            self.last_adaptation_time = time.time()
            logger.info(
                f"Applied adaptation: {action.strategy.value} "
                f"({action.parameter}: {action.old_value} -> {action.new_value})"
            )
        else:
            logger.error(f"Failed to apply adaptation: {action.strategy.value}")

        return success

    def rollback_adaptation(self, action: AdaptationAction) -> bool:
        """Rollback a previously applied adaptation.

        Args:
            action: Adaptation action to rollback

        Returns:
            True if successfully rolled back
        """
        if not action.applied or not action.rollback_available:
            return False

        if action.strategy not in self._adaptation_handlers:
            self.configuration[action.parameter] = action.old_value
            return True

        handler = self._adaptation_handlers[action.strategy]
        success = handler(action.parameter, action.old_value)

        if success:
            self.configuration[action.parameter] = action.old_value
            logger.info(
                f"Rolled back adaptation: {action.strategy.value} "
                f"({action.parameter}: {action.new_value} -> {action.old_value})"
            )

        return success

    def auto_adapt(self, health: SystemHealth) -> List[AdaptationAction]:
        """Automatically adapt system based on health.

        Args:
            health: Current system health

        Returns:
            List of applied adaptations
        """
        if health.status == HealthStatus.HEALTHY:
            return []

        recommendations = self.recommend_adaptations(health)
        applied = []

        for action in recommendations:
            if self.apply_adaptation(action):
                applied.append(action)

        return applied

    def get_adaptation_history(self, limit: int = 100) -> List[AdaptationAction]:
        """Get recent adaptation history.

        Args:
            limit: Maximum number of actions to return

        Returns:
            List of recent adaptations
        """
        return self.adaptations[-limit:]

    def get_health_trend(self, window_minutes: int = 60) -> Dict:
        """Get health trend over time window.

        Args:
            window_minutes: Time window in minutes

        Returns:
            Dictionary with trend statistics
        """
        cutoff = time.time() - (window_minutes * 60)
        recent = [h for h in self.health_history if h.timestamp >= cutoff]

        if not recent:
            return {"status": "no_data"}

        import numpy as np

        scores = [h.health_score() for h in recent]

        return {
            "current_score": scores[-1] if scores else 0,
            "avg_score": float(np.mean(scores)),
            "min_score": float(np.min(scores)),
            "max_score": float(np.max(scores)),
            "trend": (
                "improving"
                if len(scores) > 1 and scores[-1] > scores[0]
                else "declining"
            ),
            "samples": len(scores),
        }
