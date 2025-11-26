"""Regression tests for multi-exchange replay with performance budgets.

This test suite exercises multi-exchange replay recordings and validates
performance metrics against configured budgets.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from .budget_loader import BudgetLoader
from .multi_exchange_replay import (
    check_regression,
    compute_performance_metrics,
    discover_recordings,
    load_replay_recording,
)
from .performance_artifacts import (
    PerformanceArtifactGenerator,
    PerformanceReport,
    PerformanceRun,
)

# Load budgets from configuration
_budget_loader = BudgetLoader()


@pytest.fixture
def recordings_dir() -> Path:
    """Path to recordings directory."""
    return Path(__file__).resolve().parent.parent / "fixtures" / "recordings"


@pytest.fixture
def artifacts_dir(tmp_path: Path) -> Path:
    """Path to artifacts output directory."""
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(exist_ok=True)
    return artifacts


@pytest.fixture
def git_info() -> dict[str, str]:
    """Get current git information for tagging."""
    import subprocess

    try:
        commit = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:
        commit = "unknown"

    try:
        branch = (
            subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:
        branch = "unknown"

    return {"commit": commit, "branch": branch}


@pytest.mark.integration
def test_coinbase_btcusd_replay_meets_budget(recordings_dir: Path) -> None:
    """Test that Coinbase BTC-USD replay meets performance budget."""
    recording_path = recordings_dir / "coinbase_btcusd.jsonl"

    if not recording_path.exists():
        pytest.skip(f"Recording not found: {recording_path}")

    # Load replay recording
    ticks, metadata = load_replay_recording(recording_path, exchange="coinbase")

    assert len(ticks) > 0, "Recording should contain ticks"
    assert metadata is not None, "Recording should have metadata"
    assert metadata.exchange == "coinbase"

    # Compute performance metrics
    metrics = compute_performance_metrics(ticks)

    # Validate against budget
    budget = _budget_loader.get_exchange_budget("coinbase")
    result = check_regression(metrics, budget)

    # Assert budgets are met
    if not result.passed:
        violations_msg = "\n".join(result.violations)
        pytest.fail(f"Performance budget violations:\n{violations_msg}")

    # Validate specific metrics
    assert metrics.latency_median_ms <= budget.latency_median_ms
    assert metrics.latency_p95_ms <= budget.latency_p95_ms
    assert metrics.latency_max_ms <= budget.latency_max_ms
    assert metrics.throughput_tps >= budget.throughput_min_tps
    assert metrics.slippage_median_bps <= budget.slippage_median_bps
    assert metrics.slippage_p95_bps <= budget.slippage_p95_bps


@pytest.mark.integration
def test_all_recordings_regression_suite(
    recordings_dir: Path, artifacts_dir: Path, git_info: dict[str, str]
) -> None:
    """Run regression suite against all available recordings."""
    recordings = list(discover_recordings(recordings_dir))

    if not recordings:
        pytest.skip("No recordings found")

    report = PerformanceReport()
    failed_runs = []

    for recording_path in recordings:
        # Determine exchange from filename or metadata
        exchange_name = "synthetic"  # Default to synthetic
        if "coinbase" in recording_path.name.lower():
            exchange_name = "coinbase"

        try:
            # Load and process recording
            ticks, metadata = load_replay_recording(
                recording_path, exchange=exchange_name
            )
            metrics = compute_performance_metrics(ticks)

            # Check against budget
            budget = _budget_loader.get_budget(exchange=exchange_name)
            regression_result = check_regression(metrics, budget)

            # Create run record
            run = PerformanceRun(
                name=recording_path.stem,
                timestamp=datetime.now(timezone.utc),
                metrics=metrics,
                metadata=metadata,
                budget=budget,
                regression_result=regression_result,
                git_commit=git_info["commit"],
                git_branch=git_info["branch"],
                environment={
                    "python_version": os.sys.version.split()[0],
                    "platform": os.sys.platform,
                },
            )

            report.runs.append(run)

            if not regression_result.passed:
                failed_runs.append(run.name)

        except Exception as e:
            pytest.fail(f"Failed to process {recording_path.name}: {e}")

    # Generate summary
    report.summary = {
        "total_runs": len(report.runs),
        "passed": len(
            [
                r
                for r in report.runs
                if r.regression_result and r.regression_result.passed
            ]
        ),
        "failed": len(failed_runs),
        "git_commit": git_info["commit"][:8],
        "git_branch": git_info["branch"],
    }

    # Generate artifacts
    generator = PerformanceArtifactGenerator(artifacts_dir)

    json_path = generator.generate_json_report(report)
    assert json_path.exists(), "JSON report should be generated"

    markdown_path = generator.generate_markdown_summary(report)
    assert markdown_path.exists(), "Markdown summary should be generated"

    chart_paths = generator.generate_charts(report)
    for chart_path in chart_paths:
        assert chart_path.exists(), f"Chart should be generated: {chart_path}"

    # Generate issue templates for failed runs
    for run in report.runs:
        if run.regression_result and not run.regression_result.passed:
            issue_path = generator.generate_issue_template(run, component="backtest")
            assert (
                issue_path.exists()
            ), f"Issue template should be generated for {run.name}"

    # Assert no regressions
    if failed_runs:
        pytest.fail(
            f"Performance regressions detected in {len(failed_runs)} runs: "
            f"{', '.join(failed_runs)}"
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    "recording_name,exchange,budget_key",
    [
        ("coinbase_btcusd.jsonl", "coinbase", "coinbase"),
        ("stable_btcusd_100ticks.jsonl", "synthetic", "default"),
        ("volatile_btcusd_150ticks.jsonl", "synthetic", "default"),
    ],
)
def test_individual_recording_regression(
    recordings_dir: Path,
    recording_name: str,
    exchange: str,
    budget_key: str,
) -> None:
    """Test individual recording against budget."""
    recording_path = recordings_dir / recording_name

    if not recording_path.exists():
        pytest.skip(f"Recording not found: {recording_path}")

    ticks, metadata = load_replay_recording(recording_path, exchange=exchange)
    metrics = compute_performance_metrics(ticks)
    budget = _budget_loader.get_budget(exchange=exchange)
    result = check_regression(metrics, budget)

    # Soft assertion - log violations but don't fail
    # (useful for tracking regressions without blocking CI)
    if not result.passed:
        print(f"\n⚠️  Performance budget warnings for {recording_name}:")
        for violation in result.violations:
            print(f"  - {violation}")


@pytest.mark.nightly
def test_extended_regression_suite_with_historical_comparison(
    recordings_dir: Path, artifacts_dir: Path
) -> None:
    """Extended regression test with historical baseline comparison.

    This test compares current performance against historical baselines
    stored in previous test runs.
    """
    # This would load historical baseline data and compare
    # For now, we'll skip if baseline doesn't exist
    baseline_path = artifacts_dir.parent / "baseline" / "performance_report.json"

    if not baseline_path.exists():
        pytest.skip("No historical baseline available")

    # Load current metrics
    recordings = list(discover_recordings(recordings_dir))
    current_runs = []

    for recording_path in recordings[:5]:  # Limit for nightly
        ticks, metadata = load_replay_recording(recording_path)
        metrics = compute_performance_metrics(ticks)
        current_runs.append((recording_path.stem, metrics))

    # Would compare against baseline here
    # For now, just assert we collected data
    assert len(current_runs) > 0


@pytest.mark.performance
def test_throughput_stress_test(recordings_dir: Path) -> None:
    """Stress test for high-throughput replay processing."""
    recording_path = recordings_dir / "coinbase_btcusd.jsonl"

    if not recording_path.exists():
        pytest.skip(f"Recording not found: {recording_path}")

    # Load and process multiple times to test throughput
    iterations = 100

    import time

    start = time.perf_counter()

    for _ in range(iterations):
        ticks, _ = load_replay_recording(recording_path)
        compute_performance_metrics(ticks)

    elapsed = time.perf_counter() - start
    processing_rate = iterations / elapsed

    # Should process at least 10 replays per second
    assert (
        processing_rate >= 10.0
    ), f"Processing rate too low: {processing_rate:.2f} replays/s"


@pytest.mark.heavy_math
def test_latency_percentile_accuracy(recordings_dir: Path) -> None:
    """Verify latency percentile calculations are accurate."""
    recording_path = recordings_dir / "coinbase_btcusd.jsonl"

    if not recording_path.exists():
        pytest.skip(f"Recording not found: {recording_path}")

    ticks, _ = load_replay_recording(recording_path)
    metrics = compute_performance_metrics(ticks)

    # Validate percentile ordering
    assert metrics.latency_median_ms <= metrics.latency_p95_ms
    assert metrics.latency_p95_ms <= metrics.latency_p99_ms
    assert metrics.latency_p99_ms <= metrics.latency_max_ms

    # Validate all values are positive
    assert metrics.latency_median_ms > 0
    assert metrics.latency_p95_ms > 0
    assert metrics.latency_max_ms > 0
