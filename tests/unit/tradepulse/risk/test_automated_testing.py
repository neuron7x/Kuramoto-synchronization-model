"""Tests for automated risk testing module."""

# Import directly from module file to avoid torch dependency issues
import importlib.util
import sys
from pathlib import Path

import numpy as np

# First load risk_core
risk_core_spec = importlib.util.spec_from_file_location(
    "risk_core",
    Path(__file__).parent.parent.parent.parent.parent
    / "src/tradepulse/risk/risk_core.py",
)
risk_core_module = importlib.util.module_from_spec(risk_core_spec)
sys.modules["tradepulse.risk.risk_core"] = risk_core_module
risk_core_spec.loader.exec_module(risk_core_module)

# Then load automated_testing
auto_test_spec = importlib.util.spec_from_file_location(
    "tradepulse.risk.automated_testing",
    Path(__file__).parent.parent.parent.parent.parent
    / "src/tradepulse/risk/automated_testing.py",
)
auto_test_module = importlib.util.module_from_spec(auto_test_spec)
sys.modules["tradepulse.risk.automated_testing"] = auto_test_module
auto_test_spec.loader.exec_module(auto_test_module)

AutomatedRiskTester = auto_test_module.AutomatedRiskTester
MonteCarloConfig = auto_test_module.MonteCarloConfig
RiskScenario = auto_test_module.RiskScenario
ScenarioType = auto_test_module.ScenarioType
generate_flash_crash_scenarios = auto_test_module.generate_flash_crash_scenarios
generate_liquidity_crisis_scenarios = (
    auto_test_module.generate_liquidity_crisis_scenarios
)
generate_market_stress_scenarios = auto_test_module.generate_market_stress_scenarios
validate_risk_metrics = auto_test_module.validate_risk_metrics


class TestRiskScenario:
    """Test RiskScenario class."""

    def test_scenario_creation(self):
        """Test creating a risk scenario."""
        returns = np.random.normal(0, 0.01, 100)
        scenario = RiskScenario(
            name="test_scenario",
            scenario_type=ScenarioType.NORMAL_MARKET,
            returns=returns,
            description="Test scenario",
        )

        assert scenario.name == "test_scenario"
        assert scenario.scenario_type == ScenarioType.NORMAL_MARKET
        assert len(scenario.returns) == 100
        assert scenario.description == "Test scenario"

    def test_scenario_validation_passes(self):
        """Test scenario validation with valid metrics."""
        returns = np.random.normal(0, 0.01, 100)
        scenario = RiskScenario(
            name="test",
            scenario_type=ScenarioType.NORMAL_MARKET,
            returns=returns,
            description="Test",
            expected_var_range=(0.0, 0.1),
            expected_es_range=(0.0, 0.15),
        )

        errors = scenario.validate_metrics(var=0.02, es=0.03, alpha=0.975)
        assert len(errors) == 0

    def test_scenario_validation_fails_var_out_of_range(self):
        """Test scenario validation fails when VaR is out of range."""
        returns = np.random.normal(0, 0.01, 100)
        scenario = RiskScenario(
            name="test",
            scenario_type=ScenarioType.NORMAL_MARKET,
            returns=returns,
            description="Test",
            expected_var_range=(0.0, 0.02),
            expected_es_range=(0.0, 0.15),
        )

        errors = scenario.validate_metrics(var=0.05, es=0.06, alpha=0.975)
        assert len(errors) > 0
        assert any("VaR" in error for error in errors)

    def test_scenario_validation_fails_es_less_than_var(self):
        """Test scenario validation fails when ES < VaR."""
        returns = np.random.normal(0, 0.01, 100)
        scenario = RiskScenario(
            name="test",
            scenario_type=ScenarioType.NORMAL_MARKET,
            returns=returns,
            description="Test",
        )

        # ES should always be >= VaR
        errors = scenario.validate_metrics(var=0.05, es=0.03, alpha=0.975)
        assert len(errors) > 0
        assert any("ES" in error and "less than VaR" in error for error in errors)


