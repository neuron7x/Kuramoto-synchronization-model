"""CLI for running NaK cross-validation experiments."""
from __future__ import annotations

import argparse
import json
from typing import List

from ..integration.hook import DEFAULT_CONFIG
from ..validate.cv_runner import CVConfig, run_cross_validation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run NaK cross validation")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to NaK YAML config")
    parser.add_argument("--steps", type=int, default=400, help="Steps per seed")
    parser.add_argument("--seeds", type=int, default=4, help="Number of RNG seeds")
    parser.add_argument("--seed-offset", type=int, default=0, help="Offset for seed sequence")
    parser.add_argument("--base-risk", type=float, default=0.002, help="Baseline risk per trade")
    parser.add_argument("--base-position", type=float, default=1.0, help="Baseline max position")
    parser.add_argument("--base-cooldown", type=float, default=2000.0, help="Baseline cooldown in ms")
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    seeds = [args.seed_offset + i for i in range(args.seeds)]
    cv_cfg = CVConfig(
        config_path=args.config,
        seeds=seeds,
        steps=args.steps,
        base_risk_per_trade=args.base_risk,
        base_max_position=args.base_position,
        base_cooldown_ms=args.base_cooldown,
    )
    summary = run_cross_validation(cv_cfg)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
