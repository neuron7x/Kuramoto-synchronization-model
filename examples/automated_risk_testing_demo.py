"""Demo script for the Automated Risk Testing Module.

This script demonstrates how to use the automated risk testing module
to validate risk management systems with various market scenarios.
"""

# Import directly from module files to avoid dependency issues
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

from core.utils.determinism import DEFAULT_SEED, seed_numpy
# Load risk_core first
risk_core_spec = importlib.util.spec_from_file_location(
    "risk_core",
    Path(__file__).parent.parent / "src/tradepulse/risk/risk_core.py",
)
risk_core_module = importlib.util.module_from_spec(risk_core_spec)
sys.modules["tradepulse.risk.risk_core"] = risk_core_module
risk_core_spec.loader.exec_module(risk_core_module)

# Load automated_testing
auto_test_spec = importlib.util.spec_from_file_location(
    "tradepulse.risk.automated_testing",
    Path(__file__).parent.parent / "src/tradepulse/risk/automated_testing.py",
)
auto_test_module = importlib.util.module_from_spec(auto_test_spec)
sys.modules["tradepulse.risk.automated_testing"] = auto_test_module
auto_test_spec.loader.exec_module(auto_test_module)

AutomatedRiskTester = auto_test_module.AutomatedRiskTester
MonteCarloConfig = auto_test_module.MonteCarloConfig
generate_flash_crash_scenarios = auto_test_module.generate_flash_crash_scenarios
generate_liquidity_crisis_scenarios = (
    auto_test_module.generate_liquidity_crisis_scenarios
)
generate_market_stress_scenarios = auto_test_module.generate_market_stress_scenarios
validate_risk_metrics = auto_test_module.validate_risk_metrics


def demo_basic_risk_validation():
    """Demonstrate basic risk metrics validation."""
    print("\n" + "=" * 80)
    print("DEMO 1: Basic Risk Metrics Validation")
    print("=" * 80)

    # Generate sample returns
    seed_numpy(DEFAULT_SEED)
    returns = np.random.normal(0.0005, 0.015, 252)

    print(f"\nGenerated {len(returns)} daily returns")
    print(f"Mean return: {np.mean(returns):.6f}")
    print(f"Volatility: {np.std(returns):.6f}")

    # Validate risk metrics
    result = validate_risk_metrics(returns, alpha=0.975, es_limit=0.03)

    print("\nComputed Risk Metrics:")
    print(f"  VaR (97.5%): {result['metrics']['var']:.6f}")
    print(f"  ES (97.5%): {result['metrics']['es']:.6f}")
    print(f"  Sharpe Ratio: {result['metrics']['sharpe']:.4f}")
    print(f"  Kelly Fraction (EMERGENT): {result['metrics']['kelly_emergent']:.4f}")
    print(f"  Kelly Fraction (CAUTION): {result['metrics']['kelly_caution']:.4f}")
    print(f"  Kelly Fraction (KILL): {result['metrics']['kelly_kill']:.4f}")

    print(f"\nRisk Breach Status: {result['risk_breach']}")
    print(f"All Validations Passed: {result['all_valid']}")

    if not result["all_valid"]:
        print("\nValidation Failures:")
        for key, passed in result["validations"].items():
            if not passed:
                print(f"  - {key}: FAILED")


def demo_market_stress_testing():
    """Demonstrate market stress testing with predefined scenarios."""
    print("\n" + "=" * 80)
    print("DEMO 2: Market Stress Testing")
    print("=" * 80)

    # Initialize tester
    tester = AutomatedRiskTester(
        es_limit=0.03, var_alpha=0.975, f_max=1.0, seed=DEFAULT_SEED
    )

    # Generate market stress scenarios
    print("\nGenerating market stress scenarios...")
    market_scenarios = generate_market_stress_scenarios(
        num_days=252, seed=DEFAULT_SEED
    )

    print(f"Generated {len(market_scenarios)} market stress scenarios:")
    for scenario in market_scenarios:
        print(f"  - {scenario.name} ({scenario.scenario_type.value})")
        tester.add_scenario(scenario)

    # Run all scenarios
    print("\nRunning stress tests...")
    results = tester.run_all_scenarios()

    # Display results
    print("\nStress Test Results:")
    print("-" * 80)
    for result in results:
        status = "✓ PASS" if result.passed else "✗ FAIL"
        print(
            f"{status} | {result.scenario_name:30} | "
            f"VaR: {result.var:.4f} | ES: {result.es:.4f} | "
            f"Breach: {result.risk_breach:6} | "
            f"Sharpe: {result.sharpe_ratio:6.2f}"
        )

    # Generate summary
    summary = tester.generate_summary_report()
    print("\nSummary:")
    print(f"  Total Scenarios: {summary['total_scenarios']}")
    print(f"  Passed: {summary['passed']}")
    print(f"  Failed: {summary['failed']}")
    print(f"  Pass Rate: {summary['pass_rate']:.1%}")


