# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Integration test for the hero backtest scenario.

This test ensures that the hero scenario produces consistent, reproducible results
by comparing against a golden snapshot of metrics. The test validates the entire
pipeline: data preparation -> strategy signal generation -> backtest execution.

The test uses tolerance-based assertions to account for acceptable floating-point
variations while catching any significant changes in behavior.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add repo root to path for module imports
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))


def prepare_hero_data(source_path, output_path, symbol="BTC"):
    """Import and call prepare_hero_data from the example script."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "prepare_data",
        repo_root / "examples" / "hero_scenario" / "01_prepare_data.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.prepare_hero_data(source_path, output_path, symbol)


def run_hero_backtest(data_path, results_dir, initial_capital=100_000.0):
    """Import and call run_hero_backtest from the example script."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "run_backtest",
        repo_root / "examples" / "hero_scenario" / "02_run_backtest.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_hero_backtest(data_path, results_dir, initial_capital)


@pytest.fixture
def golden_metrics():
    """Load golden snapshot metrics."""
    golden_path = repo_root / "tests" / "golden" / "hero_scenario_metrics.json"
    with open(golden_path, "r") as f:
        return json.load(f)


@pytest.fixture
def temp_data_path(tmp_path):
    """Temporary path for test data."""
    return tmp_path / "btc_1h.csv"


@pytest.fixture
def temp_results_dir(tmp_path):
    """Temporary directory for test results."""
    return tmp_path / "results"


def test_hero_scenario_data_preparation(temp_data_path):
    """Test that data preparation produces valid, consistent output."""
    source_path = repo_root / "data" / "sample_crypto_ohlcv.csv"

    # Prepare data
    df = prepare_hero_data(source_path, temp_data_path, "BTC")

    # Validate output
    assert len(df) == 168, "Expected 168 bars of BTC 1h data"
    assert df.index[0].strftime("%Y-%m-%d") == "2024-01-01"
    assert df.index[-1].strftime("%Y-%m-%d") == "2024-01-07"
    assert all(col in df.columns for col in ["open", "high", "low", "close", "volume"])
    assert (df["high"] >= df["low"]).all(), "High should be >= Low"
    assert (df["high"] >= df["open"]).all() and (df["high"] >= df["close"]).all()
    assert (df["low"] <= df["open"]).all() and (df["low"] <= df["close"]).all()


def test_hero_scenario_backtest(temp_data_path, temp_results_dir, golden_metrics):
    """Test that the hero scenario backtest produces consistent results."""
    # Prepare data first
    source_path = repo_root / "data" / "sample_crypto_ohlcv.csv"
    prepare_hero_data(source_path, temp_data_path, "BTC")

    # Run backtest
    metrics = run_hero_backtest(
        temp_data_path,
        temp_results_dir,
        initial_capital=100_000.0,
    )

    # Define tolerance levels based on the type of metric
    # Financial metrics: 1e-6 relative tolerance (very strict)
    # Ratio metrics: 1e-4 relative tolerance (allows for minor numerical differences)
    # Integer counts: exact match

    def assert_close(actual, expected, rel_tol=1e-6, abs_tol=1e-9, metric_name=""):
        """Assert values are close within tolerance."""
        if expected == 0:
            assert abs(actual) < abs_tol, (
                f"{metric_name}: Expected {expected}, got {actual} "
                f"(abs difference: {abs(actual)})"
            )
        else:
            rel_diff = abs((actual - expected) / expected)
            assert rel_diff < rel_tol, (
                f"{metric_name}: Expected {expected}, got {actual} "
                f"(relative difference: {rel_diff:.2e}, tolerance: {rel_tol:.2e})"
            )

    # Test exact matches for integer counts
    assert metrics["num_trades"] == golden_metrics["num_trades"], (
        f"Number of trades mismatch: expected {golden_metrics['num_trades']}, "
        f"got {metrics['num_trades']}"
    )
    assert metrics["num_bars"] == golden_metrics["num_bars"]

    # Test financial metrics with strict tolerance
    assert_close(
        metrics["initial_capital"],
        golden_metrics["initial_capital"],
        rel_tol=1e-12,
        metric_name="initial_capital",
    )
    assert_close(
        metrics["final_equity"],
        golden_metrics["final_equity"],
        rel_tol=1e-6,
        metric_name="final_equity",
    )
    assert_close(
        metrics["total_pnl"],
        golden_metrics["total_pnl"],
        rel_tol=1e-6,
        metric_name="total_pnl",
    )
    assert_close(
        metrics["total_return_pct"],
        golden_metrics["total_return_pct"],
        rel_tol=1e-6,
        metric_name="total_return_pct",
    )

    # Test ratio metrics with moderate tolerance
    # (these can have more numerical variation due to compounding calculations)
    if metrics["sharpe_ratio"] is not None and golden_metrics["sharpe_ratio"] is not None:
        assert_close(
            metrics["sharpe_ratio"],
            golden_metrics["sharpe_ratio"],
            rel_tol=1e-4,
            metric_name="sharpe_ratio",
        )

    if metrics["max_drawdown"] is not None and golden_metrics["max_drawdown"] is not None:
        assert_close(
            metrics["max_drawdown"],
            golden_metrics["max_drawdown"],
            rel_tol=1e-4,
            metric_name="max_drawdown",
        )

    if metrics["cagr"] is not None and golden_metrics["cagr"] is not None:
        assert_close(
            metrics["cagr"],
            golden_metrics["cagr"],
            rel_tol=1e-4,
            metric_name="cagr",
        )

    if metrics["hit_ratio"] is not None and golden_metrics["hit_ratio"] is not None:
        assert_close(
            metrics["hit_ratio"],
            golden_metrics["hit_ratio"],
            rel_tol=1e-4,
            metric_name="hit_ratio",
        )

    # Test metadata matches
    assert metrics["strategy"] == golden_metrics["strategy"]
    assert metrics["instrument"] == golden_metrics["instrument"]
    assert metrics["timeframe"] == golden_metrics["timeframe"]
    assert metrics["start_date"] == golden_metrics["start_date"]
    assert metrics["end_date"] == golden_metrics["end_date"]


