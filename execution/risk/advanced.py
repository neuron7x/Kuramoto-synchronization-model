"""Advanced risk controls for TradePulse execution.

This module layers portfolio-level controls on top of the baseline
:mod:`execution.risk` engine.  The focus is deterministic behaviour, clear
math, and minimal external dependencies so that the logic can execute from
latency-sensitive contexts (synchronous or asynchronous) without excessive
allocation pressure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from statistics import fmean
from typing import Callable, Iterable, Mapping, MutableMapping, Sequence

__all__ = [
    "AdvancedRiskController",
    "AdvancedRiskState",
    "CorrelationLimitGuard",
    "DrawdownBreaker",
    "KellyCriterionPositionSizer",
    "LiquidationCascadePreventer",
    "MarginMonitor",
    "MarketCondition",
    "PositionRequest",
    "RegimeAdaptiveExposureGuard",
    "RiskMetricsCalculator",
    "RiskParityAllocator",
    "TimeWeightedExposureTracker",
    "VolatilityAdjustedSizer",
    "VolatilityRegime",
]


class VolatilityRegime(Enum):
    """Classification of realised volatility regimes for adaptive risk controls."""

    CALM = auto()
    NORMAL = auto()
    STRESSED = auto()
    CRITICAL = auto()


@dataclass(slots=True)
class _RegimeState:
    """Internal exponential moving statistics for a single symbol."""

    ewma_abs_return: float = 0.0
    samples: int = 0
    last_timestamp: float | None = None
    last_regime: VolatilityRegime | None = None
    cooldown_until: float = 0.0


class RegimeAdaptiveExposureGuard:
    """Dynamically scale exposure allowances based on realised volatility regimes.

    The guard ingests absolute returns via :meth:`observe` and maintains an
    exponentially weighted estimate of realised volatility.  The resulting regime
    classification (``CALM`` → ``CRITICAL``) is then mapped to exposure
    multipliers so higher-volatility states automatically tighten position
    limits, while tranquil markets may allow measured increases.

    Parameters are chosen to be numerically stable and deterministic so the
    guard can execute within latency-sensitive execution loops.
    """

    def __init__(
        self,
        *,
        calm_threshold: float = 0.005,
        stressed_threshold: float = 0.02,
        critical_threshold: float = 0.04,
        calm_multiplier: float = 1.1,
        stressed_multiplier: float = 0.65,
        critical_multiplier: float = 0.4,
        half_life_seconds: float = 120.0,
        min_samples: int = 5,
        cooldown_seconds: float = 30.0,
    ) -> None:
        if calm_threshold <= 0:
            raise ValueError("calm_threshold must be positive")
        if not calm_threshold < stressed_threshold < critical_threshold:
            raise ValueError("thresholds must satisfy calm < stressed < critical")
        if calm_multiplier <= 0 or stressed_multiplier <= 0 or critical_multiplier <= 0:
            raise ValueError("exposure multipliers must be positive")
        if half_life_seconds <= 0:
            raise ValueError("half_life_seconds must be positive")
        if min_samples < 1:
            raise ValueError("min_samples must be at least 1")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds cannot be negative")

        self._calm_threshold = calm_threshold
        self._stressed_threshold = stressed_threshold
        self._critical_threshold = critical_threshold
        self._multipliers = {
            VolatilityRegime.CALM: calm_multiplier,
            VolatilityRegime.NORMAL: 1.0,
            VolatilityRegime.STRESSED: stressed_multiplier,
            VolatilityRegime.CRITICAL: critical_multiplier,
        }
        self._decay = math.exp(math.log(0.5) / half_life_seconds)
        self._min_samples = min_samples
        self._cooldown = cooldown_seconds
        self._states: MutableMapping[str, _RegimeState] = {}

    def observe(
        self, symbol: str, return_value: float, timestamp: float | None = None
    ) -> VolatilityRegime:
        """Record a return observation and update the symbol's volatility regime."""

        state = self._states.setdefault(symbol, _RegimeState())
        abs_return = abs(float(return_value))
        observation_time = (
            float(timestamp)
            if timestamp is not None
            else datetime.now(timezone.utc).timestamp()
        )
        if state.samples == 0:
            state.ewma_abs_return = abs_return
        else:
            previous_timestamp = state.last_timestamp or observation_time
            delta = max(0.0, observation_time - previous_timestamp)
            decay_factor = self._decay**delta
            state.ewma_abs_return = (state.ewma_abs_return * decay_factor) + (
                (1.0 - decay_factor) * abs_return
            )

        state.samples += 1
        state.last_timestamp = observation_time

        previous_regime = state.last_regime or VolatilityRegime.NORMAL
        if state.samples < self._min_samples:
            regime = previous_regime
        else:
            regime = self._classify(state.ewma_abs_return)
            previous_severity = self._severity(previous_regime)
            current_severity = self._severity(regime)
            if current_severity > previous_severity:
                state.cooldown_until = observation_time + self._cooldown
            elif (
                current_severity < previous_severity
                and observation_time < state.cooldown_until
            ):
                regime = previous_regime

        state.last_regime = regime
        return regime

    def multiplier(self, symbol: str) -> float:
        """Return the current exposure multiplier for ``symbol``."""

        state = self._states.get(symbol)
        if state is None or state.last_regime is None:
            return 1.0
        return self._multipliers[state.last_regime]

    def regime(self, symbol: str) -> VolatilityRegime:
        """Return the most recent volatility regime for ``symbol``."""

        state = self._states.get(symbol)
        if state is None or state.last_regime is None:
            return VolatilityRegime.NORMAL
        return state.last_regime

    def _classify(self, realised_vol: float) -> VolatilityRegime:
        if realised_vol <= self._calm_threshold:
            return VolatilityRegime.CALM
        if realised_vol <= self._stressed_threshold:
            return VolatilityRegime.NORMAL
        if realised_vol <= self._critical_threshold:
            return VolatilityRegime.STRESSED
        return VolatilityRegime.CRITICAL

    @staticmethod
    def _severity(regime: VolatilityRegime) -> int:
        ordering = {
            VolatilityRegime.CALM: 0,
            VolatilityRegime.NORMAL: 1,
            VolatilityRegime.STRESSED: 2,
            VolatilityRegime.CRITICAL: 3,
        }
        return ordering[regime]


