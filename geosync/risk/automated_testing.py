# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Automated Risk Testing Module for GeoSync.

This module provides comprehensive automated testing capabilities for risk management,
including stress testing, scenario generation, Monte Carlo simulations, and validation
of risk metrics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Protocol, Tuple

import numpy as np
from numpy.typing import NDArray

try:
    from .risk_core import check_risk_breach, compute_final_size, kelly_shrink, var_es
except ImportError:
    # Fallback for direct module loading in tests
    try:
        from risk_core import (
            check_risk_breach,
            compute_final_size,
            kelly_shrink,
            var_es,
        )
    except ImportError:
        from pathlib import Path

        # Try to import from absolute path
        risk_core_path = Path(__file__).parent / "risk_core.py"
        if risk_core_path.exists():
            import importlib.util

            spec = importlib.util.spec_from_file_location("risk_core", risk_core_path)
            risk_core = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(risk_core)
            check_risk_breach = risk_core.check_risk_breach
            compute_final_size = risk_core.compute_final_size
            kelly_shrink = risk_core.kelly_shrink
            var_es = risk_core.var_es

__all__ = [
    "RiskScenario",
    "ScenarioType",
    "StressTestResult",
    "MonteCarloConfig",
    "AutomatedRiskTester",
    "generate_market_stress_scenarios",
    "generate_liquidity_crisis_scenarios",
    "generate_flash_crash_scenarios",
    "validate_risk_metrics",
]

logger = logging.getLogger(__name__)


class ScenarioType(Enum):
    """Types of risk testing scenarios."""

    NORMAL_MARKET = "normal_market"
    VOLATILE_MARKET = "volatile_market"
    TRENDING_MARKET = "trending_market"
    MEAN_REVERTING = "mean_reverting"
    FLASH_CRASH = "flash_crash"
    LIQUIDITY_CRISIS = "liquidity_crisis"
    BLACK_SWAN = "black_swan"
    REGIME_SHIFT = "regime_shift"


@dataclass
class RiskScenario:
    """A risk testing scenario with market conditions and expected outcomes."""

    name: str
    scenario_type: ScenarioType
    returns: NDArray[np.float64]
    description: str
    expected_var_range: Optional[Tuple[float, float]] = None
    expected_es_range: Optional[Tuple[float, float]] = None
    max_drawdown: Optional[float] = None
    metadata: dict = field(default_factory=dict)

    def validate_metrics(self, var: float, es: float, alpha: float = 0.975) -> List[str]:
        """Validate if computed metrics are within expected ranges.

        Returns:
            List of validation errors, empty if all validations pass
        """
        errors = []

        if self.expected_var_range:
            min_var, max_var = self.expected_var_range
            if not (min_var <= var <= max_var):
                errors.append(
                    f"VaR {var:.4f} outside expected range [{min_var:.4f}, {max_var:.4f}]"
                )

        if self.expected_es_range:
            min_es, max_es = self.expected_es_range
            if not (min_es <= es <= max_es):
                errors.append(f"ES {es:.4f} outside expected range [{min_es:.4f}, {max_es:.4f}]")

        # ES should always be >= VaR
        if es < var:
            errors.append(f"ES {es:.4f} is less than VaR {var:.4f}")

        return errors


