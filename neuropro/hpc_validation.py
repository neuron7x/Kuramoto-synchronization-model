"""
Validation and Calibration utilities for HPC-AI v4.

Provides tools for:
- Grid search calibration of hyperparameters
- Synthetic data generation
- Validation metrics computation
- Backtest utilities
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch


@dataclass
class ValidationMetrics:
    """Metrics for HPC-AI validation."""

    mean_pwpe: float
    std_pwpe: float
    action_diversity: float
    mean_td_error: float
    var_td_error: float
    sharpe_proxy: float
    final_alpha: float
    final_sigma: float
    final_beta: float


def generate_synthetic_data(
    n_days: int = 1000,
    initial_price: float = 100.0,
    volatility: float = 0.5,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate synthetic OHLCV data for testing.

    Args:
        n_days: Number of days to generate
        initial_price: Starting price
        volatility: Price volatility (std of returns)
        seed: Random seed

    Returns:
        DataFrame with OHLCV data
    """
    np.random.seed(seed)

    # Generate random walk for prices
    returns = np.random.normal(0, volatility, n_days) / 100
    prices = initial_price * np.exp(np.cumsum(returns))

    # Generate OHLCV
    data = []
    for i, close in enumerate(prices):
        open_price = close * (1 + np.random.uniform(-0.01, 0.01))
        high = max(open_price, close) * (1 + np.random.uniform(0, 0.02))
        low = min(open_price, close) * (1 - np.random.uniform(0, 0.02))
        volume = np.random.uniform(1e6, 1e7)

        data.append(
            {
                "timestamp": pd.Timestamp("2020-01-01") + pd.Timedelta(days=i),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )

    df = pd.DataFrame(data)
    df.set_index("timestamp", inplace=True)
    return df


def calibrate_perturbation_scale(
    model,
    data: pd.DataFrame,
    epsilon_grid: List[float] = [0.005, 0.01, 0.02],
    n_steps: int = 10,
) -> Tuple[float, Dict[float, float]]:
    """
    Calibrate perturbation scale using grid search.

    Args:
        model: HPC-AI model instance
        data: Market data
        epsilon_grid: Grid of epsilon values to test
        n_steps: Number of validation steps

    Returns:
        Tuple of (best_epsilon, results_dict)
    """
    results = {}

    for eps in epsilon_grid:
        model.perturbation_scale.data = torch.tensor(eps)
        pwpes = []

        for i in range(n_steps):
            start_idx = max(0, len(data) - n_steps - 100 + i)
            end_idx = start_idx + 100
            batch_data = data.iloc[start_idx:end_idx]

            try:
                pwpe = model.get_pwpe(batch_data)
                pwpes.append(pwpe)
            except Exception:
                pass

        if pwpes:
            std_pwpe = np.std(pwpes)
            sharpe_proxy = 1.0 / (std_pwpe + 1e-6) * eps * 100
            results[eps] = sharpe_proxy
        else:
            results[eps] = 0.0

    # Select best epsilon
    best_epsilon = max(results, key=results.get)
    return best_epsilon, results


def validate_hpc_ai(
    model,
    data: pd.DataFrame,
    n_steps: int = 10,
) -> ValidationMetrics:
    """
    Validate HPC-AI model on synthetic data.

    Args:
        model: HPC-AI model instance
        data: Market data
        n_steps: Number of validation steps

    Returns:
        ValidationMetrics object
    """
    pwpes = []
    actions = []
    td_errors = []
    prev_pwpe = 0.0

    for i in range(n_steps):
        start_idx = max(0, len(data) - n_steps - 100 + i)
        end_idx = start_idx + 100
        batch_data = data.iloc[start_idx:end_idx]

        try:
            # Get action
            action = model.decide_action(batch_data, prev_pwpe)
            actions.append(action)

            # Get PWPE
            state = model.afferent_synthesis(batch_data)
            pred, pwpe = model.hpc_forward(state)
            pwpes.append(pwpe.item())

            # Simulate TD update
            reward = 0.1  # Mock reward
            next_state = state
            td_error = model.sr_drl_step(
                state,
                torch.tensor([action], dtype=torch.int64),
                reward,
                next_state,
                pwpe.item(),
            )
            td_errors.append(td_error)

            prev_pwpe = pwpe.item()
        except Exception:
            pass

    # Compute metrics
    mean_pwpe = np.mean(pwpes) if pwpes else 0.0
    std_pwpe = np.std(pwpes) if pwpes else 0.0
    action_diversity = len(set(actions)) / 3.0 if actions else 0.0
    mean_td_error = np.mean(td_errors) if td_errors else 0.0
    var_td_error = np.var(td_errors) if td_errors else 0.0
    sharpe_proxy = 1.0 / (std_pwpe + 1e-6) if std_pwpe > 0 else 0.0

    # Get final parameters
    final_alpha = model.blending_alpha.item()
    final_sigma = model.perturbation_scale.item()
    final_beta = model.pwpe_threshold_base.item()

    return ValidationMetrics(
        mean_pwpe=mean_pwpe,
        std_pwpe=std_pwpe,
        action_diversity=action_diversity,
        mean_td_error=mean_td_error,
        var_td_error=var_td_error,
        sharpe_proxy=sharpe_proxy,
        final_alpha=final_alpha,
        final_sigma=final_sigma,
        final_beta=final_beta,
    )


def simple_backtest(
    model,
    data: pd.DataFrame,
    initial_capital: float = 10000.0,
    position_size: float = 0.1,
) -> Dict[str, float]:
    """
    Simple backtest of HPC-AI model.

    Args:
        model: HPC-AI model instance
        data: Market data with OHLCV
        initial_capital: Starting capital
        position_size: Fraction of capital to use per trade

    Returns:
        Dictionary with backtest metrics
    """
    capital = initial_capital
    position = 0
    entry_price = 0
    trades = []
    pwpes = []
    actions = []
    prev_pwpe = 0.0

    # Sliding window backtest
    window_size = 100
    for i in range(window_size, len(data)):
        window_data = data.iloc[i - window_size : i]

        try:
            # Decide action
            action = model.decide_action(window_data, prev_pwpe)
            actions.append(action)

            # Get PWPE
            pwpe = model.get_pwpe(window_data)
            pwpes.append(pwpe)
            prev_pwpe = pwpe

            current_price = data.iloc[i]["close"]

            # Execute action
            if action == 1 and position == 0:  # Buy
                position = (capital * position_size) / current_price
                entry_price = current_price
                capital -= capital * position_size
            elif action == 2 and position > 0:  # Sell
                capital += position * current_price
                pnl = position * (current_price - entry_price)
                trades.append(pnl)
                position = 0
                entry_price = 0

        except Exception:
            pass

    # Close any open position
    if position > 0:
        final_price = data.iloc[-1]["close"]
        capital += position * final_price
        pnl = position * (final_price - entry_price)
        trades.append(pnl)

    # Compute metrics
    total_return = (capital - initial_capital) / initial_capital
    sharpe = np.mean(trades) / np.std(trades) if trades and np.std(trades) > 0 else 0.0
    max_drawdown = (
        abs(min(np.minimum.accumulate(trades))) / initial_capital if trades else 0.0
    )
    mean_pwpe = np.mean(pwpes) if pwpes else 0.0

    # Action distribution
    action_dist = {
        "hold": actions.count(0) / len(actions) if actions else 0.0,
        "buy": actions.count(1) / len(actions) if actions else 0.0,
        "sell": actions.count(2) / len(actions) if actions else 0.0,
    }

    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "n_trades": len(trades),
        "mean_pwpe": mean_pwpe,
        "final_capital": capital,
        "action_distribution": action_dist,
    }


