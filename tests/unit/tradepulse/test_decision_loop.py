"""Tests for unified decision loop."""

import pytest
from datetime import datetime, timezone

from domain.model import (
    StrategyContext,
    StrategySignal,
    StrategyId,
    PortfolioState,
    EnvironmentMode,
    SignalDirection,
    ActionType,
    generate_signal_id,
)

from tradepulse.strategy.base import (
    Strategy,
    StrategyConfig,
)

from tradepulse.strategy.engine import (
    StrategyEngine,
    StrategyEngineConfig,
)

from tradepulse.engine.decision_loop import (
    DecisionLoop,
    DecisionLoopConfig,
    DecisionCycle,
    AcceptAllRiskEvaluator,
    SimpleBacktestAdapter,
)


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------


class SignalGeneratingStrategy(Strategy):
    """Strategy that generates configurable signals."""

    def __init__(
        self,
        config: StrategyConfig,
        signals: list[StrategySignal] | None = None,
    ):
        super().__init__(config)
        self._signals = signals or []

    def set_signals(self, signals: list[StrategySignal]) -> None:
        self._signals = signals

    def generate_signals(self, context: StrategyContext) -> list[StrategySignal]:
        return list(self._signals)


class RejectAllRiskEvaluator:
    """Risk evaluator that rejects all signals."""

    def evaluate(
        self,
        signal: StrategySignal,
        context: StrategyContext,
    ) -> tuple[bool, StrategySignal, str | None]:
        return False, signal, "rejected_by_test"


class ConfidenceFilterRiskEvaluator:
    """Risk evaluator that only approves high-confidence signals."""

    def __init__(self, min_confidence: float = 0.8):
        self._min_confidence = min_confidence

    def evaluate(
        self,
        signal: StrategySignal,
        context: StrategyContext,
    ) -> tuple[bool, StrategySignal, str | None]:
        if signal.confidence >= self._min_confidence:
            return True, signal, None
        return False, signal, f"confidence_too_low:{signal.confidence}"


def make_strategy(
    strategy_id: str = "test_strategy",
    symbols: tuple[str, ...] = ("BTCUSD",),
    signals: list[StrategySignal] | None = None,
) -> SignalGeneratingStrategy:
    """Create a test strategy."""
    config = StrategyConfig(
        strategy_id=StrategyId(strategy_id),
        name=f"Test Strategy {strategy_id}",
        symbols=symbols,
    )
    return SignalGeneratingStrategy(config, signals)


def make_signal(
    symbol: str = "BTCUSD",
    direction: SignalDirection = SignalDirection.LONG,
    strength: float = 0.8,
    confidence: float = 0.9,
    target_position: float = 0.5,
    strategy_id: str = "test_strategy",
) -> StrategySignal:
    """Create a test signal."""
    return StrategySignal(
        signal_id=generate_signal_id(),
        symbol=symbol,
        direction=direction,
        strength=strength,
        confidence=confidence,
        target_position=target_position,
        strategy_id=StrategyId(strategy_id),
    )


# -----------------------------------------------------------------------------
# DecisionLoopConfig Tests
# -----------------------------------------------------------------------------


class TestDecisionLoopConfig:
    """Tests for DecisionLoopConfig."""

    def test_default_config(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.PAPER)
        assert config.mode == EnvironmentMode.PAPER
        assert config.max_decisions_per_cycle == 100
        assert config.enable_aar is True

    def test_backtest_mode(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.BACKTEST)
        assert config.mode == EnvironmentMode.BACKTEST

    def test_live_mode(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.LIVE)
        assert config.mode == EnvironmentMode.LIVE


# -----------------------------------------------------------------------------
# SimpleBacktestAdapter Tests
# -----------------------------------------------------------------------------


class TestSimpleBacktestAdapter:
    """Tests for SimpleBacktestAdapter."""

    def test_initial_state(self) -> None:
        adapter = SimpleBacktestAdapter(initial_cash=10000.0)
        portfolio = adapter.get_portfolio_state()
        assert portfolio.cash == 10000.0
        assert portfolio.equity == 10000.0
        assert len(portfolio.positions) == 0

    def test_set_price(self) -> None:
        adapter = SimpleBacktestAdapter()
        adapter.set_price("BTCUSD", 50000.0)
        market_data = adapter.get_market_data(["BTCUSD"])
        assert "BTCUSD" in market_data
        assert market_data["BTCUSD"].last == 50000.0

    def test_mode(self) -> None:
        adapter = SimpleBacktestAdapter()
        assert adapter.mode == EnvironmentMode.BACKTEST


# -----------------------------------------------------------------------------
# DecisionLoop Tests
# -----------------------------------------------------------------------------


