"""Tests for the Neuro-Orchestrator Agent."""

from __future__ import annotations

import copy
import json

import pytest

from tradepulse.core.neuro.neuro_orchestrator import (
    LearningLoop,
    ModuleInstruction,
    NeuroOrchestrator,
    OrchestrationOutput,
    RiskContour,
    TradingScenario,
    create_orchestration_from_scenario,
)


class TestTradingScenario:
    """Test TradingScenario dataclass."""

    def test_basic_scenario(self):
        """Test basic scenario creation."""
        scenario = TradingScenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )
        assert scenario.market == "BTC/USDT"
        assert scenario.timeframe == "1h"
        assert scenario.risk_profile == "moderate"
        assert scenario.capital == 100000.0
        assert scenario.max_position_size == 0.2

    def test_custom_capital(self):
        """Test scenario with custom capital."""
        scenario = TradingScenario(
            market="ETH/USDT",
            timeframe="5m",
            risk_profile="aggressive",
            capital=50000.0,
            max_position_size=0.3,
        )
        assert scenario.capital == 50000.0
        assert scenario.max_position_size == 0.3


class TestModuleInstruction:
    """Test ModuleInstruction dataclass."""

    def test_module_instruction(self):
        """Test module instruction creation."""
        instruction = ModuleInstruction(
            module_name="action_selector",
            operation="select",
            parameters={"temperature": 1.0},
            priority=3,
        )
        assert instruction.module_name == "action_selector"
        assert instruction.operation == "select"
        assert instruction.parameters == {"temperature": 1.0}
        assert instruction.priority == 3


class TestRiskContour:
    """Test RiskContour dataclass."""

    def test_risk_contour(self):
        """Test risk contour creation."""
        contour = RiskContour(
            mode="normal",
            threat_threshold=0.5,
            exposure_limit=0.5,
            drawdown_limit=0.10,
        )
        assert contour.mode == "normal"
        assert contour.threat_threshold == 0.5
        assert contour.exposure_limit == 0.5
        assert contour.drawdown_limit == 0.10
        assert contour.var_confidence == 0.975
        assert contour.kelly_fraction_cap == 1.0


class TestLearningLoop:
    """Test LearningLoop dataclass."""

    def test_learning_loop_defaults(self):
        """Test learning loop with defaults."""
        loop = LearningLoop()
        assert loop.algorithm == "TD(0)"
        assert loop.discount_gamma == 0.99
        assert loop.learning_rate == 0.01
        assert loop.prediction_window == 1
        assert loop.error_metric == "absolute"

    def test_learning_loop_custom(self):
        """Test learning loop with custom values."""
        loop = LearningLoop(
            algorithm="TD(λ)",
            discount_gamma=0.95,
            learning_rate=0.005,
        )
        assert loop.algorithm == "TD(λ)"
        assert loop.discount_gamma == 0.95
        assert loop.learning_rate == 0.005


class TestOrchestrationOutput:
    """Test OrchestrationOutput dataclass."""

    def test_output_creation(self):
        """Test orchestration output creation."""
        module_sequence = [
            ModuleInstruction(
                module_name="data_ingestion",
                operation="ingest",
                parameters={"symbol": "BTC/USDT"},
                priority=0,
            )
        ]
        parameters = {"capital": 100000.0}
        risk_contour = RiskContour(
            mode="normal",
            threat_threshold=0.5,
            exposure_limit=0.5,
            drawdown_limit=0.10,
        )
        learning_loop = LearningLoop()

        output = OrchestrationOutput(
            module_sequence=module_sequence,
            parameters=parameters,
            risk_contour=risk_contour,
            learning_loop=learning_loop,
        )

        assert len(output.module_sequence) == 1
        assert output.parameters["capital"] == 100000.0
        assert output.risk_contour.mode == "normal"
        assert output.learning_loop.algorithm == "TD(0)"

    def test_to_json(self):
        """Test JSON serialization."""
        module_sequence = [
            ModuleInstruction(
                module_name="test_module",
                operation="test_op",
                parameters={"param1": "value1"},
                priority=0,
            )
        ]
        parameters = {"test_param": 123}
        risk_contour = RiskContour(
            mode="normal",
            threat_threshold=0.5,
            exposure_limit=0.5,
            drawdown_limit=0.10,
        )
        learning_loop = LearningLoop()

        output = OrchestrationOutput(
            module_sequence=module_sequence,
            parameters=parameters,
            risk_contour=risk_contour,
            learning_loop=learning_loop,
        )

        json_str = output.to_json()
        data = json.loads(json_str)

        assert "module_sequence" in data
        assert "parameters" in data
        assert "risk_contour" in data
        assert "learning_loop" in data
        assert data["module_sequence"][0]["module_name"] == "test_module"
        assert data["parameters"]["test_param"] == 123


