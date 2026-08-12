#!/usr/bin/env python3
"""Leave-one-symbol-out ablation.

For each symbol in the universe, drop it, rebuild the cross-sectional
κ_min signal on the remaining 9, and recompute the IC against the
180-second forward log return averaged across the remaining symbols.

Answers the reviewer question: is the edge driven by a single dominant
symbol (BTC-concentration risk), or is it truly cross-sectional?

Verdict taxonomy:
    ROBUST    — max IC drop ≤ 30% of baseline AND min IC > 0
    CONCENTRATED — removing any single symbol collapses IC (> 60% drop)
    MIXED     — between the two bands

Writes results/L2_SYMBOL_ABLATION.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

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

_log = logging.getLogger("l2_symbol_ablation")

ROBUST_REL_DROP: Final[float] = 0.30
CONCENTRATED_REL_DROP: Final[float] = 0.60


@dataclass(frozen=True)
class LeaveOneOutCell:
    removed_symbol: str
    n_symbols_remaining: int
    ic_point: float
    relative_drop: float


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser, output_default=Path("results/L2_SYMBOL_ABLATION.json"))
    parser.add_argument("--horizon-sec", type=int, default=180)
    args = parser.parse_args()

    setup_logging(str(args.log_level))

    try:
        loaded = load_substrate(Path(args.data_dir), str(args.symbols))
    except SubstrateError as exc:
        _log.error("%s", exc)
        return 2
    features = loaded.features

    horizon = int(args.horizon_sec)

    baseline_signal = cross_sectional_ricci_signal(features.ofi)
    baseline_target = _forward_log_return(features.mid, horizon)
    baseline_ic = _pooled_ic(
        np.repeat(baseline_signal[:, None], features.n_symbols, axis=1),
        baseline_target,
    )
    _log.info("baseline IC (all %d symbols): %.4f", features.n_symbols, baseline_ic)

    cells: list[LeaveOneOutCell] = []
    for idx, removed in enumerate(features.symbols):
        keep = [i for i in range(features.n_symbols) if i != idx]
        ofi_sub = features.ofi[:, keep]
        mid_sub = features.mid[:, keep]
        signal_sub = cross_sectional_ricci_signal(ofi_sub)
        target_sub = _forward_log_return(mid_sub, horizon)
        signal_panel = np.repeat(signal_sub[:, None], len(keep), axis=1)
        ic = _pooled_ic(signal_panel, target_sub)
        rel_drop = (baseline_ic - ic) / baseline_ic if baseline_ic != 0.0 else float("inf")
        cells.append(
            LeaveOneOutCell(
                removed_symbol=removed,
                n_symbols_remaining=len(keep),
                ic_point=float(ic),
                relative_drop=float(rel_drop),
            )
        )
        _log.info(
            "removed %-9s  IC=%+.4f  rel_drop=%+.1f%%",
            removed,
            ic,
            100.0 * rel_drop,
        )

    drops = np.asarray([c.relative_drop for c in cells], dtype=np.float64)
    ics = np.asarray([c.ic_point for c in cells], dtype=np.float64)
    max_drop = float(np.max(drops))
    min_ic = float(np.min(ics))

    if min_ic <= 0.0:
        verdict = "CONCENTRATED"
    elif max_drop <= ROBUST_REL_DROP:
        verdict = "ROBUST"
    elif max_drop <= CONCENTRATED_REL_DROP:
        verdict = "MIXED"
    else:
        verdict = "CONCENTRATED"

    payload: dict[str, Any] = {
        "horizon_sec": horizon,
        "baseline_ic": baseline_ic,
        "baseline_n_symbols": features.n_symbols,
        "robust_rel_drop_threshold": ROBUST_REL_DROP,
        "concentrated_rel_drop_threshold": CONCENTRATED_REL_DROP,
        "max_relative_drop": max_drop,
        "min_ic": min_ic,
        "verdict": verdict,
        "cells": [asdict(c) for c in cells],
    }
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(body)

    _log.info(
        "symbol-ablation verdict: %s  max_drop=%.1f%%  min_ic=%+.4f",
        verdict,
        100.0 * max_drop,
        min_ic,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
