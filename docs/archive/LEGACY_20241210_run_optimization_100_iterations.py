#!/usr/bin/env python
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Run Neuro-Optimization with 100 Iterations.

This script performs necessary optimizations with 100 iterations as requested.
It runs the adaptive calibrator and cross-neuromodulator optimizer to tune
the neuroscience-grounded AI trading system.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

# Configuration constants
N_ITERATIONS = 100
OPTIMIZATION_FREQUENCY = 10  # Run optimization every N iterations
POSITION_SIZE = 0.1  # Position size as fraction of capital
TRADING_DAYS_PER_YEAR = 252
NUMERICAL_EPSILON = 1e-6

# Add src to path - import modules directly to avoid package dependencies
src_path = Path(__file__).parent / "src"
neuro_path = src_path / "geosync" / "core" / "neuro"
sys.path.insert(0, str(neuro_path))

# Import optimization modules directly without package dependencies
from adaptive_calibrator import (
    AdaptiveCalibrator,
    CalibrationMetrics,
)
from neuro_optimizer import (
    NeuroOptimizer,
    OptimizationConfig,
)


class MarketSimulator:
    """Simple market simulator for optimization demonstration."""

    def __init__(self, volatility: float = 0.02, trend: float = 0.0001):
        self.volatility = volatility
        self.trend = trend
        self.price = 100.0
        self.step_count = 0

    def step(self):
        """Simulate one market step."""
        returns = np.random.normal(self.trend, self.volatility)
        self.price *= 1 + returns

        # Simulate volatility regime changes
        if self.step_count % 100 == 0:
            self.volatility = np.random.uniform(0.01, 0.04)

        self.step_count += 1

        return {
            "price": self.price,
            "returns": returns,
            "volatility": self.volatility,
            "volume": np.random.uniform(1000, 5000),
        }


class TradingSimulator:
    """Simulated trading system with neuromodulator control."""

    def __init__(self, params):
        self.params = params
        self.capital = 100000.0
        self.position = 0.0
        self.trades = []
        self.pnl_history = []

    def execute_trade(self, market_data, neuro_state):
        """Execute trade based on neuromodulator state."""
        dopamine = neuro_state.get("dopamine_level", 0.5)
        serotonin = neuro_state.get("serotonin_level", 0.3)
        gaba = neuro_state.get("gaba_inhibition", 0.4)

        # Decision logic
        if dopamine > 0.6 and gaba < 0.5 and serotonin < 0.4:
            action = "buy" if self.position <= 0 else "hold"
        elif serotonin > 0.5 or gaba > 0.6:
            action = "sell" if self.position > 0 else "hold"
        else:
            action = "hold"

        # Execute trade
        price = market_data["price"]
        if action == "buy" and self.position == 0:
            self.position = self.capital * POSITION_SIZE / price
            self.trades.append(
                {
                    "action": "buy",
                    "price": price,
                    "quantity": self.position,
                }
            )
        elif action == "sell" and self.position > 0:
            pnl = self.position * price - (self.capital * POSITION_SIZE)
            self.pnl_history.append(pnl)
            self.capital += pnl
            self.trades.append(
                {
                    "action": "sell",
                    "price": price,
                    "quantity": self.position,
                    "pnl": pnl,
                }
            )
            self.position = 0

        return {
            "action": action,
            "capital": self.capital,
            "position": self.position,
        }

    def get_performance_metrics(self):
        """Calculate performance metrics."""
        if not self.pnl_history:
            return CalibrationMetrics(
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                win_rate=0.5,
                avg_hold_time=10.0,
                dopamine_stability=0.3,
                serotonin_stress=0.3,
                gaba_inhibition_rate=0.4,
                na_ach_arousal=1.0,
                total_trades=0,
                timestamp=time.time(),
            )

        returns = np.array(self.pnl_history) / self.capital
        sharpe = (
            np.mean(returns)
            / (np.std(returns) + NUMERICAL_EPSILON)
            * np.sqrt(TRADING_DAYS_PER_YEAR)
        )

        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = running_max - cumulative
        max_dd = np.max(drawdown) if len(drawdown) > 0 else 0.0

        wins = sum(1 for pnl in self.pnl_history if pnl > 0)
        win_rate = wins / len(self.pnl_history) if self.pnl_history else 0.5

        return CalibrationMetrics(
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            avg_hold_time=50.0 / len(self.trades) if self.trades else 10.0,
            dopamine_stability=0.3,
            serotonin_stress=0.3,
            gaba_inhibition_rate=0.4,
            na_ach_arousal=1.0,
            total_trades=len(self.trades),
            timestamp=time.time(),
        )


