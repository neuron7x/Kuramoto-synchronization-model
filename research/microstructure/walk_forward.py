"""Temporal-stability summary for the rolling walk-forward IC record.

Reads `results/L2_WALK_FORWARD.json` (produced by the pre-existing
walk-forward runner at window=40min, step=5min) and condenses it into a
single-verdict report:

    STABLE_POSITIVE  if ≥70% of windows have IC > 0 AND median IC > 0.05
    MIXED            if 50-70% of windows are positive
    UNSTABLE         otherwise

Adds the tenth orthogonal validation axis to FINDINGS.md: the cross-
sectional κ_min edge is not a single-window artifact — it reappears in
the majority of non-overlapping sub-windows of Session 1.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class WalkForwardSummary:
    n_windows: int
    n_valid: int
    window_sec: int
    step_sec: int
    ic_mean: float
    ic_std: float
    ic_median: float
    ic_q25: float
    ic_q75: float
    ic_min: float
    ic_max: float
    fraction_positive: float
    fraction_above_0p05: float
    fraction_below_minus_0p05: float
    fraction_permutation_significant: float
    verdict: str


def _finite(values: list[float | None]) -> NDArray[np.float64]:
    arr = np.asarray([float("nan") if v is None else float(v) for v in values], dtype=np.float64)
    return arr


def summarize_walk_forward(wf_path: Path) -> WalkForwardSummary:
    """Load walk-forward JSON and return the stability summary."""
    with wf_path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    rows = data.get("rows", [])
    window_sec = int(data.get("window_sec", 0))
    step_sec = int(data.get("step_sec", 0))

    ics = _finite([r.get("ic_signal") for r in rows])
    perms = _finite([r.get("perm_p") for r in rows])
    valid = np.isfinite(ics)
    ics_v = ics[valid]
    perms_v = perms[valid]

    if ics_v.size == 0:
        return WalkForwardSummary(
            n_windows=len(rows),
            n_valid=0,
            window_sec=window_sec,
            step_sec=step_sec,
            ic_mean=float("nan"),
            ic_std=float("nan"),
            ic_median=float("nan"),
            ic_q25=float("nan"),
            ic_q75=float("nan"),
            ic_min=float("nan"),
            ic_max=float("nan"),
            fraction_positive=float("nan"),
            fraction_above_0p05=float("nan"),
            fraction_below_minus_0p05=float("nan"),
            fraction_permutation_significant=float("nan"),
            verdict="INCONCLUSIVE",
        )

    frac_pos = float((ics_v > 0.0).mean())
    median_ic = float(np.median(ics_v))
    if frac_pos >= 0.70 and median_ic > 0.05:
        verdict = "STABLE_POSITIVE"
    elif frac_pos >= 0.50:
        verdict = "MIXED"
    else:
        verdict = "UNSTABLE"

    return WalkForwardSummary(
        n_windows=len(rows),
        n_valid=int(ics_v.size),
        window_sec=window_sec,
        step_sec=step_sec,
        ic_mean=float(ics_v.mean()),
        ic_std=float(ics_v.std()),
        ic_median=median_ic,
        ic_q25=float(np.quantile(ics_v, 0.25)),
        ic_q75=float(np.quantile(ics_v, 0.75)),
        ic_min=float(ics_v.min()),
        ic_max=float(ics_v.max()),
        fraction_positive=frac_pos,
        fraction_above_0p05=float((ics_v > 0.05).mean()),
        fraction_below_minus_0p05=float((ics_v < -0.05).mean()),
        fraction_permutation_significant=(
            float((perms_v < 0.05).mean()) if perms_v.size > 0 else float("nan")
        ),
        verdict=verdict,
    )
