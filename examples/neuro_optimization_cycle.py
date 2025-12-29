#!/usr/bin/env python
"""Comprehensive Neuro-Optimization Cycle Demonstration.

This example demonstrates a complete iteration and optimization cycle for
TradePulse's neuroscience-grounded AI system. It shows how adaptive calibration
and cross-neuromodulator optimization work together to achieve optimal
performance while maintaining homeostatic balance.

The demonstration includes:
1. Initial configuration of neuromodulators
2. Performance monitoring and metric collection
3. Adaptive calibration based on market conditions
4. Cross-neuromodulator balance optimization
5. Real-time reporting and visualization
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

import numpy as np
from core.utils.determinism import DEFAULT_SEED, seed_numpy

# Add src to path for standalone execution
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Deterministic simulation seed for reproducible runs.
SEED = DEFAULT_SEED

# Import optimization modules
try:
    from tradepulse.core.neuro.adaptive_calibrator import (
        AdaptiveCalibrator,
        CalibrationMetrics,
    )
    from tradepulse.core.neuro.neuro_optimizer import (
        NeuroOptimizer,
        OptimizationConfig,
    )
except ImportError as e:
    print(f"Note: Running in demo mode without full imports: {e}")
    print("This is a demonstration of the optimization cycle structure.")
    print("\nTo run with full functionality, ensure TradePulse is installed:")
    print("  pip install -e .")
    sys.exit(0)


class MarketSimulator:
    """Simple market simulator for demonstration purposes."""

    def __init__(self, volatility: float = 0.02, trend: float = 0.0001):
        """Initialize market simulator.

        Parameters
        ----------
        volatility : float
            Market volatility (standard deviation of returns)
        trend : float
            Market trend (mean return)
        """
        self.volatility = volatility
        self.trend = trend
        self.price = 100.0
        self.step_count = 0

    def step(self) -> Dict[str, float]:
        """Simulate one market step.

        Returns
        -------
        Dict[str, float]
            Market data including price, volatility, volume
        """
        # Generate price movement
        returns = np.random.normal(self.trend, self.volatility)
        self.price *= (1 + returns)

        # Simulate volatility regime changes
        if self.step_count % 100 == 0:
            self.volatility = np.random.uniform(0.01, 0.04)

        self.step_count += 1

        return {
            'price': self.price,
            'returns': returns,
            'volatility': self.volatility,
            'volume': np.random.uniform(1000, 5000),
        }


class TradingSimulator:
    """Simulated trading system with neuromodulator control."""

    def __init__(self, params: Dict[str, Any]):
        """Initialize trading simulator.

        Parameters
        ----------
        params : Dict[str, Any]
            Neuromodulator parameters
        """
        self.params = params
        self.capital = 100000.0
        self.position = 0.0
        self.trades = []
        self.pnl_history = []

    def execute_trade(
        self, market_data: Dict[str, float], neuro_state: Dict[str, float]
    ) -> Dict[str, Any]:
        """Execute trade based on neuromodulator state.

        Parameters
        ----------
        market_data : Dict[str, float]
            Current market data
        neuro_state : Dict[str, float]
            Current neuromodulator state

        Returns
        -------
        Dict[str, Any]
            Trade result and updated state
        """
        # Simple trading logic based on neuromodulator state
        dopamine = neuro_state.get('dopamine_level', 0.5)
        serotonin = neuro_state.get('serotonin_level', 0.3)
        gaba = neuro_state.get('gaba_inhibition', 0.4)

        # Decision logic
        if dopamine > 0.6 and gaba < 0.5 and serotonin < 0.4:
            # High dopamine, low inhibition, low stress -> Go signal
            action = 'buy' if self.position <= 0 else 'hold'
        elif serotonin > 0.5 or gaba > 0.6:
            # High stress or inhibition -> Hold/Close
            action = 'sell' if self.position > 0 else 'hold'
        else:
            action = 'hold'

        # Execute trade
        price = market_data['price']
        if action == 'buy' and self.position == 0:
            self.position = self.capital * 0.1 / price  # 10% position
            self.trades.append({
                'action': 'buy',
                'price': price,
                'quantity': self.position,
            })
        elif action == 'sell' and self.position > 0:
            pnl = self.position * price - (self.capital * 0.1)
            self.pnl_history.append(pnl)
            self.capital += pnl
            self.trades.append({
                'action': 'sell',
                'price': price,
                'quantity': self.position,
                'pnl': pnl,
            })
            self.position = 0

        return {
            'action': action,
            'capital': self.capital,
            'position': self.position,
        }

    def get_performance_metrics(self) -> CalibrationMetrics:
        """Calculate performance metrics.

        Returns
        -------
        CalibrationMetrics
            Performance metrics for calibration
        """
        if not self.pnl_history:
            # No trades yet, return neutral metrics
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

        # Calculate metrics
        returns = np.array(self.pnl_history) / self.capital
        sharpe = np.mean(returns) / (np.std(returns) + 1e-6) * np.sqrt(252)

        # Drawdown calculation
        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = running_max - cumulative
        max_dd = np.max(drawdown) if len(drawdown) > 0 else 0.0

        # Win rate
        wins = sum(1 for pnl in self.pnl_history if pnl > 0)
        win_rate = wins / len(self.pnl_history) if self.pnl_history else 0.5

        return CalibrationMetrics(
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            avg_hold_time=50.0 / len(self.trades) if self.trades else 10.0,
            dopamine_stability=0.3,  # Would be calculated from actual dopamine history
            serotonin_stress=0.3,
            gaba_inhibition_rate=0.4,
            na_ach_arousal=1.0,
            total_trades=len(self.trades),
            timestamp=time.time(),
        )


def simulate_neuromodulator_state(
    params: Dict[str, Any], market_data: Dict[str, float], iteration: int
) -> Dict[str, float]:
    """Simulate neuromodulator state based on parameters and market.

    Parameters
    ----------
    params : Dict[str, Any]
        Neuromodulator parameters
    market_data : Dict[str, float]
        Current market data
    iteration : int
        Current iteration number

    Returns
    -------
    Dict[str, float]
        Simulated neuromodulator state
    """
    # Extract parameters
    da_params = params.get('dopamine', {})
    sero_params = params.get('serotonin', {})
    gaba_params = params.get('gaba', {})
    na_ach_params = params.get('na_ach', {})

    # Simulate dopamine (reward prediction)
    base_da = 0.5
    volatility_factor = market_data['volatility'] / 0.02  # Normalize
    dopamine_level = base_da * (1 + 0.2 * np.random.randn()) * da_params.get('burst_factor', 1.5) / 2.0
    dopamine_level = np.clip(dopamine_level, 0.1, 1.0)

    # Simulate serotonin (stress response)
    stress_base = sero_params.get('stress_threshold', 0.15)
    serotonin_level = stress_base * (1 + volatility_factor * 0.5)
    serotonin_level = np.clip(serotonin_level, 0.0, 0.8)

    # Simulate GABA (inhibition)
    gaba_base = gaba_params.get('k_inhibit', 0.4)
    gaba_inhibition = gaba_base * (1 + 0.1 * np.sin(iteration / 10))
    gaba_inhibition = np.clip(gaba_inhibition, 0.0, 0.9)

    # Simulate NA/ACh (arousal/attention)
    arousal_gain = na_ach_params.get('arousal_gain', 1.2)
    na_arousal = 1.0 + arousal_gain * volatility_factor * 0.2
    na_arousal = np.clip(na_arousal, 0.5, 2.0)

    ach_attention = 0.7 + 0.2 * np.random.randn()
    ach_attention = np.clip(ach_attention, 0.3, 1.0)

    return {
        'dopamine_level': dopamine_level,
        'serotonin_level': serotonin_level,
        'gaba_inhibition': gaba_inhibition,
        'na_arousal': na_arousal,
        'ach_attention': ach_attention,
    }


def print_section_header(title: str) -> None:
    """Print formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def print_metrics(metrics: Dict[str, Any], indent: int = 2) -> None:
    """Print metrics dictionary with formatting."""
    indent_str = " " * indent
    for key, value in metrics.items():
        if isinstance(value, dict):
            print(f"{indent_str}{key}:")
            print_metrics(value, indent + 2)
        elif isinstance(value, list):
            print(f"{indent_str}{key}: [{len(value)} items]")
        elif isinstance(value, float):
            print(f"{indent_str}{key}: {value:.4f}")
        else:
            print(f"{indent_str}{key}: {value}")


