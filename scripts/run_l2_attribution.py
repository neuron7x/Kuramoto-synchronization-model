#!/usr/bin/env python3
"""Attribution CLI — Gini concentration, signal-lag curve, autocorrelation decay.

Consumes one L2 substrate; produces an attribution JSON answering:
    Q1 — how concentrated is alpha across trades?
    Q2 — is κ leading / coincident / lagging?
    Q3 — how fast does κ forget its past?

Exit: 0 on verdict produced, 2 on data / arg error.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

from research.microstructure.attribution import (
    LAGS_DEFAULT_SEC,
    autocorrelation_decay,
    concentration_report,
    lag_ic_sweep,
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
from research.microstructure.pnl import (
    DEFAULT_DECISION_SEC,
    DEFAULT_HOLD_SEC,
    DEFAULT_MEDIAN_WINDOW_SEC,
    simulate_gross_trades,
)

_log = logging.getLogger("l2_attribution")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser, output_default=Path("results/L2_IC_ATTRIBUTION.json"))
    parser.add_argument("--horizon-sec", type=int, default=DEFAULT_HOLD_SEC)
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
    decision_idx = np.arange(0, features.n_rows, DEFAULT_DECISION_SEC, dtype=np.int64)

    trades = simulate_gross_trades(
        signal,
        features.mid,
        decision_idx=decision_idx,
        hold_rows=int(args.horizon_sec),
        median_window_rows=DEFAULT_MEDIAN_WINDOW_SEC,
    )
    conc = concentration_report(trades.gross_bp)
    lag = lag_ic_sweep(signal, target, lags_sec=LAGS_DEFAULT_SEC)
    acf = autocorrelation_decay(signal)

    payload = {
        "n_rows": features.n_rows,
        "n_symbols": features.n_symbols,
        "horizon_sec": int(args.horizon_sec),
        "concentration": asdict(conc),
        "lag": {
            "lags_sec": list(lag.lags_sec),
            "ic_per_lag": {str(k): v for k, v in lag.ic_per_lag.items()},
            "ic_peak_lag_sec": lag.ic_peak_lag_sec,
            "ic_peak_value": lag.ic_peak_value,
            "verdict": lag.verdict,
        },
        "autocorr": {
            "acf_lag_sec": list(acf.acf_lag_sec),
            "acf": list(acf.acf),
            "tau_decay_sec": acf.tau_decay_sec,
        },
    }

    body = json.dumps(payload, indent=2, sort_keys=True, default=str)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(body)
    _log.info(
        "concentration: gini=%.3f  top-5%%=%.2f%%  80%%-share=%.1f%%  "
        "lag: peak=%ds verdict=%s  τ_decay=%ss",
        conc.gini,
        conc.top_5_pct_frac_of_total * 100.0,
        conc.trades_frac_for_80_pct_of_total * 100.0,
        lag.ic_peak_lag_sec,
        lag.verdict,
        acf.tau_decay_sec,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