@dataclass(slots=True)
class MarketCondition:
    """Snapshot of market inputs required for position sizing."""

    symbol: str
    price: float
    volatility: float  # annualised volatility (decimal)
    win_probability: float | None = None
    payoff_ratio: float | None = None

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError("price must be positive")
        if self.volatility < 0:
            raise ValueError("volatility cannot be negative")
        if self.win_probability is not None and not 0 < self.win_probability < 1:
            raise ValueError("win_probability must be within (0, 1)")
        if self.payoff_ratio is not None and self.payoff_ratio <= 0:
            raise ValueError("payoff_ratio must be positive")


@dataclass(slots=True)
class PositionRequest:
    """Intention to open or adjust a position."""

    symbol: str
    notional: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class KellyCriterionPositionSizer:
    """Compute an allocation fraction using a conservative Kelly criterion."""

    def __init__(self, max_leverage: float = 3.0, drawdown_buffer: float = 0.5) -> None:
        self._max_leverage = max(1.0, float(max_leverage))
        self._drawdown_buffer = max(0.0, min(1.0, drawdown_buffer))

    def fraction(self, market: MarketCondition) -> float:
        """Return the fraction of capital to allocate to ``market``."""

        if market.win_probability is None or market.payoff_ratio is None:
            raise ValueError(
                "win_probability and payoff_ratio are required for Kelly sizing"
            )

        edge = (market.win_probability * (market.payoff_ratio + 1)) - 1
        if market.payoff_ratio == 0:
            raise ValueError("payoff_ratio cannot be zero")
        raw_fraction = edge / market.payoff_ratio
        adjusted = max(0.0, raw_fraction * self._drawdown_buffer)
        return min(adjusted, self._max_leverage)


class VolatilityAdjustedSizer:
    """Scale position sizes inversely with realised volatility."""

    def __init__(
        self, target_volatility: float = 0.15, floor: float = 0.05, ceiling: float = 5.0
    ) -> None:
        if target_volatility <= 0:
            raise ValueError("target_volatility must be positive")
        self._target = target_volatility
        self._floor = max(0.0, floor)
        self._ceiling = max(self._floor, ceiling)

    def scaling_factor(self, market: MarketCondition) -> float:
        if market.volatility == 0:
            return self._ceiling
        ratio = self._target / market.volatility
        return max(self._floor, min(self._ceiling, ratio))


class RiskMetricsCalculator:
    """Compute Value-at-Risk (VaR) and Conditional VaR (CVaR)."""

    def __init__(self, confidence: float = 0.95) -> None:
        if not 0 < confidence < 1:
            raise ValueError("confidence must be within (0, 1)")
        self._confidence = confidence

    def _loss_distribution(self, returns: Sequence[float]) -> list[float]:
        losses = [-float(r) for r in returns if r < 0]
        return sorted(losses)

    def value_at_risk(
        self, returns: Sequence[float], *, horizon_days: int = 1
    ) -> float:
        if not returns:
            return 0.0
        losses = self._loss_distribution(returns)
        if not losses:
            return 0.0
        index = max(0, math.ceil(self._confidence * len(losses)) - 1)
        index = min(index, len(losses) - 1)
        return losses[index] * math.sqrt(max(1, horizon_days))

    def conditional_value_at_risk(
        self, returns: Sequence[float], *, horizon_days: int = 1
    ) -> float:
        if not returns:
            return 0.0
        losses = self._loss_distribution(returns)
        if not losses:
            return 0.0
        start = max(0, math.ceil(self._confidence * len(losses)) - 1)
        tail = losses[start:] or losses[-1:]
        return fmean(tail) * math.sqrt(max(1, horizon_days))