def format_validation_report(
    metrics: ValidationMetrics,
    backtest_results: Optional[Dict] = None,
) -> str:
    """
    Format validation results as a report.

    Args:
        metrics: Validation metrics
        backtest_results: Optional backtest results

    Returns:
        Formatted report string
    """
    report = "=" * 60 + "\n"
    report += "HPC-AI v4 Validation Report\n"
    report += "=" * 60 + "\n\n"

    report += "Validation Metrics:\n"
    report += f"  Mean PWPE: {metrics.mean_pwpe:.4f}\n"
    report += f"  Std PWPE: {metrics.std_pwpe:.4f}\n"
    report += f"  Action Diversity: {metrics.action_diversity:.2%}\n"
    report += f"  Mean TD Error: {metrics.mean_td_error:.4f}\n"
    report += f"  Var TD Error: {metrics.var_td_error:.6f}\n"
    report += f"  Sharpe Proxy: {metrics.sharpe_proxy:.2f}\n\n"

    report += "Learned Parameters:\n"
    report += f"  Alpha (blending): {metrics.final_alpha:.4f}\n"
    report += f"  Sigma (perturbation): {metrics.final_sigma:.4f}\n"
    report += f"  Beta (gate threshold): {metrics.final_beta:.4f}\n"

    if backtest_results:
        report += "\n" + "=" * 60 + "\n"
        report += "Backtest Results:\n"
        report += "=" * 60 + "\n"
        report += f"  Total Return: {backtest_results['total_return']:.2%}\n"
        report += f"  Sharpe Ratio: {backtest_results['sharpe']:.4f}\n"
        report += f"  Max Drawdown: {backtest_results['max_drawdown']:.2%}\n"
        report += f"  Number of Trades: {backtest_results['n_trades']}\n"
        report += f"  Mean PWPE: {backtest_results['mean_pwpe']:.4f}\n"
        report += f"  Final Capital: ${backtest_results['final_capital']:.2f}\n\n"

        dist = backtest_results["action_distribution"]
        report += "  Action Distribution:\n"
        report += f"    Hold: {dist['hold']:.1%}\n"
        report += f"    Buy: {dist['buy']:.1%}\n"
        report += f"    Sell: {dist['sell']:.1%}\n"

    report += "\n" + "=" * 60 + "\n"
    return report


__all__ = [
    "ValidationMetrics",
    "generate_synthetic_data",
    "calibrate_perturbation_scale",
    "validate_hpc_ai",
    "simple_backtest",
    "format_validation_report",
]
