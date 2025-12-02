"""Base strategy interface for TradePulse.

This module defines the unified strategy contract that all strategies must
implement. The contract ensures strategies work identically across backtest,
paper trading, and live execution modes.

Key Design Principles:
    1. Single method for signal generation: generate_signals()
    2. Immutable context input (StrategyContext)
    3. Immutable signal output (StrategySignal)
    4. Strategy is stateless between calls (state in context)
    5. Pure function semantics where possible

Example:
    >>> class MomentumStrategy(Strategy):
    ...     def generate_signals(
    ...         self, context: StrategyContext
    ...     ) -> list[StrategySignal]:
    ...         # Analyze context and generate signals
    ...         return [
    ...             StrategySignal(
    ...                 signal_id=generate_signal_id(),
    ...                 symbol="BTCUSD",
    ...                 direction=SignalDirection.LONG,
    ...                 strength=0.8,
    ...             )
    ...         ]
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from domain.model import (
    StrategyContext,
    StrategySignal,
    StrategyId,
    EnvironmentMode,
)


def _freeze_mapping(mapping: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Return an immutable view over mapping."""
    if mapping is None:
        return MappingProxyType({})
    if isinstance(mapping, MappingProxyType):
        return mapping
    return MappingProxyType(dict(mapping))


def _utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


# -----------------------------------------------------------------------------
# Strategy Configuration
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    """Configuration for a strategy instance.

    Attributes:
        strategy_id: Unique identifier for this strategy instance.
        name: Human-readable name.
        description: Strategy description.
        symbols: List of symbols this strategy trades.
        parameters: Strategy-specific parameters.
        enabled: Whether the strategy is enabled.
        max_position_size: Maximum position size (normalized).
        risk_limit: Maximum risk allocation for this strategy.
        cooldown_seconds: Minimum time between signals.
        metadata: Additional configuration metadata.
    """

    strategy_id: StrategyId
    name: str
    description: str = ""
    symbols: tuple[str, ...] = field(default_factory=tuple)
    parameters: Mapping[str, Any] = field(default_factory=dict)
    enabled: bool = True
    max_position_size: float = 1.0
    risk_limit: float = 1.0
    cooldown_seconds: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))
        if not 0.0 <= self.max_position_size <= 1.0:
            raise ValueError("max_position_size must be between 0 and 1")
        if not 0.0 <= self.risk_limit <= 1.0:
            raise ValueError("risk_limit must be between 0 and 1")
        if self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds cannot be negative")


# -----------------------------------------------------------------------------
# Strategy Result
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StrategyResult:
    """Result of strategy signal generation.

    Captures the output of a single strategy evaluation, including
    generated signals and diagnostic information.

    Attributes:
        strategy_id: ID of the strategy that produced this result.
        signals: List of signals generated.
        timestamp: When the result was produced.
        elapsed_ms: Time taken to generate signals in milliseconds.
        skipped: Whether signal generation was skipped (e.g., cooldown).
        skip_reason: Reason for skipping signal generation.
        diagnostics: Additional diagnostic information.
    """

    strategy_id: StrategyId
    signals: tuple[StrategySignal, ...]
    timestamp: datetime = field(default_factory=_utc_now)
    elapsed_ms: float = 0.0
    skipped: bool = False
    skip_reason: str | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "diagnostics", _freeze_mapping(self.diagnostics))

    @property
    def has_signals(self) -> bool:
        """Return True if result contains signals."""
        return len(self.signals) > 0

    @property
    def signal_count(self) -> int:
        """Return number of signals in result."""
        return len(self.signals)


# -----------------------------------------------------------------------------
# Strategy Protocol (for duck typing)
# -----------------------------------------------------------------------------


@runtime_checkable
class StrategyProtocol(Protocol):
    """Protocol defining the strategy interface.

    Use this for duck typing when you need to accept any object
    that implements the strategy interface.
    """

    @property
    def strategy_id(self) -> StrategyId:
        """Return the strategy's unique identifier."""
        ...

    @property
    def name(self) -> str:
        """Return the strategy's name."""
        ...

    def generate_signals(self, context: StrategyContext) -> list[StrategySignal]:
        """Generate trading signals based on current context.

        Args:
            context: Current market and portfolio state.

        Returns:
            List of trading signals. Empty list means no action.
        """
        ...


# -----------------------------------------------------------------------------
# Strategy Abstract Base Class
# -----------------------------------------------------------------------------


