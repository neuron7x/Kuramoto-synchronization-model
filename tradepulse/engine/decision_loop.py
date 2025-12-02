"""Unified decision loop for all execution modes.

This module implements the central decision loop that processes
strategy signals through risk evaluation and produces action decisions.
The same logic is used for backtest, paper, and live trading modes,
with only the execution adapter differing.

Decision Loop Flow:
    1. Gather market data and portfolio state into StrategyContext
    2. Evaluate strategies to generate signals (via StrategyEngine)
    3. Filter signals through risk evaluation
    4. Convert approved signals to ActionDecisions
    5. Execute actions via mode-specific adapter (backtest/paper/live)
    6. Collect outcomes and generate AAR events
    7. Update states and loop

Key Design Principles:
    - Single logic for all modes (backtest/paper/live)
    - Immutable context and decision objects
    - Clear separation between decision and execution
    - Built-in AAR feedback loop integration
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

from domain.model import (
    # Core types
    StrategyContext,
    StrategySignal,
    PortfolioState,
    MarketDataSnapshot,
    ActionDecision,
    AAREvent,
    # Enums
    EnvironmentMode,
    ActionType,
    SignalDirection,
    # ID types
    StrategyId,
    SignalId,
)

from tradepulse.strategy.base import Strategy
from tradepulse.strategy.engine import (
    StrategyEngine,
    StrategyEngineConfig,
    EngineCycleResult,
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
# Risk Evaluation Protocol
# -----------------------------------------------------------------------------


class RiskEvaluator(Protocol):
    """Protocol for risk evaluation of signals.

    Risk evaluators filter and modify signals before they become
    action decisions. Multiple evaluators can be chained.
    """

    def evaluate(
        self,
        signal: StrategySignal,
        context: StrategyContext,
    ) -> tuple[bool, StrategySignal, str | None]:
        """Evaluate a signal against risk constraints.

        Args:
            signal: Signal to evaluate.
            context: Current strategy context.

        Returns:
            Tuple of (approved, adjusted_signal, reason).
            If not approved, reason explains why.
        """
        ...


class AcceptAllRiskEvaluator:
    """Default risk evaluator that accepts all signals."""

    def evaluate(
        self,
        signal: StrategySignal,
        context: StrategyContext,
    ) -> tuple[bool, StrategySignal, str | None]:
        return True, signal, None


# -----------------------------------------------------------------------------
# Execution Adapter Protocol
# -----------------------------------------------------------------------------


class ExecutionAdapter(ABC):
    """Abstract base for mode-specific execution.

    Each execution mode (backtest, paper, live) implements this
    interface to handle action execution appropriately.
    """

    @property
    @abstractmethod
    def mode(self) -> EnvironmentMode:
        """Return the execution mode."""
        ...

    @abstractmethod
    def execute(
        self,
        decision: ActionDecision,
        context: StrategyContext,
    ) -> ExecutionResult:
        """Execute an action decision.

        Args:
            decision: Action to execute.
            context: Current strategy context.

        Returns:
            ExecutionResult with outcome details.
        """
        ...

    @abstractmethod
    def get_portfolio_state(self) -> PortfolioState:
        """Get current portfolio state from execution layer."""
        ...

    @abstractmethod
    def get_market_data(
        self, symbols: Sequence[str]
    ) -> Mapping[str, MarketDataSnapshot]:
        """Get current market data for symbols."""
        ...


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Result of executing an action decision.

    Attributes:
        action_id: ID of the executed action.
        success: Whether execution succeeded.
        fill_price: Actual fill price (if applicable).
        fill_quantity: Actual filled quantity.
        fees: Execution fees.
        error: Error message if execution failed.
        metadata: Additional execution metadata.
    """

    action_id: str
    success: bool = True
    fill_price: float = 0.0
    fill_quantity: float = 0.0
    fees: float = 0.0
    error: str | None = None
    timestamp: datetime = field(default_factory=_utc_now)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


# -----------------------------------------------------------------------------
# Decision Loop Configuration
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DecisionLoopConfig:
    """Configuration for the decision loop.

    Attributes:
        mode: Execution mode (backtest/paper/live).
        max_decisions_per_cycle: Maximum decisions per cycle.
        enable_aar: Whether to collect AAR events.
        aar_scale: Scale factor for AAR error normalization.
        metadata: Additional configuration metadata.
    """

    mode: EnvironmentMode
    max_decisions_per_cycle: int = 100
    enable_aar: bool = True
    aar_scale: float = 100.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


