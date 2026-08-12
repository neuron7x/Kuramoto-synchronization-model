#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""One-command runner for the deterministic descriptor scenario harness.

Runs the descriptor capsule across the six seeded scenarios (nominal, noisy,
boundary, degenerate, invalid, null_baseline) and prints a deterministic JSON
report: per-scenario manifest digest, invalid-state count, normalized entropy,
JS divergence vs null, and percentile. Identical seeds reproduce the report
byte-for-byte. Descriptor-only; no trading or predictive semantics.

Run::

    python scripts/run_descriptor_scenarios.py            # base seed 42
    python scripts/run_descriptor_scenarios.py --seed 7
"""

from __future__ import annotations

import argparse
import json

from analytics.signals.descriptor_scenarios import run_all_scenarios


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42, help="base seed (default 42)")
    args = parser.parse_args(argv)
    report = run_all_scenarios(seed=args.seed)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
