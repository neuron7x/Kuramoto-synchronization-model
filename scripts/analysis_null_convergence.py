#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Null p-value convergence study across trial counts.

Runs the Kuramoto null suite at ``n_bootstrap ∈ {500, 1000, 2000, 5000}``,
same seed, same data, same families. Emits a long-form CSV suitable for
CONVERGED / NOT_CONVERGED classification: a family is CONVERGED when
``max |p(N) - p(2N)| < 0.02``; any wider gap is NOT_CONVERGED and the
required trial count is reported verbatim.

Pure offline; no network; no interactive input. Deterministic under a
fixed ``--seed``.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Final

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from research.robustness.protocols.kuramoto_contract import (  # noqa: E402
    KuramotoRobustnessContract,
)
from research.robustness.protocols.kuramoto_null_suite import (  # noqa: E402
    run_kuramoto_null_suite,
)

OUT_PATH: Final[Path] = (
    REPO / "results" / "cross_asset_kuramoto" / "robustness_v1" / "null_convergence.csv"
)
TRIAL_COUNTS: Final[tuple[int, ...]] = (500, 1000, 2000, 5000)
CONVERGENCE_TOLERANCE: Final[float] = 0.02


def _classify_convergence(
    p_by_family: dict[str, dict[int, float]],
) -> tuple[str, float, dict[str, float]]:
    """Compute per-family convergence metric and an overall verdict.

    For each family, take the maximum absolute difference between
    adjacent (N, 2N) pairs in the sorted trial sequence. If all families
    stay under ``CONVERGENCE_TOLERANCE`` → CONVERGED; otherwise
    NOT_CONVERGED.
    """
    per_family: dict[str, float] = {}
    for family, p_map in p_by_family.items():
        trials = sorted(p_map.keys())
        pairs = [
            (trials[i], trials[i + 1])
            for i in range(len(trials) - 1)
            if trials[i + 1] == trials[i] * 2
        ]
        if not pairs:
            per_family[family] = float("inf")
            continue
        max_delta = max(abs(p_map[n] - p_map[twice_n]) for n, twice_n in pairs)
        per_family[family] = max_delta
    overall_max = max(per_family.values()) if per_family else float("inf")
    status = "CONVERGED" if overall_max < CONVERGENCE_TOLERANCE else "NOT_CONVERGED"
    return status, overall_max, per_family


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="seed for the PCG64 stream (default: 42)",
    )
    parser.add_argument(
        "--out-path",
        type=Path,
        default=OUT_PATH,
        help=f"CSV output path (default: {OUT_PATH})",
    )
    args = parser.parse_args(argv)

    contract = KuramotoRobustnessContract.from_frozen_artifacts()
    p_by_family: dict[str, dict[int, float]] = {}
    rows: list[dict[str, object]] = []
    for n in TRIAL_COUNTS:
        result = run_kuramoto_null_suite(contract, n_bootstrap=n, seed=args.seed)
        for family_result in result.families:
            rows.append(
                {
                    "n_trials": n,
                    "family_id": family_result.family,
                    "observed_sharpe": round(family_result.observed_sharpe, 8),
                    "p_value": round(family_result.p_value, 8),
                    "p_value_pass": family_result.p_value_pass,
                }
            )
            p_by_family.setdefault(family_result.family, {})[n] = family_result.p_value

    args.out_path.parent.mkdir(parents=True, exist_ok=True)
    with args.out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "n_trials",
                "family_id",
                "observed_sharpe",
                "p_value",
                "p_value_pass",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    status, overall_max, per_family = _classify_convergence(p_by_family)
    print(f"wrote {args.out_path}")
    print(f"convergence status : {status}")
    print(f"overall max |Δp|   : {overall_max:.4f}")
    for family, delta in per_family.items():
        print(f"  {family:22s}  max |Δp| = {delta:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
