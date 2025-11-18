"""Tests for strategy orchestration module."""

from __future__ import annotations

import pytest

from core.agent.orchestrator import StrategyFlow, StrategyOrchestrationError
from core.agent.strategy import Strategy


class DummyStrategy(Strategy):
    """Minimal Strategy implementation for testing."""

    def __init__(self, name: str) -> None:
        self.name = name

    def evaluate(self, data: any) -> any:
        return {"strategy": self.name, "result": "success"}


class TestStrategyFlow:
    """Test StrategyFlow validation and creation."""

    def test_strategy_flow_creation_valid(self) -> None:
        strategies = [DummyStrategy("S1"), DummyStrategy("S2")]
        flow = StrategyFlow(
            name="test_flow",
            strategies=strategies,
            dataset={"data": [1, 2, 3]},
            priority=5,
        )

        assert flow.name == "test_flow"
        assert len(flow.strategies) == 2
        assert flow.priority == 5
        assert flow.raise_on_error is False

    def test_strategy_flow_with_single_strategy(self) -> None:
        strategy = DummyStrategy("SingleStrategy")
        flow = StrategyFlow(
            name="single",
            strategies=[strategy],
            dataset=None,
        )

        assert flow.name == "single"
        assert len(flow.strategies) == 1
        assert flow.strategies[0].name == "SingleStrategy"

    def test_strategy_flow_empty_name_raises_error(self) -> None:
        strategy = DummyStrategy("S1")
        with pytest.raises(ValueError) as excinfo:
            StrategyFlow(
                name="",
                strategies=[strategy],
                dataset=None,
            )
        assert "non-empty string" in str(excinfo.value)

    def test_strategy_flow_whitespace_name_raises_error(self) -> None:
        strategy = DummyStrategy("S1")
        with pytest.raises(ValueError) as excinfo:
            StrategyFlow(
                name="   ",
                strategies=[strategy],
                dataset=None,
            )
        assert "non-empty string" in str(excinfo.value)

    def test_strategy_flow_empty_strategies_raises_error(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            StrategyFlow(
                name="test",
                strategies=[],
                dataset=None,
            )
        assert "at least one strategy" in str(excinfo.value)

    def test_strategy_flow_strategies_as_string_raises_error(self) -> None:
        with pytest.raises(TypeError) as excinfo:
            StrategyFlow(
                name="test",
                strategies="not a sequence",  # type: ignore
                dataset=None,
            )
        assert "must not be a string" in str(excinfo.value)

    def test_strategy_flow_strategies_not_sequence_raises_error(self) -> None:
        with pytest.raises(TypeError) as excinfo:
            StrategyFlow(
                name="test",
                strategies={"dict": "not sequence"},  # type: ignore
                dataset=None,
            )
        assert "must be a sequence" in str(excinfo.value)

    def test_strategy_flow_invalid_strategy_type_raises_error(self) -> None:
        with pytest.raises(TypeError) as excinfo:
            StrategyFlow(
                name="test",
                strategies=["not", "strategies"],  # type: ignore
                dataset=None,
            )
        assert "Strategy instances" in str(excinfo.value)

    def test_strategy_flow_priority_not_integer_raises_error(self) -> None:
        strategy = DummyStrategy("S1")
        with pytest.raises(TypeError) as excinfo:
            StrategyFlow(
                name="test",
                strategies=[strategy],
                dataset=None,
                priority="high",  # type: ignore
            )
        assert "must be an integer" in str(excinfo.value)

    def test_strategy_flow_with_zero_priority(self) -> None:
        strategy = DummyStrategy("S1")
        flow = StrategyFlow(
            name="zero_priority",
            strategies=[strategy],
            dataset=None,
            priority=0,
        )
        assert flow.priority == 0

    def test_strategy_flow_with_negative_priority(self) -> None:
        strategy = DummyStrategy("S1")
        flow = StrategyFlow(
            name="negative_priority",
            strategies=[strategy],
            dataset=None,
            priority=-10,
        )
        assert flow.priority == -10

    def test_strategy_flow_strategies_converted_to_tuple(self) -> None:
        strategies_list = [DummyStrategy("S1"), DummyStrategy("S2")]
        flow = StrategyFlow(
            name="test",
            strategies=strategies_list,
            dataset=None,
        )
        # Should be converted to tuple for immutability
        assert isinstance(flow.strategies, tuple)
        assert len(flow.strategies) == 2


class TestStrategyOrchestrationError:
    """Test StrategyOrchestrationError exception."""

    def test_orchestration_error_creation(self) -> None:
        errors = {
            "flow1": ValueError("Invalid data"),
            "flow2": RuntimeError("Processing failed"),
        }
        results = {
            "flow3": [{"status": "success"}],
        }

        error = StrategyOrchestrationError(errors, results)

        assert len(error.errors) == 2
        assert len(error.results) == 1
        assert "flow1" in error.errors
        assert "flow2" in error.errors
        assert "flow3" in error.results

    def test_orchestration_error_message_format(self) -> None:
        errors = {
            "alpha": ValueError("Bad value"),
            "beta": RuntimeError("Runtime issue"),
        }
        results = {}

        error = StrategyOrchestrationError(errors, results)

        error_msg = str(error)
        assert "2 flow(s)" in error_msg
        assert "alpha" in error_msg
        assert "beta" in error_msg
        assert "Bad value" in error_msg or "ValueError" in error_msg

    def test_orchestration_error_with_no_errors(self) -> None:
        # Edge case: error object with no errors
        errors = {}
        results = {"flow1": [{"result": "ok"}]}

        error = StrategyOrchestrationError(errors, results)

        assert len(error.errors) == 0
        assert len(error.results) == 1
        error_msg = str(error)
        assert "0 flow(s)" in error_msg

    def test_orchestration_error_preserves_original_exceptions(self) -> None:
        original_error = ValueError("Original error message")
        errors = {"test_flow": original_error}
        results = {}

        error = StrategyOrchestrationError(errors, results)

        assert error.errors["test_flow"] is original_error
        assert isinstance(error.errors["test_flow"], ValueError)

    def test_orchestration_error_results_are_mutable_dict(self) -> None:
        errors = {}
        results = {"flow1": [{"data": 1}]}

        error = StrategyOrchestrationError(errors, results)

        # Should be able to modify the dicts
        error.results["flow2"] = [{"data": 2}]
        assert "flow2" in error.results
        assert len(error.results) == 2


class TestStrategyFlowIntegration:
    """Integration tests for StrategyFlow with realistic scenarios."""

    def test_multiple_strategies_in_flow(self) -> None:
        strategies = [
            DummyStrategy("Momentum"),
            DummyStrategy("MeanReversion"),
            DummyStrategy("Arbitrage"),
        ]

        flow = StrategyFlow(
            name="multi_strategy_portfolio",
            strategies=strategies,
            dataset={"prices": [100, 101, 99, 102]},
            priority=10,
        )

        assert flow.name == "multi_strategy_portfolio"
        assert len(flow.strategies) == 3
        assert all(isinstance(s, DummyStrategy) for s in flow.strategies)

    def test_flow_with_raise_on_error_flag(self) -> None:
        strategy = DummyStrategy("TestStrat")
        flow = StrategyFlow(
            name="strict_flow",
            strategies=[strategy],
            dataset=None,
            raise_on_error=True,
        )

        assert flow.raise_on_error is True

    def test_flows_can_be_sorted_by_priority(self) -> None:
        flow1 = StrategyFlow(
            name="low",
            strategies=[DummyStrategy("S1")],
            dataset=None,
            priority=1,
        )
        flow2 = StrategyFlow(
            name="high",
            strategies=[DummyStrategy("S2")],
            dataset=None,
            priority=10,
        )
        flow3 = StrategyFlow(
            name="medium",
            strategies=[DummyStrategy("S3")],
            dataset=None,
            priority=5,
        )

        flows = [flow1, flow2, flow3]
        sorted_flows = sorted(flows, key=lambda f: f.priority, reverse=True)

        assert sorted_flows[0].name == "high"
        assert sorted_flows[1].name == "medium"
        assert sorted_flows[2].name == "low"
