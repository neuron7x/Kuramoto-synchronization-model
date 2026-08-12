# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Performance report I/O utilities.

This module provides standardized functions for writing performance
metrics to JSON files with consistent structure and validation.
"""

import json
from pathlib import Path
from typing import Any, Dict


def write_perf_report(results: Dict[str, Any], path: Path) -> None:
    """Write performance results to a JSON file.

    Creates the parent directory if it doesn't exist and writes
    the results with proper formatting.

    Parameters
    ----------
    results : Dict[str, Any]
        Performance metrics dictionary
    path : Path
        Output file path (e.g., Path("reports/perf/golden_path_backtest.json"))

    Raises
    ------
    ValueError
        If results dictionary is missing required keys
    OSError
        If unable to create directory or write file
    """
    # Validate required keys
    required_keys = ["env", "latency_ms", "throughput", "config"]
    missing_keys = [key for key in required_keys if key not in results]
    if missing_keys:
        raise ValueError(f"Performance results missing required keys: {missing_keys}")

    # Validate latency_ms structure
    latency_required = ["p50", "p95", "p99", "mean"]
    latency_missing = [key for key in latency_required if key not in results.get("latency_ms", {})]
    if latency_missing:
        raise ValueError(f"Latency metrics missing required keys: {latency_missing}")

    # Validate throughput structure
    throughput_required = ["bars_per_second"]
    throughput_missing = [
        key for key in throughput_required if key not in results.get("throughput", {})
    ]
    if throughput_missing:
        raise ValueError(f"Throughput metrics missing required keys: {throughput_missing}")

    # Create parent directory if needed
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write JSON with formatting
    try:
        with open(path, "w") as f:
            json.dump(results, f, indent=2, sort_keys=False)
    except Exception as e:
        raise OSError(f"Failed to write performance report to {path}: {e}")


def read_perf_report(path: Path) -> Dict[str, Any]:
    """Read performance results from a JSON file.

    Parameters
    ----------
    path : Path
        Input file path

    Returns
    -------
    Dict[str, Any]
        Performance metrics dictionary

    Raises
    ------
    FileNotFoundError
        If the file doesn't exist
    json.JSONDecodeError
        If the file is not valid JSON
    """
    if not path.exists():
        raise FileNotFoundError(f"Performance report not found: {path}")

    with open(path, "r") as f:
        return json.load(f)


def format_summary(results: Dict[str, Any]) -> str:
    """Format performance results as a human-readable summary.

    Parameters
    ----------
    results : Dict[str, Any]
        Performance metrics dictionary

    Returns
    -------
    str
        Formatted summary string
    """
    latency = results.get("latency_ms", {})
    throughput = results.get("throughput", {})
    env = results.get("env", {})

    summary = []
    summary.append("Performance Summary")
    summary.append("=" * 60)
    summary.append("")

    # Environment
    summary.append("Environment:")
    summary.append(f"  Python: {env.get('python_version', 'unknown')}")
    summary.append(f"  OS: {env.get('os', 'unknown')} {env.get('os_release', '')}")
    summary.append(f"  Commit: {env.get('commit_hash', 'unknown')}")
    summary.append("")

    # Latency
    summary.append("Latency (ms):")
    summary.append(f"  p50: {latency.get('p50', 0):.2f}ms")
    summary.append(f"  p95: {latency.get('p95', 0):.2f}ms")
    summary.append(f"  p99: {latency.get('p99', 0):.2f}ms")
    summary.append(f"  mean: {latency.get('mean', 0):.2f}ms")
    summary.append("")

    # Throughput
    summary.append("Throughput:")
    summary.append(f"  {throughput.get('bars_per_second', 0):.0f} bars/second")
    if "iterations_per_second" in throughput:
        summary.append(f"  {throughput.get('iterations_per_second', 0):.1f} iterations/second")
    summary.append("")

    # Memory
    if "memory_peak_mb" in results:
        summary.append(f"Memory: {results['memory_peak_mb']:.1f} MB")
        summary.append("")

    return "\n".join(summary)