class TestNeuroOrchestrator:
    """Test NeuroOrchestrator class."""

    def test_initialization(self):
        """Test orchestrator initialization."""
        orchestrator = NeuroOrchestrator(
            free_energy_threshold=1.5,
            enable_tacl_validation=True,
        )
        assert orchestrator._free_energy_threshold == 1.5
        assert orchestrator._enable_tacl_validation is True

    def test_orchestrate_conservative(self):
        """Test orchestration with conservative risk profile."""
        scenario = TradingScenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="conservative",
        )
        orchestrator = NeuroOrchestrator()
        output = orchestrator.orchestrate(scenario)

        # Check module sequence
        assert len(output.module_sequence) == 6
        module_names = [m.module_name for m in output.module_sequence]
        assert "data_ingestion" in module_names
        assert "action_selector" in module_names
        assert "learning_loop" in module_names
        assert "tacl_monitor" in module_names

        # Check parameters for conservative profile
        assert output.parameters["learning_rate"] == 0.005
        assert output.parameters["discount_gamma"] == 0.95
        assert output.parameters["exposure_limit"] == 0.3

        # Check risk contour
        assert output.risk_contour.mode == "conservative"
        assert output.risk_contour.threat_threshold == 0.3
        assert output.risk_contour.exposure_limit == 0.3
        assert output.risk_contour.drawdown_limit == 0.05

        # Check learning loop
        assert output.learning_loop.discount_gamma == 0.95
        assert output.learning_loop.learning_rate == 0.005

    def test_orchestrate_moderate(self):
        """Test orchestration with moderate risk profile."""
        scenario = TradingScenario(
            market="ETH/USDT",
            timeframe="5m",
            risk_profile="moderate",
        )
        orchestrator = NeuroOrchestrator()
        output = orchestrator.orchestrate(scenario)

        # Check parameters for moderate profile
        assert output.parameters["learning_rate"] == 0.01
        assert output.parameters["discount_gamma"] == 0.99
        assert output.parameters["exposure_limit"] == 0.5

        # Check risk contour
        assert output.risk_contour.mode == "normal"
        assert output.risk_contour.threat_threshold == 0.5
        assert output.risk_contour.drawdown_limit == 0.10

    def test_orchestrate_aggressive(self):
        """Test orchestration with aggressive risk profile."""
        scenario = TradingScenario(
            market="SOL/USDT",
            timeframe="15m",
            risk_profile="aggressive",
        )
        orchestrator = NeuroOrchestrator()
        output = orchestrator.orchestrate(scenario)

        # Check parameters for aggressive profile
        assert output.parameters["learning_rate"] == 0.02
        assert output.parameters["discount_gamma"] == 0.99
        assert output.parameters["exposure_limit"] == 0.8

        # Check risk contour
        assert output.risk_contour.mode == "aggressive"
        assert output.risk_contour.threat_threshold == 0.7
        assert output.risk_contour.drawdown_limit == 0.20

    def test_module_sequence_order(self):
        """Test that module sequence follows correct priority order."""
        scenario = TradingScenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )
        orchestrator = NeuroOrchestrator()
        output = orchestrator.orchestrate(scenario)

        # Check execution order
        expected_order = [
            "data_ingestion",
            "feature_extraction",
            "risk_assessment",
            "action_selector",
            "learning_loop",
            "tacl_monitor",
        ]
        actual_order = [m.module_name for m in output.module_sequence]
        assert actual_order == expected_order

        # Check priorities are ascending
        priorities = [m.priority for m in output.module_sequence]
        assert priorities == sorted(priorities)

    def test_neuromodulator_parameters(self):
        """Test that neuromodulator parameters are included."""
        scenario = TradingScenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )
        orchestrator = NeuroOrchestrator()
        output = orchestrator.orchestrate(scenario)

        # Check neuromodulator parameters
        assert "dopamine" in output.parameters
        assert "serotonin" in output.parameters
        assert "gaba" in output.parameters
        assert "na_ach" in output.parameters

        # Check dopamine config
        dopamine = output.parameters["dopamine"]
        assert "burst_factor" in dopamine
        assert "decay_rate" in dopamine
        assert "invigoration_threshold" in dopamine

    def test_tacl_parameters(self):
        """Test that TACL parameters are included."""
        scenario = TradingScenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )
        orchestrator = NeuroOrchestrator()
        output = orchestrator.orchestrate(scenario)

        # Check TACL parameters
        assert "tacl" in output.parameters
        tacl = output.parameters["tacl"]
        assert tacl["monotonic_descent"] is True
        assert "epsilon_tolerance" in tacl
        assert "crisis_detection" in tacl
        assert "protocol_options" in tacl

    def test_custom_parameters_override(self):
        """Test that custom parameters override defaults."""
        scenario = TradingScenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )
        custom_params = {
            "learning_rate": 0.025,
            "temperature": 2.0,
        }
        orchestrator = NeuroOrchestrator()
        output = orchestrator.orchestrate(scenario, custom_parameters=custom_params)

        assert output.parameters["learning_rate"] == 0.025
        assert output.parameters["temperature"] == 2.0

    def test_custom_parameters_nested_merge(self):
        """Custom overrides should merge nested dictionaries rather than replace them."""
        scenario = TradingScenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )
        custom_params = {
            "dopamine": {"burst_factor": 2.25},
            "tacl": {"epsilon_tolerance": 0.02},
        }

        orchestrator = NeuroOrchestrator()
        output = orchestrator.orchestrate(scenario, custom_parameters=custom_params)

        # Existing nested fields should still be present after applying overrides.
        dopamine = output.parameters["dopamine"]
        assert dopamine["burst_factor"] == 2.25
        assert dopamine["decay_rate"] == 0.95
        assert dopamine["invigoration_threshold"] == 0.6

        tacl = output.parameters["tacl"]
        assert tacl["epsilon_tolerance"] == 0.02
        assert tacl["monotonic_descent"] is True
        assert tacl["crisis_detection"] is True

    def test_custom_parameters_dot_path_override(self):
        """Dot notation keys should target nested configuration fields."""
        scenario = TradingScenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )
        custom_params = {
            "dopamine": {"decay_rate": 0.92},
            "dopamine.burst_factor": 2.5,
            "tacl.protocol_options": ["CRDT", "gRPC"],
        }

        orchestrator = NeuroOrchestrator()
        output = orchestrator.orchestrate(scenario, custom_parameters=custom_params)

        dopamine = output.parameters["dopamine"]
        assert dopamine["decay_rate"] == 0.92
        assert dopamine["burst_factor"] == 2.5

        tacl = output.parameters["tacl"]
        assert tacl["protocol_options"] == ["CRDT", "gRPC"]

    def test_custom_parameters_dot_path_conflict(self):
        """Conflicting dot-path overrides should raise a helpful error."""
        scenario = TradingScenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )
        custom_params = {
            "dopamine": 0.8,
            "dopamine.burst_factor": 2.0,
        }

        orchestrator = NeuroOrchestrator()

        with pytest.raises(ValueError, match="dopamine"):
            orchestrator.orchestrate(scenario, custom_parameters=custom_params)

    def test_custom_parameters_not_mutated(self):
        """User-supplied override mappings should remain unchanged."""
        scenario = TradingScenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )
        custom_params = {
            "dopamine": {"burst_factor": 2.25},
        }
        original_snapshot = copy.deepcopy(custom_params)

        orchestrator = NeuroOrchestrator()
        orchestrator.orchestrate(scenario, custom_parameters=custom_params)

        assert custom_params == original_snapshot

    def test_free_energy_validation(self):
        """Test TACL free-energy validation."""
        scenario = TradingScenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )

        # Should not raise with valid threshold
        orchestrator = NeuroOrchestrator(free_energy_threshold=1.5)
        output = orchestrator.orchestrate(scenario)
        assert output.parameters["free_energy_threshold"] == 1.5

    def test_free_energy_threshold_validation_failure(self):
        """Test that high free-energy threshold is rejected."""
        scenario = TradingScenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )
        custom_params = {"free_energy_threshold": 2.5}
        orchestrator = NeuroOrchestrator(enable_tacl_validation=True)

        with pytest.raises(ValueError, match="exceeds safe limit"):
            orchestrator.orchestrate(scenario, custom_parameters=custom_params)

    def test_temperature_validation_failure(self):
        """Test that excessive temperature is rejected."""
        scenario = TradingScenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )
        custom_params = {"temperature": 3.0}
        orchestrator = NeuroOrchestrator(enable_tacl_validation=True)

        with pytest.raises(ValueError, match="exceeds safe limit"):
            orchestrator.orchestrate(scenario, custom_parameters=custom_params)

    def test_monotonic_descent_validation(self):
        """Test that monotonic descent cannot be disabled."""
        scenario = TradingScenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )
        custom_params = {"tacl": {"monotonic_descent": False}}
        orchestrator = NeuroOrchestrator(enable_tacl_validation=True)

        with pytest.raises(ValueError, match="must be enabled"):
            orchestrator.orchestrate(scenario, custom_parameters=custom_params)

    def test_validation_disabled(self):
        """Test orchestration with validation disabled."""
        scenario = TradingScenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )
        # Should allow high threshold when validation disabled
        custom_params = {"free_energy_threshold": 3.0}
        orchestrator = NeuroOrchestrator(enable_tacl_validation=False)
        output = orchestrator.orchestrate(scenario, custom_parameters=custom_params)

        assert output.parameters["free_energy_threshold"] == 3.0


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_create_orchestration_from_scenario(self):
        """Test convenience function for creating orchestration."""
        output = create_orchestration_from_scenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
            capital=50000.0,
            max_position_size=0.3,
        )

        assert len(output.module_sequence) == 6
        assert output.parameters["capital"] == 50000.0
        assert output.parameters["max_position_size"] == 0.3
        assert output.risk_contour.mode == "normal"

    def test_create_orchestration_json_output(self):
        """Test that convenience function produces valid JSON."""
        output = create_orchestration_from_scenario(
            market="ETH/USDT",
            timeframe="5m",
            risk_profile="conservative",
        )

        json_str = output.to_json()
        data = json.loads(json_str)

        assert "module_sequence" in data
        assert "parameters" in data
        assert "risk_contour" in data
        assert "learning_loop" in data


