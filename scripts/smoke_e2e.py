#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Nightly smoke end-to-end pipeline for GeoSync."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("GEOSYNC_LIGHT_DATA_IMPORT", "1")

from core.data.dataset_contracts import contract_by_path  # noqa: E402
from core.data.fingerprint import record_run_fingerprint  # noqa: E402
from core.pipelines import SmokeE2EConfig, SmokeE2EPipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the GeoSync smoke E2E pipeline.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=ROOT / "data" / "sample.csv",
        help="Path to CSV source data.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "reports" / "smoke-e2e",
        help="Directory for smoke pipeline artifacts.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20240615,
        help="Seed used for deterministic outputs.",
    )
    parser.add_argument(
        "--fee",
        type=float,
        default=0.0005,
        help="Trading fee applied during the backtest stage.",
    )
    parser.add_argument(
        "--momentum-window",
        type=int,
        default=12,
        help="Lookback window for deterministic momentum signal construction.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    csv_path = args.csv.resolve()
    if not csv_path.exists():
        raise SystemExit(f"CSV source not found: {csv_path}")

    contract = contract_by_path(csv_path)
    if contract:
        record_run_fingerprint(contract, run_type="backtest")

    pipeline = SmokeE2EPipeline()
    config = SmokeE2EConfig(
        csv_path=csv_path,
        output_dir=args.output_dir,
        seed=args.seed,
        fee=args.fee,
        momentum_window=args.momentum_window,
    )
    run = pipeline.run(config)
    print(json.dumps(run.summary, indent=2))


if __name__ == "__main__":
    main()
