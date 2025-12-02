"""Strategy Engine for coordinating strategy execution.

This module provides the StrategyEngine class that coordinates
execution of multiple strategies, handling registration, lifecycle
management, and signal aggregation.

The engine ensures all strategies receive the same context and
that their outputs are properly collected for the decision loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Mapping, MutableMapping

from domain.model import (
    StrategyContext,
    StrategySignal,
    StrategyId,
    EnvironmentMode,
)

from .base import (
    Strategy,
    StrategyConfig,
    StrategyResult,
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
# Engine State
# -----------------------------------------------------------------------------


class StrategyEngineState(str, Enum):
    """State of the strategy engine."""

    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


# -----------------------------------------------------------------------------
# Engine Configuration
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StrategyEngineConfig:
    """Configuration for StrategyEngine.

    Attributes:
        mode: Environment mode (backtest/paper/live).
        max_signals_per_cycle: Maximum signals to process per cycle.
        parallel_execution: Whether to execute strategies in parallel.
        error_handling: How to handle strategy errors ("skip" or "raise").
        collect_diagnostics: Whether to collect diagnostic information.
        metadata: Additional configuration metadata.
    """

    mode: EnvironmentMode = EnvironmentMode.PAPER
    max_signals_per_cycle: int = 100
    parallel_execution: bool = False
    error_handling: str = "skip"  # "skip" or "raise"
    collect_diagnostics: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))
        if self.max_signals_per_cycle < 1:
            raise ValueError("max_signals_per_cycle must be positive")
        if self.error_handling not in ("skip", "raise"):
            raise ValueError("error_handling must be 'skip' or 'raise'")


# -----------------------------------------------------------------------------
# Engine Cycle Result
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EngineCycleResult:
    """Result of a single engine evaluation cycle.

    Captures all signals and diagnostics from processing all
    registered strategies.

    Attributes:
        signals: All signals generated this cycle.
        results: Per-strategy results.
        timestamp: When the cycle completed.
        elapsed_ms: Total cycle time in milliseconds.
        strategies_evaluated: Number of strategies evaluated.
        strategies_skipped: Number of strategies skipped.
        errors: Any errors encountered.
    """

    signals: tuple[StrategySignal, ...]
    results: Mapping[StrategyId, StrategyResult]
    timestamp: datetime = field(default_factory=_utc_now)
    elapsed_ms: float = 0.0
    strategies_evaluated: int = 0
    strategies_skipped: int = 0
    errors: tuple[tuple[StrategyId, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "results", _freeze_mapping(self.results))

    @property
    def total_signals(self) -> int:
        """Return total number of signals."""
        return len(self.signals)

    @property
    def has_errors(self) -> bool:
        """Return True if any errors occurred."""
        return len(self.errors) > 0


# -----------------------------------------------------------------------------
# Strategy Engine
# -----------------------------------------------------------------------------


SignalCallback = Callable[[StrategySignal, StrategyResult], None]
ErrorCallback = Callable[[StrategyId, Exception], None]


class StrategyEngine:
    """Engine for coordinating strategy execution.

    The StrategyEngine manages a collection of strategies and provides
    a unified interface for evaluating them against market conditions.
    It handles:
        - Strategy registration and lifecycle
        - Parallel or sequential execution
        - Signal collection and filtering
        - Error handling and diagnostics

    Example:
        >>> engine = StrategyEngine(StrategyEngineConfig())
        >>> engine.register(my_strategy)
        >>> result = engine.evaluate(context)
        >>> for signal in result.signals:
        ...     print(f"Signal: {signal.symbol} {signal.direction}")
    """

    def __init__(self, config: StrategyEngineConfig) -> None:
        """Initialize the strategy engine.

        Args:
            config: Engine configuration.
        """
        self._config = config
        self._state = StrategyEngineState.STOPPED
        self._strategies: MutableMapping[StrategyId, Strategy] = {}
        self._signal_callbacks: list[SignalCallback] = []
        self._error_callbacks: list[ErrorCallback] = []

    @property
    def config(self) -> StrategyEngineConfig:
        """Return engine configuration."""
        return self._config

    @property
    def state(self) -> StrategyEngineState:
        """Return current engine state."""
        return self._state

    @property
    def mode(self) -> EnvironmentMode:
        """Return current environment mode."""
        return self._config.mode

    @property
    def strategies(self) -> Mapping[StrategyId, Strategy]:
        """Return registered strategies."""
        return MappingProxyType(dict(self._strategies))

    @property
    def strategy_count(self) -> int:
        """Return number of registered strategies."""
        return len(self._strategies)

    # -------------------------------------------------------------------------
    # Lifecycle Methods
    # -------------------------------------------------------------------------

    def start(self) -> None:
        """Start the engine."""
        if self._state == StrategyEngineState.RUNNING:
            return
        self._state = StrategyEngineState.RUNNING

    def stop(self) -> None:
        """Stop the engine."""
        if self._state == StrategyEngineState.STOPPED:
            return
        self._state = StrategyEngineState.STOPPED

    def pause(self) -> None:
        """Pause the engine."""
        if self._state != StrategyEngineState.RUNNING:
            return
        self._state = StrategyEngineState.PAUSED

    def resume(self) -> None:
        """Resume the engine from paused state."""
        if self._state != StrategyEngineState.PAUSED:
            return
        self._state = StrategyEngineState.RUNNING

    # -------------------------------------------------------------------------
    # Strategy Management
    # -------------------------------------------------------------------------

    def register(self, strategy: Strategy) -> None:
        """Register a strategy with the engine.

        Args:
            strategy: Strategy to register.

        Raises:
            ValueError: If strategy with same ID is already registered.
        """
        if strategy.strategy_id in self._strategies:
            raise ValueError(
                f"Strategy '{strategy.strategy_id}' is already registered"
            )
        self._strategies[strategy.strategy_id] = strategy

    def unregister(self, strategy_id: StrategyId) -> bool:
        """Unregister a strategy from the engine.

        Args:
            strategy_id: ID of strategy to unregister.

        Returns:
            True if strategy was unregistered, False if not found.
        """
        if strategy_id not in self._strategies:
            return False
        del self._strategies[strategy_id]
        return True

    def get_strategy(self, strategy_id: StrategyId) -> Strategy | None:
        """Get a registered strategy by ID.

        Args:
            strategy_id: ID of strategy to get.

        Returns:
            Strategy if found, None otherwise.
        """
        return self._strategies.get(strategy_id)

    def reset_strategies(self) -> None:
        """Reset all registered strategies."""
        for strategy in self._strategies.values():
            strategy.reset()

    # -------------------------------------------------------------------------
    # Callbacks
    # -------------------------------------------------------------------------

    def on_signal(self, callback: SignalCallback) -> None:
        """Register a callback for signal events.

        Args:
            callback: Function called when a signal is generated.
        """
        self._signal_callbacks.append(callback)

    def on_error(self, callback: ErrorCallback) -> None:
        """Register a callback for error events.

        Args:
            callback: Function called when an error occurs.
        """
        self._error_callbacks.append(callback)

    # -------------------------------------------------------------------------
    # Evaluation
    # -------------------------------------------------------------------------

    def evaluate(self, context: StrategyContext) -> EngineCycleResult:
        """Evaluate all registered strategies.

        Runs all enabled strategies with the given context and
        collects their signals.

        Args:
            context: Current market and portfolio state.

        Returns:
            EngineCycleResult with all generated signals.
        """
        import time

        # Check if engine is running
        if self._state != StrategyEngineState.RUNNING:
            return EngineCycleResult(
                signals=(),
                results={},
                strategies_evaluated=0,
                strategies_skipped=len(self._strategies),
            )

        start = time.perf_counter()
        all_signals: list[StrategySignal] = []
        results: dict[StrategyId, StrategyResult] = {}
        errors: list[tuple[StrategyId, str]] = []
        evaluated = 0
        skipped = 0

        # Process each strategy
        for strategy_id, strategy in self._strategies.items():
            try:
                result = strategy.evaluate(context)
                results[strategy_id] = result

                if result.skipped:
                    skipped += 1
                else:
                    evaluated += 1
                    for signal in result.signals:
                        all_signals.append(signal)
                        self._notify_signal(signal, result)

                        # Check signal limit
                        if len(all_signals) >= self._config.max_signals_per_cycle:
                            break

            except Exception as e:
                errors.append((strategy_id, str(e)))
                self._notify_error(strategy_id, e)
                if self._config.error_handling == "raise":
                    raise

            if len(all_signals) >= self._config.max_signals_per_cycle:
                break

        elapsed_ms = (time.perf_counter() - start) * 1000

        return EngineCycleResult(
            signals=tuple(all_signals),
            results=results,
            elapsed_ms=elapsed_ms,
            strategies_evaluated=evaluated,
            strategies_skipped=skipped,
            errors=tuple(errors),
        )

    def evaluate_single(
        self, strategy_id: StrategyId, context: StrategyContext
    ) -> StrategyResult | None:
        """Evaluate a single strategy.

        Args:
            strategy_id: ID of strategy to evaluate.
            context: Current market and portfolio state.

        Returns:
            StrategyResult if strategy found, None otherwise.
        """
        strategy = self._strategies.get(strategy_id)
        if strategy is None:
            return None
        return strategy.evaluate(context)

    # -------------------------------------------------------------------------
    # Internal Methods
    # -------------------------------------------------------------------------

    def _notify_signal(self, signal: StrategySignal, result: StrategyResult) -> None:
        """Notify all signal callbacks."""
        for callback in self._signal_callbacks:
            try:
                callback(signal, result)
            except Exception:
                pass  # Don't let callback errors affect processing

    def _notify_error(self, strategy_id: StrategyId, error: Exception) -> None:
        """Notify all error callbacks."""
        for callback in self._error_callbacks:
            try:
                callback(strategy_id, error)
            except Exception:
                pass  # Don't let callback errors affect processing


# -----------------------------------------------------------------------------
# Exports
# -----------------------------------------------------------------------------

__all__ = [
    "StrategyEngine",
    "StrategyEngineConfig",
    "StrategyEngineState",
    "EngineCycleResult",
]
