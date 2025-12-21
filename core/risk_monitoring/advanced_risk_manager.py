# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""High-Precision Advanced Risk Management Module.

This module implements a comprehensive risk management system for AI-powered
trading, integrating:

* **Adaptive Risk Modulation**: Dynamic adjustment of risk exposure based on
  real-time volatility, liquidity, and market depth analysis.
* **Free Energy Optimization**: Active inference principles to minimize
  uncertainty and optimize decision-making under market stress.
* **Stress Response Protocols**: Adaptive behavior for extreme drawdowns,
  volatility surges, and liquidity crises.
* **Scalability & Fault Tolerance**: Thread-safe design with graceful
  degradation and error recovery.
* **Auditing and Transparency**: Comprehensive logging, monitoring, and
  reporting for regulatory compliance.

Example:
    >>> from core.risk_monitoring.advanced_risk_manager import (
    ...     AdvancedRiskManager,
    ...     MarketDepthData,
    ...     LiquidityMetrics,
    ... )
    >>> manager = AdvancedRiskManager()
    >>> market_depth = MarketDepthData(
    ...     bids=[(100.0, 1000.0), (99.5, 2000.0)],
    ...     asks=[(100.5, 1500.0), (101.0, 2500.0)],
    ... )
    >>> liquidity = manager.analyze_liquidity(market_depth)
    >>> assessment = manager.assess_risk(
    ...     current_price=100.0,
    ...     volatility=0.02,
    ...     liquidity_metrics=liquidity,
    ... )
    >>> print(f"Risk Score: {assessment.risk_score:.2%}")
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Sequence

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "AdvancedRiskManager",
    "AdvancedRiskConfig",
    "RiskState",
    "StressResponseProtocol",
    "MarketDepthData",
    "LiquidityMetrics",
    "FreeEnergyState",
    "RiskAuditEntry",
    "AdvancedRiskAssessment",
]

LOGGER = logging.getLogger(__name__)


# =============================================================================
# Enumerations
# =============================================================================

# Module-level order maps for O(1) lookup in enum comparison operators
_PROTOCOL_ORDER_MAP: dict[str, int] = {
    "normal": 0,
    "defensive": 1,
    "protective": 2,
    "halt": 3,
    "emergency": 4,
}

_RISK_STATE_ORDER_MAP: dict[str, int] = {
    "optimal": 0,
    "stable": 1,
    "elevated": 2,
    "stressed": 3,
    "critical": 4,
}


class StressResponseProtocol(str, Enum):
    """Stress response protocol levels for adaptive behavior.

    Attributes:
        NORMAL: Normal trading operations.
        DEFENSIVE: Reduced position sizes, tighter stops.
        PROTECTIVE: Minimal new positions, prepare for exits.
        HALT: Complete halt of new trading.
        EMERGENCY: Emergency liquidation mode.
    """

    NORMAL = "normal"
    DEFENSIVE = "defensive"
    PROTECTIVE = "protective"
    HALT = "halt"
    EMERGENCY = "emergency"

    def _order_index(self) -> int:
        """Get the order index for severity comparison."""
        return _PROTOCOL_ORDER_MAP[self.value]

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, StressResponseProtocol):
            return NotImplemented
        return self._order_index() < other._order_index()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, StressResponseProtocol):
            return NotImplemented
        return self._order_index() <= other._order_index()

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, StressResponseProtocol):
            return NotImplemented
        return self._order_index() > other._order_index()

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, StressResponseProtocol):
            return NotImplemented
        return self._order_index() >= other._order_index()


class RiskState(str, Enum):
    """Overall risk state of the system.

    Attributes:
        OPTIMAL: Low risk, optimal for aggressive strategies.
        STABLE: Normal risk levels.
        ELEVATED: Elevated risk requiring caution.
        STRESSED: High stress, significant risk.
        CRITICAL: Critical risk level, immediate action needed.
    """

    OPTIMAL = "optimal"
    STABLE = "stable"
    ELEVATED = "elevated"
    STRESSED = "stressed"
    CRITICAL = "critical"

    def _order_index(self) -> int:
        """Get the order index for severity comparison."""
        return _RISK_STATE_ORDER_MAP[self.value]

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, RiskState):
            return NotImplemented
        return self._order_index() < other._order_index()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, RiskState):
            return NotImplemented
        return self._order_index() <= other._order_index()

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, RiskState):
            return NotImplemented
        return self._order_index() > other._order_index()

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, RiskState):
            return NotImplemented
        return self._order_index() >= other._order_index()


# =============================================================================
# Data Classes
# =============================================================================


