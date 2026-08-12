#!/usr/bin/env python3
"""Regime-conditional IC decomposition.

The canonical IC = 0.122 is pooled across all regime states. This
splits it into high-vol and low-vol halves using the rv-q75 mask,
and reports IC per regime. Answers: does the Ricci cross-sectional
edge live in volatile windows or quiet ones?

Verdict taxonomy:
    VOL_DRIVEN    — high-vol IC > 2 × low-vol IC
    UNIFORM       — high-vol IC ≈ low-vol IC (within 30 %)
    QUIET_DRIVEN  — low-vol IC > 2 × high-vol IC
    INCONCLUSIVE  — one half too small to estimate

Writes results/L2_REGIME_CONDITIONAL_IC.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from research.microstructure.killtest import (
    _forward_log_return,
    _pooled_ic,
    cross_sectional_ricci_signal,
)
from research.microstructure.l2_cli import (
    SubstrateError,
    add_common_args,
    load_substrate,
    setup_logging,
)
from research.microstructure.regime import (
    regime_mask_from_quantile,
    rolling_rv_regime,
)

_log = logging.getLogger("l2_regime_cond_ic")


@dataclass(frozen=True)
class RegimeICCell:
    regime: str  # "HIGH_VOL" | "LOW_VOL"
    n_rows: int
    ic: float


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser, output_default=Path("results/L2_REGIME_CONDITIONAL_IC.json"))
    parser.add_argument("--horizon-sec", type=int, default=180)
    parser.add_argument("--regime-quantile", type=float, default=0.75)
    parser.add_argument("--regime-window-sec", type=int, default=300)
    args = parser.parse_args()

    setup_logging(str(args.log_level))

    try:
        loaded = load_substrate(Path(args.data_dir), str(args.symbols))
    except SubstrateError as exc:
        _log.error("%s", exc)
        return 2
    features = loaded.features

    signal = cross_sectional_ricci_signal(features.ofi)
    target = _forward_log_return(features.mid, int(args.horizon_sec))
    signal_panel = np.repeat(signal[:, None], features.n_symbols, axis=1)

    baseline_ic = _pooled_ic(signal_panel, target)
    _log.info("pooled IC (all regimes): %+.4f", baseline_ic)

    rv_score = rolling_rv_regime(features, window_rows=int(args.regime_window_sec))
    high_mask_rows = regime_mask_from_quantile(rv_score, quantile=float(args.regime_quantile))

    def _ic_on_rows(row_mask: np.ndarray[Any, np.dtype[np.bool_]]) -> tuple[int, float]:
        s_sub = signal_panel[row_mask]
        t_sub = target[row_mask]
        if s_sub.size < 50:
            return int(row_mask.sum()), float("nan")
        return int(row_mask.sum()), _pooled_ic(s_sub, t_sub)

    n_hi, ic_hi = _ic_on_rows(high_mask_rows)
    n_lo, ic_lo = _ic_on_rows(~high_mask_rows)

    _log.info("HIGH_VOL: n=%d IC=%+.4f", n_hi, ic_hi)
    _log.info("LOW_VOL : n=%d IC=%+.4f", n_lo, ic_lo)

    cells = [
        RegimeICCell(regime="HIGH_VOL", n_rows=n_hi, ic=ic_hi),
        RegimeICCell(regime="LOW_VOL", n_rows=n_lo, ic=ic_lo),
    ]

    if not (np.isfinite(ic_hi) and np.isfinite(ic_lo)):
        verdict = "INCONCLUSIVE"
        ratio = float("nan")
    else:
        abs_hi = abs(ic_hi)
        abs_lo = abs(ic_lo)
        if abs_lo < 1e-9:
            ratio = float("inf") if abs_hi > 0 else 0.0
        else:
            ratio = abs_hi / abs_lo
        if ratio > 2.0:
            verdict = "VOL_DRIVEN"
        elif ratio > 0.77:  # 1 / 1.3 ≈ 0.77, within ±30 %
            verdict = "UNIFORM"
        else:
            verdict = "QUIET_DRIVEN"

    payload: dict[str, Any] = {
        "horizon_sec": int(args.horizon_sec),
        "regime_quantile": float(args.regime_quantile),
        "regime_window_sec": int(args.regime_window_sec),
        "baseline_ic_pooled": float(baseline_ic),
        "abs_ratio_high_over_low": float(ratio),
        "verdict": verdict,
        "cells": [asdict(c) for c in cells],
    }
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(body)

    _log.info(
        "regime-conditional IC verdict: %s  |IC_hi|/|IC_lo| = %.2f",
        verdict,
        ratio,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
