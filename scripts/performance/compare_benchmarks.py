# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Compare benchmark results against a baseline and fail on regressions.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def _load(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def compare_benchmarks(
    baseline_file: str, current_file: str, threshold: float
) -> list[dict[str, Any]]:
    baseline = _load(baseline_file)
    current = _load(current_file)

    regressions: list[dict[str, Any]] = []

    current_benchmarks = {bench["name"]: bench for bench in current.get("benchmarks", [])}
    for base in baseline.get("benchmarks", []):
        name = base.get("name")
        if name not in current_benchmarks:
            continue
        base_mean = base.get("stats", {}).get("mean")
        curr_mean = current_benchmarks[name].get("stats", {}).get("mean")
        if base_mean is None or curr_mean is None:
            continue
        if base_mean == 0:
            continue
        delta = (curr_mean - base_mean) / base_mean
        if delta > threshold:
            regressions.append(
                {
                    "name": name,
                    "baseline": base_mean,
                    "current": curr_mean,
                    "delta": delta,
                }
            )
    return regressions


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, help="Path to baseline benchmark JSON")
    parser.add_argument("--current", required=True, help="Path to current benchmark JSON")
    parser.add_argument(
        "--threshold", type=float, default=0.20, help="Allowed relative regression (0.20 = 20%)"
    )
    args = parser.parse_args(argv)

    regressions = compare_benchmarks(args.baseline, args.current, args.threshold)
    if regressions:
        print("❌ Performance regressions detected:")
        for reg in regressions:
            delta_pct = reg["delta"] * 100
            print(
                f"  {reg['name']}: +{delta_pct:.1f}% "
                f"({reg['baseline']:.6f}s → {reg['current']:.6f}s)"
            )
        return 1

    print("✅ No performance regressions detected")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