@dataclass(slots=True)
class MarketDepthData:
    """Market depth (order book) data for liquidity analysis.

    Attributes:
        bids: List of (price, quantity) tuples for bid side.
        asks: List of (price, quantity) tuples for ask side.
        timestamp: When data was captured.
        symbol: Optional symbol identifier.
    """

    bids: Sequence[tuple[float, float]] = field(default_factory=list)
    asks: Sequence[tuple[float, float]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    symbol: str = ""

    def get_mid_price(self) -> float | None:
        """Calculate mid-price from best bid and ask."""
        if not self.bids or not self.asks:
            return None
        best_bid = self.bids[0][0] if self.bids else 0.0
        best_ask = self.asks[0][0] if self.asks else 0.0
        if best_bid <= 0 or best_ask <= 0:
            return None
        return (best_bid + best_ask) / 2.0

    def get_spread_bps(self) -> float:
        """Calculate spread in basis points."""
        if not self.bids or not self.asks:
            return float("inf")
        best_bid = self.bids[0][0]
        best_ask = self.asks[0][0]
        if best_bid <= 0:
            return float("inf")
        return (best_ask - best_bid) / best_bid * 10000.0


@dataclass(slots=True)
class LiquidityMetrics:
    """Comprehensive liquidity analysis metrics.

    Attributes:
        bid_depth_value: Total value of bids within analysis range.
        ask_depth_value: Total value of asks within analysis range.
        imbalance_ratio: Order book imbalance (-1 to 1).
        spread_bps: Bid-ask spread in basis points.
        market_impact_estimate: Estimated market impact for target size.
        liquidity_score: Overall liquidity score (0-1, higher is better).
        depth_levels_analyzed: Number of price levels analyzed.
        timestamp: Analysis timestamp.
    """

    bid_depth_value: float = 0.0
    ask_depth_value: float = 0.0
    imbalance_ratio: float = 0.0
    spread_bps: float = 0.0
    market_impact_estimate: float = 0.0
    liquidity_score: float = 1.0
    depth_levels_analyzed: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "bid_depth_value": self.bid_depth_value,
            "ask_depth_value": self.ask_depth_value,
            "imbalance_ratio": self.imbalance_ratio,
            "spread_bps": self.spread_bps,
            "market_impact_estimate": self.market_impact_estimate,
            "liquidity_score": self.liquidity_score,
            "depth_levels_analyzed": self.depth_levels_analyzed,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(slots=True)
class FreeEnergyState:
    """Free energy state for active inference optimization.

    Implements the free energy principle from active inference theory,
    where the system minimizes surprise (free energy) to maintain
    stability and make optimal decisions.

    Attributes:
        current_free_energy: Current free energy value.
        prediction_error: Difference between expected and observed state.
        precision: Inverse variance (confidence in predictions).
        entropy: System entropy measure.
        stability_metric: Lyapunov-like stability indicator.
        descent_rate: Rate of free energy descent.
        is_monotonic: Whether free energy is strictly decreasing.
    """

    current_free_energy: float = 0.0
    prediction_error: float = 0.0
    precision: float = 1.0
    entropy: float = 0.0
    stability_metric: float = 1.0
    descent_rate: float = 0.0
    is_monotonic: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "current_free_energy": self.current_free_energy,
            "prediction_error": self.prediction_error,
            "precision": self.precision,
            "entropy": self.entropy,
            "stability_metric": self.stability_metric,
            "descent_rate": self.descent_rate,
            "is_monotonic": self.is_monotonic,
        }


@dataclass(slots=True)
class RiskAuditEntry:
    """Audit entry for comprehensive risk action logging.

    Attributes:
        entry_id: Unique entry identifier.
        timestamp: When action occurred.
        action_type: Type of risk action.
        trigger_source: What triggered the action.
        risk_state: Risk state when action occurred.
        protocol: Active stress response protocol.
        details: Additional action details.
        position_adjustment: Position size adjustment applied.
        free_energy_state: Free energy state at action time.
    """

    entry_id: str
    timestamp: datetime
    action_type: str
    trigger_source: str
    risk_state: RiskState
    protocol: StressResponseProtocol
    details: dict[str, Any] = field(default_factory=dict)
    position_adjustment: float = 1.0
    free_energy_state: FreeEnergyState | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp.isoformat(),
            "action_type": self.action_type,
            "trigger_source": self.trigger_source,
            "risk_state": self.risk_state.value,
            "protocol": self.protocol.value,
            "details": self.details,
            "position_adjustment": self.position_adjustment,
            "free_energy_state": (
                self.free_energy_state.to_dict() if self.free_energy_state else None
            ),
        }


@dataclass(slots=True)
class AdvancedRiskAssessment:
    """Comprehensive risk assessment result.

    Attributes:
        timestamp: Assessment timestamp.
        risk_state: Current risk state.
        protocol: Recommended stress response protocol.
        risk_score: Composite risk score (0-1).
        volatility_contribution: Risk from volatility.
        liquidity_contribution: Risk from liquidity.
        drawdown_contribution: Risk from drawdown.
        position_multiplier: Recommended position size multiplier.
        free_energy_state: Current free energy state.
        liquidity_metrics: Latest liquidity analysis.
        recommendations: List of recommended actions.
        is_trading_allowed: Whether trading is permitted.
    """

    timestamp: datetime
    risk_state: RiskState = RiskState.STABLE
    protocol: StressResponseProtocol = StressResponseProtocol.NORMAL
    risk_score: float = 0.0
    volatility_contribution: float = 0.0
    liquidity_contribution: float = 0.0
    drawdown_contribution: float = 0.0
    position_multiplier: float = 1.0
    free_energy_state: FreeEnergyState | None = None
    liquidity_metrics: LiquidityMetrics | None = None
    recommendations: tuple[str, ...] = ()
    is_trading_allowed: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "risk_state": self.risk_state.value,
            "protocol": self.protocol.value,
            "risk_score": self.risk_score,
            "volatility_contribution": self.volatility_contribution,
            "liquidity_contribution": self.liquidity_contribution,
            "drawdown_contribution": self.drawdown_contribution,
            "position_multiplier": self.position_multiplier,
            "free_energy_state": (
                self.free_energy_state.to_dict() if self.free_energy_state else None
            ),
            "liquidity_metrics": (
                self.liquidity_metrics.to_dict() if self.liquidity_metrics else None
            ),
            "recommendations": list(self.recommendations),
            "is_trading_allowed": self.is_trading_allowed,
        }