def demo_crisis_scenarios():
    """Demonstrate liquidity crisis and flash crash scenarios."""
    print("\n" + "=" * 80)
    print("DEMO 3: Crisis Scenarios Testing")
    print("=" * 80)

    # Initialize tester
    tester = AutomatedRiskTester(es_limit=0.05, seed=DEFAULT_SEED)

    # Generate crisis scenarios
    print("\nGenerating crisis scenarios...")
    crisis_scenarios = generate_liquidity_crisis_scenarios(
        num_days=252, seed=DEFAULT_SEED
    )
    flash_scenarios = generate_flash_crash_scenarios(
        num_days=252, crash_magnitude=0.15, seed=DEFAULT_SEED
    )

    all_crisis_scenarios = crisis_scenarios + flash_scenarios

    print(f"Generated {len(all_crisis_scenarios)} crisis scenarios:")
    for scenario in all_crisis_scenarios:
        print(f"  - {scenario.name} ({scenario.scenario_type.value})")
        tester.add_scenario(scenario)

    # Run scenarios
    print("\nRunning crisis scenario tests...")
    results = tester.run_all_scenarios()

    # Display detailed results
    print("\nCrisis Scenario Results:")
    print("-" * 80)
    for result in results:
        status = "✓ PASS" if result.passed else "✗ FAIL"
        print(f"\n{status} {result.scenario_name}")
        print(f"  VaR: {result.var:.6f}")
        print(f"  ES: {result.es:.6f}")
        print(f"  Max Drawdown: {result.max_drawdown:.4%}")
        print(f"  Kelly Fraction: {result.kelly_fraction:.4f}")
        print(f"  Risk Breach: {result.risk_breach}")

        if result.validation_errors:
            print("  Validation Errors:")
            for error in result.validation_errors:
                print(f"    - {error}")


def demo_monte_carlo_simulation():
    """Demonstrate Monte Carlo simulation."""
    print("\n" + "=" * 80)
    print("DEMO 4: Monte Carlo Risk Simulation")
    print("=" * 80)

    # Initialize tester
    tester = AutomatedRiskTester(es_limit=0.03, seed=DEFAULT_SEED)

    # Configure Monte Carlo
    config = MonteCarloConfig(
        num_simulations=100,
        num_periods=252,
        mu=0.0005,  # 0.05% daily return
        sigma=0.015,  # 1.5% daily volatility
        alpha=0.975,
        seed=DEFAULT_SEED,
    )

    print("\nMonte Carlo Configuration:")
    print(f"  Simulations: {config.num_simulations}")
    print(f"  Periods per simulation: {config.num_periods}")
    print(f"  Expected daily return: {config.mu:.4%}")
    print(f"  Daily volatility: {config.sigma:.4%}")
    print(f"  Confidence level: {config.alpha:.1%}")

    # Run simulation
    print(f"\nRunning {config.num_simulations} Monte Carlo simulations...")
    results = tester.run_monte_carlo_simulation(config)

    # Analyze results
    vars = [r.var for r in results]
    ess = [r.es for r in results]
    kellys = [r.kelly_fraction for r in results]
    breaches = sum(1 for r in results if r.risk_breach == "BREACH")

    print("\nMonte Carlo Results:")
    print("  VaR Statistics:")
    print(f"    Mean: {np.mean(vars):.6f}")
    print(f"    Std: {np.std(vars):.6f}")
    print(f"    Min: {np.min(vars):.6f}")
    print(f"    Max: {np.max(vars):.6f}")
    print(f"    Median: {np.median(vars):.6f}")

    print("\n  ES Statistics:")
    print(f"    Mean: {np.mean(ess):.6f}")
    print(f"    Std: {np.std(ess):.6f}")
    print(f"    Min: {np.min(ess):.6f}")
    print(f"    Max: {np.max(ess):.6f}")
    print(f"    Median: {np.median(ess):.6f}")

    print("\n  Kelly Fraction Statistics:")
    print(f"    Mean: {np.mean(kellys):.6f}")
    print(f"    Std: {np.std(kellys):.6f}")
    print(f"    Min: {np.min(kellys):.6f}")
    print(f"    Max: {np.max(kellys):.6f}")

    print(
        f"\n  Risk Breaches: {breaches} / {config.num_simulations} "
        f"({breaches/config.num_simulations:.1%})"
    )


