"""
Grid search optimization for Gumbel-Softmax temperature parameter.

Tunes τ (temperature) in range [1.0, 100.0] to optimize:
- Action diversity
- Reward modulation
- PWPE stability

Tests on both synthetic and real data.
"""

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd
import torch

from neuropro.hpc_active_inference_v4 import HPCActiveInferenceModuleV4
from neuropro.hpc_validation import (
    generate_synthetic_data,
)


@dataclass
class ExplorationResult:
    """Results for a specific temperature setting."""

    temperature: float
    action_diversity: float
    mean_pwpe: float
    std_pwpe: float
    sharpe_proxy: float
    hold_pct: float
    buy_pct: float
    sell_pct: float
    mean_reward: float
    std_reward: float


def test_temperature_setting(
    temperature: float,
    data: pd.DataFrame,
    model: HPCActiveInferenceModuleV4,
    n_steps: int = 20,
) -> ExplorationResult:
    """
    Test a specific Gumbel-Softmax temperature setting.

    Args:
        temperature: Temperature parameter τ
        data: Market data
        model: HPC-AI model
        n_steps: Number of decision steps to test

    Returns:
        ExplorationResult with metrics
    """
    # Override temperature
    original_temp = model.gumbel_temp
    model.gumbel_temp = temperature

    actions = []
    pwpes = []
    rewards = []
    prev_pwpe = 0.0

    expert_metrics = torch.tensor([1.0, 0.1, 0.2])

    for i in range(n_steps):
        window = (
            data.iloc[i * 20 : (i + 1) * 20 + 80]
            if len(data) >= (i + 1) * 20 + 80
            else data.iloc[-100:]
        )

        # Get action
        action = model.decide_action(window, prev_pwpe)
        actions.append(action)

        # Get PWPE
        pwpe = model.get_pwpe(window)
        pwpes.append(pwpe)

        # Compute reward
        state = model.afferent_synthesis(window)
        _, pwpe_tensor = model.hpc_forward(state)
        reward = model.compute_self_reward(expert_metrics, pwpe_tensor.item())
        rewards.append(reward)

        prev_pwpe = pwpe

    # Restore original temperature
    model.gumbel_temp = original_temp

    # Compute metrics
    action_counts = {0: actions.count(0), 1: actions.count(1), 2: actions.count(2)}
    total_actions = len(actions)
    diversity = len(set(actions)) / 3.0

    return ExplorationResult(
        temperature=temperature,
        action_diversity=diversity,
        mean_pwpe=float(np.mean(pwpes)),
        std_pwpe=float(np.std(pwpes)),
        sharpe_proxy=1.0 / (np.std(pwpes) + 1e-6),
        hold_pct=action_counts[0] / total_actions,
        buy_pct=action_counts[1] / total_actions,
        sell_pct=action_counts[2] / total_actions,
        mean_reward=float(np.mean(rewards)),
        std_reward=float(np.std(rewards)),
    )


def grid_search_temperature(
    temp_grid: List[float],
    data_synthetic: pd.DataFrame,
    data_real: pd.DataFrame = None,
) -> Dict[str, List[ExplorationResult]]:
    """
    Grid search over temperature values.

    Args:
        temp_grid: List of temperature values to test
        data_synthetic: Synthetic market data
        data_real: Optional real market data

    Returns:
        Dictionary with results for synthetic and real data
    """
    results = {
        "synthetic": [],
        "real": [] if data_real is not None else None,
    }

    print("=" * 80)
    print("Gumbel-Softmax Temperature Grid Search")
    print("=" * 80)
    print(f"Testing {len(temp_grid)} temperature values: {temp_grid}")
    print()

    # Test on synthetic data
    print("Testing on Synthetic Data")
    print("-" * 80)

    for temp in temp_grid:
        # Create fresh model for each temperature
        model = HPCActiveInferenceModuleV4(
            input_dim=10,
            state_dim=64,
            action_dim=3,
            hidden_dim=128,
            hpc_levels=3,
        )

        result = test_temperature_setting(temp, data_synthetic, model, n_steps=20)
        results["synthetic"].append(result)

        print(
            f"τ={temp:6.1f}: diversity={result.action_diversity:.2%}, "
            f"PWPE={result.mean_pwpe:7.2f}±{result.std_pwpe:5.2f}, "
            f"Sharpe={result.sharpe_proxy:6.2f}, "
            f"actions=[H:{result.hold_pct:.1%} B:{result.buy_pct:.1%} S:{result.sell_pct:.1%}]"
        )

    # Test on real data if provided
    if data_real is not None:
        print()
        print("Testing on Real Data")
        print("-" * 80)

        for temp in temp_grid:
            model = HPCActiveInferenceModuleV4(
                input_dim=10,
                state_dim=64,
                action_dim=3,
                hidden_dim=128,
                hpc_levels=3,
            )

            result = test_temperature_setting(temp, data_real, model, n_steps=15)
            results["real"].append(result)

            print(
                f"τ={temp:6.1f}: diversity={result.action_diversity:.2%}, "
                f"PWPE={result.mean_pwpe:7.2f}±{result.std_pwpe:5.2f}, "
                f"Sharpe={result.sharpe_proxy:6.2f}, "
                f"actions=[H:{result.hold_pct:.1%} B:{result.buy_pct:.1%} S:{result.sell_pct:.1%}]"
            )

    return results