# -----------------------------------------------------------------------------
# Decision Cycle Result
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DecisionCycle:
    """Result of a single decision loop cycle.

    Captures all outputs from processing strategies through
    risk evaluation, decision making, and execution.

    Attributes:
        timestamp: When the cycle completed.
        context: Strategy context used for this cycle.
        signals: Signals generated by strategies.
        decisions: Action decisions made.
        results: Execution results.
        aar_events: AAR events generated.
        elapsed_ms: Total cycle time in milliseconds.
        metadata: Additional cycle metadata.
    """

    timestamp: datetime
    context: StrategyContext
    signals: tuple[StrategySignal, ...]
    decisions: tuple[ActionDecision, ...]
    results: tuple[ExecutionResult, ...]
    aar_events: tuple[AAREvent, ...]
    elapsed_ms: float = 0.0
    signals_approved: int = 0
    signals_rejected: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    @property
    def total_signals(self) -> int:
        """Return total signals generated."""
        return len(self.signals)

    @property
    def total_decisions(self) -> int:
        """Return total decisions made."""
        return len(self.decisions)

    @property
    def successful_executions(self) -> int:
        """Return count of successful executions."""
        return sum(1 for r in self.results if r.success)


# -----------------------------------------------------------------------------
# Decision Loop
# -----------------------------------------------------------------------------


