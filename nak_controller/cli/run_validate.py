"""CLI entry point for running NaK validation scenarios.

Copyright (c) 2024 TradePulse Technologies. All rights reserved.
Licensed under the TradePulse Proprietary License Agreement (TPLA).
"""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from ..validate.cv_runner import run_cv


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="nak_controller/conf/nak.yaml")
    parser.add_argument("--steps", type=int, default=1600)
    parser.add_argument("--seeds", type=int, default=8)
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = run_cv(args.config, steps=args.steps, seeds=args.seeds)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
