#!/usr/bin/env python3
"""Purged & embargoed K-fold CV CLI — time-series-aware OOS IC.

Uses Lopez de Prado purged K-fold on the Ricci κ_min signal vs
forward mid-return. Reports per-fold IC, aggregate stats, and the
count of positive-IC folds (a crude stability signal).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

from research.microstructure.cv import (
    DEFAULT_EMBARGO_SEC,
    DEFAULT_K,
    purged_kfold_ic,
)
from research.microstructure.killtest import (
    _forward_log_return,
    cross_sectional_ricci_signal,
)
from research.microstructure.l2_cli import (
    SubstrateError,
    add_common_args,
    load_substrate,
    setup_logging,
)

_log = logging.getLogger("l2_purged_cv")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser, output_default=Path("results/L2_PURGED_CV.json"))
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--horizon-sec", type=int, default=180)
    parser.add_argument("--embargo-sec", type=int, default=DEFAULT_EMBARGO_SEC)
    args = parser.parse_args()

    setup_logging(str(args.log_level))

    try:
        loaded = load_substrate(Path(args.data_dir), str(args.symbols))
    except SubstrateError as exc:
        _log.error("%s", exc)
        return 2
    features = loaded.features

    signal_1d = cross_sectional_ricci_signal(features.ofi)
    signal_panel = np.repeat(signal_1d[:, None], features.n_symbols, axis=1)
    target_panel = _forward_log_return(features.mid, int(args.horizon_sec))

    report = purged_kfold_ic(
        signal_panel,
        target_panel,
        k=int(args.k),
        horizon_rows=int(args.horizon_sec),
        embargo_rows=int(args.embargo_sec),
    )

    payload = asdict(report)
    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(body)
    _log.info(
        "purged-CV K=%d horizon=%d embargo=%d  IC mean=%.4f median=%.4f min=%.4f max=%.4f  "
        "positive folds=%.0f%%",
        report.k,
        report.horizon_rows,
        report.embargo_rows,
        report.ic_mean,
        report.ic_median,
        report.ic_min,
        report.ic_max,
        report.pos_fold_frac * 100.0,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