class DecisionLoop:
    """Central decision loop for all execution modes.

    The DecisionLoop coordinates strategy evaluation, risk filtering,
    and action execution. It uses the same logic regardless of mode,
    with only the execution adapter differing.

    Example:
        >>> # Create components
        >>> engine = StrategyEngine(StrategyEngineConfig())
        >>> adapter = BacktestExecutionAdapter(...)
        >>> evaluator = MaxDrawdownRiskEvaluator(max_drawdown=0.1)
        >>>
        >>> # Create and run loop
        >>> loop = DecisionLoop(config, engine, adapter, evaluator)
        >>> cycle = loop.step()
        >>> print(f"Generated {cycle.total_signals} signals")
    """

    def __init__(
        self,
        config: DecisionLoopConfig,
        strategy_engine: StrategyEngine,
        execution_adapter: ExecutionAdapter,
        risk_evaluator: RiskEvaluator | None = None,
    ) -> None:
        """Initialize the decision loop.

        Args:
            config: Loop configuration.
            strategy_engine: Engine for running strategies.
            execution_adapter: Mode-specific execution handler.
            risk_evaluator: Optional risk evaluator. Uses AcceptAll if None.
        """
        self._config = config
        self._engine = strategy_engine
        self._adapter = execution_adapter
        self._risk_evaluator = risk_evaluator or AcceptAllRiskEvaluator()
        self._cycle_count = 0

    @property
    def config(self) -> DecisionLoopConfig:
        """Return loop configuration."""
        return self._config

    @property
    def mode(self) -> EnvironmentMode:
        """Return current execution mode."""
        return self._config.mode

    @property
    def cycle_count(self) -> int:
        """Return number of cycles executed."""
        return self._cycle_count

    def step(
        self,
        symbols: Sequence[str] | None = None,
        timestamp: datetime | None = None,
    ) -> DecisionCycle:
        """Execute one decision cycle.

        This is the main entry point for the decision loop. It:
        1. Gathers context (portfolio + market data)
        2. Evaluates strategies
        3. Filters signals through risk
        4. Converts to action decisions
        5. Executes via adapter
        6. Generates AAR events

        Args:
            symbols: Symbols to get market data for. If None, uses
                     symbols from registered strategies.
            timestamp: Timestamp for this cycle. If None, uses current time.

        Returns:
            DecisionCycle with all outputs from this cycle.
        """
        import time

        start = time.perf_counter()
        ts = timestamp or _utc_now()

        # Gather symbols from strategies if not provided
        if symbols is None:
            symbols = self._gather_symbols()

        # Build context
        context = self._build_context(symbols, ts)

        # Evaluate strategies
        engine_result = self._engine.evaluate(context)

        # Process signals through risk and generate decisions
        signals = engine_result.signals
        decisions: list[ActionDecision] = []
        results: list[ExecutionResult] = []
        aar_events: list[AAREvent] = []
        approved = 0
        rejected = 0

        for signal in signals:
            # Risk evaluation
            is_approved, adjusted_signal, reject_reason = self._risk_evaluator.evaluate(
                signal, context
            )

            if not is_approved:
                rejected += 1
                continue

            approved += 1

            # Convert to decision
            decision = self._signal_to_decision(adjusted_signal, context)
            decisions.append(decision)

            # Check decision limit
            if len(decisions) >= self._config.max_decisions_per_cycle:
                break

        # Execute decisions
        for decision in decisions:
            result = self._adapter.execute(decision, context)
            results.append(result)

            # Generate AAR event if enabled
            if self._config.enable_aar:
                aar_event = self._generate_aar_event(decision, result)
                aar_events.append(aar_event)

        elapsed_ms = (time.perf_counter() - start) * 1000
        self._cycle_count += 1

        return DecisionCycle(
            timestamp=ts,
            context=context,
            signals=signals,
            decisions=tuple(decisions),
            results=tuple(results),
            aar_events=tuple(aar_events),
            elapsed_ms=elapsed_ms,
            signals_approved=approved,
            signals_rejected=rejected,
        )

    def run_cycles(
        self,
        count: int,
        symbols: Sequence[str] | None = None,
    ) -> list[DecisionCycle]:
        """Run multiple decision cycles.

        Args:
            count: Number of cycles to run.
            symbols: Symbols to process.

        Returns:
            List of DecisionCycle results.
        """
        cycles = []
        for _ in range(count):
            cycle = self.step(symbols=symbols)
            cycles.append(cycle)
        return cycles

    def reset(self) -> None:
        """Reset the decision loop state."""
        self._cycle_count = 0
        self._engine.reset_strategies()

    # -------------------------------------------------------------------------
    # Internal Methods
    # -------------------------------------------------------------------------

    def _gather_symbols(self) -> list[str]:
        """Gather all symbols from registered strategies."""
        symbols: set[str] = set()
        for strategy in self._engine.strategies.values():
            symbols.update(strategy.symbols)
        return sorted(symbols)

    def _build_context(
        self,
        symbols: Sequence[str],
        timestamp: datetime,
    ) -> StrategyContext:
        """Build strategy context from current state."""
        portfolio = self._adapter.get_portfolio_state()
        market_data = self._adapter.get_market_data(symbols)

        return StrategyContext(
            mode=self._config.mode,
            portfolio=portfolio,
            market_data=market_data,
            timestamp=timestamp,
        )

    def _signal_to_decision(
        self,
        signal: StrategySignal,
        context: StrategyContext,
    ) -> ActionDecision:
        """Convert a strategy signal to an action decision."""
        # Determine action type from signal
        action_type = self._determine_action_type(signal, context)

        # Calculate quantity from target position
        quantity = self._calculate_quantity(signal, context)

        return ActionDecision(
            action_id=f"dec_{uuid.uuid4().hex[:16]}",
            action_type=action_type,
            symbol=signal.symbol,
            quantity=quantity,
            signal_id=signal.signal_id,
            strategy_id=signal.strategy_id,
            confidence=signal.confidence,
            rationale=signal.rationale,
            metadata=dict(signal.metadata),
        )

    def _determine_action_type(
        self,
        signal: StrategySignal,
        context: StrategyContext,
    ) -> ActionType:
        """Determine action type from signal direction and current position."""
        position = context.get_position(signal.symbol)
        current_qty = position.quantity if position else 0.0

        if signal.direction == SignalDirection.FLAT:
            if abs(current_qty) > 1e-9:
                return ActionType.CLOSE
            return ActionType.HOLD

        if signal.direction == SignalDirection.LONG:
            if current_qty < 0:
                # Close short and go long
                return ActionType.BUY
            elif current_qty > 0:
                if signal.target_position > current_qty:
                    return ActionType.SCALE_IN
                elif signal.target_position < current_qty:
                    return ActionType.REDUCE
                return ActionType.HOLD
            else:
                return ActionType.BUY

        if signal.direction == SignalDirection.SHORT:
            if current_qty > 0:
                # Close long and go short
                return ActionType.SELL
            elif current_qty < 0:
                if signal.target_position < current_qty:
                    return ActionType.SCALE_IN
                elif signal.target_position > current_qty:
                    return ActionType.REDUCE
                return ActionType.HOLD
            else:
                return ActionType.SELL

        return ActionType.HOLD

    def _calculate_quantity(
        self,
        signal: StrategySignal,
        context: StrategyContext,
    ) -> float:
        """Calculate order quantity from signal and context."""
        position = context.get_position(signal.symbol)
        current_qty = position.quantity if position else 0.0

        # Target position is normalized (-1 to 1)
        # We need to convert to actual quantity
        # For now, use simple approach: abs difference from current
        target = signal.target_position

        if signal.direction == SignalDirection.FLAT:
            return abs(current_qty)

        return abs(target - current_qty)

    def _generate_aar_event(
        self,
        decision: ActionDecision,
        result: ExecutionResult,
    ) -> AAREvent:
        """Generate AAR event from decision and execution result."""
        # Simple prediction: expected zero slippage, zero fees
        # Outcome: actual fill price vs expected, fees
        prediction = 0.0  # Expected additional cost
        outcome = result.fees  # Actual additional cost

        if decision.price is not None and result.fill_price > 0:
            # Slippage calculation
            expected_price = decision.price
            actual_price = result.fill_price
            slippage = abs(actual_price - expected_price)
            outcome += slippage

        return AAREvent.from_prediction_outcome(
            action_id=decision.action_id,
            prediction=prediction,
            outcome=-outcome,  # Negative because costs are bad
            strategy_id=decision.strategy_id,
            scale=self._config.aar_scale,
            context_snapshot={
                "mode": self._config.mode.value,
                "symbol": decision.symbol,
                "action_type": decision.action_type.value,
                "quantity": decision.quantity,
            },
        )


