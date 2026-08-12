#!/usr/bin/env python
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CLI script to generate multi-exchange replay performance reports.

This script processes replay recordings and generates comprehensive performance
reports with charts and regression analysis.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
ROOT = Path(__file__).resolve().parents[2]
SAFE_PATH_RE = re.compile(r"[A-Za-z0-9_./-]+")

from tests.performance.multi_exchange_replay import (
    PerformanceBudget,
    check_regression,
    compute_performance_metrics,
    discover_recordings,
    load_replay_recording,
)
from tests.performance.performance_artifacts import (
    PerformanceArtifactGenerator,
    PerformanceReport,
    PerformanceRun,
)


def get_git_info() -> dict[str, str]:
    """Get current git information."""
    import logging
    import subprocess

    logger = logging.getLogger("geosync.scripts.generate_replay_report")

    try:
        commit = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except FileNotFoundError:
        logger.debug("git command not found - unable to retrieve commit hash")
        commit = "unknown"
    except subprocess.CalledProcessError as exc:
        logger.debug(
            "git rev-parse HEAD failed with exit code %d - may not be a git repository",
            exc.returncode,
        )
        commit = "unknown"
    except Exception as exc:
        logger.warning(
            "Unexpected error retrieving git commit hash: %s",
            exc,
            exc_info=True,
        )
        commit = "unknown"

    try:
        branch = (
            subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except FileNotFoundError:
        logger.debug("git command not found - unable to retrieve branch name")
        branch = "unknown"
    except subprocess.CalledProcessError as exc:
        logger.debug(
            "git rev-parse --abbrev-ref HEAD failed with exit code %d",
            exc.returncode,
        )
        branch = "unknown"
    except Exception as exc:
        logger.warning(
            "Unexpected error retrieving git branch name: %s",
            exc,
            exc_info=True,
        )
        branch = "unknown"

    return {"commit": commit, "branch": branch}


def _validate_repo_dir(value: str, *, must_exist: bool) -> Path:
    if not SAFE_PATH_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "Paths may only contain letters, numbers, and ./_- characters."
        )
    path = Path(value).expanduser().resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Path must be inside repository root ({ROOT}).") from exc
    if must_exist and not path.exists():
        raise argparse.ArgumentTypeError(f"Directory does not exist: {path}")
    if path.exists() and not path.is_dir():
        raise argparse.ArgumentTypeError(f"Expected directory path, got: {path}")
    return path


def _validate_recordings_dir(value: str) -> Path:
    return _validate_repo_dir(value, must_exist=True)


def _validate_output_dir(value: str) -> Path:
    return _validate_repo_dir(value, must_exist=False)