@dataclass(slots=True)
class AdvancedRiskConfig:
    """Configuration for advanced risk manager.

    Attributes:
        volatility_lookback: Periods for volatility calculation.
        liquidity_depth_levels: Order book levels for analysis.
        spread_stress_threshold_bps: Spread threshold for stress.
        imbalance_stress_threshold: Order book imbalance threshold.
        drawdown_elevated_threshold: Drawdown for elevated state.
        drawdown_stressed_threshold: Drawdown for stressed state.
        drawdown_critical_threshold: Drawdown for critical state.
        volatility_elevated_ratio: Volatility ratio for elevated.
        volatility_stressed_ratio: Volatility ratio for stressed.
        volatility_critical_ratio: Volatility ratio for critical.
        fe_learning_rate: Free energy learning rate.
        fe_precision_base: Base precision for free energy.
        fe_monotonicity_epsilon: Epsilon for monotonicity check.
        position_reduction_defensive: Position multiplier for defensive.
        position_reduction_protective: Position multiplier for protective.
        audit_log_max_entries: Maximum audit entries to retain.
        enable_fault_tolerance: Enable graceful degradation.

    Raises:
        ValueError: If configuration parameters are invalid.
    """

    volatility_lookback: int = 20
    liquidity_depth_levels: int = 10
    spread_stress_threshold_bps: float = 50.0
    imbalance_stress_threshold: float = 0.6
    drawdown_elevated_threshold: float = 0.05
    drawdown_stressed_threshold: float = 0.10
    drawdown_critical_threshold: float = 0.15
    volatility_elevated_ratio: float = 1.5
    volatility_stressed_ratio: float = 2.0
    volatility_critical_ratio: float = 3.0
    fe_learning_rate: float = 0.1
    fe_precision_base: float = 1.0
    fe_monotonicity_epsilon: float = 1e-4
    position_reduction_defensive: float = 0.7
    position_reduction_protective: float = 0.3
    audit_log_max_entries: int = 10000
    enable_fault_tolerance: bool = True

    def __post_init__(self) -> None:
        """Validate configuration parameters."""
        if self.volatility_lookback < 2:
            raise ValueError("volatility_lookback must be >= 2")
        if self.liquidity_depth_levels < 1:
            raise ValueError("liquidity_depth_levels must be >= 1")
        if self.spread_stress_threshold_bps <= 0:
            raise ValueError("spread_stress_threshold_bps must be positive")
        if not 0 < self.imbalance_stress_threshold <= 1:
            raise ValueError("imbalance_stress_threshold must be in (0, 1]")
        if not 0 < self.drawdown_elevated_threshold < self.drawdown_stressed_threshold:
            raise ValueError(
                "drawdown thresholds must be: 0 < elevated < stressed < critical"
            )
        if not self.drawdown_stressed_threshold < self.drawdown_critical_threshold <= 1:
            raise ValueError(
                "drawdown thresholds must be: 0 < elevated < stressed < critical <= 1"
            )
        if not 1 < self.volatility_elevated_ratio < self.volatility_stressed_ratio:
            raise ValueError(
                "volatility ratios must be: 1 < elevated < stressed < critical"
            )
        if not self.volatility_stressed_ratio < self.volatility_critical_ratio:
            raise ValueError(
                "volatility ratios must be: 1 < elevated < stressed < critical"
            )
        if not 0 < self.fe_learning_rate <= 1:
            raise ValueError("fe_learning_rate must be in (0, 1]")
        if self.fe_precision_base <= 0:
            raise ValueError("fe_precision_base must be positive")
        if not 0 < self.position_reduction_defensive <= 1:
            raise ValueError("position_reduction_defensive must be in (0, 1]")
        if not 0 < self.position_reduction_protective <= 1:
            raise ValueError("position_reduction_protective must be in (0, 1]")
        if self.audit_log_max_entries < 1:
            raise ValueError("audit_log_max_entries must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "volatility_lookback": self.volatility_lookback,
            "liquidity_depth_levels": self.liquidity_depth_levels,
            "spread_stress_threshold_bps": self.spread_stress_threshold_bps,
            "imbalance_stress_threshold": self.imbalance_stress_threshold,
            "drawdown_elevated_threshold": self.drawdown_elevated_threshold,
            "drawdown_stressed_threshold": self.drawdown_stressed_threshold,
            "drawdown_critical_threshold": self.drawdown_critical_threshold,
            "volatility_elevated_ratio": self.volatility_elevated_ratio,
            "volatility_stressed_ratio": self.volatility_stressed_ratio,
            "volatility_critical_ratio": self.volatility_critical_ratio,
            "fe_learning_rate": self.fe_learning_rate,
            "fe_precision_base": self.fe_precision_base,
            "fe_monotonicity_epsilon": self.fe_monotonicity_epsilon,
            "position_reduction_defensive": self.position_reduction_defensive,
            "position_reduction_protective": self.position_reduction_protective,
            "audit_log_max_entries": self.audit_log_max_entries,
            "enable_fault_tolerance": self.enable_fault_tolerance,
        }


# =============================================================================
# Main Class
# =============================================================================