# -----------------------------------------------------------------------------
# Simple Backtest Execution Adapter
# -----------------------------------------------------------------------------


class SimpleBacktestAdapter(ExecutionAdapter):
    """Simple execution adapter for backtesting.

    This is a minimal implementation for testing purposes.
    Production backtest adapters should be more sophisticated.
    """

    def __init__(
        self,
        initial_cash: float = 10000.0,
        fee_rate: float = 0.001,
    ) -> None:
        self._cash = initial_cash
        self._initial_cash = initial_cash
        self._fee_rate = fee_rate
        self._positions: dict[str, float] = {}
        self._prices: dict[str, float] = {}

    @property
    def mode(self) -> EnvironmentMode:
        return EnvironmentMode.BACKTEST

    def set_price(self, symbol: str, price: float) -> None:
        """Set current price for a symbol (for testing)."""
        self._prices[symbol] = price

    def execute(
        self,
        decision: ActionDecision,
        context: StrategyContext,
    ) -> ExecutionResult:
        """Execute a decision in backtest mode."""
        price = self._prices.get(decision.symbol, 100.0)
        quantity = decision.quantity
        fees = quantity * price * self._fee_rate

        # Update position
        current_pos = self._positions.get(decision.symbol, 0.0)
        if decision.action_type == ActionType.BUY:
            self._positions[decision.symbol] = current_pos + quantity
            self._cash -= quantity * price + fees
        elif decision.action_type == ActionType.SELL:
            self._positions[decision.symbol] = current_pos - quantity
            self._cash += quantity * price - fees
        elif decision.action_type == ActionType.CLOSE:
            self._positions[decision.symbol] = 0.0
            if current_pos > 0:
                self._cash += abs(current_pos) * price - fees
            else:
                self._cash -= abs(current_pos) * price + fees

        return ExecutionResult(
            action_id=decision.action_id,
            success=True,
            fill_price=price,
            fill_quantity=quantity,
            fees=fees,
        )

    def get_portfolio_state(self) -> PortfolioState:
        """Get current portfolio state."""
        from domain.model import PositionState

        positions = {}
        total_value = self._cash

        for symbol, quantity in self._positions.items():
            if abs(quantity) > 1e-9:
                price = self._prices.get(symbol, 100.0)
                positions[symbol] = PositionState(
                    symbol=symbol,
                    quantity=quantity,
                    entry_price=price,  # Simplified
                    current_price=price,
                )
                total_value += abs(quantity) * price

        return PortfolioState(
            positions=positions,
            cash=self._cash,
            equity=total_value,
            peak_equity=max(total_value, self._initial_cash),
        )

    def get_market_data(
        self, symbols: Sequence[str]
    ) -> Mapping[str, MarketDataSnapshot]:
        """Get market data for symbols."""
        result = {}
        for symbol in symbols:
            price = self._prices.get(symbol, 100.0)
            result[symbol] = MarketDataSnapshot(
                symbol=symbol,
                bid=price * 0.999,
                ask=price * 1.001,
                last=price,
            )
        return result


# -----------------------------------------------------------------------------
# Exports
# -----------------------------------------------------------------------------

__all__ = [
    "DecisionLoop",
    "DecisionLoopConfig",
    "DecisionCycle",
    "ExecutionAdapter",
    "ExecutionResult",
    "RiskEvaluator",
    "AcceptAllRiskEvaluator",
    "SimpleBacktestAdapter",
]