def test_hero_scenario_output_files(temp_data_path, temp_results_dir):
    """Test that all expected output files are created."""
    # Prepare data
    source_path = repo_root / "data" / "sample_crypto_ohlcv.csv"
    prepare_hero_data(source_path, temp_data_path, "BTC")

    # Run backtest
    run_hero_backtest(temp_data_path, temp_results_dir, initial_capital=100_000.0)

    # Check that expected files exist
    assert (temp_results_dir / "metrics.json").exists()
    assert (temp_results_dir / "equity_curve.csv").exists()
    assert (temp_results_dir / "trades_summary.json").exists()

    # Validate metrics.json structure
    with open(temp_results_dir / "metrics.json", "r") as f:
        metrics = json.load(f)
    required_keys = [
        "initial_capital",
        "final_equity",
        "total_pnl",
        "total_return_pct",
        "num_trades",
        "sharpe_ratio",
        "max_drawdown",
        "num_bars",
        "strategy",
        "instrument",
        "timeframe",
    ]
    for key in required_keys:
        assert key in metrics, f"Missing required key in metrics: {key}"


def test_hero_scenario_performance():
    """Test that the hero scenario completes in reasonable time."""
    import time

    source_path = repo_root / "data" / "sample_crypto_ohlcv.csv"

    # Use in-memory paths for speed
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)
        data_path = temp_path / "btc_1h.csv"
        results_dir = temp_path / "results"

        start_time = time.time()

        # Prepare data
        prepare_hero_data(source_path, data_path, "BTC")

        # Run backtest
        run_hero_backtest(data_path, results_dir, initial_capital=100_000.0)

        elapsed = time.time() - start_time

        # Should complete in less than 3 minutes (180 seconds)
        # In practice, should be much faster (< 10 seconds)
        assert elapsed < 180, f"Hero scenario took {elapsed:.2f}s (should be < 180s)"


@pytest.mark.parametrize("initial_capital", [10_000.0, 100_000.0, 1_000_000.0])
def test_hero_scenario_scaling(temp_data_path, temp_results_dir, initial_capital):
    """Test that the hero scenario works with different initial capital levels."""
    # Prepare data
    source_path = repo_root / "data" / "sample_crypto_ohlcv.csv"
    prepare_hero_data(source_path, temp_data_path, "BTC")

    # Run backtest
    metrics = run_hero_backtest(temp_data_path, temp_results_dir, initial_capital)

    # Basic validation
    assert metrics["initial_capital"] == initial_capital
    assert metrics["num_trades"] >= 0
    assert metrics["final_equity"] > 0

    # Return percentage should be consistent regardless of capital
    # (though absolute P&L scales with capital)
    expected_return_pct = 0.801696700  # From golden snapshot
    assert abs(metrics["total_return_pct"] - expected_return_pct) < 1e-4


if __name__ == "__main__":
    # Allow running this test file directly
    pytest.main([__file__, "-v"])
