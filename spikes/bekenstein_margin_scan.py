#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Bekenstein saturation-ratio scan: 5 systems, daily-energy-throughput interpretation.

Per-system saturation ratio = claimed_bits / I_max(R, E). The ratio does NOT
measure cognitive efficiency — I_max depends only on (R, E) and is identical
for any object of those dimensions, regardless of whether it computes. The
ratio measures the fraction of the universal Bekenstein-Hawking ceiling that
the system's claimed information content occupies.

Fulfils PR #406 promise. Energy convention here is E = P · 86400 s (one
day of throughput), not E = m·c² (rest energy). Both are valid Bekenstein
inputs; daily-throughput is the user-specified interpretation for this scan.

Output: markdown table to stdout + JSON to spikes/bekenstein_scan_results.json
Invariant: every bekenstein_saturation_ratio must be < 1.0. Otherwise PhysicsViolation.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.physics.thermodynamic_budget import bekenstein_cognitive_ceiling  # noqa: E402

SECONDS_PER_DAY: float = 86_400.0


class PhysicsViolation(Exception):
    """Raised when a row's bekenstein_saturation_ratio >= 1.0 (INV-BEKENSTEIN-COGNITIVE)."""


@dataclass(frozen=True, slots=True)
class System:
    name: str
    radius_m: float
    power_W: float
    estimated_actual_bits: float


@dataclass(frozen=True, slots=True)
class MarginRow:
    name: str
    radius_m: float
    energy_J: float
    theoretical_max_bits: float
    estimated_actual_bits: float
    bekenstein_saturation_ratio: float
    log10_margin: float


SYSTEMS: tuple[System, ...] = (
    System(
        name="human_brain",
        radius_m=0.07,
        power_W=20.0,
        estimated_actual_bits=2.5e15,
    ),
    System(
        name="fruit_fly_brain",
        radius_m=5.0e-4,
        power_W=1.0e-5,
        estimated_actual_bits=1.0e9,
    ),
    System(
        name="c_elegans",
        radius_m=5.0e-5,
        power_W=1.0e-7,
        estimated_actual_bits=1.0e4,
    ),
    System(
        name="gpt4_estimate",
        radius_m=0.5,
        power_W=1.0e6,
        estimated_actual_bits=1.0e13,
    ),
    System(
        name="geosync_node",
        radius_m=0.1,
        power_W=50.0,
        estimated_actual_bits=1.0e12,
    ),
)


def compute_row(system: System) -> MarginRow:
    energy_J = system.power_W * SECONDS_PER_DAY
    ceiling = bekenstein_cognitive_ceiling(system.radius_m, energy_J)
    if ceiling <= 0.0:
        ratio = math.inf
    else:
        ratio = system.estimated_actual_bits / ceiling
    log10_margin = math.log10(ratio) if ratio > 0.0 else float("-inf")
    return MarginRow(
        name=system.name,
        radius_m=system.radius_m,
        energy_J=energy_J,
        theoretical_max_bits=ceiling,
        estimated_actual_bits=system.estimated_actual_bits,
        bekenstein_saturation_ratio=ratio,
        log10_margin=log10_margin,
    )


def scan(systems: tuple[System, ...] = SYSTEMS) -> tuple[MarginRow, ...]:
    return tuple(compute_row(s) for s in systems)


def assert_no_violation(rows: tuple[MarginRow, ...]) -> None:
    violations = [r for r in rows if r.bekenstein_saturation_ratio >= 1.0]
    if violations:
        names = ", ".join(f"{r.name}={r.bekenstein_saturation_ratio:.3e}" for r in violations)
        raise PhysicsViolation(f"INV-BEKENSTEIN-COGNITIVE violated: {names}")


def _fmt(value: float) -> str:
    if value == 0.0:
        return "0"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return f"{value:.3e}"


def render_markdown(rows: tuple[MarginRow, ...]) -> str:
    lines = [
        "| system | R [m] | E [J] | I_max bits | actual bits | saturation ratio | log10(ratio) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r.name} | {_fmt(r.radius_m)} | {_fmt(r.energy_J)} | "
            f"{_fmt(r.theoretical_max_bits)} | {_fmt(r.estimated_actual_bits)} | "
            f"{_fmt(r.bekenstein_saturation_ratio)} | {r.log10_margin:.2f} |"
        )
    return "\n".join(lines)


def rows_to_json(rows: tuple[MarginRow, ...]) -> list[dict[str, object]]:
    return [
        {
            "name": r.name,
            "radius_m": r.radius_m,
            "energy_J": r.energy_J,
            "theoretical_max_bits": r.theoretical_max_bits,
            "estimated_actual_bits": r.estimated_actual_bits,
            "bekenstein_saturation_ratio": r.bekenstein_saturation_ratio,
            "log10_margin": r.log10_margin,
        }
        for r in rows
    ]


def main() -> None:
    rows = scan()
    assert_no_violation(rows)
    print(render_markdown(rows))
    out_path = Path(__file__).parent / "bekenstein_scan_results.json"
    out_path.write_text(
        json.dumps(rows_to_json(rows), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("\nPASS: 5/5 bekenstein_saturation_ratio < 1.0")
    print(f"JSON: {out_path}")


if __name__ == "__main__":
    main()
