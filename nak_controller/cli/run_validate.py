"""CLI entry point for running NaK validation sweeps."""
from __future__ import annotations

import argparse
import json
from typing import List

from ..integration.hook import DEFAULT_CONFIG
from ..validate.cv_runner import CVConfig, run_cross_validation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run NaK validation sweep")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to NaK YAML config")
    parser.add_argument("--steps", type=int, default=200, help="Steps per seed")
    parser.add_argument("--seeds", type=int, default=2, help="Number of RNG seeds")
    parser.add_argument("--seed-offset", type=int, default=0, help="Offset for seed sequence")
    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    seeds = [args.seed_offset + i for i in range(args.seeds)]
    cv_cfg = CVConfig(
        config_path=args.config,
        seeds=seeds,
        steps=args.steps,
    )
    summary = run_cross_validation(cv_cfg)
    payload = {
        "baseline": {
            "mean_risk": summary["baseline_mean_risk"],
            "cvar": summary["baseline_cvar"],
        },
        "nak": {
            "mean_risk": summary["nak_mean_risk"],
            "cvar": summary["nak_cvar"],
            "health_mean": summary["nak_health_mean"],
            "samples": summary["samples"],
        },
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
