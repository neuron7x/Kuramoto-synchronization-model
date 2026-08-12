# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Targeted mutation testing harness for the trading engine."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Sequence

DEFAULT_THRESHOLD = 0.9
DEFAULT_REPORT_DIR = Path("reports/mutmut/trading_engine")
DEFAULT_MUTATION_TARGETS = ("execution/paper_trading.py",)
DEFAULT_RUNNER = "python -m pytest tests/execution/test_paper_trading.py tests/smoke -q"
DEFAULT_TESTS_DIR = "tests"


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _run_command(command: Sequence[str], *, env: dict[str, str]) -> None:
    completed = subprocess.run(command, env=env, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command '{shlex.join(command)}' failed with exit code {completed.returncode}"
        )


def _mutmut_run(
    *,
    paths: Sequence[str],
    runner: str,
    tests_dir: str,
    env: dict[str, str],
) -> None:
    command: list[str] = [sys.executable, "-m", "mutmut", "run"]
    for path in paths:
        command.extend(["--paths-to-mutate", path])
    command.extend(["--tests-dir", tests_dir, "--runner", runner, "--use-coverage"])
    _run_command(command, env=env)


def _mutmut_results(*, destination: Path, env: dict[str, str]) -> None:
    with destination.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(
            [sys.executable, "-m", "mutmut", "results"],
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if completed.returncode != 0:
        raise RuntimeError("mutmut results command failed; see output for details")


def _enforce_threshold(*, threshold: float, summary_path: Path, env: dict[str, str]) -> None:
    command = [
        sys.executable,
        "-m",
        "tools.mutation.kill_rate_guard",
        "--threshold",
        str(threshold),
        "--summary",
        str(summary_path),
    ]
    _run_command(command, env=env)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="Minimum acceptable kill rate for trading engine mutants (default: 0.9).",
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        default=list(DEFAULT_MUTATION_TARGETS),
        help="Source files subject to mutation testing.",
    )
    parser.add_argument(
        "--runner",
        default=DEFAULT_RUNNER,
        help="Test runner command executed by mutmut.",
    )
    parser.add_argument(
        "--tests-dir",
        default=DEFAULT_TESTS_DIR,
        help="Root directory for the test suite.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="Directory where mutation artifacts are written.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    report_dir = args.reports_dir
    _ensure_directory(report_dir)

    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(Path.cwd()))

    _mutmut_run(paths=args.paths, runner=args.runner, tests_dir=args.tests_dir, env=env)

    summary_path = report_dir / "summary.json"
    results_path = report_dir / "results.txt"

    _enforce_threshold(threshold=args.threshold, summary_path=summary_path, env=env)
    _mutmut_results(destination=results_path, env=env)

    print(
        "Mutation analysis for trading engine completed successfully.",
        f"Threshold: {args.threshold:.2f}.",
    )
    print(f"Summary: {summary_path}")
    print(f"Results: {results_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
