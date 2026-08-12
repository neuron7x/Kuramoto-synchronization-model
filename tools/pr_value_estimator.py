# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Objective PR value estimation using transparent engineering-cost models.

Outputs scenarios across hourly rate / hours-per-LOC / risk multiplier so
the buyer side cannot accuse a single-point bias. The numbers are
engineering replacement-cost estimates only — not market cap, not revenue.

Usage:
    python tools/pr_value_estimator.py
    -> reports/pr_value_estimate.json
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Scenario:
    name: str
    hourly_rate_usd: float
    dev_hours_per_100_loc: float
    qa_multiplier: float
    risk_multiplier: float


def changed_loc(base_ref: str = "HEAD~1") -> int:
    """Return total added+deleted LOC vs ``base_ref`` (best-effort)."""
    out = subprocess.check_output(
        ["git", "diff", "--numstat", f"{base_ref}..HEAD"], text=True
    ).strip()
    total = 0
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        a, d, _ = parts
        if a.isdigit():
            total += int(a)
        if d.isdigit():
            total += int(d)
    return total


def estimate(loc: int, sc: Scenario) -> dict[str, Any]:
    """Compute one scenario row."""
    dev_hours = (loc / 100.0) * sc.dev_hours_per_100_loc
    qa_hours = dev_hours * sc.qa_multiplier
    gross_hours = (dev_hours + qa_hours) * sc.risk_multiplier
    value = gross_hours * sc.hourly_rate_usd
    return {
        "scenario": sc.name,
        "loc_touched": float(loc),
        "estimated_hours": round(gross_hours, 2),
        "hourly_rate_usd": sc.hourly_rate_usd,
        "estimated_value_usd": round(value, 2),
    }


if __name__ == "__main__":
    loc = changed_loc()
    scenarios = [
        Scenario("lean_individual", 35.0, 1.4, 0.25, 1.05),
        Scenario("professional_ua_remote", 60.0, 1.7, 0.35, 1.10),
        Scenario("senior_global_consulting", 120.0, 2.0, 0.45, 1.20),
    ]
    result: dict[str, Any] = {
        "method": "LOC-effort transparent model",
        "base_ref": "HEAD~1",
        "scenarios": [estimate(loc, s) for s in scenarios],
    }
    path = Path("reports/pr_value_estimate.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
