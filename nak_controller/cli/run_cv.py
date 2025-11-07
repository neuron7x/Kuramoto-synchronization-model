"""Cross-validation harness for the NaK controller."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..validate.cv_runner import run_validation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run NaK controller cross-validation sweep"
    )
    parser.add_argument(
        "--config", type=Path, required=True, help="Path to configuration YAML"
    )
    parser.add_argument(
        "--steps", type=int, default=150, help="Simulation steps per fold"
    )
    parser.add_argument(
        "--folds", type=int, default=5, help="Number of folds (mapped to seeds)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Base RNG seed (defaults to 0 if omitted)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    results = run_validation(
        str(args.config), steps=args.steps, seeds=args.folds, seed=args.seed
    )
    json.dump(results, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