def demo_comprehensive_report():
    """Demonstrate comprehensive testing with report generation."""
    print("\n" + "=" * 80)
    print("DEMO 5: Comprehensive Testing with Report")
    print("=" * 80)

    # Initialize tester
    tester = AutomatedRiskTester(es_limit=0.03, var_alpha=0.975, seed=DEFAULT_SEED)

    # Add all types of scenarios
    print("\nBuilding comprehensive test suite...")

    market_scenarios = generate_market_stress_scenarios(
        num_days=252, seed=DEFAULT_SEED
    )
    crisis_scenarios = generate_liquidity_crisis_scenarios(
        num_days=252, seed=DEFAULT_SEED
    )
    flash_scenarios = generate_flash_crash_scenarios(
        num_days=252, crash_magnitude=0.12, seed=DEFAULT_SEED
    )

    all_scenarios = market_scenarios + crisis_scenarios + flash_scenarios

    for scenario in all_scenarios:
        tester.add_scenario(scenario)

    print(f"Added {len(all_scenarios)} scenarios to test suite")

    # Run all tests
    print("\nExecuting comprehensive test suite...")
    tester.run_all_scenarios()

    # Generate and save report
    print("\nGenerating comprehensive report...")
    summary = tester.generate_summary_report()

    # Save to file
    output_file = (
        Path(__file__).parent.parent / "test_results" / "risk_test_report.json"
    )
    output_file.parent.mkdir(exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Report saved to: {output_file}")

    # Display summary
    print("\n" + "=" * 80)
    print("COMPREHENSIVE TEST SUMMARY")
    print("=" * 80)
    print(f"\nTotal Scenarios Tested: {summary['total_scenarios']}")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Pass Rate: {summary['pass_rate']:.1%}")

    print("\nAggregate Risk Metrics:")
    print(
        f"  VaR: {summary['metrics']['var']['mean']:.6f} ± "
        f"{summary['metrics']['var']['std']:.6f}"
    )
    print(
        f"  ES: {summary['metrics']['es']['mean']:.6f} ± "
        f"{summary['metrics']['es']['std']:.6f}"
    )
    print(
        f"  Max Drawdown: {summary['metrics']['max_drawdown']['mean']:.4%} ± "
        f"{summary['metrics']['max_drawdown']['std']:.4%}"
    )

    if "sharpe_ratio" in summary["metrics"]:
        print(
            f"  Sharpe Ratio: {summary['metrics']['sharpe_ratio']['mean']:.4f} ± "
            f"{summary['metrics']['sharpe_ratio']['std']:.4f}"
        )


def main():
    """Run all demos."""
    print("\n")
    print(
        "╔═══════════════════════════════════════════════════════════════════════════╗"
    )
    print(
        "║           TradePulse Automated Risk Testing Module Demo                   ║"
    )
    print(
        "╚═══════════════════════════════════════════════════════════════════════════╝"
    )

    try:
        demo_basic_risk_validation()
        demo_market_stress_testing()
        demo_crisis_scenarios()
        demo_monte_carlo_simulation()
        demo_comprehensive_report()

        print("\n" + "=" * 80)
        print("All demos completed successfully!")
        print("=" * 80 + "\n")

    except Exception as e:
        print(f"\n❌ Error during demo: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
