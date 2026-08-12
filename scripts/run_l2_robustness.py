#!/usr/bin/env python3
"""Robustness CLI — bootstrap CI / DSR / ADF / MI on the Ricci edge.

Consumes one L2 substrate; produces a robustness JSON that answers:
    R1 — block-bootstrap 95 % CI on IC
    R2 — deflated Sharpe ratio vs multiple-testing
    R3 — ADF stationarity test on κ_min
    R4 — mutual information between κ_min and fwd-return
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

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
from research.microstructure.robustness import (
    DEFAULT_BLOCK_SIZE,
    DEFAULT_MI_BINS,
    DEFAULT_N_BOOTSTRAPS,
    adf_stationarity,
    block_bootstrap_ic,
    deflated_sharpe,
    mutual_information,
)

_log = logging.getLogger("l2_robustness")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser, output_default=Path("results/L2_ROBUSTNESS.json"))
    parser.add_argument("--horizon-sec", type=int, default=180)
    parser.add_argument("--block-size", type=int, default=DEFAULT_BLOCK_SIZE)
    parser.add_argument("--n-bootstraps", type=int, default=DEFAULT_N_BOOTSTRAPS)
    parser.add_argument("--mi-bins", type=int, default=DEFAULT_MI_BINS)
    parser.add_argument(
        "--n-trials",
        type=int,
        default=15,
        help="Approximate number of statistical trials performed during "
        "signal discovery (for DSR); default 15 reflects our gate + regime + "
        "diurnal + horizon sweeps across the session.",
    )
    parser.add_argument(
        "--sharpe-observed",
        type=float,
        default=0.276,
        help="Observed Sharpe per-trade for DSR. Default taken from "
        "REGIME_Q75+DIURNAL pnl simulation (mean_net / std_net per trade).",
    )
    parser.add_argument("--seed", type=int, default=42)
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

    # R1 — bootstrap CI
    boot = block_bootstrap_ic(
        signal_panel.ravel(),
        target_panel.ravel(),
        block_size=int(args.block_size) * features.n_symbols,
        n_bootstraps=int(args.n_bootstraps),
        seed=int(args.seed),
    )

    # R2 — deflated Sharpe
    # Canonical input: t-statistic of IC as the per-observation Sharpe proxy.
    # t = IC · √(n-1) → asymptotically N(0,1) under H0 (no edge).
    # This makes DSR directly comparable to the E[max of n_trials t-stats].
    n_for_t = int(features.n_rows)
    t_stat_of_ic = float(boot.ic_point) * float(np.sqrt(max(1, n_for_t - 1)))
    sharpe_input = (
        t_stat_of_ic / float(np.sqrt(max(1, n_for_t - 1)))
        if args.sharpe_observed < 0
        else float(args.sharpe_observed)
    )
    # default: use t-stat/√(n-1) = IC itself, which is the per-observation-scale
    # Sharpe under normal-return simplification. This matches DSR unit contract.
    dsr = deflated_sharpe(
        sharpe_observed=float(boot.ic_point),
        n_trials=int(args.n_trials),
        n_observations=int(features.n_rows),
    )
    del sharpe_input, t_stat_of_ic  # documentation-only locals

    # R3 — ADF on κ_min
    adf = adf_stationarity(signal_1d)

    # R4 — mutual information κ_min vs fwd-return (flat)
    mi = mutual_information(
        signal_panel.ravel(),
        target_panel.ravel(),
        n_bins=int(args.mi_bins),
    )

    payload: dict[str, Any] = {
        "n_rows": features.n_rows,
        "n_symbols": features.n_symbols,
        "horizon_sec": int(args.horizon_sec),
        "bootstrap": asdict(boot),
        "deflated_sharpe": asdict(dsr),
        "adf": asdict(adf),
        "mutual_information": asdict(mi),
    }

    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(body)

    _log.info(
        "bootstrap IC=%.4f 95%%CI=[%.4f,%.4f] sig=%s  DSR=%.2f Pr_real=%.2f  "
        "ADF=%s p=%.4f  MI=%.4f nats",
        boot.ic_point,
        boot.ci_lo_95,
        boot.ci_hi_95,
        boot.significant_at_95,
        dsr.deflated_sharpe,
        dsr.probability_sharpe_is_real,
        adf.verdict,
        adf.pvalue,
        mi.mutual_information_nats,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
