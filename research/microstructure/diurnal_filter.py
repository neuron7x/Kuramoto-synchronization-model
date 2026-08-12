"""Diurnal-aware sign filter for the Ricci cross-sectional signal.

Consumes a `L2_DIURNAL_PROFILE.json` artifact produced by
`scripts/run_l2_diurnal_profile.py` and emits a per-row trading direction:

    +1  → hour's calibrated IC is significantly positive → go with the signal
    -1  → hour's calibrated IC is significantly negative → go against
     0  → hour is underpowered / not significant → flat

Intended consumer: `research.microstructure.pnl.simulate_gross_trades`
via its `direction_override` parameter. Replaces the default basket-sign
rule (signal > rolling_median → +1, else −1) with a regime-aware rule
that honors the observed diurnal sign flip (PR #240:
SIGN_FLIP_CONFIRMED, 5 POS + 5 NEG UTC hours at p<0.05).

Calibration contract:
    τ (ic_gate)      minimum |hourly_IC| to trade in that hour
    p_gate           maximum permutation_p to trade in that hour
Defaults match the spine `killtest._IC_GATE = 0.03` and
`killtest._PERM_PVALUE_GATE = 0.05`. When multi-day substrate closes
U1, recalibrate by re-running the diurnal profiler and loading the
fresh JSON through `load_hourly_direction_map`.

No numerical logic pollutes this module — it's pure mapping and sign
dispatch. Zero IO in the core decision function; IO confined to
`load_hourly_direction_map`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
from numpy.typing import NDArray

from research.microstructure.diurnal import utc_hour_of_row

DEFAULT_IC_GATE: Final[float] = 0.03
DEFAULT_PVALUE_GATE: Final[float] = 0.05


@dataclass(frozen=True)
class HourlyDirection:
    """One bucket of the diurnal direction map."""

    hour_utc: int
    direction: int  # +1 / 0 / -1
    confidence: float  # |ic_signal| when direction != 0, else 0.0
    n_rows: int
    ic_signal: float
    permutation_p: float


def _classify(
    ic: float | None,
    p: float | None,
    *,
    ic_gate: float,
    pvalue_gate: float,
) -> tuple[int, float]:
    """Map (IC, p) to (direction, confidence)."""
    if ic is None or p is None or not np.isfinite(ic) or not np.isfinite(p):
        return 0, 0.0
    if p > pvalue_gate:
        return 0, 0.0
    if abs(ic) < ic_gate:
        return 0, 0.0
    direction = 1 if ic > 0 else -1
    return direction, float(abs(ic))


def load_hourly_direction_map(
    profile_path: Path,
    *,
    ic_gate: float = DEFAULT_IC_GATE,
    pvalue_gate: float = DEFAULT_PVALUE_GATE,
) -> dict[int, HourlyDirection]:
    """Parse an L2_DIURNAL_PROFILE.json file into a {hour: HourlyDirection} map."""
    data = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    raw_buckets = data.get("hour_buckets")
    if not isinstance(raw_buckets, dict):
        raise ValueError(f"malformed profile at {profile_path}: .hour_buckets is not an object")
    result: dict[int, HourlyDirection] = {}
    for hour_str, bucket in raw_buckets.items():
        h = int(hour_str)
        if h < 0 or h > 23:
            raise ValueError(f"invalid hour key {hour_str!r} in profile")
        ic_raw = bucket.get("ic_signal")
        p_raw = bucket.get("permutation_p")
        ic = float(ic_raw) if ic_raw is not None else float("nan")
        p = float(p_raw) if p_raw is not None else float("nan")
        direction, confidence = _classify(ic, p, ic_gate=ic_gate, pvalue_gate=pvalue_gate)
        result[h] = HourlyDirection(
            hour_utc=h,
            direction=direction,
            confidence=confidence,
            n_rows=int(bucket.get("n_rows", 0)),
            ic_signal=ic,
            permutation_p=p,
        )
    return result


def direction_per_row(
    hourly_map: dict[int, HourlyDirection],
    *,
    start_ms: int,
    n_rows: int,
) -> NDArray[np.int64]:
    """Return a (n_rows,) array where each entry is the calibrated direction
    for the UTC hour of that 1-second row. Hours not present in the map
    → 0 (flat, conservative default).
    """
    if n_rows < 0:
        raise ValueError(f"n_rows must be >= 0, got {n_rows}")
    hours = utc_hour_of_row(start_ms, n_rows)
    direction = np.zeros(n_rows, dtype=np.int64)
    for h, entry in hourly_map.items():
        if entry.direction == 0:
            continue
        mask = hours == h
        direction[mask] = entry.direction
    return direction


def summarize_map(hourly_map: dict[int, HourlyDirection]) -> dict[str, int]:
    """Terse diagnostic: counts of +1/-1/0 hours in the calibrated map."""
    counts = {"+1": 0, "-1": 0, "0": 0}
    for entry in hourly_map.values():
        if entry.direction == 1:
            counts["+1"] += 1
        elif entry.direction == -1:
            counts["-1"] += 1
        else:
            counts["0"] += 1
    counts["total"] = len(hourly_map)
    return counts