def analyze_results(results: Dict[str, List[ExplorationResult]]):
    """
    Analyze grid search results and recommend optimal temperature.

    Args:
        results: Dictionary with results from grid search
    """
    print()
    print("=" * 80)
    print("Analysis and Recommendations")
    print("=" * 80)

    # Analyze synthetic results
    synthetic_results = results["synthetic"]

    # Find optimal by different criteria
    best_diversity = max(synthetic_results, key=lambda r: r.action_diversity)
    best_sharpe = max(synthetic_results, key=lambda r: r.sharpe_proxy)
    best_stability = min(synthetic_results, key=lambda r: r.std_pwpe)

    print("\nSynthetic Data:")
    print(
        f"  Best Diversity: τ={best_diversity.temperature:.1f} "
        f"(diversity={best_diversity.action_diversity:.2%})"
    )
    print(
        f"  Best Sharpe: τ={best_sharpe.temperature:.1f} "
        f"(Sharpe={best_sharpe.sharpe_proxy:.2f})"
    )
    print(
        f"  Best Stability: τ={best_stability.temperature:.1f} "
        f"(PWPE std={best_stability.std_pwpe:.2f})"
    )

    # Analyze real results if available
    if results["real"] is not None:
        real_results = results["real"]

        best_diversity_real = max(real_results, key=lambda r: r.action_diversity)
        best_sharpe_real = max(real_results, key=lambda r: r.sharpe_proxy)
        best_stability_real = min(real_results, key=lambda r: r.std_pwpe)

        print("\nReal Data:")
        print(
            f"  Best Diversity: τ={best_diversity_real.temperature:.1f} "
            f"(diversity={best_diversity_real.action_diversity:.2%})"
        )
        print(
            f"  Best Sharpe: τ={best_sharpe_real.temperature:.1f} "
            f"(Sharpe={best_sharpe_real.sharpe_proxy:.2f})"
        )
        print(
            f"  Best Stability: τ={best_stability_real.temperature:.1f} "
            f"(PWPE std={best_stability_real.std_pwpe:.2f})"
        )

    # Overall recommendation
    print("\nRecommendation:")
    # Balance diversity and stability
    synthetic_scores = []
    for r in synthetic_results:
        # Score: balance diversity, sharpe, and stability
        score = (
            r.action_diversity * 0.3  # Favor exploration
            + (r.sharpe_proxy / 10.0) * 0.3  # Normalize sharpe
            + (1.0 / (r.std_pwpe + 1)) * 0.4  # Favor stability
        )
        synthetic_scores.append((r.temperature, score))

    best_overall = max(synthetic_scores, key=lambda x: x[1])
    print(f"  Optimal τ={best_overall[0]:.1f} (balanced score={best_overall[1]:.4f})")
    print(f"  Use τ={best_overall[0]:.1f} for exploration (high uncertainty)")
    print("  Use τ=100.0 for exploitation (low uncertainty)")


def run_exploration_optimization():
    """Run complete exploration optimization."""
    # Temperature grid: logarithmic spacing from 1.0 to 100.0
    temp_grid = [1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0]

    # Generate synthetic data
    print("Generating synthetic data...")
    data_synthetic = generate_synthetic_data(n_days=500, volatility=1.0, seed=42)

    # Try to load real data if available
    data_real = None
    try:
        # Attempt to load real data from examples
        import os

        real_data_path = "/home/runner/work/TradePulse/TradePulse/aapl_2020_2025.csv"
        if os.path.exists(real_data_path):
            data_real = pd.read_csv(real_data_path, index_col=0, parse_dates=True)
            print(f"Loaded real data: {len(data_real)} samples")
    except Exception:
        print("Real data not available, using synthetic only")

    # Run grid search
    results = grid_search_temperature(temp_grid, data_synthetic, data_real)

    # Analyze and recommend
    analyze_results(results)

    print("\n" + "=" * 80)
    print("Grid Search Complete")
    print("=" * 80)

    return results


if __name__ == "__main__":
    results = run_exploration_optimization()