def simulate_neuromodulator_state(params, market_data, iteration):
    """Simulate neuromodulator state based on parameters and market."""
    da_params = params.get("dopamine", {})
    sero_params = params.get("serotonin", {})
    gaba_params = params.get("gaba", {})
    na_ach_params = params.get("na_ach", {})

    volatility_factor = market_data["volatility"] / 0.02

    dopamine_level = 0.5 * (1 + 0.2 * np.random.randn()) * da_params.get("burst_factor", 1.5) / 2.0
    dopamine_level = np.clip(dopamine_level, 0.1, 1.0)

    stress_base = sero_params.get("stress_threshold", 0.15)
    serotonin_level = stress_base * (1 + volatility_factor * 0.5)
    serotonin_level = np.clip(serotonin_level, 0.0, 0.8)

    gaba_base = gaba_params.get("k_inhibit", 0.4)
    gaba_inhibition = gaba_base * (1 + 0.1 * np.sin(iteration / 10))
    gaba_inhibition = np.clip(gaba_inhibition, 0.0, 0.9)

    arousal_gain = na_ach_params.get("arousal_gain", 1.2)
    na_arousal = 1.0 + arousal_gain * volatility_factor * 0.2
    na_arousal = np.clip(na_arousal, 0.5, 2.0)

    ach_attention = 0.7 + 0.2 * np.random.randn()
    ach_attention = np.clip(ach_attention, 0.3, 1.0)

    return {
        "dopamine_level": dopamine_level,
        "serotonin_level": serotonin_level,
        "gaba_inhibition": gaba_inhibition,
        "na_arousal": na_arousal,
        "ach_attention": ach_attention,
    }


