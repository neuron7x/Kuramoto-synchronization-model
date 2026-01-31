"""Run a deterministic backtest regression gate for pull requests."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import argparse
import logging
from pathlib import Path

from observability.incidents import IncidentManager
from scripts.nightly import BaselineStore, NightlyRegressionRunner
from scripts.nightly.regression import create_default_backtest_scenarios
from scripts.runtime import EXIT_CODES, configure_deterministic_runtime, configure_logging
from scripts.runtime import create_artifact_manager

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-path",
        type=Path,
        default=Path("configs/nightly/baselines.json"),
        help="Path to the regression baseline configuration JSON.",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("reports/backtest-regression"),
        help="Directory for generated artifacts.",
    )
    parser.add_argument(
        "--history-path",
        type=Path,
        default=Path("reports/backtest-regression/history.jsonl"),
        help="Location of the JSONL history log.",
    )
    parser.add_argument(
        "--incident-root",
        type=Path,
        default=Path("reports/incidents"),
        help="Directory used to persist automatically created incidents.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    configure_deterministic_runtime()
    configure_logging(logging.INFO)

    baseline_store = BaselineStore(args.baseline_path)
    artifact_manager = create_artifact_manager("backtest_regression", root=args.artifact_root)
    incident_manager = IncidentManager(args.incident_root)

    runner = NightlyRegressionRunner(
        baseline_store=baseline_store,
        artifact_manager=artifact_manager,
        history_path=args.history_path,
        incident_manager=incident_manager,
        backtest_scenarios=create_default_backtest_scenarios(),
        e2e_scenarios=(),
    )
    summary = runner.run()

    if summary.deviations:
        LOGGER.error(
            "Backtest regression detected %s deviations",
            len(summary.deviations),
        )
        return EXIT_CODES["circuit_breaker_open"]

    LOGGER.info("Backtest regression completed without deviations.")
    return EXIT_CODES["success"]


if __name__ == "__main__":
    raise SystemExit(main())