class TestAutomatedRiskTester:
    """Test AutomatedRiskTester class."""

    def test_tester_initialization(self):
        """Test tester initialization with default parameters."""
        tester = AutomatedRiskTester()

        assert tester.es_limit == 0.03
        assert tester.var_alpha == 0.975
        assert tester.f_max == 1.0
        assert len(tester.scenarios) == 0
        assert len(tester.results) == 0

    def test_tester_initialization_with_custom_params(self):
        """Test tester initialization with custom parameters."""
        tester = AutomatedRiskTester(es_limit=0.05, var_alpha=0.95, f_max=0.8, seed=42)

        assert tester.es_limit == 0.05
        assert tester.var_alpha == 0.95
        assert tester.f_max == 0.8
        assert tester.seed == 42

    def test_add_scenario(self):
        """Test adding scenarios to the tester."""
        tester = AutomatedRiskTester()
        returns = np.random.normal(0, 0.01, 100)

        scenario = RiskScenario(
            name="test",
            scenario_type=ScenarioType.NORMAL_MARKET,
            returns=returns,
            description="Test",
        )

        tester.add_scenario(scenario)
        assert len(tester.scenarios) == 1
        assert tester.scenarios[0] == scenario

    def test_run_stress_test(self):
        """Test running a single stress test."""
        tester = AutomatedRiskTester(seed=42)
        np.random.seed(42)
        returns = np.random.normal(0, 0.01, 100)

        scenario = RiskScenario(
            name="normal_market",
            scenario_type=ScenarioType.NORMAL_MARKET,
            returns=returns,
            description="Normal market test",
        )

        result = tester.run_stress_test(scenario)

        assert result.scenario_name == "normal_market"
        assert result.scenario_type == ScenarioType.NORMAL_MARKET
        assert result.var >= 0
        assert result.es >= 0
        assert result.es >= result.var  # ES should be >= VaR
        assert result.alpha == 0.975
        assert 0 <= result.kelly_fraction <= 1.0
        assert result.risk_breach in ["OK", "BREACH"]
        assert result.max_drawdown <= 0  # Drawdown should be negative
        assert result.duration_seconds >= 0

    def test_run_all_scenarios(self):
        """Test running all scenarios."""
        tester = AutomatedRiskTester(seed=42)
        np.random.seed(42)

        # Add multiple scenarios
        for i in range(3):
            returns = np.random.normal(0, 0.01, 100)
            scenario = RiskScenario(
                name=f"scenario_{i}",
                scenario_type=ScenarioType.NORMAL_MARKET,
                returns=returns,
                description=f"Test scenario {i}",
            )
            tester.add_scenario(scenario)

        results = tester.run_all_scenarios()

        assert len(results) == 3
        assert len(tester.results) == 3
        assert all(r.scenario_name.startswith("scenario_") for r in results)

    def test_run_monte_carlo_simulation(self):
        """Test Monte Carlo simulation."""
        tester = AutomatedRiskTester(seed=42)

        config = MonteCarloConfig(
            num_simulations=10,
            num_periods=100,
            mu=0.0005,
            sigma=0.01,
            seed=42,
        )

        results = tester.run_monte_carlo_simulation(config)

        assert len(results) == 10
        assert all(r.scenario_type == ScenarioType.NORMAL_MARKET for r in results)
        assert all(r.var >= 0 for r in results)
        assert all(r.es >= r.var for r in results)

    def test_generate_summary_report_empty(self):
        """Test summary report generation with no results."""
        tester = AutomatedRiskTester()

        summary = tester.generate_summary_report()

        assert summary["status"] == "no_results"
        assert "message" in summary

    def test_generate_summary_report(self):
        """Test summary report generation with results."""
        tester = AutomatedRiskTester(seed=42)
        np.random.seed(42)

        # Add and run scenarios
        for i in range(3):
            returns = np.random.normal(0, 0.01, 100)
            scenario = RiskScenario(
                name=f"scenario_{i}",
                scenario_type=ScenarioType.NORMAL_MARKET,
                returns=returns,
                description=f"Test scenario {i}",
            )
            tester.add_scenario(scenario)

        tester.run_all_scenarios()

        summary = tester.generate_summary_report()

        assert summary["total_scenarios"] == 3
        assert "passed" in summary
        assert "failed" in summary
        assert "pass_rate" in summary
        assert "metrics" in summary
        assert "var" in summary["metrics"]
        assert "es" in summary["metrics"]
        assert "max_drawdown" in summary["metrics"]
        assert len(summary["results"]) == 3

    def test_calculate_max_drawdown(self):
        """Test maximum drawdown calculation."""
        # Create returns with known drawdown
        returns = np.array([0.1, -0.2, -0.1, 0.15, 0.05])

        max_dd = AutomatedRiskTester._calculate_max_drawdown(returns)

        assert max_dd < 0  # Drawdown should be negative
        assert max_dd <= 0  # Should be at most 0

    def test_calculate_sharpe_ratio(self):
        """Test Sharpe ratio calculation."""
        # Create returns with known characteristics
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.01, 252)

        sharpe = AutomatedRiskTester._calculate_sharpe_ratio(returns)

        # Sharpe ratio should be reasonable for these parameters
        assert -5 < sharpe < 5  # Typical range for daily returns annualized

    def test_calculate_sharpe_ratio_zero_volatility(self):
        """Test Sharpe ratio with zero volatility."""
        returns = np.zeros(100)

        sharpe = AutomatedRiskTester._calculate_sharpe_ratio(returns)

        assert sharpe == 0.0


