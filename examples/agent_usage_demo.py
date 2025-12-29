#!/usr/bin/env python3
"""
Demonstration of core.agent module functionality.

This example shows how to use the various components of the agent system:
- Multi-armed bandits for strategy selection
- Strategy evaluation and batch processing
- Memory system for caching successful strategies
- Orchestration for concurrent evaluation
- Scheduling for periodic execution
"""


import numpy as np
import pandas as pd

from core.utils.determinism import DEFAULT_SEED, seed_numpy

SEED = DEFAULT_SEED

# Note: This is a demonstration script showing the API usage.
# In production, ensure all dependencies are installed.


def demo_bandits():
    """Demonstrate multi-armed bandit algorithms."""
    print("=" * 60)
    print("Multi-Armed Bandits Demo")
    print("=" * 60)

    from core.agent.bandits import UCB1, EpsilonGreedy

    # Define strategy arms
    strategies = ["momentum", "mean_reversion", "breakout"]

    # Epsilon-Greedy Algorithm
    print("\n1. Epsilon-Greedy Algorithm")
    print("-" * 40)
    eg_bandit = EpsilonGreedy(strategies, epsilon=0.1)

    # Simulate exploration and exploitation
    for i in range(10):
        arm = eg_bandit.select()
        # Simulate reward based on strategy
        reward = np.random.normal(0.5, 0.2)
        eg_bandit.update(arm, reward)
        print(
            f"  Round {i+1}: Selected {arm}, Reward: {reward:.3f}, "
            f"Estimate: {eg_bandit.estimate(arm):.3f}, "
            f"Pulls: {eg_bandit.pulls(arm)}"
        )

    # UCB1 Algorithm
    print("\n2. UCB1 Algorithm")
    print("-" * 40)
    ucb_bandit = UCB1(strategies)

    for i in range(10):
        arm = ucb_bandit.select()
        reward = np.random.normal(0.5, 0.2)
        ucb_bandit.update(arm, reward)
        print(
            f"  Round {i+1}: Selected {arm}, Reward: {reward:.3f}, "
            f"Estimate: {ucb_bandit.estimate(arm):.3f}, "
            f"Pulls: {ucb_bandit.pulls(arm)}"
        )


def demo_strategy_evaluation():
    """Demonstrate strategy evaluation."""
    print("\n" + "=" * 60)
    print("Strategy Evaluation Demo")
    print("=" * 60)

    from core.agent import Strategy, evaluate_strategies

    # Create synthetic market data
    dates = pd.date_range(start="2024-01-01", periods=252, freq="D")
    prices = 100 + np.cumsum(np.random.normal(0.001, 0.02, len(dates)))
    data = pd.DataFrame({"close": prices}, index=dates)

    # Define strategies with different parameters
    strategies = [
        Strategy(name="momentum_short", params={"lookback": 10, "threshold": 0.3}),
        Strategy(name="momentum_medium", params={"lookback": 20, "threshold": 0.5}),
        Strategy(name="momentum_long", params={"lookback": 50, "threshold": 0.7}),
        Strategy(name="mean_reversion", params={"lookback": 30, "threshold": 0.4}),
    ]

    print(f"\nEvaluating {len(strategies)} strategies on {len(data)} days of data...")

    # Evaluate strategies
    results = evaluate_strategies(
        strategies,
        data,
        max_workers=2,
        chunk_size=4,
    )

    # Display results
    print("\nResults:")
    print("-" * 60)
    for result in results:
        status = "✓" if result.succeeded else "✗"
        score = f"{result.score:.4f}" if result.score is not None else "N/A"
        print(
            f"  {status} {result.strategy.name:20s} Score: {score:>8s} "
            f"Time: {result.duration:.3f}s"
        )


def demo_strategy_memory():
    """Demonstrate strategy memory system."""
    print("\n" + "=" * 60)
    print("Strategy Memory Demo")
    print("=" * 60)

    from core.agent.memory import StrategyMemory, StrategySignature

    # Initialize memory
    memory = StrategyMemory(max_records=10, decay_lambda=1e-6)

    # Simulate storing strategies with market signatures
    strategies_data = [
        ("momentum_bull", (0.95, 0.05, 0.3, 2.1, 0.1), 0.85),
        ("mean_reversion", (0.80, 0.10, 0.4, 1.8, 0.15), 0.75),
        ("breakout", (0.70, -0.05, 0.2, 2.3, 0.20), 0.65),
        ("momentum_bear", (0.90, -0.10, -0.1, 1.5, 0.25), 0.90),
        ("trend_following", (0.85, 0.08, 0.35, 2.0, 0.12), 0.80),
    ]

    print("\nStoring strategies with market signatures:")
    print("-" * 60)
    for name, sig_tuple, score in strategies_data:
        sig = StrategySignature(*sig_tuple)
        memory.add(name, sig, score)
        print(
            f"  Added: {name:20s} Score: {score:.2f} "
            f"R={sig.R:.2f} ΔH={sig.delta_H:.2f}"
        )

    # Retrieve top performers
    print("\nTop 3 strategies:")
    print("-" * 60)
    top_strategies = memory.topk(k=3)
    for i, record in enumerate(top_strategies, 1):
        print(
            f"  #{i} {record.name:20s} Score: {record.score:.2f} "
            f"R={record.signature.R:.2f}"
        )