def main():
    """Run complete optimization cycle demonstration."""
    seed_numpy(SEED)
    print("\n" + "╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "Neuro-Optimization Cycle Demonstration".center(78) + "║")
    print("║" + "Complete Iteration & Optimization for Neuroscience AI".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝")

    # -------------------------------------------------------------------------
    # Phase 1: Initialize System
    # -------------------------------------------------------------------------
    print_section_header("Phase 1: System Initialization")

    # Define initial neuromodulator parameters
    initial_params = {
        'dopamine': {
            'discount_gamma': 0.99,
            'learning_rate': 0.01,
            'burst_factor': 1.5,
            'base_temperature': 1.0,
            'invigoration_threshold': 0.6,
        },
        'serotonin': {
            'stress_threshold': 0.15,
            'release_threshold': 0.10,
            'desensitization_rate': 0.01,
            'floor_min': 0.2,
        },
        'gaba': {
            'k_inhibit': 0.4,
            'impulse_threshold': 0.5,
            'stdp_lr': 0.01,
            'max_inhibition': 0.85,
        },
        'na_ach': {
            'arousal_gain': 1.2,
            'attention_gain': 1.0,
            'risk_min': 0.5,
            'risk_max': 1.5,
        },
    }

    print("Initial Parameters:")
    print_metrics(initial_params)

    # Initialize calibrator and optimizer
    calibrator = AdaptiveCalibrator(
        initial_params,
        temperature_initial=1.0,
        temperature_decay=0.98,
        patience=20,
    )

    opt_config = OptimizationConfig(
        balance_weight=0.35,
        performance_weight=0.45,
        stability_weight=0.20,
        learning_rate=0.01,
        enable_plasticity=True,
    )

    optimizer = NeuroOptimizer(opt_config)

    print("\nCalibrator initialized:")
    print(f"  Temperature: {calibrator.state.temperature:.2f}")
    print(f"  Patience: {calibrator.patience}")

    print("\nOptimizer initialized:")
    print(f"  Balance weight: {opt_config.balance_weight:.2f}")
    print(f"  Performance weight: {opt_config.performance_weight:.2f}")
    print(f"  Learning rate: {opt_config.learning_rate:.3f}")

    # Initialize market and trading simulators
    market = MarketSimulator(volatility=0.02, trend=0.0001)
    trader = TradingSimulator(initial_params)

    print("\nMarket simulator initialized")
    print("Trading simulator initialized")

    # -------------------------------------------------------------------------
    # Phase 2: Iteration Cycle
    # -------------------------------------------------------------------------
    print_section_header("Phase 2: Optimization Iteration Cycle")

    n_iterations = 100
    current_params = initial_params.copy()

    print(f"Running {n_iterations} optimization iterations...")
    print("(Progress will be shown every 20 iterations)\n")

    for i in range(n_iterations):
        # 1. Simulate market step
        market_data = market.step()

        # 2. Simulate neuromodulator state
        neuro_state = simulate_neuromodulator_state(
            current_params, market_data, i
        )

        # 3. Execute trade
        trader.execute_trade(market_data, neuro_state)

        # 4. Every 20 steps, run optimization
        if i > 0 and i % 20 == 0:
            print(f"\n--- Iteration {i} ---")

            # Get performance metrics
            perf_metrics = trader.get_performance_metrics()

            print("Performance Metrics:")
            print(f"  Sharpe Ratio: {perf_metrics.sharpe_ratio:.2f}")
            print(f"  Max Drawdown: {perf_metrics.max_drawdown:.2%}")
            print(f"  Win Rate: {perf_metrics.win_rate:.2%}")
            print(f"  Total Trades: {perf_metrics.total_trades}")

            # Run adaptive calibration
            current_params = calibrator.step(perf_metrics)

            print("\nCalibration Update:")
            print(f"  Temperature: {calibrator.state.temperature:.3f}")
            print(f"  Best Score: {calibrator.state.best_score:.3f}")
            print(f"  Iterations since improvement: {i - calibrator.state.last_improvement}")

            # Run cross-neuromodulator optimization
            performance_score = perf_metrics.composite_score()
            updated_params, balance = optimizer.optimize(
                current_params,
                neuro_state,
                performance_score,
            )

            print("\nBalance Metrics:")
            print(f"  DA/5-HT Ratio: {balance.dopamine_serotonin_ratio:.2f}")
            print(f"  E/I Balance: {balance.gaba_excitation_balance:.2f}")
            print(f"  Balance Score: {balance.overall_balance_score:.2f}")
            print(f"  Homeostatic Deviation: {balance.homeostatic_deviation:.2f}")

            # Merge optimized parameters
            current_params = updated_params
            trader.params = current_params

    # -------------------------------------------------------------------------
    # Phase 3: Final Report
    # -------------------------------------------------------------------------
    print_section_header("Phase 3: Final Optimization Report")

    # Get calibration report
    cal_report = calibrator.get_calibration_report()
    print("Calibration Report:")
    print_metrics(cal_report)

    # Get optimization report
    opt_report = optimizer.get_optimization_report()
    print("\nOptimization Report:")
    print_metrics(opt_report)

    # Get final parameters
    best_params = calibrator.get_best_params()
    print("\n\nBest Parameters Found:")
    print_metrics(best_params)

    # Save results
    results = {
        'calibration_report': cal_report,
        'optimization_report': opt_report,
        'best_parameters': best_params,
        'final_capital': trader.capital,
        'total_trades': len(trader.trades),
    }

    output_path = Path(__file__).parent / "neuro_optimization_results.json"
    with open(output_path, 'w') as f:
        # Convert numpy types for JSON serialization
        def convert(obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj

        json.dump(results, f, indent=2, default=convert)

    print(f"\n\nResults saved to: {output_path}")

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    print_section_header("Summary")

    print("Key Achievements:")
    print(f"  ✓ Completed {n_iterations} optimization iterations")
    print(f"  ✓ Executed {len(trader.trades)} trades")
    print(f"  ✓ Final capital: ${trader.capital:,.2f}")
    print(f"  ✓ Best calibration score: {calibrator.state.best_score:.3f}")
    print(f"  ✓ Final balance score: {opt_report.get('avg_balance_score', 0):.3f}")

    print("\nNeuromodulator System Status:")
    health = opt_report.get('health_status', {})
    status = health.get('status', 'unknown')
    message = health.get('message', 'No status available')
    print(f"  Status: {status.upper()}")
    print(f"  {message}")

    if health.get('issues'):
        print("\n  Issues:")
        for issue in health['issues']:
            print(f"    • {issue}")

    print("\nRecommendations:")
    for rec in cal_report.get('recommendations', []):
        print(f"  • {rec}")

    print("\n" + "=" * 80)
    print("Optimization cycle completed successfully!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
