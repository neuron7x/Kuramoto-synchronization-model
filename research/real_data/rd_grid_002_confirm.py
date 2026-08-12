#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""RD-GRID-002 stage 2 — confirmation and the terminal verdict.

Stage 1 (`rd_grid_002.py`) screened 3444 tests against each cell's own noise floor.
This stage applies the rest of the preregistered decision rule to the survivors:

  * an empirical p-value from 200 circular shifts (the 20 used for the screen give a
    floor of 1/21 and cannot support an FDR at q = 0.05);
  * a moving-block bootstrap 95 % CI (2000 resamples, seed 42);
  * Benjamini-Hochberg FDR at q = 0.05 across **all** tests, not just the survivors;
  * replication: the same (signal, symbol, bar, horizon) cell must hold on **both**
    validation dates with the **same sign**, and must already have held on discovery.

The screen's own false-positive rate is known in advance and is not a free parameter:
the noise floor is the maximum of 20 shifts, so under a true null a cell passes with
probability ~= 1/21 = 4.8 %. Any signal whose pass rate sits at that number is noise
by construction.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from research.real_data.rd_grid_002 import (
    DISCOVERY_DATES,
    SIGNAL_FN,
    SIGNALS,
    VALIDATION_DATES,
    _spearman,
    block_bootstrap_ci,
    load_bars,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "research" / "rd_grid_002"
SEED = 42
N_SHIFTS_P = 200
FDR_Q = 0.05
NULL_PASS_RATE = 1 / 21  # the screen's own false-positive rate, by construction


def empirical_p(sig: np.ndarray, tgt: np.ndarray, rng: np.random.Generator, bar_s: int) -> float:
    """Tail probability of |IC_obs| under the circular-shift null.

    AMENDMENT A-1 (see the preregistration). The *counted* version of this p-value has a
    hard floor of 1/(N+1) = 4.98e-3 at N=200, while BH-FDR at q=0.05 over 3444 tests
    demands p <= 1.45e-5 for the top-ranked test. No test could pass — not even the
    positive control at IC=0.457, which is how the defect was caught.

    Same null model, same 200 shifts. Only the tail is evaluated parametrically instead
    of counted: Fisher-z the null ICs, estimate their scale, and read off the Gaussian
    tail. This removes the counting floor and changes nothing else.
    """
    from scipy.stats import norm

    obs = abs(_spearman(sig, tgt))
    n = len(sig)
    lo = max(1, 3600 // bar_s)
    if n <= 2 * lo or not np.isfinite(obs):
        return 1.0
    shifts = rng.integers(lo, n - lo, size=N_SHIFTS_P)
    null = np.array([_spearman(np.roll(sig, int(s)), tgt) for s in shifts])
    null = null[np.isfinite(null)]
    if null.size < 20:
        return 1.0
    # Fisher-z stabilises the variance of a correlation; the shift null is centred at 0
    # by construction (alignment destroyed), so only its scale is estimated.
    zn = np.arctanh(np.clip(null, -0.999999, 0.999999))
    sigma = float(np.std(zn, ddof=1))
    if not np.isfinite(sigma) or sigma <= 0:
        return 1.0
    z_obs = float(np.arctanh(min(obs, 0.999999)))
    return float(2.0 * norm.sf(z_obs / sigma))


def bh_fdr(p: np.ndarray, q: float) -> np.ndarray:
    m = len(p)
    order = np.argsort(p)
    reject = np.zeros(m, dtype=bool)
    kmax = -1
    for i, oi in enumerate(order):
        if p[oi] <= (i + 1) / m * q:
            kmax = i
    for i, oi in enumerate(order):
        if i <= kmax:
            reject[oi] = True
    return reject


def main() -> int:
    rng = np.random.default_rng(SEED)
    grid = json.loads((OUT / "grid.json").read_text(encoding="utf-8"))
    tests = [t for t in grid["tests"] if t.get("ic") is not None]

    cands = [t for t in tests if t["outcome"] == "CANDIDATE"]
    print(f"stage-1 candidates: {len(cands):,} of {len(tests):,} tests")
    print(f"screen's null pass rate (max of 20 shifts): {NULL_PASS_RATE*100:.1f}%\n")

    # Cache the (symbol, date, bar) frames and signals; a candidate re-derives nothing.
    cache: dict[tuple, tuple] = {}

    def series(sym, date, bar, signame):
        key = (sym, date, bar, signame)
        if key not in cache:
            df = load_bars(sym, date, bar)
            s = SIGNAL_FN[signame](df)
            cache[key] = (df, s)
        return cache[key]

    for i, t in enumerate(cands, 1):
        df, s = series(t["symbol"], t["date"], t["bar_s"], t["signal"])
        tgt = df["mid_returns"].shift(-t["horizon"])
        j = pd.concat([s.rename("s"), tgt.rename("t")], axis=1).dropna()
        x, y = j["s"].to_numpy(), j["t"].to_numpy()
        t["p_emp"] = empirical_p(x, y, rng, t["bar_s"])
        lo, hi = block_bootstrap_ci(x, y, rng, t["bar_s"])
        t["ci95"] = [lo, hi]
        t["ci_excludes_zero"] = bool(np.isfinite(lo) and np.isfinite(hi) and lo * hi > 0)
        if i % 100 == 0:
            print(f"  confirmed {i}/{len(cands)}", flush=True)

    # BH-FDR across ALL tests: a non-candidate gets p = 1.0, which is honest — it did
    # not beat its own noise floor, so it has no evidence against the null.
    pv = np.array([t.get("p_emp", 1.0) for t in tests])
    rej = bh_fdr(pv, FDR_Q)
    for t, r in zip(tests, rej):
        t["fdr_reject"] = bool(r)

    # Replication: a cell must hold on BOTH validation dates, same sign, and have been
    # present on discovery.
    def key(t):
        return (t["signal"], t["symbol"], t["bar_s"], t["horizon"])

    by_cell: dict[tuple, list] = defaultdict(list)
    for t in tests:
        by_cell[key(t)].append(t)

    survivors = []
    for k, group in by_cell.items():
        val = [t for t in group if t["date"] in VALIDATION_DATES]
        dis = [t for t in group if t["date"] in DISCOVERY_DATES]
        if len(val) < 2 or not dis:
            continue
        ok_val = all(
            t.get("ci_excludes_zero") and t.get("fdr_reject") and t["outcome"] == "CANDIDATE"
            for t in val
        )
        same_sign = len({np.sign(t["ic"]) for t in val}) == 1
        on_discovery = any(t["outcome"] == "CANDIDATE" for t in dis)
        if ok_val and same_sign and on_discovery:
            survivors.append(
                {
                    "signal": k[0],
                    "symbol": k[1],
                    "bar_s": k[2],
                    "horizon": k[3],
                    "validation_ic": [round(t["ic"], 5) for t in val],
                    "validation_ci": [t["ci95"] for t in val],
                }
            )

    # Per-signal summary
    summary = {}
    for sg in SIGNALS:
        valid = [t for t in tests if t["signal"] == sg and t["outcome"] != "INSTRUMENT_INVALID"]
        invalid = [t for t in tests if t["signal"] == sg and t["outcome"] == "INSTRUMENT_INVALID"]
        cand = [t for t in valid if t["outcome"] == "CANDIDATE"]
        fdr = [t for t in valid if t.get("fdr_reject")]
        surv = [s for s in survivors if s["signal"] == sg]
        summary[sg] = {
            "tests_valid": len(valid),
            "tests_instrument_invalid": len(invalid),
            "beat_noise_floor": len(cand),
            "beat_rate": round(len(cand) / max(1, len(valid)), 4),
            "null_expected_rate": round(NULL_PASS_RATE, 4),
            "survive_fdr": len(fdr),
            "survive_full_rule": len(surv),
            "max_abs_ic": round(max((abs(t["ic"]) for t in valid), default=0.0), 5),
        }

    verdict = {
        "protocol": "docs/research/PREREG_RD_GRID_002_2026-07-13.md",
        "tests_total": len(tests),
        "fdr_q": FDR_Q,
        "screen_null_pass_rate": round(NULL_PASS_RATE, 4),
        "per_signal": summary,
        "survivors": survivors,
        "positive_control_ok": summary["qi"]["survive_full_rule"] > 0,
        "VERDICT": None,
    }
    if not verdict["positive_control_ok"]:
        verdict["VERDICT"] = (
            "HARNESS_VOID — the positive control did not survive; no conclusion about GeoSync may be drawn"
        )
    elif summary["kappa_forman"]["survive_full_rule"] > 0:
        verdict["VERDICT"] = "SUPPORTED"
    else:
        verdict["VERDICT"] = "NOT_SUPPORTED_TERMINAL"

    (OUT / "verdict.json").write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    (OUT / "grid_confirmed.json").write_text(
        json.dumps({"tests": tests}, indent=2) + "\n", encoding="utf-8"
    )

    print("\n" + "=" * 78)
    print(
        f"{'signal':<15} {'valid':>7} {'invalid':>8} {'beat':>6} {'rate':>7} "
        f"{'FDR':>5} {'SURVIVE':>8} {'max|IC|':>9}"
    )
    for sg in ["qi", "ofi_l1", "mom", "plv_spread", "spread_stress", "kappa_forman"]:
        s = summary[sg]
        print(
            f"{sg:<15} {s['tests_valid']:>7} {s['tests_instrument_invalid']:>8} "
            f"{s['beat_noise_floor']:>6} {s['beat_rate']*100:>6.1f}% "
            f"{s['survive_fdr']:>5} {s['survive_full_rule']:>8} {s['max_abs_ic']:>9.5f}"
        )
    print("=" * 78)
    print(f"  null-expected beat rate: {NULL_PASS_RATE*100:.1f}%")
    print(f"\n  VERDICT: {verdict['VERDICT']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
