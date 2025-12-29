"""Demonstrate ECSInspiredRegulator usage in a reproducible simulation."""

import os
from pathlib import Path

import numpy as np
import pandas as pd

from core.neuro.ecs_regulator import ECSInspiredRegulator
from core.utils.determinism import DEFAULT_SEED


def simulate_market_data(
    n_steps: int, seed: int = DEFAULT_SEED
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Simulate market returns, drawdowns, and phase data.

    Args:
        n_steps: Number of simulation steps
        seed: Random seed for reproducibility

    Returns:
        Tuple of (returns, drawdowns, phases)
    """
    rng = np.random.default_rng(seed)

    # Generate market returns with varying volatility regimes
    market_returns = []
    phases = []

    for i in range(n_steps):
        # Simulate different market regimes
        if i < n_steps // 3:
            # Stable period
            ret = rng.normal(0.001, 0.01)
            phase = "stable"
        elif i < 2 * n_steps // 3:
            # Chaotic period
            ret = rng.normal(-0.002, 0.05)
            phase = "chaotic"
        else:
            # Transition/recovery
            ret = rng.normal(0.002, 0.02)
            phase = rng.choice(["transition", "stable"])

        market_returns.append(ret)
        phases.append(phase)

    returns = np.array(market_returns)
    cum_returns = pd.Series(np.cumprod(1 + returns))
    peak_curve = cum_returns.cummax()
    drawdowns = ((peak_curve - cum_returns) / (peak_curve + 1e-10)).to_numpy()

    return returns, drawdowns, phases


def calculate_performance_metrics(returns: np.ndarray, actions: list[int]) -> dict:
    """Calculate trading performance metrics.

    Args:
        returns: Market returns
        actions: Trading actions (-1, 0, 1)

    Returns:
        Dictionary of performance metrics
    """
    # Simulate strategy returns based on actions
    strategy_returns = []
    for i, action in enumerate(actions):
        if action == 1:  # Buy
            strategy_returns.append(returns[i])
        elif action == -1:  # Sell
            strategy_returns.append(-returns[i])
        else:  # Hold
            strategy_returns.append(0.0)

    strategy_returns = np.array(strategy_returns)

    # Calculate metrics
    total_return = np.sum(strategy_returns)
    volatility = np.std(strategy_returns)
    sharpe_ratio = (np.mean(strategy_returns) / (volatility + 1e-10)) * np.sqrt(252)

    cum_strategy = np.cumprod(1 + strategy_returns)
    peak_curve = np.maximum.accumulate(cum_strategy)
    max_dd = np.max((peak_curve - cum_strategy) / (peak_curve + 1e-10))

    return {
        "total_return": float(total_return),
        "volatility": float(volatility),
        "sharpe_ratio": float(sharpe_ratio),
        "max_drawdown": float(max_dd),
        "num_buys": int(np.sum(np.array(actions) == 1)),
        "num_sells": int(np.sum(np.array(actions) == -1)),
        "num_holds": int(np.sum(np.array(actions) == 0)),
    }


def main():
    """Run ECS regulator simulation demo."""
    print("=" * 70)
    print("ECS-Inspired Regulator Demo for TradePulse")
    print("=" * 70)
    print()

    # Configuration
    n_steps = int(os.getenv("ECS_DEMO_STEPS", "200"))
    seed = DEFAULT_SEED
    output_dir = Path(os.getenv("ECS_DEMO_OUTPUT_DIR", "/tmp"))
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize regulator
    print("Initializing ECS-Inspired Regulator...")
    regulator = ECSInspiredRegulator(
        initial_risk_threshold=0.05,
        smoothing_alpha=0.9,
        stress_threshold=0.1,
        chronic_threshold=5,
        fe_scaling=1.0,
        seed=seed,
    )
    print(f"  Risk Threshold: {regulator.risk_threshold:.4f}")
    print(f"  Stress Threshold: {regulator.stress_threshold:.4f}")
    print(f"  Chronic Threshold: {regulator.chronic_threshold} periods")
    print()

    # Simulate market data
    print(f"Simulating {n_steps} steps of market data...")
    market_returns, drawdowns, phases = simulate_market_data(n_steps, seed)
    print(f"  Mean return: {np.mean(market_returns):.4f}")
    print(f"  Volatility: {np.std(market_returns):.4f}")
    print(f"  Max drawdown: {np.max(drawdowns):.4f}")
    print()

    # Run simulation
    print("Running ECS regulator simulation...")
    actions = []
    signals = []
    fe_history = []
    stress_history = []
    prev_fe = None

    rng = np.random.default_rng(seed)

    for i in range(n_steps):
        # Update stress with market conditions
        regulator.update_stress(
            market_returns[: i + 1], drawdowns[i] if i > 0 else 0.0, prev_fe
        )
        prev_fe = regulator.free_energy_proxy

        # Adapt parameters based on context
        regulator.adapt_parameters(context_phase=phases[i])

        # Generate trading signal (from hypothetical TradePulseCompositeEngine)
        signal = market_returns[i] * rng.uniform(0.8, 1.2)
        signals.append(signal)

        # Decide action
        action = regulator.decide_action(signal, context_phase=phases[i])
        actions.append(action)

        # Track metrics
        fe_history.append(regulator.free_energy_proxy)
        stress_history.append(regulator.stress_level)

    print("Simulation completed!")
    print()

    # Analyze results
    print("=" * 70)
    print("Simulation Results")
    print("=" * 70)

    # Final state
    metrics = regulator.get_metrics()
    print("\nFinal Regulator State:")
    print(f"  Stress Level: {metrics.stress_level:.4f}")
    print(f"  Free Energy Proxy: {metrics.free_energy_proxy:.4f}")
    print(f"  Risk Threshold: {metrics.risk_threshold:.4f}")
    print(f"  Compensatory Factor: {metrics.compensatory_factor:.4f}")
    print(f"  Chronic Counter: {metrics.chronic_counter}")
    print(f"  Is Chronic: {metrics.is_chronic}")

    # Action distribution
    action_counts = np.bincount(np.array(actions) + 1, minlength=3)
    print("\nAction Distribution:")
    print(f"  Sells:  {action_counts[0]:4d} ({action_counts[0]/n_steps*100:.1f}%)")
    print(f"  Holds:  {action_counts[1]:4d} ({action_counts[1]/n_steps*100:.1f}%)")
    print(f"  Buys:   {action_counts[2]:4d} ({action_counts[2]/n_steps*100:.1f}%)")

    # Performance metrics
    performance = calculate_performance_metrics(market_returns, actions)
    print("\nPerformance Metrics:")
    print(f"  Total Return: {performance['total_return']:.4f}")
    print(f"  Volatility: {performance['volatility']:.4f}")
    print(f"  Sharpe Ratio: {performance['sharpe_ratio']:.4f}")
    print(f"  Max Drawdown: {performance['max_drawdown']:.4f}")

    # Free energy analysis
    print("\nFree Energy Analysis:")
    print(f"  Initial FE: {fe_history[0]:.4f}")
    print(f"  Final FE: {fe_history[-1]:.4f}")
    print(f"  Mean FE: {np.mean(fe_history):.4f}")
    print(f"  Max FE: {np.max(fe_history):.4f}")

    # Chronic stress detection
    chronic_periods = sum(1 for s in stress_history if s > regulator.stress_threshold)
    print("\nStress Analysis:")
    print(
        f"  High Stress Periods: {chronic_periods}/{n_steps} ({chronic_periods/n_steps*100:.1f}%)"
    )
    print(f"  Mean Stress: {np.mean(stress_history):.4f}")
    print(f"  Max Stress: {np.max(stress_history):.4f}")

    # Export trace
    print("\nExporting trace data...")
    trace = regulator.get_trace()
    print(f"  Trace records: {len(trace)}")

    # Save to Parquet for TradePulse integration (with CSV fallback)
    trace_file = output_dir / "ecs_regulator_trace.parquet"
    try:
        trace.to_parquet(trace_file)
        print(f"  Saved to: {trace_file}")
    except (ImportError, ValueError):
        trace_file = trace_file.with_suffix(".csv")
        trace.to_csv(trace_file, index=False)
        print(f"  Parquet engine unavailable, saved CSV to: {trace_file}")

    # Create summary CSV
    summary_df = pd.DataFrame(
        {
            "step": range(n_steps),
            "return": market_returns,
            "drawdown": drawdowns,
            "phase": phases,
            "signal": signals,
            "action": actions,
            "stress": stress_history,
            "free_energy": fe_history,
        }
    )

    summary_file = output_dir / "ecs_regulator_summary.csv"
    summary_df.to_csv(summary_file, index=False)
    print(f"  Summary saved to: {summary_file}")

    print()
    print("=" * 70)
    print("Integration Notes:")
    print("=" * 70)
    print(
        """
The ECS-Inspired Regulator can be integrated with TradePulse components:

1. FractalMotivationController Integration:
   - Pass ECS stress_level as additional signal to FractalMotivationController
   - Use ECS compensatory_factor to modulate motivation signals
   - Combine ECS free_energy_proxy with TACL thermodynamic control

2. Kuramoto-Ricci Phase Integration:
   - Obtain context_phase from TradePulseCompositeEngine.analyze_market()
   - Pass phase to adapt_parameters() and decide_action()
   - Use phase-dependent modulation for risk management

3. Event-Driven Backtesting:
   - Integrate with EventDrivenBacktestEngine
   - Use historical Polygon data (2020-2025)
   - Monitor Sharpe ratio (target >1.2) and max drawdown (target <15%)

4. TACL Alignment:
   - Map stress_level to TACL free_energy_proxy
   - Enforce monotonic descent (ΔFE ≤ 0)
   - Use Lyapunov-like checks for stability

5. Logging and Compliance:
   - Export trace to Parquet for MiFID II compliance
   - Integrate with Hydra config system
   - Store in TradePulse feature store

Example integration code:

    from core.neuro import ECSInspiredRegulator, FractalMotivationController

    # Initialize
    ecs_reg = ECSInspiredRegulator()
    motivation = FractalMotivationController(actions=["buy", "sell", "hold"])

    # Trading loop
    ecs_reg.update_stress(returns, drawdown)
    ecs_reg.adapt_parameters(phase)
    ecs_action = ecs_reg.decide_action(signal, phase)

    # Combine with motivation system
    motivation_decision = motivation.recommend(
        state=[ecs_reg.stress_level, signal],
        signals={"risk_ok": ecs_reg.risk_threshold > 0.01}
    )
"""
    )

    print("=" * 70)
    print("Demo completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    main()