class AdvancedRiskManager:
    """High-precision advanced risk manager for AI trading systems.

    Integrates adaptive risk modulation, free energy optimization,
    stress response protocols, and comprehensive auditing for
    transparent and compliant risk management.

    Example:
        >>> manager = AdvancedRiskManager()
        >>> assessment = manager.assess_risk(
        ...     current_price=100.0,
        ...     volatility=0.02,
        ... )
        >>> if not assessment.is_trading_allowed:
        ...     print("Trading halted due to risk conditions")
    """

    def __init__(
        self,
        config: AdvancedRiskConfig | None = None,
        *,
        time_source: Callable[[], datetime] | None = None,
    ) -> None:
        """Initialize the advanced risk manager.

        Args:
            config: Manager configuration.
            time_source: Optional time source for testing.
        """
        self._config = config or AdvancedRiskConfig()
        self._time = time_source or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()

        # State tracking
        self._current_protocol = StressResponseProtocol.NORMAL
        self._current_risk_state = RiskState.STABLE
        self._position_multiplier = 1.0

        # Historical data for analysis
        self._returns_history: deque[float] = deque(
            maxlen=self._config.volatility_lookback * 5
        )
        self._volatility_history: deque[float] = deque(
            maxlen=self._config.volatility_lookback
        )
        self._drawdown_history: deque[float] = deque(
            maxlen=self._config.volatility_lookback
        )

        # Free energy state
        self._fe_state = FreeEnergyState()
        self._fe_history: deque[float] = deque(maxlen=100)
        self._baseline_volatility: float | None = None

        # Peak tracking for drawdown
        self._peak_equity = 0.0
        self._current_equity = 0.0

        # Audit trail
        self._audit_trail: deque[RiskAuditEntry] = deque(
            maxlen=self._config.audit_log_max_entries
        )
        self._audit_counter = 0

        # Fault tolerance state
        self._last_successful_assessment: AdvancedRiskAssessment | None = None
        self._consecutive_errors = 0

        LOGGER.info(
            "Advanced risk manager initialized",
            extra={"config": self._config.to_dict()},
        )

    @property
    def config(self) -> AdvancedRiskConfig:
        """Get current configuration."""
        return self._config

    @property
    def current_protocol(self) -> StressResponseProtocol:
        """Get current stress response protocol."""
        with self._lock:
            return self._current_protocol

    @property
    def current_risk_state(self) -> RiskState:
        """Get current risk state."""
        with self._lock:
            return self._current_risk_state

    @property
    def position_multiplier(self) -> float:
        """Get current position size multiplier."""
        with self._lock:
            return self._position_multiplier

    def analyze_liquidity(
        self,
        market_depth: MarketDepthData,
        *,
        target_trade_size: float = 0.0,
    ) -> LiquidityMetrics:
        """Analyze market depth for liquidity assessment.

        Computes comprehensive liquidity metrics from order book data,
        including depth, imbalance, and estimated market impact.

        Args:
            market_depth: Current order book data.
            target_trade_size: Target trade size for impact estimation.

        Returns:
            Comprehensive liquidity metrics.
        """
        with self._lock:
            try:
                # Calculate bid depth
                bid_depth = 0.0
                bid_levels = min(
                    len(market_depth.bids), self._config.liquidity_depth_levels
                )
                for price, qty in market_depth.bids[:bid_levels]:
                    if price > 0 and qty > 0:
                        bid_depth += price * qty

                # Calculate ask depth
                ask_depth = 0.0
                ask_levels = min(
                    len(market_depth.asks), self._config.liquidity_depth_levels
                )
                for price, qty in market_depth.asks[:ask_levels]:
                    if price > 0 and qty > 0:
                        ask_depth += price * qty

                # Calculate imbalance
                total_depth = bid_depth + ask_depth
                if total_depth > 0:
                    imbalance = (bid_depth - ask_depth) / total_depth
                else:
                    imbalance = 0.0

                # Calculate spread
                spread_bps = market_depth.get_spread_bps()
                if not math.isfinite(spread_bps):
                    spread_bps = 1000.0  # Assign high value for missing data

                # Estimate market impact
                impact = 0.0
                if target_trade_size > 0 and total_depth > 0:
                    # Simple linear impact model
                    impact = target_trade_size / total_depth * 100.0

                # Calculate overall liquidity score
                # Higher depth, lower spread, balanced book = better liquidity
                depth_score = min(1.0, total_depth / 1_000_000.0)  # Normalize
                spread_score = max(0.0, 1.0 - spread_bps / 100.0)
                balance_score = 1.0 - abs(imbalance)
                liquidity_score = (depth_score + spread_score + balance_score) / 3.0

                return LiquidityMetrics(
                    bid_depth_value=bid_depth,
                    ask_depth_value=ask_depth,
                    imbalance_ratio=imbalance,
                    spread_bps=spread_bps,
                    market_impact_estimate=impact,
                    liquidity_score=liquidity_score,
                    depth_levels_analyzed=max(bid_levels, ask_levels),
                    timestamp=self._time(),
                )

            except Exception as e:
                if self._config.enable_fault_tolerance:
                    LOGGER.warning("Liquidity analysis failed: %s", e)
                    return LiquidityMetrics(
                        liquidity_score=0.5,  # Conservative default
                        timestamp=self._time(),
                    )
                raise

    def update_free_energy(
        self,
        observed_volatility: float,
        observed_drawdown: float,
        *,
        expected_volatility: float | None = None,
    ) -> FreeEnergyState:
        """Update free energy state based on observations.

        Implements active inference free energy minimization:
        F = (1/2) * precision * prediction_error^2 + entropy

        Args:
            observed_volatility: Current observed volatility.
            observed_drawdown: Current drawdown.
            expected_volatility: Expected volatility (uses baseline if None).

        Returns:
            Updated free energy state.
        """
        with self._lock:
            safe_drawdown = 0.0
            if math.isfinite(observed_drawdown):
                safe_drawdown = min(max(observed_drawdown, 0.0), 1.0)

            if not math.isfinite(observed_volatility) or observed_volatility < 0:
                observed_volatility = (
                    self._baseline_volatility
                    if self._baseline_volatility is not None
                    and math.isfinite(self._baseline_volatility)
                    else 0.0
                )

            # Update baseline if not set
            if self._baseline_volatility is None or not math.isfinite(
                self._baseline_volatility
            ):
                self._baseline_volatility = max(0.001, observed_volatility)

            expected = (
                expected_volatility
                if expected_volatility is not None
                else self._baseline_volatility
            )
            if not math.isfinite(expected) or expected <= 0:
                expected = self._baseline_volatility

            # Prediction error (surprise)
            prediction_error = abs(observed_volatility - expected)
            if not math.isfinite(prediction_error):
                prediction_error = 0.0

            # Precision (inverse variance of recent observations)
            # Use ddof=1 for unbiased sample variance estimation
            vol_history = list(self._volatility_history)
            if len(vol_history) >= 3:
                variance = float(np.var(vol_history, ddof=1))
                # Guard against negative variance from numerical instability
                variance = max(0.0, variance)
                precision = self._config.fe_precision_base / (variance + 1e-6)
            else:
                precision = self._config.fe_precision_base

            # Clamp precision for numerical stability
            precision = max(0.01, min(100.0, precision))

            # Compute entropy from drawdown and volatility
            # Higher uncertainty = higher entropy
            entropy = (
                0.5 * math.log(max(1e-6, observed_volatility))
                + 0.5 * safe_drawdown
            )

            # Free energy: F = precision * prediction_error^2 / 2 + entropy
            new_fe = (precision * prediction_error * prediction_error / 2.0) + entropy
            if not math.isfinite(new_fe):
                new_fe = self._fe_state.current_free_energy

            # Check monotonicity
            previous_fe = self._fe_state.current_free_energy
            is_monotonic = (
                new_fe <= previous_fe + self._config.fe_monotonicity_epsilon
            )

            # If violating monotonicity, apply correction
            if not is_monotonic and len(self._fe_history) > 0:
                # Apply decay to enforce descent
                new_fe = previous_fe * 0.995

            # Compute descent rate
            if len(self._fe_history) >= 2:
                descent_rate = (
                    self._fe_history[-1] - new_fe
                ) / max(1, len(self._fe_history))
            else:
                descent_rate = 0.0

            # Compute stability metric (Lyapunov-like)
            # Use ddof=1 for unbiased sample variance estimation
            if len(self._fe_history) >= 5:
                recent_fe = list(self._fe_history)[-5:]
                fe_variance = float(np.var(recent_fe, ddof=1))
                # Guard against negative variance from numerical instability
                fe_variance = max(0.0, fe_variance)
                stability = 1.0 / (1.0 + fe_variance)
            else:
                stability = 1.0

            # Update state
            self._fe_state = FreeEnergyState(
                current_free_energy=new_fe,
                prediction_error=prediction_error,
                precision=precision,
                entropy=max(0, entropy),
                stability_metric=stability,
                descent_rate=descent_rate,
                is_monotonic=is_monotonic,
            )

            # Track history
            self._fe_history.append(new_fe)

            return self._fe_state

    def assess_risk(
        self,
        *,
        current_price: float | None = None,
        peak_price: float | None = None,
        volatility: float | None = None,
        returns: NDArray[np.float64] | list[float] | None = None,
        equity: float | None = None,
        liquidity_metrics: LiquidityMetrics | None = None,
    ) -> AdvancedRiskAssessment:
        """Perform comprehensive risk assessment.

        Analyzes all risk dimensions and returns a complete assessment
        with recommended actions and position adjustments.

        Args:
            current_price: Current market price.
            peak_price: Peak price for drawdown calculation.
            volatility: Current volatility (calculated from returns if None).
            returns: Recent price returns.
            equity: Current portfolio equity.
            liquidity_metrics: Pre-computed liquidity metrics.

        Returns:
            Comprehensive risk assessment.
        """
        with self._lock:
            try:
                now = self._time()

                # Update returns history
                if returns is not None:
                    returns_array = np.asarray(returns, dtype=float)
                    for r in returns_array.flatten():
                        if np.isfinite(r):
                            self._returns_history.append(float(r))

                # Calculate volatility
                # Use ddof=1 for unbiased sample standard deviation estimation
                if volatility is not None:
                    current_vol = volatility
                elif len(self._returns_history) >= 2:
                    returns_sample = list(self._returns_history)[-20:]
                    current_vol = float(np.std(returns_sample, ddof=1))
                    # Guard against NaN from constant series (std=0 with ddof=1)
                    if not np.isfinite(current_vol):
                        current_vol = 0.0
                else:
                    current_vol = 0.0

                if not np.isfinite(current_vol) or current_vol < 0:
                    current_vol = 0.0

                current_vol = float(current_vol)
                self._volatility_history.append(current_vol)

                # Update equity and drawdown
                if equity is not None:
                    self._current_equity = equity
                    if equity > self._peak_equity:
                        self._peak_equity = equity

                # Calculate drawdown
                if (
                    current_price is not None
                    and peak_price is not None
                    and peak_price > 0
                ):
                    drawdown = max(0.0, (peak_price - current_price) / peak_price)
                elif self._peak_equity > 0:
                    drawdown = max(
                        0.0,
                        (self._peak_equity - self._current_equity) / self._peak_equity,
                    )
                else:
                    drawdown = 0.0

                if not np.isfinite(drawdown) or drawdown < 0:
                    drawdown = 0.0
                else:
                    drawdown = min(drawdown, 1.0)

                self._drawdown_history.append(drawdown)

                # Update free energy
                self.update_free_energy(current_vol, drawdown)

                # Assess individual risk components
                vol_risk = self._assess_volatility_risk(current_vol)
                liq_risk = self._assess_liquidity_risk(liquidity_metrics)
                dd_risk = self._assess_drawdown_risk(drawdown)

                # Composite risk score (weighted average)
                risk_score = (
                    0.35 * vol_risk
                    + 0.25 * liq_risk
                    + 0.40 * dd_risk
                )

                # Factor in free energy stability
                if self._fe_state.stability_metric < 0.5:
                    risk_score = min(1.0, risk_score * 1.2)
                if not self._fe_state.is_monotonic:
                    risk_score = min(1.0, risk_score * 1.1)

                risk_score = float(np.clip(risk_score, 0.0, 1.0))

                # Determine risk state
                risk_state = self._determine_risk_state(risk_score)

                # Determine stress response protocol
                protocol = self._determine_protocol(risk_state, risk_score)

                # Calculate position multiplier
                position_mult = self._calculate_position_multiplier(protocol)

                # Determine if trading is allowed
                trading_allowed = protocol not in (
                    StressResponseProtocol.HALT,
                    StressResponseProtocol.EMERGENCY,
                )

                # Generate recommendations
                recommendations = self._generate_recommendations(
                    risk_state, protocol, vol_risk, liq_risk, dd_risk
                )

                # Update internal state
                self._current_risk_state = risk_state
                self._current_protocol = protocol
                self._position_multiplier = position_mult

                assessment = AdvancedRiskAssessment(
                    timestamp=now,
                    risk_state=risk_state,
                    protocol=protocol,
                    risk_score=risk_score,
                    volatility_contribution=vol_risk,
                    liquidity_contribution=liq_risk,
                    drawdown_contribution=dd_risk,
                    position_multiplier=position_mult,
                    free_energy_state=self._fe_state,
                    liquidity_metrics=liquidity_metrics,
                    recommendations=tuple(recommendations),
                    is_trading_allowed=trading_allowed,
                )

                # Record audit entry
                self._record_audit_entry(
                    action_type="risk_assessment",
                    trigger_source="scheduled",
                    details={
                        "volatility": current_vol,
                        "drawdown": drawdown,
                        "risk_score": risk_score,
                    },
                )

                # Update fault tolerance state
                self._last_successful_assessment = assessment
                self._consecutive_errors = 0

                return assessment

            except Exception as e:
                self._consecutive_errors += 1
                LOGGER.error("Risk assessment failed: %s", e, exc_info=True)

                if self._config.enable_fault_tolerance:
                    return self._get_fallback_assessment(str(e))
                raise

    def escalate_protocol(
        self,
        reason: str,
        *,
        source: str = "manual",
    ) -> StressResponseProtocol:
        """Escalate to the next higher stress response protocol.

        Args:
            reason: Reason for escalation.
            source: Source of escalation request.

        Returns:
            New protocol level after escalation.
        """
        with self._lock:
            protocol_order = [
                StressResponseProtocol.NORMAL,
                StressResponseProtocol.DEFENSIVE,
                StressResponseProtocol.PROTECTIVE,
                StressResponseProtocol.HALT,
                StressResponseProtocol.EMERGENCY,
            ]

            current_idx = protocol_order.index(self._current_protocol)
            if current_idx < len(protocol_order) - 1:
                new_protocol = protocol_order[current_idx + 1]
                self._current_protocol = new_protocol
                self._position_multiplier = self._calculate_position_multiplier(
                    new_protocol
                )

                self._record_audit_entry(
                    action_type="protocol_escalation",
                    trigger_source=source,
                    details={"reason": reason, "new_protocol": new_protocol.value},
                )

                LOGGER.warning(
                    "Protocol escalated to %s: %s",
                    new_protocol.value,
                    reason,
                )

            return self._current_protocol

    def deescalate_protocol(
        self,
        reason: str,
        *,
        source: str = "system",
    ) -> StressResponseProtocol:
        """De-escalate to the next lower stress response protocol.

        Args:
            reason: Reason for de-escalation.
            source: Source of de-escalation request.

        Returns:
            New protocol level after de-escalation.
        """
        with self._lock:
            protocol_order = [
                StressResponseProtocol.NORMAL,
                StressResponseProtocol.DEFENSIVE,
                StressResponseProtocol.PROTECTIVE,
                StressResponseProtocol.HALT,
                StressResponseProtocol.EMERGENCY,
            ]

            current_idx = protocol_order.index(self._current_protocol)
            if current_idx > 0:
                new_protocol = protocol_order[current_idx - 1]
                self._current_protocol = new_protocol
                self._position_multiplier = self._calculate_position_multiplier(
                    new_protocol
                )

                self._record_audit_entry(
                    action_type="protocol_deescalation",
                    trigger_source=source,
                    details={"reason": reason, "new_protocol": new_protocol.value},
                )

                LOGGER.info(
                    "Protocol de-escalated to %s: %s",
                    new_protocol.value,
                    reason,
                )

            return self._current_protocol

    def is_trading_allowed(self) -> bool:
        """Check if trading is currently allowed.

        Returns:
            True if trading operations are permitted.
        """
        with self._lock:
            return self._current_protocol not in (
                StressResponseProtocol.HALT,
                StressResponseProtocol.EMERGENCY,
            )

    def get_position_adjustment(self) -> float:
        """Get current position size adjustment multiplier.

        Returns:
            Multiplier to apply to position sizes (0.0 to 1.0).
        """
        with self._lock:
            return self._position_multiplier

    def get_audit_trail(
        self,
        *,
        limit: int | None = None,
        action_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get audit trail entries.

        Args:
            limit: Maximum number of entries to return.
            action_type: Filter by action type.

        Returns:
            List of audit entries as dictionaries.
        """
        with self._lock:
            entries = list(self._audit_trail)

            if action_type:
                entries = [e for e in entries if e.action_type == action_type]

            if limit:
                entries = entries[-limit:]

            return [e.to_dict() for e in entries]

    def get_status(self) -> dict[str, Any]:
        """Get comprehensive manager status.

        Returns:
            Status dictionary with all current state information.
        """
        with self._lock:
            return {
                "risk_state": self._current_risk_state.value,
                "protocol": self._current_protocol.value,
                "position_multiplier": self._position_multiplier,
                "trading_allowed": self.is_trading_allowed(),
                "free_energy_state": self._fe_state.to_dict(),
                "baseline_volatility": self._baseline_volatility,
                "returns_count": len(self._returns_history),
                "audit_entries_count": len(self._audit_trail),
                "consecutive_errors": self._consecutive_errors,
                "config": self._config.to_dict(),
            }

    def reset(self) -> None:
        """Reset manager to initial state."""
        with self._lock:
            self._current_protocol = StressResponseProtocol.NORMAL
            self._current_risk_state = RiskState.STABLE
            self._position_multiplier = 1.0

            self._returns_history.clear()
            self._volatility_history.clear()
            self._drawdown_history.clear()

            self._fe_state = FreeEnergyState()
            self._fe_history.clear()
            self._baseline_volatility = None

            self._peak_equity = 0.0
            self._current_equity = 0.0

            self._audit_trail.clear()
            self._audit_counter = 0

            self._last_successful_assessment = None
            self._consecutive_errors = 0

            LOGGER.info("Advanced risk manager reset")

    def get_historical_statistics(self) -> dict[str, Any]:
        """Get statistical summary of historical risk data.

        Provides insights into the manager's performance over time,
        useful for backtesting and optimization.

        Returns:
            Dictionary with historical statistics.
        """
        with self._lock:
            stats: dict[str, Any] = {
                "data_points": {
                    "returns": len(self._returns_history),
                    "volatility": len(self._volatility_history),
                    "drawdown": len(self._drawdown_history),
                    "free_energy": len(self._fe_history),
                },
            }

            # Volatility statistics
            # Use ddof=1 for unbiased sample standard deviation estimation
            if self._volatility_history:
                vol_list = list(self._volatility_history)
                vol_std = float(np.std(vol_list, ddof=1)) if len(vol_list) > 1 else 0.0
                # Guard against NaN from constant series
                if not np.isfinite(vol_std):
                    vol_std = 0.0
                stats["volatility_stats"] = {
                    "mean": float(np.mean(vol_list)),
                    "std": vol_std,
                    "min": float(min(vol_list)),
                    "max": float(max(vol_list)),
                    "current": vol_list[-1] if vol_list else None,
                }

            # Drawdown statistics
            if self._drawdown_history:
                dd_list = list(self._drawdown_history)
                stats["drawdown_stats"] = {
                    "mean": float(np.mean(dd_list)),
                    "max": float(max(dd_list)),
                    "current": dd_list[-1] if dd_list else None,
                }

            # Free energy statistics
            # Use ddof=1 for unbiased sample standard deviation estimation
            if self._fe_history:
                fe_list = list(self._fe_history)
                fe_std = float(np.std(fe_list, ddof=1)) if len(fe_list) > 1 else 0.0
                # Guard against NaN from constant series
                if not np.isfinite(fe_std):
                    fe_std = 0.0
                stats["free_energy_stats"] = {
                    "mean": float(np.mean(fe_list)),
                    "std": fe_std,
                    "min": float(min(fe_list)),
                    "max": float(max(fe_list)),
                    "current": fe_list[-1] if fe_list else None,
                    "is_stable": self._fe_state.stability_metric > 0.5,
                }

            # Audit statistics
            if self._audit_trail:
                action_counts: dict[str, int] = {}
                for entry in self._audit_trail:
                    action_counts[entry.action_type] = (
                        action_counts.get(entry.action_type, 0) + 1
                    )
                stats["audit_stats"] = {
                    "total_entries": len(self._audit_trail),
                    "action_counts": action_counts,
                }

            return stats

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _assess_volatility_risk(self, volatility: float) -> float:
        """Assess risk contribution from volatility.

        Math Contract:
            Input: volatility (float >= 0), uses self._baseline_volatility (float > 0)
            Output: risk score in [0.0, 1.0]
            Invariants:
                - Result is always finite
                - Result is monotonic with respect to volatility/baseline ratio
            NaN/Inf Policy: Return conservative default (0.3) if inputs invalid
            Tolerance: rtol=1e-7 for float64 computations
        """
        # Guard against non-finite volatility input
        if not np.isfinite(volatility) or volatility < 0:
            return 0.3  # Conservative default for invalid input

        if self._baseline_volatility is None or self._baseline_volatility <= 0:
            return 0.3  # Default moderate risk when no baseline

        vol_ratio = volatility / self._baseline_volatility

        # Guard against non-finite ratio (shouldn't happen but defensive)
        if not np.isfinite(vol_ratio):
            return 0.3

        if vol_ratio >= self._config.volatility_critical_ratio:
            return 1.0
        elif vol_ratio >= self._config.volatility_stressed_ratio:
            normalized = (vol_ratio - self._config.volatility_stressed_ratio) / (
                self._config.volatility_critical_ratio
                - self._config.volatility_stressed_ratio
            )
            return 0.6 + 0.4 * normalized
        elif vol_ratio >= self._config.volatility_elevated_ratio:
            normalized = (vol_ratio - self._config.volatility_elevated_ratio) / (
                self._config.volatility_stressed_ratio
                - self._config.volatility_elevated_ratio
            )
            return 0.3 + 0.3 * normalized
        else:
            return max(0.0, (vol_ratio - 1.0) / (
                self._config.volatility_elevated_ratio - 1.0
            ) * 0.3)

    def _assess_liquidity_risk(
        self, liquidity: LiquidityMetrics | None
    ) -> float:
        """Assess risk contribution from liquidity."""
        if liquidity is None:
            return 0.3  # Default moderate risk when no data

        risk = 0.0

        # Spread risk
        if liquidity.spread_bps > self._config.spread_stress_threshold_bps:
            spread_excess = (
                liquidity.spread_bps - self._config.spread_stress_threshold_bps
            ) / self._config.spread_stress_threshold_bps
            risk = max(risk, min(1.0, spread_excess))

        # Imbalance risk
        imbalance = abs(liquidity.imbalance_ratio)
        if imbalance > self._config.imbalance_stress_threshold:
            imbalance_excess = (
                imbalance - self._config.imbalance_stress_threshold
            ) / (1.0 - self._config.imbalance_stress_threshold)
            risk = max(risk, min(1.0, imbalance_excess))

        # Low liquidity score risk
        if liquidity.liquidity_score < 0.3:
            risk = max(risk, 1.0 - liquidity.liquidity_score * 2)

        return risk

    def _assess_drawdown_risk(self, drawdown: float) -> float:
        """Assess risk contribution from drawdown."""
        if drawdown >= self._config.drawdown_critical_threshold:
            return 1.0
        elif drawdown >= self._config.drawdown_stressed_threshold:
            normalized = (drawdown - self._config.drawdown_stressed_threshold) / (
                self._config.drawdown_critical_threshold
                - self._config.drawdown_stressed_threshold
            )
            return 0.6 + 0.4 * normalized
        elif drawdown >= self._config.drawdown_elevated_threshold:
            normalized = (drawdown - self._config.drawdown_elevated_threshold) / (
                self._config.drawdown_stressed_threshold
                - self._config.drawdown_elevated_threshold
            )
            return 0.3 + 0.3 * normalized
        else:
            return drawdown / self._config.drawdown_elevated_threshold * 0.3

    def _determine_risk_state(self, risk_score: float) -> RiskState:
        """Determine overall risk state from composite score."""
        if risk_score >= 0.8:
            return RiskState.CRITICAL
        elif risk_score >= 0.6:
            return RiskState.STRESSED
        elif risk_score >= 0.3:
            return RiskState.ELEVATED
        elif risk_score >= 0.1:
            return RiskState.STABLE
        else:
            return RiskState.OPTIMAL

    def _determine_protocol(
        self, risk_state: RiskState, risk_score: float
    ) -> StressResponseProtocol:
        """Determine appropriate stress response protocol."""
        protocol_map = {
            RiskState.OPTIMAL: StressResponseProtocol.NORMAL,
            RiskState.STABLE: StressResponseProtocol.NORMAL,
            RiskState.ELEVATED: StressResponseProtocol.DEFENSIVE,
            RiskState.STRESSED: StressResponseProtocol.PROTECTIVE,
            RiskState.CRITICAL: StressResponseProtocol.HALT,
        }

        new_protocol = protocol_map.get(risk_state, StressResponseProtocol.NORMAL)

        # Don't automatically de-escalate from halt/emergency
        if self._current_protocol in (
            StressResponseProtocol.HALT,
            StressResponseProtocol.EMERGENCY,
        ):
            if new_protocol not in (
                StressResponseProtocol.HALT,
                StressResponseProtocol.EMERGENCY,
            ):
                # Require explicit de-escalation
                return self._current_protocol

        return new_protocol

    def _calculate_position_multiplier(
        self, protocol: StressResponseProtocol
    ) -> float:
        """Calculate position size multiplier for protocol."""
        multipliers = {
            StressResponseProtocol.NORMAL: 1.0,
            StressResponseProtocol.DEFENSIVE: self._config.position_reduction_defensive,
            StressResponseProtocol.PROTECTIVE: self._config.position_reduction_protective,
            StressResponseProtocol.HALT: 0.0,
            StressResponseProtocol.EMERGENCY: 0.0,
        }
        return multipliers.get(protocol, 1.0)

    def _generate_recommendations(
        self,
        risk_state: RiskState,
        protocol: StressResponseProtocol,
        vol_risk: float,
        liq_risk: float,
        dd_risk: float,
    ) -> list[str]:
        """Generate actionable recommendations."""
        recommendations: list[str] = []

        if risk_state == RiskState.CRITICAL:
            recommendations.append(
                "CRITICAL: Immediate risk reduction required. Halt new trades."
            )

        if vol_risk >= 0.6:
            recommendations.append(
                f"HIGH VOLATILITY: Consider reducing position sizes (vol risk: {vol_risk:.1%})"
            )

        if liq_risk >= 0.6:
            recommendations.append(
                f"LIQUIDITY STRESS: Review execution strategies (liq risk: {liq_risk:.1%})"
            )

        if dd_risk >= 0.6:
            recommendations.append(
                f"DRAWDOWN ALERT: Review stop-loss levels (dd risk: {dd_risk:.1%})"
            )

        if not self._fe_state.is_monotonic:
            recommendations.append(
                "FREE ENERGY: System instability detected, extra caution advised"
            )

        if protocol == StressResponseProtocol.PROTECTIVE:
            recommendations.append(
                "PROTECTIVE MODE: Only essential trades, prepare exit strategies"
            )
        elif protocol == StressResponseProtocol.HALT:
            recommendations.append(
                "TRADING HALTED: Monitor conditions for recovery"
            )

        return recommendations

    def _record_audit_entry(
        self,
        action_type: str,
        trigger_source: str,
        details: dict[str, Any],
    ) -> None:
        """Record an entry to the audit trail."""
        self._audit_counter += 1
        entry = RiskAuditEntry(
            entry_id=f"RISK-{self._audit_counter:08d}",
            timestamp=self._time(),
            action_type=action_type,
            trigger_source=trigger_source,
            risk_state=self._current_risk_state,
            protocol=self._current_protocol,
            details=details,
            position_adjustment=self._position_multiplier,
            free_energy_state=FreeEnergyState(
                current_free_energy=self._fe_state.current_free_energy,
                prediction_error=self._fe_state.prediction_error,
                precision=self._fe_state.precision,
                entropy=self._fe_state.entropy,
                stability_metric=self._fe_state.stability_metric,
                descent_rate=self._fe_state.descent_rate,
                is_monotonic=self._fe_state.is_monotonic,
            ),
        )
        self._audit_trail.append(entry)

    def _get_fallback_assessment(self, error_msg: str) -> AdvancedRiskAssessment:
        """Get fallback assessment when primary assessment fails."""
        # If we have a recent successful assessment, use conservative version
        if self._last_successful_assessment is not None:
            base = self._last_successful_assessment
            # Use custom comparison operators for proper severity ordering
            fallback_risk_state = (
                base.risk_state
                if base.risk_state >= RiskState.ELEVATED
                else RiskState.ELEVATED
            )
            return AdvancedRiskAssessment(
                timestamp=self._time(),
                risk_state=fallback_risk_state,
                protocol=StressResponseProtocol.DEFENSIVE,
                risk_score=min(1.0, base.risk_score + 0.2),
                volatility_contribution=base.volatility_contribution,
                liquidity_contribution=base.liquidity_contribution,
                drawdown_contribution=base.drawdown_contribution,
                position_multiplier=self._config.position_reduction_defensive,
                free_energy_state=self._fe_state,
                liquidity_metrics=base.liquidity_metrics,
                recommendations=(
                    f"FALLBACK MODE: Assessment error ({error_msg}), using conservative defaults",
                ),
                is_trading_allowed=True,
            )

        # No prior assessment, use very conservative defaults
        return AdvancedRiskAssessment(
            timestamp=self._time(),
            risk_state=RiskState.ELEVATED,
            protocol=StressResponseProtocol.DEFENSIVE,
            risk_score=0.5,
            position_multiplier=self._config.position_reduction_defensive,
            recommendations=(
                f"FALLBACK MODE: Initial assessment error ({error_msg}), using defensive defaults",
            ),
            is_trading_allowed=True,
        )
