# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Risk Monitoring Framework - Unified Interface.

This module provides the main RiskMonitoringFramework class that integrates:
- Adaptive threshold calibration
- Stress detection
- Regulatory compliance
- Performance tracking
- Fail-safe mechanisms

Example:
    >>> from core.risk_monitoring import RiskMonitoringFramework
    >>> framework = RiskMonitoringFramework()
    >>> assessment = framework.assess(market_state, portfolio_state)
    >>> if assessment.requires_action:
    ...     framework.execute_mitigation(assessment.recommended_action)
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
from numpy.typing import NDArray

from .adaptive_thresholds import (
    AdaptiveThresholdCalibrator,
    CalibratedThresholds,
)
from .compliance import (
    ComplianceManager,
    RegulationType,
)
from .fail_safe import (
    FailSafeAction,
    FailSafeController,
    FailSafeLevel,
    FailSafeState,
)
from .performance_tracker import (
    PerformanceMetrics,
    PerformanceReport,
    PerformanceTracker,
    PerformanceTrackerConfig,
)
from .stress_detection import (
    MarketSignals,
    StressAssessment,
    StressDetector,
    StressLevel,
)

__all__ = [
    "RiskMonitoringFramework",
    "RiskAssessment",
    "RiskMonitoringConfig",
]

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RiskMonitoringConfig:
    """Configuration for the Risk Monitoring Framework.

    Attributes:
        entity_id: Entity identifier for compliance.
        storage_path: Path for compliance and audit storage.
        initial_capital: Starting capital for performance tracking.
        periods_per_year: Trading periods per year for annualization.
        enable_adaptive_thresholds: Enable adaptive threshold calibration.
        enable_stress_detection: Enable stress detection.
        enable_compliance: Enable compliance tracking.
        enable_performance_tracking: Enable performance tracking.
        enable_fail_safe: Enable fail-safe mechanisms.
        auto_escalate: Automatically escalate based on stress detection.
        high_drawdown_threshold: Drawdown threshold for high stress escalation.
        elevated_drawdown_threshold: Drawdown threshold for elevated stress.
    """

    entity_id: str = "TRADEPULSE"
    storage_path: Path | str = Path("./risk_monitoring_data")
    initial_capital: float = 100_000.0
    periods_per_year: int = 252
    enable_adaptive_thresholds: bool = True
    enable_stress_detection: bool = True
    enable_compliance: bool = True
    enable_performance_tracking: bool = True
    enable_fail_safe: bool = True
    auto_escalate: bool = True
    high_drawdown_threshold: float = 0.15  # 15% drawdown triggers high stress
    elevated_drawdown_threshold: float = 0.10  # 10% drawdown triggers elevated stress

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_id": self.entity_id,
            "storage_path": str(self.storage_path),
            "initial_capital": self.initial_capital,
            "periods_per_year": self.periods_per_year,
            "enable_adaptive_thresholds": self.enable_adaptive_thresholds,
            "enable_stress_detection": self.enable_stress_detection,
            "enable_compliance": self.enable_compliance,
            "enable_performance_tracking": self.enable_performance_tracking,
            "enable_fail_safe": self.enable_fail_safe,
            "auto_escalate": self.auto_escalate,
            "high_drawdown_threshold": self.high_drawdown_threshold,
            "elevated_drawdown_threshold": self.elevated_drawdown_threshold,
        }


@dataclass(slots=True)
class RiskAssessment:
    """Comprehensive risk assessment result.

    Attributes:
        timestamp: When assessment was performed.
        stress_assessment: Stress detection result.
        thresholds: Current calibrated thresholds.
        performance: Current performance metrics.
        fail_safe_state: Current fail-safe state.
        requires_action: Whether mitigation action is required.
        recommended_action: Recommended fail-safe action.
        risk_score: Composite risk score (0-1).
        summary: Human-readable summary.
    """

    timestamp: datetime
    stress_assessment: StressAssessment | None = None
    thresholds: CalibratedThresholds | None = None
    performance: PerformanceMetrics | None = None
    fail_safe_state: FailSafeState | None = None
    requires_action: bool = False
    recommended_action: FailSafeAction = FailSafeAction.NONE
    risk_score: float = 0.0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "stress_assessment": self.stress_assessment.to_dict() if self.stress_assessment else None,
            "thresholds": self.thresholds.to_dict() if self.thresholds else None,
            "performance": self.performance.to_dict() if self.performance else None,
            "fail_safe_state": self.fail_safe_state.to_dict() if self.fail_safe_state else None,
            "requires_action": self.requires_action,
            "recommended_action": self.recommended_action.value,
            "risk_score": self.risk_score,
            "summary": self.summary,
        }


