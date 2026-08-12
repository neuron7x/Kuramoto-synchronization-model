# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CLI entry point to run the GeoSync Pro validation."""

from __future__ import annotations

import argparse
import json
import os

from ..validate.validate import run_validation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--out", type=str, default="artifacts/validate.csv")
    parser.add_argument("--metrics", type=str, default="artifacts/metrics.json")
    args = parser.parse_args()

    df, metrics = run_validation(args.steps)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    df.to_csv(args.out, index=False)
    with open(args.metrics, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print("Wrote:", args.out)
    print("Metrics:", metrics)


if __name__ == "__main__":
    main()