class TestScenarioGenerators:
    """Test scenario generation functions."""

    def test_generate_market_stress_scenarios(self):
        """Test market stress scenario generation."""
        scenarios = generate_market_stress_scenarios(num_days=100, seed=42)

        assert len(scenarios) > 0
        assert all(isinstance(s, RiskScenario) for s in scenarios)
        assert any(s.scenario_type == ScenarioType.NORMAL_MARKET for s in scenarios)
        assert any(s.scenario_type == ScenarioType.VOLATILE_MARKET for s in scenarios)
        assert any(s.scenario_type == ScenarioType.TRENDING_MARKET for s in scenarios)
        assert all(len(s.returns) == 100 for s in scenarios)

    def test_generate_liquidity_crisis_scenarios(self):
        """Test liquidity crisis scenario generation."""
        scenarios = generate_liquidity_crisis_scenarios(num_days=100, seed=42)

        assert len(scenarios) > 0
        assert all(isinstance(s, RiskScenario) for s in scenarios)
        assert all(s.scenario_type == ScenarioType.LIQUIDITY_CRISIS for s in scenarios)
        assert all(len(s.returns) == 100 for s in scenarios)

    def test_generate_flash_crash_scenarios(self):
        """Test flash crash scenario generation."""
        scenarios = generate_flash_crash_scenarios(
            num_days=100, crash_magnitude=0.15, seed=42
        )

        assert len(scenarios) > 0
        assert all(isinstance(s, RiskScenario) for s in scenarios)
        assert all(s.scenario_type == ScenarioType.FLASH_CRASH for s in scenarios)
        assert all(len(s.returns) == 100 for s in scenarios)

        # Check that crashes are present
        for scenario in scenarios:
            # Should have at least one large negative return
            assert np.min(scenario.returns) < -0.05


class TestValidateRiskMetrics:
    """Test risk metrics validation function."""

    def test_validate_risk_metrics_normal_returns(self):
        """Test risk metrics validation with normal returns."""
        np.random.seed(42)
        returns = np.random.normal(0.0005, 0.01, 252)

        result = validate_risk_metrics(returns, alpha=0.975, es_limit=0.03)

        assert "metrics" in result
        assert "validations" in result
        assert "all_valid" in result
        assert "risk_breach" in result

        metrics = result["metrics"]
        assert metrics["var"] >= 0
        assert metrics["es"] >= 0
        assert metrics["es"] >= metrics["var"]
        assert 0 <= metrics["kelly_emergent"] <= 1.0
        assert metrics["kelly_kill"] == 0.0

        # Check validations
        validations = result["validations"]
        assert validations["var_positive"]
        assert validations["es_positive"]
        assert validations["es_gte_var"]
        assert validations["kelly_in_range"]
        assert validations["kelly_kill_zero"]

    def test_validate_risk_metrics_high_risk_returns(self):
        """Test risk metrics validation with high-risk returns."""
        np.random.seed(42)
        # Create returns with high volatility and negative drift
        returns = np.random.normal(-0.01, 0.05, 252)

        result = validate_risk_metrics(returns, alpha=0.975, es_limit=0.03)

        # With high volatility and negative drift, ES should be high
        assert result["metrics"]["es"] > 0
        # Risk breach might be triggered
        assert result["risk_breach"] in ["OK", "BREACH"]

    def test_validate_risk_metrics_kelly_fractions(self):
        """Test Kelly fraction validation across regimes."""
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.01, 252)

        result = validate_risk_metrics(returns, alpha=0.975, es_limit=0.03)

        metrics = result["metrics"]
        kelly_emergent = metrics["kelly_emergent"]
        kelly_caution = metrics["kelly_caution"]
        kelly_kill = metrics["kelly_kill"]

        # CAUTION should be about half of EMERGENT
        assert abs(kelly_caution - kelly_emergent / 2) < 0.1

        # KILL should be zero
        assert kelly_kill == 0.0

        # All should be non-negative
        assert kelly_emergent >= 0
        assert kelly_caution >= 0

    def test_validate_risk_metrics_empty_returns(self):
        """Test risk metrics validation with empty returns."""
        returns = np.array([])

        result = validate_risk_metrics(returns, alpha=0.975, es_limit=0.03)

        # Should handle empty array gracefully
        assert result["metrics"]["var"] == 0.0
        assert result["metrics"]["es"] == 0.0
        assert result["metrics"]["mu"] == 0.0
        assert result["metrics"]["sigma"] == 0.0
        assert result["metrics"]["sharpe"] == 0.0
        assert result["risk_breach"] == "OK"
        assert result["all_valid"] is True

    def test_validate_risk_metrics_filters_non_finite_values(self):
        """Non-finite values should be ignored when computing metrics."""

        returns = np.array([0.01, np.nan, np.inf, -0.02])

        result = validate_risk_metrics(returns, alpha=0.975, es_limit=0.03)
        metrics = result["metrics"]

        assert np.isfinite(metrics["var"]) and metrics["var"] >= 0
        assert np.isfinite(metrics["es"]) and metrics["es"] >= metrics["var"]
        assert np.isfinite(metrics["mu"]) and np.isfinite(metrics["sigma"])
        assert np.isfinite(metrics["kelly_emergent"])
        assert np.isfinite(metrics["kelly_caution"])
        assert np.isfinite(metrics["kelly_kill"])
        assert result["risk_breach"] in {"OK", "BREACH"}
        assert all(result["validations"].values())