def demo_orchestration():
    """Demonstrate strategy orchestration."""
    print("\n" + "=" * 60)
    print("Strategy Orchestration Demo")
    print("=" * 60)

    from core.agent import Strategy, StrategyFlow, StrategyOrchestrator

    # Create synthetic data for different instruments
    data_spy = pd.DataFrame({"close": 100 + np.cumsum(np.random.normal(0, 1, 100))})
    data_qqq = pd.DataFrame({"close": 200 + np.cumsum(np.random.normal(0, 1.5, 100))})

    # Create strategy batches
    spy_strategies = [
        Strategy(name=f"spy_strat_{i}", params={"lookback": 20 + i * 10})
        for i in range(3)
    ]

    qqq_strategies = [
        Strategy(name=f"qqq_strat_{i}", params={"lookback": 15 + i * 10})
        for i in range(3)
    ]

    # Create flows
    flows = [
        StrategyFlow(
            name="spy_evaluation",
            strategies=spy_strategies,
            dataset=data_spy,
            priority=1,
        ),
        StrategyFlow(
            name="qqq_evaluation",
            strategies=qqq_strategies,
            dataset=data_qqq,
            priority=2,
        ),
    ]

    print(f"\nOrchestrating {len(flows)} flows...")

    # Execute flows concurrently
    with StrategyOrchestrator(max_parallel=2) as orchestrator:
        results = orchestrator.run_flows(flows)

    print("\nFlow Results:")
    print("-" * 60)
    for flow_name, evaluations in results.items():
        print(f"\n  Flow: {flow_name}")
        for eval_result in evaluations:
            score = f"{eval_result.score:.4f}" if eval_result.score else "N/A"
            print(f"    - {eval_result.strategy.name}: {score}")


def demo_scheduling():
    """Demonstrate job scheduling."""
    print("\n" + "=" * 60)
    print("Job Scheduling Demo")
    print("=" * 60)

    import time

    from core.agent import Strategy, StrategyJob, StrategyScheduler

    # Create simple strategies
    strategies = [Strategy(name="test_strategy", params={"lookback": 20})]

    def data_provider():
        """Simulate fetching latest data."""
        return pd.DataFrame({"close": np.random.randn(50) + 100})

    # Create scheduler
    scheduler = StrategyScheduler(max_sleep=1.0, idle_sleep=0.5)

    # Interval-based job
    job = StrategyJob(
        name="quick_eval",
        strategies=strategies,
        data_provider=data_provider,
        interval=2.0,  # Every 2 seconds
    )

    print("\nAdding interval-based job...")
    scheduler.add_job(job, run_immediately=True)

    # Start scheduler
    print("Starting scheduler for 5 seconds...")
    scheduler.start()

    # Let it run for a bit
    time.sleep(5)

    # Stop scheduler
    scheduler.stop(timeout=2.0)

    # Get job status
    status = scheduler.get_status("quick_eval")
    print("\nJob Status:")
    print(f"  Name: {status.name}")
    print(f"  Enabled: {status.enabled}")
    print(f"  Last run: {status.last_run_at is not None}")
    print(f"  Result count: {status.result_count}")

    # Get results
    results = scheduler.get_last_results("quick_eval")
    if results:
        print(f"\nLast evaluation ran {len(results)} strategies")


def demo_pi_agent():
    """Demonstrate PiAgent with instability detection."""
    print("\n" + "=" * 60)
    print("PI Agent Demo")
    print("=" * 60)

    from core.agent import PiAgent, Strategy

    # Create strategy
    strategy = Strategy(
        name="adaptive_momentum",
        params={
            "lookback": 20,
            "threshold": 0.5,
            "instability_threshold": 0.2,
        },
    )

    # Create PI agent
    agent = PiAgent(strategy=strategy, hysteresis=0.05)

    # Simulate market states
    market_states = [
        {"R": 0.60, "delta_H": 0.05, "kappa_mean": 0.3, "transition_score": 0.1},
        {"R": 0.75, "delta_H": -0.02, "kappa_mean": 0.1, "transition_score": 0.2},
        {"R": 0.85, "delta_H": -0.10, "kappa_mean": -0.2, "transition_score": 0.4},
        {"R": 0.70, "delta_H": 0.03, "kappa_mean": 0.2, "transition_score": 0.1},
    ]

    print("\nSimulating market regime changes:")
    print("-" * 60)
    for i, state in enumerate(market_states, 1):
        is_unstable = agent.detect_instability(state)
        action = agent.evaluate_and_adapt(state)

        print(f"\n  Time {i}:")
        print(
            f"    Market: R={state['R']:.2f}, ΔH={state['delta_H']:.2f}, "
            f"κ={state['kappa_mean']:.2f}"
        )
        print(f"    Instability: {'YES ⚠️ ' if is_unstable else 'NO ✓'}")
        print(f"    Action: {action.upper()}")


def main():
    """Run all demonstrations."""
    seed_numpy(SEED)
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print("║" + "  TradePulse Core Agent Module - Usage Demonstration".center(58) + "║")
    print("║" + " " * 58 + "║")
    print("╚" + "=" * 58 + "╝")

    try:
        demo_bandits()
        demo_strategy_evaluation()
        demo_strategy_memory()
        demo_orchestration()
        demo_scheduling()
        demo_pi_agent()

        print("\n" + "=" * 60)
        print("All demonstrations completed successfully! ✓")
        print("=" * 60)
        print()

    except ImportError as e:
        print(f"\n⚠️  Import Error: {e}")
        print("Please ensure all dependencies are installed:")
        print("  pip install -r requirements.txt")
    except Exception as e:
        print(f"\n✗ Error during demonstration: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
