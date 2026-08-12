#!/usr/bin/env python3
"""Per-symbol IC decomposition: is the edge uniformly distributed, or concentrated?

The pooled Spearman IC of Ricci κ_min vs 3-min forward mid-return is
computed across symbols × time. This script breaks that down by symbol
alone: for each of the 10 perps, compute IC of the (same 1D Ricci signal)
vs that symbol's own forward mid-return.

If IC is approximately uniform across symbols, the cross-sectional
Ricci signal encodes a broad-market predictor. If IC is concentrated in
2-3 names, the edge is really about those instruments' idiosyncratic
response to cross-sectional order-flow structure.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from research.microstructure.killtest import (
    _load_parquets as load_parquets,
)
from research.microstructure.killtest import (
    build_feature_frame,
    cross_sectional_ricci_signal,
)
from research.microstructure.l2_schema import DEFAULT_SYMBOLS


def _forward_log_return_1d(mid: np.ndarray, horizon_rows: int) -> np.ndarray:
    log_mid = np.log(mid)
    fwd = np.full_like(log_mid, np.nan)
    if horizon_rows >= log_mid.shape[0]:
        return fwd
    fwd[:-horizon_rows] = log_mid[horizon_rows:] - log_mid[:-horizon_rows]
    return fwd


def main() -> int:
    data_dir = Path("data/binance_l2_perp")
    frames = load_parquets(data_dir, DEFAULT_SYMBOLS)
    features = build_feature_frame(frames, DEFAULT_SYMBOLS)
    print(f"substrate: n_rows={features.n_rows}  n_symbols={features.n_symbols}\n")

    signal = cross_sectional_ricci_signal(features.ofi)
    primary_horizon = 180

    rows: list[dict[str, float | str]] = []
    print(f"{'symbol':<12} {'IC':>9} {'p':>8} {'n_valid':>8}")
    print("-" * 42)
    for k, sym in enumerate(features.symbols):
        tgt = _forward_log_return_1d(features.mid[:, k], primary_horizon)
        mask = np.isfinite(signal) & np.isfinite(tgt)
        if mask.sum() < 50:
            continue
        s = signal[mask]
        t = tgt[mask]
        if float(np.std(s)) < 1e-14 or float(np.std(t)) < 1e-14:
            rho = float("nan")
            p = float("nan")
        else:
            rho_raw, p_raw = spearmanr(s, t)
            rho = float(rho_raw)
            p = float(p_raw)
        rows.append(
            {
                "symbol": sym,
                "ic": rho,
                "p": p,
                "n_valid": int(mask.sum()),
            }
        )
        print(f"{sym:<12} {rho:>+9.4f} {p:>8.4f} {int(mask.sum()):>8}")

    ic_values = [r["ic"] for r in rows if isinstance(r["ic"], float) and np.isfinite(r["ic"])]
    if ic_values:
        print(
            f"\nsummary: n={len(ic_values)}  mean={np.mean(ic_values):+.4f}  "
            f"median={np.median(ic_values):+.4f}  "
            f"min={min(ic_values):+.4f}  max={max(ic_values):+.4f}  "
            f"pos_frac={sum(1 for x in ic_values if x > 0) / len(ic_values):.2%}"
        )

    Path("results").mkdir(exist_ok=True)
    Path("results/L2_PER_SYMBOL_IC.json").write_text(
        json.dumps({"primary_horizon_sec": primary_horizon, "rows": rows}, indent=2),
        encoding="utf-8",
    )
    print("\nwrote results/L2_PER_SYMBOL_IC.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