def main():
    """Run 100 iterations of optimization."""
    print("\n" + "=" * 80)
    print("  Neuro-Optimization with 100 Iterations")
    print("  Виконання оптимізацій з 100 ітераціями")
    print("=" * 80 + "\n")

    # Initialize system
    print("Phase 1: Initialization")
    print("-" * 80)

    initial_params = {
        "dopamine": {
            "discount_gamma": 0.99,
            "learning_rate": 0.01,
            "burst_factor": 1.5,
            "base_temperature": 1.0,
            "invigoration_threshold": 0.6,
        },
        "serotonin": {
            "stress_threshold": 0.15,
            "release_threshold": 0.10,
            "desensitization_rate": 0.01,
            "floor_min": 0.2,
        },
        "gaba": {
            "k_inhibit": 0.4,
            "impulse_threshold": 0.5,
            "stdp_lr": 0.01,
            "max_inhibition": 0.85,
        },
        "na_ach": {
            "arousal_gain": 1.2,
            "attention_gain": 1.0,
            "risk_min": 0.5,
            "risk_max": 1.5,
        },
    }

    print("✓ Initial parameters configured")

    calibrator = AdaptiveCalibrator(
        initial_params,
        temperature_initial=1.0,
        temperature_decay=0.98,
        patience=20,
    )
    print("✓ Adaptive Calibrator initialized")

    opt_config = OptimizationConfig(
        balance_weight=0.35,
        performance_weight=0.45,
        stability_weight=0.20,
        learning_rate=0.01,
        enable_plasticity=True,
    )

    optimizer = NeuroOptimizer(opt_config)
    print("✓ Cross-Neuromodulator Optimizer initialized")

    market = MarketSimulator(volatility=0.02, trend=0.0001)
    trader = TradingSimulator(initial_params)
    print("✓ Market and Trading simulators initialized")

    # Run optimization iterations
    print(f"\n\nPhase 2: Running {N_ITERATIONS} Optimization Iterations")
    print("-" * 80)

    current_params = initial_params.copy()

    start_time = time.time()

    for i in range(N_ITERATIONS):
        # Simulate market step
        market_data = market.step()

        # Simulate neuromodulator state
        neuro_state = simulate_neuromodulator_state(current_params, market_data, i)

        # Execute trade
        trader.execute_trade(market_data, neuro_state)

        # Run optimization at configured frequency
        if i > 0 and i % OPTIMIZATION_FREQUENCY == 0:
            # Get performance metrics
            perf_metrics = trader.get_performance_metrics()

            # Run adaptive calibration
            current_params = calibrator.step(perf_metrics)

            # Run cross-neuromodulator optimization
            performance_score = perf_metrics.composite_score()
            updated_params, balance = optimizer.optimize(
                current_params,
                neuro_state,
                performance_score,
            )

            # Apply updated parameters
            current_params = updated_params
            trader.params = current_params

            # Progress update
            print(
                f"  Iteration {i:3d}/{N_ITERATIONS}: "
                f"Sharpe={perf_metrics.sharpe_ratio:.2f}, "
                f"Balance={balance.overall_balance_score:.2f}, "
                f"Trades={perf_metrics.total_trades}"
            )

    elapsed_time = time.time() - start_time

    print(f"\n✓ Completed {N_ITERATIONS} iterations in {elapsed_time:.2f} seconds")
    print(f"  ({N_ITERATIONS / elapsed_time:.1f} iterations/second)")

    # Final report
    print("\n\nPhase 3: Final Results")
    print("-" * 80)

    cal_report = calibrator.get_calibration_report()
    opt_report = optimizer.get_optimization_report()
    best_params = calibrator.get_best_params()

    print("\nCalibration Results:")
    print(f"  Status: {cal_report.get('status', 'unknown')}")
    print(f"  Iteration: {cal_report.get('iteration', 0)}")
    print(f"  Best score: {cal_report.get('best_score', 0):.4f}")
    print(f"  Temperature: {cal_report.get('current_temperature', 0):.4f}")
    print(f"  Iterations since improvement: {cal_report.get('iterations_since_improvement', 0)}")
    print(f"  Exploration state: {cal_report.get('exploration_state', 'unknown')}")

    print("\nOptimization Results:")
    print(f"  Total iterations: {opt_report.get('total_iterations', 0)}")
    print(f"  Average balance score: {opt_report.get('avg_balance_score', 0):.4f}")
    convergence = opt_report.get("convergence", {})
    print(
        f"  Convergence status: {'Converged' if convergence.get('converged', False) else 'Not converged'}"
    )

    health = opt_report.get("health_status", {})
    print("\nSystem Health:")
    print(f"  Status: {health.get('status', 'unknown').upper()}")
    print(f"  Message: {health.get('message', 'N/A')}")

    print("\nTrading Performance:")
    print(f"  Final capital: ${trader.capital:,.2f}")
    print(f"  Total trades: {len(trader.trades)}")
    print(f"  Profit/Loss: ${trader.capital - 100000:,.2f}")

    print("\nRecommendations:")
    for rec in cal_report.get("recommendations", []):
        print(f"  • {rec}")

    # Save results
    results = {
        "task": f"Neuro-optimization with {N_ITERATIONS} iterations",
        "completed_iterations": N_ITERATIONS,
        "elapsed_time_seconds": elapsed_time,
        "iterations_per_second": N_ITERATIONS / elapsed_time,
        "calibration_report": cal_report,
        "optimization_report": opt_report,
        "best_parameters": best_params,
        "final_capital": trader.capital,
        "total_trades": len(trader.trades),
        "profit_loss": trader.capital - 100000,
    }

    output_path = Path(__file__).parent / "optimization_results_100_iterations.json"
    with open(output_path, "w") as f:

        def convert(obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj

        json.dump(results, f, indent=2, default=convert)

    print(f"\n\n✓ Results saved to: {output_path}")

    print("\n" + "=" * 80)
    print("  Optimization Complete!")
    print(f"  {N_ITERATIONS} iterations successfully executed")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