class MarginMonitor:
    """Track and validate margin utilisation in real time."""

    def __init__(self, margin_limit: float, maintenance_margin: float) -> None:
        if margin_limit <= 0:
            raise ValueError("margin_limit must be positive")
        if maintenance_margin <= 0:
            raise ValueError("maintenance_margin must be positive")
        self._margin_limit = margin_limit
        self._maintenance_margin = maintenance_margin
        self._utilisation = 0.0

    @property
    def utilisation(self) -> float:
        return self._utilisation

    def update(self, required_margin: float, account_equity: float) -> bool:
        if account_equity <= 0:
            raise ValueError("account_equity must be positive")
        utilisation = required_margin / account_equity
        self._utilisation = utilisation
        return (
            utilisation <= self._margin_limit
            and utilisation <= self._maintenance_margin
        )


class CorrelationLimitGuard:
    """Ensure portfolio exposure accounts for inter-asset correlation."""

    def __init__(
        self, correlation_matrix: Mapping[tuple[str, str], float], max_exposure: float
    ) -> None:
        self._correlations = dict(correlation_matrix)
        self._max_exposure = max_exposure

    def effective_exposure(self, positions: Mapping[str, float]) -> float:
        symbols = list(positions.keys())
        exposure = 0.0
        for i, sym_i in enumerate(symbols):
            for j, sym_j in enumerate(symbols):
                weight = 1.0 if i == j else self._correlations.get((sym_i, sym_j), 0.0)
                exposure += positions[sym_i] * positions[sym_j] * weight
        return math.sqrt(max(exposure, 0.0))

    def within_limits(self, positions: Mapping[str, float]) -> bool:
        return self.effective_exposure(positions) <= self._max_exposure


class DrawdownBreaker:
    """Trip a circuit breaker when drawdown exceeds a threshold."""

    def __init__(self, max_drawdown: float = 0.15) -> None:
        if not 0 < max_drawdown < 1:
            raise ValueError("max_drawdown must be within (0, 1)")
        self._max_drawdown = max_drawdown
        self._peak_equity = 0.0
        self._current_drawdown = 0.0

    @property
    def current_drawdown(self) -> float:
        return self._current_drawdown

    def record_equity(self, equity: float) -> bool:
        if equity <= 0:
            raise ValueError("equity must be positive")
        if equity > self._peak_equity:
            self._peak_equity = equity
            self._current_drawdown = 0.0
        else:
            self._current_drawdown = 1 - (equity / self._peak_equity)
        return self._current_drawdown < self._max_drawdown


class TimeWeightedExposureTracker:
    """Maintain an exponentially weighted moving exposure estimate."""

    def __init__(self, half_life_seconds: float = 300.0) -> None:
        if half_life_seconds <= 0:
            raise ValueError("half_life_seconds must be positive")
        self._decay = math.exp(math.log(0.5) / half_life_seconds)
        self._last_timestamp: float | None = None
        self._exposure = 0.0

    @property
    def exposure(self) -> float:
        return self._exposure

    def update(self, notional: float, timestamp: float) -> float:
        if self._last_timestamp is None:
            self._exposure = abs(notional)
        else:
            delta = max(0.0, timestamp - self._last_timestamp)
            decay_factor = self._decay**delta
            self._exposure = (self._exposure * decay_factor) + abs(notional)
        self._last_timestamp = timestamp
        return self._exposure


class RiskParityAllocator:
    """Compute portfolio weights targeting equal risk contribution."""

    def __init__(self, minimum_weight: float = 0.0) -> None:
        self._min_weight = max(0.0, minimum_weight)

    def weights(self, volatilities: Mapping[str, float]) -> Mapping[str, float]:
        inv_vols = {
            symbol: 1.0 / vol for symbol, vol in volatilities.items() if vol > 0
        }
        total = sum(inv_vols.values())
        if total == 0:
            return {symbol: 0.0 for symbol in volatilities}
        return {
            symbol: max(self._min_weight, value / total)
            for symbol, value in inv_vols.items()
        }


class LiquidationCascadePreventer:
    """Limit exposures relative to estimated market liquidity."""

    def __init__(
        self, liquidity_provider: Callable[[str], float], max_fraction: float = 0.1
    ) -> None:
        self._liquidity_provider = liquidity_provider
        self._max_fraction = max(0.0, min(1.0, max_fraction))

    def validate(self, positions: Mapping[str, float]) -> bool:
        for symbol, notional in positions.items():
            liquidity = self._liquidity_provider(symbol)
            if liquidity <= 0:
                return False
            if abs(notional) > liquidity * self._max_fraction:
                return False
        return True


