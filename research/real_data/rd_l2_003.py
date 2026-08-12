#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""RD-L2-003 — the depth axis, at power.

Protocol: `docs/research/PREREG_RD_GRID_002_2026-07-13.md`, amendments A-2 and A-3, both
recorded before this ran.

The 4-date L2 attempt was underpowered: under the full rule even the demonstrated control
(`qi_l1`) survived 0 cells. A bar that a provably-real effect cannot clear is not a
finding. A-3 extends the panel to 16 dates (8 discovery / 8 validation) on 3 symbols, in
the window where the venue publishes BOTH `bookDepth` and `bookTicker` — the control needs
the latter's bid/ask sizes, and `bookTicker` stops in March 2024.

Replication is the session-pooled form specified in A-3, applied identically to the
control and to the instrument:

    mean IC over the 8 validation sessions (session = independent unit)
    bootstrap CI over SESSIONS excludes zero
    sign agrees in >= 7 of 8 validation sessions
    pooled p survives BH-FDR at q = 0.05
    effect already present on the 8 discovery sessions
"""

from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from research.kernels.ofi_unity_live import ofi_unity_kernel
from research.real_data.rd_grid_002 import _spearman
from research.real_data.rd_grid_002_l2 import load_depth

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "research" / "rd_l2_003"

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
HORIZONS = (1, 2, 5, 10)
WINDOW = 20
SEED = 42
BAR_S = 30
N_BOOT_SESS = 5000
FDR_Q = 0.05
SIGN_MIN = 7  # of 8 validation sessions


def usable_dates() -> list[str]:
    dep = {
        os.path.basename(f).split("-", 1)[1][:10]
        for f in glob.glob(str(ROOT / "data/real/binance_bookdepth/*.csv"))
    }
    out = []
    for d in sorted(dep):
        if all(
            (ROOT / f"data/real/binance_bookticker/{s}-{d}-bookticker-1000ms.csv").is_file()
            and (ROOT / f"data/real/binance_bookdepth/{s}-{d}-bookdepth.csv").is_file()
            for s in SYMBOLS
        ):
            out.append(d)
    return out


def signals(d: pd.DataFrame) -> dict[str, pd.Series]:
    cols = [f"bid_{i}" for i in range(1, 6)] + [f"ask_{i}" for i in range(1, 6)]
    b5 = d[[f"bid_{i}" for i in range(1, 6)]].sum(axis=1)
    a5 = d[[f"ask_{i}" for i in range(1, 6)]].sum(axis=1)
    return {
        "ofi_unity": ofi_unity_kernel(d[cols], window=WINDOW),  # GeoSync kernel, real L2
        "qi_l1": (d["bid_volume"] - d["ask_volume"])
        / (d["bid_volume"] + d["ask_volume"]),  # control
        "depth_imb_l5": (b5 - a5) / (b5 + a5),
    }


def main() -> int:
    rng = np.random.default_rng(SEED)
    dates = usable_dates()
    if len(dates) < 8:
        print(f"only {len(dates)} paired dates — insufficient for the A-3 panel", file=sys.stderr)
        return 1
    n_dis = len(dates) // 2
    DIS, VAL = dates[:n_dis], dates[n_dis:]
    print(f"panel: {len(dates)} paired dates — {len(DIS)} discovery / {len(VAL)} validation")
    print(f"  discovery : {' '.join(DIS)}")
    print(f"  validation: {' '.join(VAL)}\n")

    per_session: dict[tuple, dict[str, float]] = defaultdict(dict)  # (sig,sym,h) -> {date: ic}

    for sym in SYMBOLS:
        for date in dates:
            d = load_depth(sym, date)
            if d is None or len(d) < WINDOW * 5:
                continue
            for name, sig in signals(d).items():
                for h in HORIZONS:
                    tgt = d["mid_returns"].shift(-h)
                    j = pd.concat([sig.rename("s"), tgt.rename("t")], axis=1).dropna()
                    if len(j) < 300:
                        continue
                    x, y = j["s"].to_numpy(float), j["t"].to_numpy(float)
                    if np.std(x) < 1e-30:
                        continue
                    per_session[(name, sym, h)][date] = _spearman(x, y)
        print(f"  {sym} done", flush=True)

    # Session-pooled inference (A-3). The session is the independent unit.
    cells = []
    for (name, sym, h), by_date in per_session.items():
        val = np.array([by_date[d] for d in VAL if d in by_date], dtype=float)
        dis = np.array([by_date[d] for d in DIS if d in by_date], dtype=float)
        val = val[np.isfinite(val)]
        dis = dis[np.isfinite(dis)]
        if len(val) < SIGN_MIN or len(dis) < 4:
            continue
        mean_ic = float(val.mean())
        boot = np.array(
            [rng.choice(val, size=len(val), replace=True).mean() for _ in range(N_BOOT_SESS)]
        )
        lo, hi = float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))
        sign_agree = int(max((val > 0).sum(), (val < 0).sum()))
        # Two-sided p from the session bootstrap (fraction of resamples crossing zero).
        p = float(2 * min((boot <= 0).mean(), (boot >= 0).mean()))
        p = max(p, 1.0 / N_BOOT_SESS)
        cells.append(
            {
                "signal": name,
                "symbol": sym,
                "horizon": h,
                "n_val": int(len(val)),
                "n_dis": int(len(dis)),
                "mean_ic_validation": round(mean_ic, 6),
                "mean_ic_discovery": round(float(dis.mean()), 6),
                "ci95_over_sessions": [round(lo, 6), round(hi, 6)],
                "ci_excludes_zero": bool(lo * hi > 0),
                "sign_agreement": sign_agree,
                "sign_ok": bool(sign_agree >= SIGN_MIN),
                "p_pooled": p,
                "discovery_same_sign": bool(
                    np.sign(dis.mean()) == np.sign(mean_ic) and abs(dis.mean()) > 0
                ),
            }
        )

    # BH-FDR across all cells
    p = np.array([c["p_pooled"] for c in cells])
    m = len(p)
    order = np.argsort(p)
    rej = np.zeros(m, bool)
    kmax = -1
    for i, oi in enumerate(order):
        if p[oi] <= (i + 1) / m * FDR_Q:
            kmax = i
    for i, oi in enumerate(order):
        if i <= kmax:
            rej[oi] = True
    for c, r in zip(cells, rej):
        c["fdr_reject"] = bool(r)
        c["SURVIVES"] = bool(
            c["ci_excludes_zero"] and c["sign_ok"] and c["fdr_reject"] and c["discovery_same_sign"]
        )

    OUT.mkdir(parents=True, exist_ok=True)
    control_survives = sum(c["SURVIVES"] for c in cells if c["signal"] == "qi_l1")
    verdict = (
        "HARNESS_VOID — the demonstrated control failed even at power; the depth axis is "
        "declared PERMANENTLY OPEN per the binding commitment in A-2"
        if control_survives == 0
        else (
            "SUPPORTED"
            if any(c["SURVIVES"] for c in cells if c["signal"] == "ofi_unity")
            else "NOT_SUPPORTED_TERMINAL"
        )
    )
    (OUT / "verdict.json").write_text(
        json.dumps(
            {"panel": {"discovery": DIS, "validation": VAL}, "cells": cells, "VERDICT": verdict},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print("\n" + "=" * 84)
    print(
        f"{'signal':<15} {'cells':>6} {'CI≠0':>6} {'sign≥7/8':>9} {'FDR':>5} {'SURVIVES':>9} {'max|meanIC|':>12}"
    )
    for sg in ("qi_l1", "ofi_unity", "depth_imb_l5"):
        c = [x for x in cells if x["signal"] == sg]
        if not c:
            continue
        tag = {"qi_l1": "  <- CONTROL", "ofi_unity": "  <- GeoSync", "depth_imb_l5": ""}[sg]
        print(
            f"{sg:<15} {len(c):>6} {sum(x['ci_excludes_zero'] for x in c):>6} "
            f"{sum(x['sign_ok'] for x in c):>9} {sum(x['fdr_reject'] for x in c):>5} "
            f"{sum(x['SURVIVES'] for x in c):>9} "
            f"{max(abs(x['mean_ic_validation']) for x in c):>12.5f}{tag}"
        )
    print("=" * 84)
    print(f"\n  VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
