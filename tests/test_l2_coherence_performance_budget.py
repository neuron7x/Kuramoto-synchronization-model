"""Task 6 · Performance budget enforcement.

The committed full-cycle manifest records cycle_duration_sec and per-
stage durations. Assert the budget against a canonical ceiling so
accidental quadratic or unbounded loops cause a hard CI fail instead
of silent slowdown.

Budget was chosen empirically with headroom:
    - full cycle: ≤ 240 s  (current reference: ~81 s)
    - any single stage: ≤ 120 s  (reference killtest 36 s, robustness 20 s)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_MANIFEST = Path("results/L2_FULL_CYCLE_MANIFEST.json")

_FULL_CYCLE_BUDGET_SEC = 240.0
_PER_STAGE_BUDGET_SEC = 120.0


def _load_manifest() -> dict[str, Any]:
    if not _MANIFEST.exists():
        pytest.skip(f"{_MANIFEST} not present")
    with _MANIFEST.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def test_full_cycle_duration_within_budget() -> None:
    manifest = _load_manifest()
    dur = float(manifest["cycle_duration_sec"])
    assert (
        dur <= _FULL_CYCLE_BUDGET_SEC
    ), f"full cycle took {dur:.1f}s, budget {_FULL_CYCLE_BUDGET_SEC}s"


def test_every_stage_within_per_stage_budget() -> None:
    manifest = _load_manifest()
    offenders = [
        (s["name"], float(s["duration_sec"]))
        for s in manifest["stages"]
        if float(s["duration_sec"]) > _PER_STAGE_BUDGET_SEC
    ]
    assert not offenders, f"stages exceeding {_PER_STAGE_BUDGET_SEC}s budget: {offenders}"


def test_manifest_cycle_duration_equals_sum_plus_overhead() -> None:
    """Sanity — cycle_duration_sec is at least the sum of stage durations."""
    manifest = _load_manifest()
    cycle = float(manifest["cycle_duration_sec"])
    stage_sum = sum(float(s["duration_sec"]) for s in manifest["stages"])
    assert cycle >= stage_sum - 1e-6, (
        f"manifest cycle_duration_sec={cycle:.3f} < Σ stages={stage_sum:.3f} "
        "— manifest inconsistency"
    )