class Strategy(ABC):
    """Abstract base class for trading strategies.

    All strategies must inherit from this class and implement the
    generate_signals method. The base class provides common functionality
    including configuration management and result wrapping.

    Attributes:
        config: Strategy configuration.

    Example:
        >>> class SimpleStrategy(Strategy):
        ...     def generate_signals(
        ...         self, context: StrategyContext
        ...     ) -> list[StrategySignal]:
        ...         # Your signal logic here
        ...         return []
    """

    def __init__(self, config: StrategyConfig) -> None:
        """Initialize strategy with configuration.

        Args:
            config: Strategy configuration.
        """
        self._config = config
        self._last_signal_time: datetime | None = None

    @property
    def config(self) -> StrategyConfig:
        """Return strategy configuration."""
        return self._config

    @property
    def strategy_id(self) -> StrategyId:
        """Return the strategy's unique identifier."""
        return self._config.strategy_id

    @property
    def name(self) -> str:
        """Return the strategy's name."""
        return self._config.name

    @property
    def symbols(self) -> tuple[str, ...]:
        """Return the symbols this strategy trades."""
        return self._config.symbols

    @property
    def is_enabled(self) -> bool:
        """Return True if strategy is enabled."""
        return self._config.enabled

    @abstractmethod
    def generate_signals(self, context: StrategyContext) -> list[StrategySignal]:
        """Generate trading signals based on current context.

        This is the core method that strategies must implement. It receives
        the complete current state (portfolio, market data) and should return
        a list of signals indicating desired actions.

        The method should be deterministic given the same context.

        Args:
            context: Current market and portfolio state.

        Returns:
            List of trading signals. Empty list means no action.

        Note:
            Signals are recommendations that will be filtered through
            risk management before becoming orders. Don't implement
            risk checks here - that's the risk engine's job.
        """
        ...

    def evaluate(self, context: StrategyContext) -> StrategyResult:
        """Evaluate strategy and wrap result.

        This method handles common logic like cooldown checking and
        timing, then calls generate_signals for the actual logic.

        Args:
            context: Current market and portfolio state.

        Returns:
            StrategyResult containing generated signals and diagnostics.
        """
        import time

        # Check if strategy is enabled
        if not self.is_enabled:
            return StrategyResult(
                strategy_id=self.strategy_id,
                signals=(),
                skipped=True,
                skip_reason="strategy_disabled",
            )

        # Check cooldown
        if self._is_in_cooldown(context.timestamp):
            return StrategyResult(
                strategy_id=self.strategy_id,
                signals=(),
                skipped=True,
                skip_reason="cooldown",
            )

        # Generate signals with timing
        start = time.perf_counter()
        try:
            signals = self.generate_signals(context)
        except Exception as e:
            return StrategyResult(
                strategy_id=self.strategy_id,
                signals=(),
                skipped=True,
                skip_reason=f"error:{type(e).__name__}",
                diagnostics={"error": str(e)},
            )
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Update last signal time if signals were generated
        if signals:
            self._last_signal_time = context.timestamp

        return StrategyResult(
            strategy_id=self.strategy_id,
            signals=tuple(signals),
            timestamp=context.timestamp,
            elapsed_ms=elapsed_ms,
        )

    def _is_in_cooldown(self, current_time: datetime) -> bool:
        """Check if strategy is in cooldown period."""
        if self._config.cooldown_seconds <= 0:
            return False
        if self._last_signal_time is None:
            return False
        elapsed = (current_time - self._last_signal_time).total_seconds()
        return elapsed < self._config.cooldown_seconds

    def on_fill(self, order_id: str, quantity: float, price: float) -> None:
        """Handle fill notification (optional override).

        Called when an order generated by this strategy is filled.
        Override this method if your strategy needs to track fills.

        Args:
            order_id: ID of the filled order.
            quantity: Filled quantity.
            price: Fill price.
        """
        pass

    def on_cancel(self, order_id: str, reason: str | None = None) -> None:
        """Handle order cancellation notification (optional override).

        Called when an order generated by this strategy is cancelled.
        Override this method if your strategy needs to track cancellations.

        Args:
            order_id: ID of the cancelled order.
            reason: Cancellation reason.
        """
        pass

    def reset(self) -> None:
        """Reset strategy state (optional override).

        Called when the strategy should reset its internal state,
        such as at the start of a new backtest or session.
        """
        self._last_signal_time = None


# -----------------------------------------------------------------------------
# Exports
# -----------------------------------------------------------------------------

__all__ = [
    "Strategy",
    "StrategyProtocol",
    "StrategyResult",
    "StrategyConfig",
]