def _validate_non_negative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected a number, got {value!r}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("Value must be zero or positive.")
    return parsed


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate multi-exchange replay performance reports"
    )
    parser.add_argument(
        "--recordings-dir",
        type=_validate_recordings_dir,
        default=Path("tests/fixtures/recordings"),
        help="Directory containing replay recordings",
    )
    parser.add_argument(
        "--output-dir",
        type=_validate_output_dir,
        default=Path(".ci_artifacts/multi-exchange-replay"),
        help="Directory to write output artifacts",
    )
    parser.add_argument(
        "--latency-median-ms",
        type=_validate_non_negative_float,
        default=60.0,
        help="Latency median budget in milliseconds",
    )
    parser.add_argument(
        "--latency-p95-ms",
        type=_validate_non_negative_float,
        default=100.0,
        help="Latency P95 budget in milliseconds",
    )
    parser.add_argument(
        "--latency-max-ms",
        type=_validate_non_negative_float,
        default=200.0,
        help="Latency max budget in milliseconds",
    )
    parser.add_argument(
        "--throughput-min-tps",
        type=_validate_non_negative_float,
        default=5.0,
        help="Minimum throughput in ticks per second",
    )
    parser.add_argument(
        "--slippage-median-bps",
        type=_validate_non_negative_float,
        default=5.0,
        help="Slippage median budget in basis points",
    )
    parser.add_argument(
        "--slippage-p95-bps",
        type=_validate_non_negative_float,
        default=15.0,
        help="Slippage P95 budget in basis points",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit with non-zero status if regressions detected",
    )
    parser.add_argument(
        "--generate-charts",
        action="store_true",
        default=True,
        help="Generate performance charts",
    )
    parser.add_argument(
        "--generate-issues",
        action="store_true",
        help="Generate GitHub issue templates for regressions",
    )

    args = parser.parse_args()

    args.recordings_dir = _validate_recordings_dir(str(args.recordings_dir))
    args.output_dir = _validate_output_dir(str(args.output_dir))
    args.latency_median_ms = _validate_non_negative_float(str(args.latency_median_ms))
    args.latency_p95_ms = _validate_non_negative_float(str(args.latency_p95_ms))
    args.latency_max_ms = _validate_non_negative_float(str(args.latency_max_ms))
    args.throughput_min_tps = _validate_non_negative_float(str(args.throughput_min_tps))
    args.slippage_median_bps = _validate_non_negative_float(str(args.slippage_median_bps))
    args.slippage_p95_bps = _validate_non_negative_float(str(args.slippage_p95_bps))

    # Ensure output directory exists
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Create performance budget
    budget = PerformanceBudget(
        latency_median_ms=args.latency_median_ms,
        latency_p95_ms=args.latency_p95_ms,
        latency_max_ms=args.latency_max_ms,
        throughput_min_tps=args.throughput_min_tps,
        slippage_median_bps=args.slippage_median_bps,
        slippage_p95_bps=args.slippage_p95_bps,
    )

    # Discover recordings
    recordings = list(discover_recordings(args.recordings_dir))

    if not recordings:
        print(f"No recordings found in {args.recordings_dir}", file=sys.stderr)
        return 1

    print(f"Found {len(recordings)} recording(s)")

    # Get git info
    git_info = get_git_info()

    # Process recordings
    report = PerformanceReport()
    failed_runs = []

    for recording_path in recordings:
        print(f"\nProcessing: {recording_path.name}")

        try:
            # Load and process recording
            ticks, metadata = load_replay_recording(recording_path)
            metrics = compute_performance_metrics(ticks)

            print(f"  Ticks: {len(ticks)}")
            print(f"  Latency median: {metrics.latency_median_ms:.2f}ms")
            print(f"  Latency P95: {metrics.latency_p95_ms:.2f}ms")
            print(f"  Throughput: {metrics.throughput_tps:.2f} tps")
            print(f"  Slippage median: {metrics.slippage_median_bps:.2f}bps")

            # Check against budget
            regression_result = check_regression(metrics, budget)

            if not regression_result.passed:
                print("  ⚠️  REGRESSION DETECTED")
                for violation in regression_result.violations:
                    print(f"    - {violation}")
                failed_runs.append(recording_path.stem)
            else:
                print("  ✅ Passed")

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
                    "python_version": sys.version.split()[0],
                    "platform": sys.platform,
                },
            )

            report.runs.append(run)

        except Exception as e:
            print(f"  ❌ Error: {e}", file=sys.stderr)
            continue

    # Generate summary
    report.summary = {
        "total_runs": len(report.runs),
        "passed": len(
            [r for r in report.runs if r.regression_result and r.regression_result.passed]
        ),
        "failed": len(failed_runs),
        "git_commit": git_info["commit"][:8],
        "git_branch": git_info["branch"],
    }

    # Generate artifacts
    print("\nGenerating artifacts...")
    generator = PerformanceArtifactGenerator(args.output_dir)

    json_path = generator.generate_json_report(report)
    print(f"  JSON report: {json_path}")

    markdown_path = generator.generate_markdown_summary(report)
    print(f"  Markdown summary: {markdown_path}")

    if args.generate_charts:
        chart_paths = generator.generate_charts(report)
        for chart_path in chart_paths:
            print(f"  Chart: {chart_path}")

    if args.generate_issues:
        for run in report.runs:
            if run.regression_result and not run.regression_result.passed:
                issue_path = generator.generate_issue_template(run)
                print(f"  Issue template: {issue_path}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Summary: {report.summary['passed']}/{report.summary['total_runs']} passed")

    if failed_runs:
        print(f"\nRegressions detected in: {', '.join(failed_runs)}")
        if args.fail_on_regression:
            return 1
    else:
        print("\n✅ All performance budgets met!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