class TestDecisionLoop:
    """Tests for DecisionLoop."""

    def test_step_with_no_strategies(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.BACKTEST)
        engine = StrategyEngine(StrategyEngineConfig())
        engine.start()
        adapter = SimpleBacktestAdapter()

        loop = DecisionLoop(config, engine, adapter)
        cycle = loop.step()

        assert cycle.total_signals == 0
        assert cycle.total_decisions == 0
        assert loop.cycle_count == 1

    def test_step_generates_decisions(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.BACKTEST)
        engine = StrategyEngine(StrategyEngineConfig())

        signal = make_signal()
        strategy = make_strategy(signals=[signal])
        engine.register(strategy)
        engine.start()

        adapter = SimpleBacktestAdapter()
        adapter.set_price("BTCUSD", 50000.0)

        loop = DecisionLoop(config, engine, adapter)
        cycle = loop.step(symbols=["BTCUSD"])

        assert cycle.total_signals == 1
        assert cycle.total_decisions == 1
        assert cycle.signals_approved == 1
        assert cycle.signals_rejected == 0

    def test_step_executes_decisions(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.BACKTEST)
        engine = StrategyEngine(StrategyEngineConfig())

        signal = make_signal(target_position=0.1)
        strategy = make_strategy(signals=[signal])
        engine.register(strategy)
        engine.start()

        adapter = SimpleBacktestAdapter(initial_cash=10000.0, fee_rate=0.001)
        adapter.set_price("BTCUSD", 100.0)

        loop = DecisionLoop(config, engine, adapter)
        cycle = loop.step(symbols=["BTCUSD"])

        assert len(cycle.results) == 1
        assert cycle.results[0].success is True
        assert cycle.successful_executions == 1

    def test_step_generates_aar_events(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.BACKTEST, enable_aar=True)
        engine = StrategyEngine(StrategyEngineConfig())

        signal = make_signal()
        strategy = make_strategy(signals=[signal])
        engine.register(strategy)
        engine.start()

        adapter = SimpleBacktestAdapter()
        adapter.set_price("BTCUSD", 50000.0)

        loop = DecisionLoop(config, engine, adapter)
        cycle = loop.step(symbols=["BTCUSD"])

        assert len(cycle.aar_events) == 1
        assert cycle.aar_events[0].action_id == cycle.decisions[0].action_id

    def test_step_without_aar(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.BACKTEST, enable_aar=False)
        engine = StrategyEngine(StrategyEngineConfig())

        signal = make_signal()
        strategy = make_strategy(signals=[signal])
        engine.register(strategy)
        engine.start()

        adapter = SimpleBacktestAdapter()
        adapter.set_price("BTCUSD", 50000.0)

        loop = DecisionLoop(config, engine, adapter)
        cycle = loop.step(symbols=["BTCUSD"])

        assert len(cycle.aar_events) == 0

    def test_risk_evaluator_filters_signals(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.BACKTEST)
        engine = StrategyEngine(StrategyEngineConfig())

        signal = make_signal()
        strategy = make_strategy(signals=[signal])
        engine.register(strategy)
        engine.start()

        adapter = SimpleBacktestAdapter()
        evaluator = RejectAllRiskEvaluator()

        loop = DecisionLoop(config, engine, adapter, evaluator)
        cycle = loop.step(symbols=["BTCUSD"])

        assert cycle.total_signals == 1
        assert cycle.total_decisions == 0
        assert cycle.signals_approved == 0
        assert cycle.signals_rejected == 1

    def test_confidence_filter(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.BACKTEST)
        engine = StrategyEngine(StrategyEngineConfig())

        high_conf = make_signal(confidence=0.9, symbol="HIGH")
        low_conf = make_signal(confidence=0.5, symbol="LOW")
        strategy = make_strategy(symbols=("HIGH", "LOW"), signals=[high_conf, low_conf])
        engine.register(strategy)
        engine.start()

        adapter = SimpleBacktestAdapter()
        adapter.set_price("HIGH", 100.0)
        adapter.set_price("LOW", 100.0)
        evaluator = ConfidenceFilterRiskEvaluator(min_confidence=0.8)

        loop = DecisionLoop(config, engine, adapter, evaluator)
        cycle = loop.step(symbols=["HIGH", "LOW"])

        assert cycle.total_signals == 2
        assert cycle.signals_approved == 1
        assert cycle.signals_rejected == 1
        # Only the high confidence signal should have a decision
        assert cycle.total_decisions == 1
        assert cycle.decisions[0].symbol == "HIGH"

    def test_max_decisions_limit(self) -> None:
        config = DecisionLoopConfig(
            mode=EnvironmentMode.BACKTEST,
            max_decisions_per_cycle=1,
        )
        engine = StrategyEngine(StrategyEngineConfig())

        signals = [
            make_signal(symbol="BTC"),
            make_signal(symbol="ETH"),
            make_signal(symbol="SOL"),
        ]
        strategy = make_strategy(
            symbols=("BTC", "ETH", "SOL"),
            signals=signals,
        )
        engine.register(strategy)
        engine.start()

        adapter = SimpleBacktestAdapter()
        adapter.set_price("BTC", 100.0)
        adapter.set_price("ETH", 100.0)
        adapter.set_price("SOL", 100.0)

        loop = DecisionLoop(config, engine, adapter)
        cycle = loop.step(symbols=["BTC", "ETH", "SOL"])

        assert cycle.total_signals == 3
        assert cycle.total_decisions == 1

    def test_run_cycles(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.BACKTEST)
        engine = StrategyEngine(StrategyEngineConfig())

        signal = make_signal()
        strategy = make_strategy(signals=[signal])
        engine.register(strategy)
        engine.start()

        adapter = SimpleBacktestAdapter()
        adapter.set_price("BTCUSD", 50000.0)

        loop = DecisionLoop(config, engine, adapter)
        cycles = loop.run_cycles(3, symbols=["BTCUSD"])

        assert len(cycles) == 3
        assert loop.cycle_count == 3

    def test_reset(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.BACKTEST)
        engine = StrategyEngine(StrategyEngineConfig())
        engine.start()
        adapter = SimpleBacktestAdapter()

        loop = DecisionLoop(config, engine, adapter)
        loop.step()
        loop.step()

        assert loop.cycle_count == 2

        loop.reset()
        assert loop.cycle_count == 0

    def test_action_type_buy(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.BACKTEST)
        engine = StrategyEngine(StrategyEngineConfig())

        signal = make_signal(direction=SignalDirection.LONG, target_position=0.5)
        strategy = make_strategy(signals=[signal])
        engine.register(strategy)
        engine.start()

        adapter = SimpleBacktestAdapter()
        adapter.set_price("BTCUSD", 100.0)

        loop = DecisionLoop(config, engine, adapter)
        cycle = loop.step(symbols=["BTCUSD"])

        assert len(cycle.decisions) == 1
        assert cycle.decisions[0].action_type == ActionType.BUY

    def test_action_type_sell(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.BACKTEST)
        engine = StrategyEngine(StrategyEngineConfig())

        signal = make_signal(direction=SignalDirection.SHORT, target_position=-0.5)
        strategy = make_strategy(signals=[signal])
        engine.register(strategy)
        engine.start()

        adapter = SimpleBacktestAdapter()
        adapter.set_price("BTCUSD", 100.0)

        loop = DecisionLoop(config, engine, adapter)
        cycle = loop.step(symbols=["BTCUSD"])

        assert len(cycle.decisions) == 1
        assert cycle.decisions[0].action_type == ActionType.SELL

    def test_action_type_close(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.BACKTEST)
        engine = StrategyEngine(StrategyEngineConfig())

        # First, establish a position
        buy_signal = make_signal(direction=SignalDirection.LONG, target_position=0.5)
        strategy = make_strategy(signals=[buy_signal])
        engine.register(strategy)
        engine.start()

        adapter = SimpleBacktestAdapter()
        adapter.set_price("BTCUSD", 100.0)

        loop = DecisionLoop(config, engine, adapter)
        loop.step(symbols=["BTCUSD"])  # Opens position

        # Now send a flat signal
        flat_signal = make_signal(direction=SignalDirection.FLAT, target_position=0.0)
        strategy.set_signals([flat_signal])

        cycle = loop.step(symbols=["BTCUSD"])

        assert len(cycle.decisions) == 1
        assert cycle.decisions[0].action_type == ActionType.CLOSE

    def test_multiple_strategies(self) -> None:
        config = DecisionLoopConfig(mode=EnvironmentMode.BACKTEST)
        engine = StrategyEngine(StrategyEngineConfig())

        strategy1 = make_strategy(
            strategy_id="strat1",
            symbols=("BTC",),
            signals=[make_signal(symbol="BTC", strategy_id="strat1")],
        )
        strategy2 = make_strategy(
            strategy_id="strat2",
            symbols=("ETH",),
            signals=[make_signal(symbol="ETH", strategy_id="strat2")],
        )

        engine.register(strategy1)
        engine.register(strategy2)
        engine.start()

        adapter = SimpleBacktestAdapter()
        adapter.set_price("BTC", 50000.0)
        adapter.set_price("ETH", 3000.0)

        loop = DecisionLoop(config, engine, adapter)
        cycle = loop.step(symbols=["BTC", "ETH"])

        assert cycle.total_signals == 2
        assert cycle.total_decisions == 2
        symbols = {d.symbol for d in cycle.decisions}
        assert symbols == {"BTC", "ETH"}


class TestDecisionCycle:
    """Tests for DecisionCycle."""

    def test_properties(self) -> None:
        cycle = DecisionCycle(
            timestamp=datetime.now(timezone.utc),
            context=StrategyContext(
                mode=EnvironmentMode.BACKTEST,
                portfolio=PortfolioState(),
            ),
            signals=(make_signal(), make_signal()),
            decisions=(),
            results=(),
            aar_events=(),
            signals_approved=1,
            signals_rejected=1,
        )

        assert cycle.total_signals == 2
        assert cycle.total_decisions == 0
        assert cycle.successful_executions == 0