@dataclass(slots=True)
class AdvancedRiskState:
    """Mutable snapshot of the risk controller state."""

    market_data: MutableMapping[str, MarketCondition] = field(default_factory=dict)
    positions: MutableMapping[str, float] = field(default_factory=dict)
    equity: float = 0.0
    returns_history: MutableMapping[str, list[float]] = field(default_factory=dict)


class AdvancedRiskController:
    """High-level orchestrator combining advanced risk components."""

    def __init__(
        self,
        *,
        capital: float,
        margin_monitor: MarginMonitor,
        correlation_guard: CorrelationLimitGuard,
        drawdown_breaker: DrawdownBreaker,
        exposure_tracker: TimeWeightedExposureTracker,
        liquidation_guard: LiquidationCascadePreventer,
        risk_metrics: RiskMetricsCalculator,
        kelly_sizer: KellyCriterionPositionSizer,
        vol_sizer: VolatilityAdjustedSizer,
        regime_guard: RegimeAdaptiveExposureGuard | None = None,
    ) -> None:
        if capital <= 0:
            raise ValueError("capital must be positive")
        self._capital = capital
        self._margin_monitor = margin_monitor
        self._correlation_guard = correlation_guard
        self._drawdown_breaker = drawdown_breaker
        self._exposure_tracker = exposure_tracker
        self._liquidation_guard = liquidation_guard
        self._risk_metrics = risk_metrics
        self._kelly_sizer = kelly_sizer
        self._vol_sizer = vol_sizer
        self._regime_guard = regime_guard
        self._state = AdvancedRiskState(equity=capital)

    @property
    def state(self) -> AdvancedRiskState:
        return self._state

    def register_market_condition(self, market: MarketCondition) -> None:
        self._state.market_data[market.symbol] = market

    def record_return(
        self, symbol: str, returns: Iterable[float | tuple[float, datetime]]
    ) -> None:
        """Store historical returns and update adaptive risk telemetry."""

        history = self._state.returns_history.setdefault(symbol, [])
        max_points = 2_048
        for entry in returns:
            if isinstance(entry, tuple):
                if len(entry) != 2:
                    raise ValueError("return tuples must contain value and timestamp")
                value, ts = entry
                value = float(value)
                if not isinstance(ts, datetime):
                    raise TypeError("timestamp must be a datetime instance")
                timestamp = ts.astimezone(timezone.utc)
            else:
                value = float(entry)
                timestamp = datetime.now(timezone.utc)

            history.append(value)
            if len(history) > max_points:
                del history[:-max_points]

            if self._regime_guard is not None:
                self._regime_guard.observe(symbol, value, timestamp.timestamp())

    def evaluate_order(
        self, request: PositionRequest, *, account_equity: float
    ) -> bool:
        market = self._state.market_data.get(request.symbol)
        if market is None:
            raise ValueError(f"Missing market data for {request.symbol}")

        kelly_fraction = min(1.0, self._kelly_sizer.fraction(market))
        volatility_scale = self._vol_sizer.scaling_factor(market)
        desired_notional = self._capital * kelly_fraction * volatility_scale
        if self._regime_guard is not None:
            desired_notional *= self._regime_guard.multiplier(request.symbol)
        aggregated_notional = (
            self._state.positions.get(request.symbol, 0.0) + request.notional
        )

        positions_preview = dict(self._state.positions)
        positions_preview[request.symbol] = aggregated_notional

        if not self._correlation_guard.within_limits(positions_preview):
            return False
        if not self._liquidation_guard.validate(positions_preview):
            return False

        required_margin = abs(aggregated_notional)
        if not self._margin_monitor.update(required_margin, account_equity):
            return False

        exposure = self._exposure_tracker.update(
            request.notional, request.timestamp.timestamp()
        )
        if exposure > desired_notional:
            return False

        if not self._drawdown_breaker.record_equity(account_equity):
            return False

        self._state.positions[request.symbol] = aggregated_notional
        self._state.equity = account_equity
        return True

    def portfolio_var(self, symbol: str) -> float:
        returns = self._state.returns_history.get(symbol, [])
        return self._risk_metrics.value_at_risk(returns)

    def portfolio_cvar(self, symbol: str) -> float:
        returns = self._state.returns_history.get(symbol, [])
        return self._risk_metrics.conditional_value_at_risk(returns)

    def volatility_regime(self, symbol: str) -> VolatilityRegime:
        """Expose the adaptive volatility regime for the requested symbol."""

        if self._regime_guard is None:
            raise RuntimeError("RegimeAdaptiveExposureGuard is not configured")
        return self._regime_guard.regime(symbol)