class TestStressTestResultSerialization:
    """Test StressTestResult serialization."""

    def test_stress_test_result_to_dict(self):
        """Test converting stress test result to dictionary."""
        tester = AutomatedRiskTester(seed=42)
        np.random.seed(42)
        returns = np.random.normal(0, 0.01, 100)

        scenario = RiskScenario(
            name="test",
            scenario_type=ScenarioType.NORMAL_MARKET,
            returns=returns,
            description="Test",
        )

        result = tester.run_stress_test(scenario)
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "scenario_name" in result_dict
        assert "scenario_type" in result_dict
        assert "var" in result_dict
        assert "es" in result_dict
        assert "alpha" in result_dict
        assert "kelly_fraction" in result_dict
        assert "risk_breach" in result_dict
        assert "max_drawdown" in result_dict
        assert "sharpe_ratio" in result_dict
        assert "validation_errors" in result_dict
        assert "passed" in result_dict
        assert "timestamp" in result_dict
        assert "duration_seconds" in result_dict

        # Check types
        assert isinstance(result_dict["scenario_name"], str)
        assert isinstance(result_dict["scenario_type"], str)
        assert isinstance(result_dict["var"], float)
        assert isinstance(result_dict["es"], float)
        assert isinstance(result_dict["validation_errors"], list)
        assert isinstance(result_dict["passed"], bool)


class TestIntegrationScenarios:
    """Integration tests with realistic scenarios."""

    def test_full_stress_test_suite(self):
        """Test running a full stress test suite."""
        tester = AutomatedRiskTester(seed=42)

        # Add market stress scenarios
        market_scenarios = generate_market_stress_scenarios(num_days=252, seed=42)
        for scenario in market_scenarios:
            tester.add_scenario(scenario)

        # Add liquidity crisis scenarios
        crisis_scenarios = generate_liquidity_crisis_scenarios(num_days=252, seed=42)
        for scenario in crisis_scenarios:
            tester.add_scenario(scenario)

        # Add flash crash scenarios
        crash_scenarios = generate_flash_crash_scenarios(
            num_days=252, crash_magnitude=0.10, seed=42
        )
        for scenario in crash_scenarios:
            tester.add_scenario(scenario)

        # Run all scenarios
        results = tester.run_all_scenarios()

        # Verify results
        assert len(results) > 0
        assert len(results) == len(tester.scenarios)

        # Check that all scenarios were tested
        scenario_names = {r.scenario_name for r in results}
        assert len(scenario_names) == len(results)  # All unique

        # Generate summary
        summary = tester.generate_summary_report()
        assert summary["total_scenarios"] == len(results)
        assert summary["pass_rate"] >= 0.0
        assert summary["pass_rate"] <= 1.0

    def test_monte_carlo_with_validation(self):
        """Test Monte Carlo simulation with metric validation."""
        tester = AutomatedRiskTester(seed=42)

        config = MonteCarloConfig(
            num_simulations=50,
            num_periods=252,
            mu=0.0005,
            sigma=0.015,
            alpha=0.975,
            seed=42,
        )

        results = tester.run_monte_carlo_simulation(config)

        # All simulations should complete
        assert len(results) == 50

        # Check statistical properties
        vars = [r.var for r in results]
        ess = [r.es for r in results]

        # Mean VaR and ES should be in reasonable range
        mean_var = np.mean(vars)
        mean_es = np.mean(ess)

        assert 0 < mean_var < 0.1  # Reasonable for 97.5% confidence
        assert 0 < mean_es < 0.15
        assert mean_es > mean_var  # ES should be greater than VaR on average

        # Generate summary
        summary = tester.generate_summary_report()
        assert summary["metrics"]["var"]["mean"] > 0
        assert summary["metrics"]["es"]["mean"] > 0