class RiskMonitoringFramework:
    """Unified Risk Monitoring and Mitigation Framework.

    Provides comprehensive risk monitoring for autonomous trading agents,
    combining adaptive thresholds, stress detection, compliance, performance
    tracking, and fail-safe mechanisms.

    Example:
        >>> framework = RiskMonitoringFramework()
        >>> # Update with market data
        >>> framework.update_market_data(returns=returns, volumes=volumes)
        >>> # Assess current risk
        >>> signals = MarketSignals(...)
        >>> assessment = framework.assess(signals, equity=current_equity)
        >>> # Take action if needed
        >>> if assessment.requires_action:
        ...     framework.fail_safe.escalate_to(
        ...         FailSafeLevel.CAUTION,
        ...         assessment.summary
        ...     )
    """

    def __init__(
        self,
        config: RiskMonitoringConfig | None = None,
        *,
        time_source: Callable[[], datetime] | None = None,
    ) -> None:
        """Initialize the risk monitoring framework.

        Args:
            config: Framework configuration.
            time_source: Optional time source for testing.
        """
        self._config = config or RiskMonitoringConfig()
        self._time = time_source or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()

        storage_path = Path(self._config.storage_path)
        storage_path.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self._threshold_calibrator: AdaptiveThresholdCalibrator | None = None
        if self._config.enable_adaptive_thresholds:
            self._threshold_calibrator = AdaptiveThresholdCalibrator(
                time_source=self._time
            )

        self._stress_detector: StressDetector | None = None
        if self._config.enable_stress_detection:
            self._stress_detector = StressDetector(time_source=self._time)

        self._compliance: ComplianceManager | None = None
        if self._config.enable_compliance:
            self._compliance = ComplianceManager(
                storage_path=storage_path / "compliance",
                entity_id=self._config.entity_id,
            )

        self._performance: PerformanceTracker | None = None
        if self._config.enable_performance_tracking:
            perf_config = PerformanceTrackerConfig(
                initial_capital=self._config.initial_capital,
                periods_per_year=self._config.periods_per_year,
            )
            self._performance = PerformanceTracker(
                perf_config, time_source=self._time
            )

        self._fail_safe: FailSafeController | None = None
        if self._config.enable_fail_safe:
            self._fail_safe = FailSafeController(
                time_source=self._time,
                on_state_change=self._on_fail_safe_change,
            )

        LOGGER.info(
            "Risk Monitoring Framework initialized",
            extra={"config": self._config.to_dict()},
        )

    @property
    def config(self) -> RiskMonitoringConfig:
        """Get current configuration."""
        return self._config

    @property
    def threshold_calibrator(self) -> AdaptiveThresholdCalibrator | None:
        """Access threshold calibrator component."""
        return self._threshold_calibrator

    @property
    def stress_detector(self) -> StressDetector | None:
        """Access stress detector component."""
        return self._stress_detector

    @property
    def compliance(self) -> ComplianceManager | None:
        """Access compliance manager component."""
        return self._compliance

    @property
    def performance(self) -> PerformanceTracker | None:
        """Access performance tracker component."""
        return self._performance

    @property
    def fail_safe(self) -> FailSafeController | None:
        """Access fail-safe controller component."""
        return self._fail_safe

    def update_market_data(
        self,
        *,
        returns: NDArray[np.float64] | list[float] | None = None,
        volumes: NDArray[np.float64] | list[float] | None = None,
        asset: str | None = None,
    ) -> CalibratedThresholds | None:
        """Update market data for threshold calibration.

        Args:
            returns: Recent period returns.
            volumes: Recent trading volumes.
            asset: Asset identifier for asset-specific calibration.

        Returns:
            Updated calibrated thresholds if calibration is enabled.
        """
        with self._lock:
            if self._threshold_calibrator:
                thresholds = self._threshold_calibrator.update(
                    returns=returns,
                    volumes=volumes,
                    asset=asset,
                )

                # Record for compliance
                if self._compliance:
                    self._compliance.record_audit_entry(
                        event_type="threshold_calibration",
                        actor="system",
                        action="Updated risk thresholds",
                        details={
                            "volatility_regime": thresholds.volatility_regime,
                            "adaptation_factor": thresholds.adaptation_factor,
                        },
                    )

                return thresholds
            return None

    def update_equity(self, equity: float) -> PerformanceMetrics | None:
        """Update current equity for performance tracking.

        Args:
            equity: Current portfolio equity.

        Returns:
            Updated performance metrics if tracking is enabled.
        """
        with self._lock:
            if self._performance:
                metrics = self._performance.update_equity(equity)

                # Check for performance-based risk triggers using configured thresholds
                if self._fail_safe and self._config.auto_escalate:
                    if metrics.current_drawdown > self._config.high_drawdown_threshold:
                        self._fail_safe.report_stress("high", source="performance_tracker")
                    elif metrics.current_drawdown > self._config.elevated_drawdown_threshold:
                        self._fail_safe.report_stress("elevated", source="performance_tracker")

                return metrics
            return None

    def assess(
        self,
        signals: MarketSignals | None = None,
        *,
        equity: float | None = None,
    ) -> RiskAssessment:
        """Perform comprehensive risk assessment.

        Args:
            signals: Current market signals for stress detection.
            equity: Current equity for performance update.

        Returns:
            Comprehensive risk assessment.
        """
        with self._lock:
            now = self._time()

            # Update equity if provided
            performance: PerformanceMetrics | None = None
            if equity is not None and self._performance:
                performance = self._performance.update_equity(equity)

            # Stress detection
            stress_assessment: StressAssessment | None = None
            if signals and self._stress_detector:
                stress_assessment = self._stress_detector.assess(signals)

                # Auto-escalate if enabled
                if self._config.auto_escalate and self._fail_safe:
                    self._fail_safe.report_stress(
                        stress_assessment.stress_level.value,
                        source="stress_detector",
                    )

            # Get current thresholds
            thresholds: CalibratedThresholds | None = None
            if self._threshold_calibrator:
                thresholds = self._threshold_calibrator.get_thresholds()

            # Get fail-safe state
            fail_safe_state: FailSafeState | None = None
            if self._fail_safe:
                fail_safe_state = self._fail_safe.get_state()

            # Calculate composite risk score
            risk_score = self._calculate_risk_score(
                stress_assessment, thresholds, performance, fail_safe_state
            )

            # Determine if action is required
            requires_action, recommended_action = self._determine_action(
                stress_assessment, fail_safe_state, risk_score
            )

            # Generate summary
            summary = self._generate_summary(
                stress_assessment, thresholds, performance, fail_safe_state, risk_score
            )

            # Record assessment for compliance
            if self._compliance:
                self._compliance.record_audit_entry(
                    event_type="risk_assessment",
                    actor="system",
                    action="Performed risk assessment",
                    details={
                        "risk_score": risk_score,
                        "requires_action": requires_action,
                        "stress_level": stress_assessment.stress_level.value if stress_assessment else None,
                    },
                    risk_decision=recommended_action.value if requires_action else None,
                )

            return RiskAssessment(
                timestamp=now,
                stress_assessment=stress_assessment,
                thresholds=thresholds,
                performance=performance,
                fail_safe_state=fail_safe_state,
                requires_action=requires_action,
                recommended_action=recommended_action,
                risk_score=risk_score,
                summary=summary,
            )

    def execute_mitigation(self, action: FailSafeAction) -> bool:
        """Execute a mitigation action.

        Args:
            action: The action to execute.

        Returns:
            True if action was successfully initiated.
        """
        with self._lock:
            if not self._fail_safe:
                LOGGER.warning("Fail-safe not enabled, cannot execute mitigation")
                return False

            LOGGER.info("Executing mitigation action: %s", action.value)

            # Record for compliance
            if self._compliance:
                self._compliance.record_audit_entry(
                    event_type="mitigation_action",
                    actor="system",
                    action=f"Executed mitigation: {action.value}",
                    risk_decision=action.value,
                )

            # Acknowledge the action
            self._fail_safe.acknowledge_action(action)
            return True

    def generate_compliance_report(
        self,
        *,
        regulation: RegulationType = RegulationType.INTERNAL,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Generate a regulatory compliance report.

        Args:
            regulation: Target regulation.
            period_start: Start of reporting period.
            period_end: End of reporting period.

        Returns:
            Report dictionary if compliance is enabled.
        """
        with self._lock:
            if not self._compliance:
                return None

            now = self._time()
            start = period_start or now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = period_end or now

            report = self._compliance.generate_report(
                regulation=regulation,
                period_start=start,
                period_end=end,
            )
            return report.to_dict()

    def generate_performance_report(self) -> PerformanceReport | None:
        """Generate detailed performance report.

        Returns:
            Performance report if tracking is enabled.
        """
        with self._lock:
            if self._performance:
                return self._performance.generate_report()
            return None

    def get_status(self) -> dict[str, Any]:
        """Get current framework status.

        Returns:
            Dictionary with component statuses.
        """
        with self._lock:
            status: dict[str, Any] = {
                "framework_enabled": True,
                "config": self._config.to_dict(),
            }

            if self._threshold_calibrator:
                status["thresholds"] = self._threshold_calibrator.get_status()

            if self._stress_detector:
                status["stress"] = self._stress_detector.get_status()

            if self._compliance:
                status["compliance"] = self._compliance.get_compliance_status()

            if self._performance:
                status["performance"] = self._performance.get_status()

            if self._fail_safe:
                status["fail_safe"] = self._fail_safe.get_state().to_dict()

            return status

    def is_trading_allowed(self) -> bool:
        """Check if trading is currently allowed.

        Returns:
            True if trading is allowed by all components.
        """
        with self._lock:
            if self._fail_safe:
                return self._fail_safe.is_trading_allowed()
            return True

    def get_position_multiplier(self) -> float:
        """Get current position size multiplier.

        Combines threshold calibration and fail-safe multipliers.

        Returns:
            Effective position multiplier.
        """
        with self._lock:
            multiplier = 1.0

            if self._threshold_calibrator:
                thresholds = self._threshold_calibrator.get_thresholds()
                # Adjust based on volatility regime
                if thresholds.volatility_regime == "high":
                    multiplier *= 0.7
                elif thresholds.volatility_regime == "low":
                    multiplier *= 1.2

            if self._fail_safe:
                multiplier *= self._fail_safe.get_position_multiplier()

            return max(0.0, min(1.5, multiplier))

    def reset(self) -> None:
        """Reset all components to initial state."""
        with self._lock:
            if self._threshold_calibrator:
                self._threshold_calibrator.reset()
            if self._stress_detector:
                self._stress_detector.reset()
            if self._performance:
                self._performance.reset()
            if self._fail_safe:
                self._fail_safe.reset()

            LOGGER.info("Risk Monitoring Framework reset")

    def _on_fail_safe_change(self, state: FailSafeState) -> None:
        """Handle fail-safe state changes."""
        if self._compliance:
            self._compliance.record_audit_entry(
                event_type="fail_safe_change",
                actor=state.source,
                action=f"Fail-safe state changed to {state.level.value}",
                details=state.to_dict(),
                risk_decision=state.level.value if state.active else None,
            )

    def _calculate_risk_score(
        self,
        stress: StressAssessment | None,
        thresholds: CalibratedThresholds | None,
        performance: PerformanceMetrics | None,
        fail_safe: FailSafeState | None,
    ) -> float:
        """Calculate composite risk score (0-1)."""
        scores: list[float] = []

        if stress:
            scores.append(stress.composite_score)

        if thresholds and thresholds.volatility_regime == "high":
            scores.append(0.6)
        elif thresholds and thresholds.volatility_regime == "low":
            scores.append(0.2)
        else:
            scores.append(0.4)

        if performance:
            # Drawdown contributes to risk
            dd_score = min(1.0, performance.current_drawdown * 5)  # 20% dd = 100% risk
            scores.append(dd_score)

        if fail_safe:
            level_scores = {
                FailSafeLevel.NORMAL: 0.0,
                FailSafeLevel.CAUTION: 0.3,
                FailSafeLevel.RESTRICTED: 0.6,
                FailSafeLevel.HALT: 0.9,
                FailSafeLevel.EMERGENCY: 1.0,
            }
            scores.append(level_scores.get(fail_safe.level, 0.0))

        return sum(scores) / len(scores) if scores else 0.0

    def _determine_action(
        self,
        stress: StressAssessment | None,
        fail_safe: FailSafeState | None,
        risk_score: float,
    ) -> tuple[bool, FailSafeAction]:
        """Determine if action is required and recommend action."""
        if risk_score < 0.3:
            return False, FailSafeAction.NONE

        if stress and stress.stress_level == StressLevel.CRITICAL:
            return True, FailSafeAction.HALT_TRADING

        if stress and stress.stress_level == StressLevel.HIGH:
            return True, FailSafeAction.CLOSE_POSITIONS

        if risk_score >= 0.6:
            return True, FailSafeAction.REDUCE_POSITIONS

        if risk_score >= 0.4:
            return True, FailSafeAction.CANCEL_PENDING

        return False, FailSafeAction.NONE

    def _generate_summary(
        self,
        stress: StressAssessment | None,
        thresholds: CalibratedThresholds | None,
        performance: PerformanceMetrics | None,
        fail_safe: FailSafeState | None,
        risk_score: float,
    ) -> str:
        """Generate human-readable risk summary."""
        parts: list[str] = [f"Risk Score: {risk_score:.1%}"]

        if stress:
            parts.append(f"Stress: {stress.stress_level.value}")

        if thresholds:
            parts.append(f"Volatility: {thresholds.volatility_regime}")

        if performance:
            parts.append(f"Drawdown: {performance.current_drawdown:.1%}")

        if fail_safe:
            parts.append(f"Fail-safe: {fail_safe.level.value}")

        return " | ".join(parts)