class TestJSONOutput:
    """Test JSON output format compliance."""

    def test_json_format_complete(self):
        """Test that JSON output has all required keys."""
        output = create_orchestration_from_scenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )

        json_str = output.to_json()
        data = json.loads(json_str)

        # Check all required keys
        assert "module_sequence" in data
        assert "parameters" in data
        assert "risk_contour" in data
        assert "learning_loop" in data

    def test_json_module_sequence_structure(self):
        """Test module sequence structure in JSON."""
        output = create_orchestration_from_scenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )

        data = json.loads(output.to_json())
        modules = data["module_sequence"]

        for module in modules:
            assert "module_name" in module
            assert "operation" in module
            assert "parameters" in module
            assert "priority" in module

    def test_json_risk_contour_structure(self):
        """Test risk contour structure in JSON."""
        output = create_orchestration_from_scenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )

        data = json.loads(output.to_json())
        risk_contour = data["risk_contour"]

        assert "mode" in risk_contour
        assert "threat_threshold" in risk_contour
        assert "exposure_limit" in risk_contour
        assert "drawdown_limit" in risk_contour
        assert "var_confidence" in risk_contour
        assert "kelly_fraction_cap" in risk_contour

    def test_json_learning_loop_structure(self):
        """Test learning loop structure in JSON."""
        output = create_orchestration_from_scenario(
            market="BTC/USDT",
            timeframe="1h",
            risk_profile="moderate",
        )

        data = json.loads(output.to_json())
        learning_loop = data["learning_loop"]

        assert "algorithm" in learning_loop
        assert "discount_gamma" in learning_loop
        assert "learning_rate" in learning_loop
        assert "prediction_window" in learning_loop
        assert "error_metric" in learning_loop
        assert "update_rule" in learning_loop