@dataclass
class StressTestResult:
    """Results from a stress test execution."""

    scenario_name: str
    scenario_type: ScenarioType
    var: float
    es: float
    alpha: float
    kelly_fraction: float
    risk_breach: str
    max_drawdown: float
    sharpe_ratio: float
    validation_errors: List[str]
    passed: bool
    timestamp: datetime
    duration_seconds: float

    def to_dict(self) -> dict:
        """Convert result to dictionary for reporting."""
        return {
            "scenario_name": self.scenario_name,
            "scenario_type": self.scenario_type.value,
            "var": self.var,
            "es": self.es,
            "alpha": self.alpha,
            "kelly_fraction": self.kelly_fraction,
            "risk_breach": self.risk_breach,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "validation_errors": self.validation_errors,
            "passed": self.passed,
            "timestamp": self.timestamp.isoformat(),
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class MonteCarloConfig:
    """Configuration for Monte Carlo simulations."""

    num_simulations: int = 1000
    num_periods: int = 252
    mu: float = 0.0005  # Daily expected return
    sigma: float = 0.02  # Daily volatility
    alpha: float = 0.975
    seed: Optional[int] = None


class RiskMetricsProtocol(Protocol):
    """Protocol for risk metrics calculation."""

    def compute_var_es(self, returns: NDArray[np.float64], alpha: float) -> Tuple[float, float]:
        """Compute VaR and ES."""
        ...

    def compute_kelly_fraction(self, mu: float, sigma2: float, ews_level: str) -> float:
        """Compute Kelly fraction."""
        ...


class AutomatedRiskTester:
    """Automated risk testing framework for comprehensive risk validation."""

    def __init__(
        self,
        es_limit: float = 0.03,
        var_alpha: float = 0.975,
        f_max: float = 1.0,
        seed: Optional[int] = None,
    ):
        """Initialize automated risk tester.

        Args:
            es_limit: Maximum allowed Expected Shortfall
            var_alpha: Confidence level for VaR/ES calculations
            f_max: Maximum Kelly fraction
            seed: Random seed for reproducibility
        """
        self.es_limit = es_limit
        self.var_alpha = var_alpha
        self.f_max = f_max
        self.seed = seed
        if seed is not None:
            np.random.seed(seed)

        self.scenarios: List[RiskScenario] = []
        self.results: List[StressTestResult] = []

    def add_scenario(self, scenario: RiskScenario) -> None:
        """Add a risk scenario to the test suite."""
        self.scenarios.append(scenario)
        logger.info(f"Added scenario: {scenario.name} ({scenario.scenario_type.value})")

    def run_stress_test(self, scenario: RiskScenario) -> StressTestResult:
        """Run a single stress test scenario.

        Args:
            scenario: The risk scenario to test

        Returns:
            StressTestResult with metrics and validation status
        """
        start_time = datetime.now()

        # Calculate risk metrics
        var, es = var_es(scenario.returns, self.var_alpha)

        # Calculate Kelly fraction (using sample statistics)
        mu = float(np.mean(scenario.returns))
        sigma2 = float(np.var(scenario.returns))
        kelly_frac = kelly_shrink(mu, sigma2, "EMERGENT", self.f_max)

        # Check risk breach
        breach = check_risk_breach(es, self.es_limit)

        # Calculate additional metrics
        max_dd = self._calculate_max_drawdown(scenario.returns)
        sharpe = self._calculate_sharpe_ratio(scenario.returns)

        # Validate against expected ranges
        validation_errors = scenario.validate_metrics(var, es, self.var_alpha)

        # Check if scenario passed
        passed = len(validation_errors) == 0

        duration = (datetime.now() - start_time).total_seconds()

        result = StressTestResult(
            scenario_name=scenario.name,
            scenario_type=scenario.scenario_type,
            var=var,
            es=es,
            alpha=self.var_alpha,
            kelly_fraction=kelly_frac,
            risk_breach=breach,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            validation_errors=validation_errors,
            passed=passed,
            timestamp=datetime.now(),
            duration_seconds=duration,
        )

        self.results.append(result)
        logger.info(f"Completed stress test: {scenario.name} - {'PASSED' if passed else 'FAILED'}")

        return result

    def run_all_scenarios(self) -> List[StressTestResult]:
        """Run all configured stress test scenarios.

        Returns:
            List of all stress test results
        """
        logger.info(f"Running {len(self.scenarios)} stress test scenarios...")
        results = []

        for scenario in self.scenarios:
            result = self.run_stress_test(scenario)
            results.append(result)

        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed

        logger.info(
            f"Stress testing complete: {passed} passed, {failed} failed "
            f"out of {len(results)} total scenarios"
        )

        return results

    def run_monte_carlo_simulation(self, config: MonteCarloConfig) -> List[StressTestResult]:
        """Run Monte Carlo simulation with multiple random scenarios.

        Args:
            config: Monte Carlo configuration

        Returns:
            List of results from all simulated scenarios
        """
        logger.info(f"Running Monte Carlo simulation with {config.num_simulations} iterations...")

        if config.seed is not None:
            np.random.seed(config.seed)

        mc_results = []

        for i in range(config.num_simulations):
            # Generate random returns
            returns = np.random.normal(loc=config.mu, scale=config.sigma, size=config.num_periods)

            # Create scenario
            scenario = RiskScenario(
                name=f"monte_carlo_{i + 1}",
                scenario_type=ScenarioType.NORMAL_MARKET,
                returns=returns,
                description=f"Monte Carlo simulation iteration {i + 1}",
                metadata={
                    "simulation_id": i + 1,
                    "mu": config.mu,
                    "sigma": config.sigma,
                },
            )

            # Run test
            result = self.run_stress_test(scenario)
            mc_results.append(result)

        # Calculate aggregate statistics
        vars = [r.var for r in mc_results]
        ess = [r.es for r in mc_results]

        logger.info(
            f"Monte Carlo complete - VaR: mean={np.mean(vars):.4f}, "
            f"std={np.std(vars):.4f}, ES: mean={np.mean(ess):.4f}, "
            f"std={np.std(ess):.4f}"
        )

        return mc_results

    def generate_summary_report(self) -> dict:
        """Generate a summary report of all test results.

        Returns:
            Dictionary containing summary statistics and results
        """
        if not self.results:
            return {"status": "no_results", "message": "No test results available"}

        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        pass_rate = passed / len(self.results) if self.results else 0.0

        # Calculate aggregate metrics
        vars = [r.var for r in self.results]
        ess = [r.es for r in self.results]
        drawdowns = [r.max_drawdown for r in self.results]
        sharpes = [r.sharpe_ratio for r in self.results if not np.isnan(r.sharpe_ratio)]

        summary = {
            "total_scenarios": len(self.results),
            "passed": passed,
            "failed": failed,
            "pass_rate": pass_rate,
            "metrics": {
                "var": {
                    "mean": float(np.mean(vars)),
                    "std": float(np.std(vars)),
                    "min": float(np.min(vars)),
                    "max": float(np.max(vars)),
                },
                "es": {
                    "mean": float(np.mean(ess)),
                    "std": float(np.std(ess)),
                    "min": float(np.min(ess)),
                    "max": float(np.max(ess)),
                },
                "max_drawdown": {
                    "mean": float(np.mean(drawdowns)),
                    "std": float(np.std(drawdowns)),
                    "min": float(np.min(drawdowns)),
                    "max": float(np.max(drawdowns)),
                },
            },
            "results": [r.to_dict() for r in self.results],
        }

        if sharpes:
            summary["metrics"]["sharpe_ratio"] = {
                "mean": float(np.mean(sharpes)),
                "std": float(np.std(sharpes)),
                "min": float(np.min(sharpes)),
                "max": float(np.max(sharpes)),
            }

        return summary

    @staticmethod
    def _calculate_max_drawdown(returns: NDArray[np.float64]) -> float:
        """Calculate maximum drawdown from returns."""
        if len(returns) == 0:
            return 0.0

        cumulative = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max

        return float(np.min(drawdown))

    @staticmethod
    def _calculate_sharpe_ratio(returns: NDArray[np.float64], risk_free_rate: float = 0.0) -> float:
        """Calculate Sharpe ratio from returns."""
        if len(returns) == 0:
            return 0.0

        excess_returns = returns - risk_free_rate
        mean_excess = np.mean(excess_returns)
        std_excess = np.std(excess_returns)

        if std_excess == 0:
            return 0.0

        # Annualize (assuming daily returns)
        sharpe = (mean_excess / std_excess) * np.sqrt(252)

        return float(sharpe)


def generate_market_stress_scenarios(
    num_days: int = 252, seed: Optional[int] = None
) -> List[RiskScenario]:
    """Generate market stress test scenarios.

    Args:
        num_days: Number of trading days to simulate
        seed: Random seed for reproducibility

    Returns:
        List of market stress scenarios
    """
    if seed is not None:
        np.random.seed(seed)

    scenarios = []

    # Normal market conditions
    normal_returns = np.random.normal(0.0005, 0.01, num_days)
    scenarios.append(
        RiskScenario(
            name="normal_market",
            scenario_type=ScenarioType.NORMAL_MARKET,
            returns=normal_returns,
            description="Normal market conditions with low volatility",
            expected_var_range=(0.01, 0.025),
            expected_es_range=(0.015, 0.035),
        )
    )

    # High volatility market
    volatile_returns = np.random.normal(0.0, 0.03, num_days)
    scenarios.append(
        RiskScenario(
            name="high_volatility_market",
            scenario_type=ScenarioType.VOLATILE_MARKET,
            returns=volatile_returns,
            description="High volatility market conditions",
            expected_var_range=(0.04, 0.08),
            expected_es_range=(0.05, 0.10),
        )
    )

    # Trending bull market
    trend = np.linspace(0, 0.5, num_days)
    noise = np.random.normal(0, 0.015, num_days)
    bull_returns = np.diff(trend + noise, prepend=0)
    scenarios.append(
        RiskScenario(
            name="bull_market",
            scenario_type=ScenarioType.TRENDING_MARKET,
            returns=bull_returns,
            description="Strong upward trending market",
        )
    )

    # Trending bear market
    bear_trend = np.linspace(0, -0.4, num_days)
    bear_noise = np.random.normal(0, 0.02, num_days)
    bear_returns = np.diff(bear_trend + bear_noise, prepend=0)
    scenarios.append(
        RiskScenario(
            name="bear_market",
            scenario_type=ScenarioType.TRENDING_MARKET,
            returns=bear_returns,
            description="Strong downward trending market",
        )
    )

    # Mean-reverting market
    mean_rev_returns = np.random.normal(0, 0.01, num_days)
    for i in range(1, len(mean_rev_returns)):
        mean_rev_returns[i] -= 0.3 * mean_rev_returns[i - 1]
    scenarios.append(
        RiskScenario(
            name="mean_reverting_market",
            scenario_type=ScenarioType.MEAN_REVERTING,
            returns=mean_rev_returns,
            description="Mean-reverting market with negative autocorrelation",
        )
    )

    return scenarios


def generate_liquidity_crisis_scenarios(
    num_days: int = 252, seed: Optional[int] = None
) -> List[RiskScenario]:
    """Generate liquidity crisis scenarios with extreme conditions.

    Args:
        num_days: Number of trading days to simulate
        seed: Random seed for reproducibility

    Returns:
        List of liquidity crisis scenarios
    """
    if seed is not None:
        np.random.seed(seed)

    scenarios = []

    # Sudden liquidity crunch
    normal_phase = np.random.normal(0.0005, 0.01, num_days // 2)
    crisis_phase = np.random.normal(-0.005, 0.05, num_days // 2)
    crisis_returns = np.concatenate([normal_phase, crisis_phase])

    scenarios.append(
        RiskScenario(
            name="liquidity_crisis",
            scenario_type=ScenarioType.LIQUIDITY_CRISIS,
            returns=crisis_returns,
            description="Sudden liquidity crisis with increased volatility and negative drift",
            expected_var_range=(0.06, 0.15),
            expected_es_range=(0.08, 0.20),
        )
    )

    # Gradually deteriorating liquidity
    vol_schedule = np.linspace(0.01, 0.08, num_days)
    deteriorating_returns = np.array([np.random.normal(-0.001, vol) for vol in vol_schedule])

    scenarios.append(
        RiskScenario(
            name="gradual_liquidity_deterioration",
            scenario_type=ScenarioType.LIQUIDITY_CRISIS,
            returns=deteriorating_returns,
            description="Gradual deterioration of market liquidity",
        )
    )

    return scenarios


def generate_flash_crash_scenarios(
    num_days: int = 252, crash_magnitude: float = 0.15, seed: Optional[int] = None
) -> List[RiskScenario]:
    """Generate flash crash scenarios with sudden extreme moves.

    Args:
        num_days: Number of trading days to simulate
        crash_magnitude: Magnitude of the flash crash (as fraction)
        seed: Random seed for reproducibility

    Returns:
        List of flash crash scenarios
    """
    if seed is not None:
        np.random.seed(seed)

    scenarios = []

    # Single flash crash
    returns = np.random.normal(0.0005, 0.01, num_days)
    crash_day = num_days // 2
    returns[crash_day] = -crash_magnitude
    # Partial recovery next day
    returns[crash_day + 1] = crash_magnitude * 0.4

    scenarios.append(
        RiskScenario(
            name="single_flash_crash",
            scenario_type=ScenarioType.FLASH_CRASH,
            returns=returns,
            description=f"Single flash crash of {crash_magnitude * 100:.1f}% with partial recovery",
            expected_var_range=(0.02, 0.05),
            expected_es_range=(0.04, 0.10),
        )
    )

    # Multiple mini crashes
    returns_multi = np.random.normal(0.0005, 0.01, num_days)
    crash_days = [num_days // 4, num_days // 2, 3 * num_days // 4]
    for day in crash_days:
        returns_multi[day] = -crash_magnitude / 2
        returns_multi[day + 1] = crash_magnitude * 0.3

    scenarios.append(
        RiskScenario(
            name="multiple_flash_crashes",
            scenario_type=ScenarioType.FLASH_CRASH,
            returns=returns_multi,
            description="Multiple smaller flash crashes throughout the period",
        )
    )

    return scenarios


def validate_risk_metrics(
    returns: NDArray[np.float64],
    alpha: float = 0.975,
    es_limit: float = 0.03,
) -> dict:
    """Validate risk metrics for a given return series.

    Args:
        returns: Array of returns (non-finite values are ignored)
        alpha: Confidence level for VaR/ES
        es_limit: Maximum allowed ES

    Returns:
        Dictionary containing computed metrics and validation results
    """
    returns_array = np.asarray(returns, dtype=float)
    finite_returns = returns_array[np.isfinite(returns_array)]

    # Early exit for empty or all-invalid input to avoid NaNs and runtime warnings
    if finite_returns.size == 0:
        zero_metrics = {
            "var": 0.0,
            "es": 0.0,
            "mu": 0.0,
            "sigma": 0.0,
            "sharpe": 0.0,
            "kelly_emergent": 0.0,
            "kelly_caution": 0.0,
            "kelly_kill": 0.0,
        }

        validations = {
            "var_positive": True,
            "es_positive": True,
            "es_gte_var": True,
            "kelly_in_range": True,
            "kelly_caution_half_emergent": True,
            "kelly_kill_zero": True,
            "risk_breach_correct": True,
        }

        return {
            "metrics": zero_metrics,
            "validations": validations,
            "all_valid": True,
            "risk_breach": "OK",
        }

    # Calculate metrics
    var, es = var_es(finite_returns, alpha)

    mu = float(np.mean(finite_returns))
    sigma2 = float(np.var(finite_returns))

    # Calculate Kelly fractions for different regimes
    kelly_emergent = kelly_shrink(mu, sigma2, "EMERGENT")
    kelly_caution = kelly_shrink(mu, sigma2, "CAUTION")
    kelly_kill = kelly_shrink(mu, sigma2, "KILL")

    # Check risk breach
    breach = check_risk_breach(es, es_limit)

    # Calculate Sharpe ratio
    sharpe = (mu / np.sqrt(sigma2)) * np.sqrt(252) if sigma2 > 0 else 0.0

    # Validation checks
    validations = {
        "var_positive": var >= 0,
        "es_positive": es >= 0,
        "es_gte_var": es >= var,
        "kelly_in_range": 0 <= kelly_emergent <= 1.0,
        "kelly_caution_half_emergent": abs(kelly_caution - kelly_emergent / 2) < 0.01,
        "kelly_kill_zero": kelly_kill == 0.0,
        "risk_breach_correct": (breach == "BREACH") == (es > es_limit),
    }

    all_valid = all(validations.values())

    return {
        "metrics": {
            "var": var,
            "es": es,
            "mu": mu,
            "sigma": np.sqrt(sigma2),
            "sharpe": sharpe,
            "kelly_emergent": kelly_emergent,
            "kelly_caution": kelly_caution,
            "kelly_kill": kelly_kill,
        },
        "validations": validations,
        "all_valid": all_valid,
        "risk_breach": breach,
    }
