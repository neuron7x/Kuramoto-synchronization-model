#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""RD-GRID-002-L2 — close the last escape: multi-level order-book depth.

The main grid ran on `bookTicker` (top-of-book). The remaining objection is
"you only looked at L1". This closes it.

`bookDepth` gives cumulative depth in five bands on each side (±1..±5 % of mid),
every ~30 s. That is exactly the input `research/kernels/ofi_unity_live.py` was
written for: it scans for `bid*`/`ask*` column pairs and takes the leading eigenvalue
of the order-flow correlation matrix, normalised by the number of levels. **On L1 data
there is a single pair, the matrix is 1×1, and the kernel returns the constant 1.0** —
it could never have been tested on top-of-book data at all.

The depth file has no prices, so the target (forward mid-return) is joined from the
`bookTicker` bars with a backward as-of merge — never forward, which would leak.

Signals:
  * `ofi_unity`      — the GeoSync kernel, on real 5-level depth
  * `depth_imb_l5`   — POSITIVE CONTROL: (Σbid − Σask)/(Σbid + Σask) across the 5 bands.
                       The L2 analogue of queue imbalance. If it fails, the L2 harness
                       is broken and no conclusion may be drawn.

Same null (circular shifts), same bootstrap, same rule as the main grid.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from research.kernels.ofi_unity_live import ofi_unity_kernel
from research.real_data.rd_grid_002 import _spearman, block_bootstrap_ci, load_bars
from research.real_data.rd_grid_002_confirm import empirical_p

ROOT = Path(__file__).resolve().parents[2]
DEPTH = ROOT / "data" / "real" / "binance_bookdepth"
OUT = ROOT / "artifacts" / "research" / "rd_grid_002"

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
DISCOVERY = ("2024-02-05", "2024-02-20")
VALIDATION = ("2024-03-06", "2024-03-19")
HORIZONS = (1, 2, 5, 10)     # in 30 s depth snapshots
WINDOW = 20                  # snapshots (~10 min) — the depth series is 2880/day
SEED = 42
BAR_S = 30


def load_depth(symbol: str, date: str) -> pd.DataFrame | None:
    f = DEPTH / f"{symbol}-{date}-bookdepth.csv"
    if not f.is_file():
        return None
    d = pd.read_csv(f)
    d["ts"] = pd.to_datetime(d["ts"], utc=True)
    d = d.sort_values("ts").set_index("ts")

    bars = load_bars(symbol, date, 1)
    if bars is None:
        return None
    mid = bars[["mid", "bid_volume", "ask_volume"]].copy()
    # Backward as-of: each depth snapshot is matched to the LAST mid at or before it.
    # A forward match would let the future leak into the feature.
    d = pd.merge_asof(
        d.reset_index(), mid.reset_index(), on="ts", direction="backward", tolerance=pd.Timedelta("5s")
    ).dropna(subset=["mid", "bid_volume", "ask_volume"]).set_index("ts")
    d["mid_returns"] = np.log(d["mid"] / d["mid"].shift(1))
    return d.dropna(subset=["mid_returns"])


def main() -> int:
    rng = np.random.default_rng(SEED)
    rows: list[dict] = []

    for sym in SYMBOLS:
        for date in DISCOVERY + VALIDATION:
            d = load_depth(sym, date)
            if d is None or len(d) < WINDOW * 5:
                continue
            cols = [f"bid_{i}" for i in range(1, 6)] + [f"ask_{i}" for i in range(1, 6)]
            lvl = d[cols]

            # GeoSync instrument, on the input it was actually designed for.
            unity = ofi_unity_kernel(lvl, window=WINDOW)

            # Positive control at L2 — AMENDMENT A-2.
            #
            # The first control (`depth_imb_l5`, cumulative depth across the +/-1-5%
            # bands) beat its noise floor in 0 of 48 tests and voided the sub-study. It
            # was ASSUMED positive and is not: cumulative depth far from the touch is not
            # an established predictor. Top-of-book queue imbalance is — and its
            # positivity here is a MEASURED fact from the main grid (186/576 floor-beats,
            # 25 full-rule survivors), established before this sub-study and independently
            # of the hypothesis under test.
            b5 = d[[f"bid_{i}" for i in range(1, 6)]].sum(axis=1)
            a5 = d[[f"ask_{i}" for i in range(1, 6)]].sum(axis=1)
            imb = ((b5 - a5) / (b5 + a5)).rename("depth_imb_l5")
            qi_l1 = ((d["bid_volume"] - d["ask_volume"])
                     / (d["bid_volume"] + d["ask_volume"])).rename("qi_l1")

            for signame, sig in (("ofi_unity", unity), ("qi_l1", qi_l1), ("depth_imb_l5", imb)):
                for h in HORIZONS:
                    tgt = d["mid_returns"].shift(-h)
                    j = pd.concat([sig.rename("s"), tgt.rename("t")], axis=1).dropna()
                    if len(j) < 300:
                        continue
                    x, y = j["s"].to_numpy(float), j["t"].to_numpy(float)
                    if np.std(x) < 1e-30:
                        rows.append({"symbol": sym, "date": date, "signal": signame, "horizon": h,
                                     "outcome": "DEGENERATE_CONSTANT_SIGNAL"})
                        continue
                    ic = _spearman(x, y)
                    lo_sh = max(1, 3600 // BAR_S)
                    shifts = rng.integers(lo_sh, max(lo_sh + 1, len(x) - lo_sh), size=20)
                    nf = float(max(abs(_spearman(np.roll(x, int(s)), y)) for s in shifts))
                    p = empirical_p(x, y, rng, BAR_S)
                    lo, hi = block_bootstrap_ci(x, y, rng, BAR_S)
                    rows.append({
                        "symbol": sym, "date": date,
                        "split": "discovery" if date in DISCOVERY else "validation",
                        "signal": signame, "horizon": h, "n": int(len(j)),
                        "ic": round(float(ic), 6), "noise_floor": round(nf, 6),
                        "p": float(p), "ci95": [lo, hi],
                        "beats_floor": bool(abs(ic) > nf),
                        "ci_excludes_zero": bool(np.isfinite(lo) and np.isfinite(hi) and lo * hi > 0),
                    })
            print(f"  {sym} {date}: {len(d):,} depth snapshots", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "l2.json").write_text(json.dumps({"tests": rows}, indent=2) + "\n", encoding="utf-8")

    print("\n" + "=" * 72)
    for sg in ("qi_l1", "depth_imb_l5", "ofi_unity"):
        r = [x for x in rows if x.get("signal") == sg and "ic" in x]
        deg = [x for x in rows if x.get("signal") == sg and x.get("outcome")]
        if not r:
            print(f"{sg:<15} no valid tests ({len(deg)} degenerate)")
            continue
        beat = sum(x["beats_floor"] for x in r)
        surv = sum(x["beats_floor"] and x["ci_excludes_zero"] for x in r
                   if x["split"] == "validation")
        tag = {"qi_l1": "  <-- POSITIVE CONTROL (A-2, demonstrated)",
               "depth_imb_l5": "  <-- retired control (assumed, failed)",
               "ofi_unity": "  <-- GeoSync kernel"}[sg]
        print(f"{sg:<15} tests={len(r):>3}  beats floor={beat:>3}  "
              f"validation survivors={surv:>2}  max|IC|={max(abs(x['ic']) for x in r):.5f}{tag}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
