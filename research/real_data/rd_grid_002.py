#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""RD-GRID-002 — the exhaustion grid.

Protocol: ``docs/research/PREREG_RD_GRID_002_2026-07-13.md``, sealed before any grid
result existed (commit e5c3c31f).

8 symbols x 4 dates x 3 bar sizes x 6 signals x 6 horizons = 3456 tests. All reported.

Three outcomes are kept distinct, because conflating the first two is how a corpus
accumulates false nulls:

    INSTRUMENT_INVALID  the kernel's precondition fails here; nothing is learned
    NULL                the kernel ran validly and found nothing beyond its noise floor
    SIGNAL              the kernel ran validly and beat every null

`qi` (queue imbalance) is the **positive control**: the canonical top-of-book predictor
from the microstructure literature, not a GeoSync instrument. If it lights up and the
GeoSync signals do not, the null is attributable to the instruments. If it also fails,
the harness is broken and the grid is void — that is what gets reported.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import hilbert
from scipy.stats import rankdata, spearmanr

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "real" / "binance_bookticker"
OUT = ROOT / "artifacts" / "research" / "rd_grid_002"

# --- preregistered constants --------------------------------------------------
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "ADAUSDT", "ALGOUSDT", "CELRUSDT", "RVNUSDT")
DISCOVERY_DATES = ("2024-02-05", "2024-02-20")
VALIDATION_DATES = ("2024-03-06", "2024-03-19")
BARS = (1, 10, 60)                       # seconds
HORIZONS = (1, 2, 5, 10, 30, 60)         # bars
SIGNALS = ("kappa_forman", "qi", "ofi_l1", "spread_stress", "plv_spread", "mom")
WINDOW = 60                              # bars, the kernel's own window
N_SHIFTS = 20                            # circular shifts for the noise floor
N_BOOT = 2000
BLOCK_SECONDS = 300
SEED = 42
DEAD_MAX = 0.20                          # > 20% dead windows => INSTRUMENT_INVALID
FDR_Q = 0.05


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 200:
        return float("nan")
    r = spearmanr(x[m], y[m]).statistic
    return float(r) if np.isfinite(r) else float("nan")


def load_bars(symbol: str, date: str, bar_s: int) -> pd.DataFrame | None:
    f = RAW / f"{symbol}-{date}-bookticker-1000ms.csv"
    if not f.is_file():
        return None
    df = pd.read_csv(f)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").set_index("ts")
    if bar_s > 1:
        # Deterministic downsample: the LAST quote inside each bin, exactly as the
        # 1s bars were built from ticks. No interpolation, no forward-fill across
        # empty bins — an empty bin is a bin with no quote, not a repeated quote.
        df = df.resample(f"{bar_s}s").last().dropna(subset=["bid_close", "ask_close"])
    mid = (df["bid_close"] + df["ask_close"]) / 2.0
    df["mid"] = mid
    df["spread"] = df["ask_close"] - df["bid_close"]
    df["mid_returns"] = np.log(mid / mid.shift(1))
    return df.dropna(subset=["mid_returns"])


def dead_window_fraction(df: pd.DataFrame) -> float:
    """Windows containing a zero-variance feature — the kernel's precondition."""
    from numpy.lib.stride_tricks import sliding_window_view

    feat = pd.DataFrame(
        {
            "bid_r": np.log(df["bid_close"] / df["bid_close"].shift(1)),
            "ask_r": np.log(df["ask_close"] / df["ask_close"].shift(1)),
            "spread": df["spread"],
            "mid_r": df["mid_returns"],
            "dspread": df["spread"].diff(),
        }
    ).replace([np.inf, -np.inf], np.nan).dropna()
    v = feat.to_numpy(float)
    if len(v) < WINDOW + 1:
        return 1.0
    var = sliding_window_view(v, WINDOW, axis=0).var(axis=2)
    return float((var < 1e-30).any(axis=1).mean())


# --- signals ------------------------------------------------------------------


def sig_kappa_forman(df: pd.DataFrame) -> pd.Series:
    """The GeoSync instrument, unmodified path through core/physics/forman_ricci.py."""
    from geosync.core.physics.forman_ricci import FormanRicciCurvature

    feat = pd.DataFrame(
        {
            "bid_r": np.log(df["bid_close"] / df["bid_close"].shift(1)),
            "ask_r": np.log(df["ask_close"] / df["ask_close"].shift(1)),
            "spread": df["spread"],
            "mid_r": df["mid_returns"],
            "dspread": df["spread"].diff(),
        }
    ).replace([np.inf, -np.inf], np.nan).dropna()
    ricci = FormanRicciCurvature(threshold=0.30)
    v = feat.to_numpy(float)
    out = pd.Series(np.nan, index=feat.index)
    for t in range(WINDOW - 1, len(feat)):
        w = v[t - WINDOW + 1 : t + 1]
        with np.errstate(invalid="ignore"):
            corr = np.corrcoef(w, rowvar=False)
        out.iloc[t] = ricci.compute_from_correlation(
            np.atleast_2d(np.asarray(corr, dtype=float))
        ).kappa_mean
    return out.dropna()


def sig_qi(df: pd.DataFrame) -> pd.Series:
    """POSITIVE CONTROL — queue imbalance. Canonical, not a GeoSync instrument."""
    b, a = df["bid_volume"], df["ask_volume"]
    return ((b - a) / (b + a)).replace([np.inf, -np.inf], np.nan).dropna()


def sig_ofi_l1(df: pd.DataFrame) -> pd.Series:
    """Order-flow imbalance at L1 (Cont–Kukanov–Stoikov construction), rolled over WINDOW."""
    bp, bq = df["bid_close"].to_numpy(), df["bid_volume"].to_numpy()
    ap, aq = df["ask_close"].to_numpy(), df["ask_volume"].to_numpy()
    e = np.zeros(len(df))
    e[1:] = (
        np.where(bp[1:] >= bp[:-1], bq[1:], 0.0)
        - np.where(bp[1:] <= bp[:-1], bq[:-1], 0.0)
        - np.where(ap[1:] <= ap[:-1], aq[1:], 0.0)
        + np.where(ap[1:] >= ap[:-1], aq[:-1], 0.0)
    )
    return pd.Series(e, index=df.index).rolling(WINDOW).sum().dropna()


def sig_spread_stress(df: pd.DataFrame) -> pd.Series:
    s = df["spread"]
    z = (s - s.rolling(WINDOW).mean()) / s.rolling(WINDOW).std()
    return z.replace([np.inf, -np.inf], np.nan).dropna()


def sig_plv_spread(df: pd.DataFrame) -> pd.Series:
    """Phase-locking value between mid-return and spread, via the analytic signal."""
    r = df["mid_returns"].to_numpy(float)
    s = df["spread"].to_numpy(float)
    if np.std(s) < 1e-30 or np.std(r) < 1e-30:
        return pd.Series(dtype=float)
    pr = np.angle(hilbert(r - r.mean()))
    ps = np.angle(hilbert(s - s.mean()))
    z = pd.Series(np.exp(1j * (pr - ps)), index=df.index)
    return z.rolling(WINDOW).mean().abs().dropna()


def sig_mom(df: pd.DataFrame) -> pd.Series:
    return df["mid_returns"].rolling(WINDOW).sum().dropna()


SIGNAL_FN = {
    "kappa_forman": sig_kappa_forman,
    "qi": sig_qi,
    "ofi_l1": sig_ofi_l1,
    "spread_stress": sig_spread_stress,
    "plv_spread": sig_plv_spread,
    "mom": sig_mom,
}


# --- statistics ---------------------------------------------------------------


def noise_floor(sig: np.ndarray, tgt: np.ndarray, rng: np.random.Generator, bar_s: int) -> float:
    """Max |IC| over circular shifts >= 1 h. Preserves both autocorrelations, destroys
    only the alignment: the only fair null for two serially correlated series."""
    n = len(sig)
    lo = max(1, 3600 // bar_s)
    if n <= 2 * lo:
        return float("nan")
    shifts = rng.integers(lo, n - lo, size=N_SHIFTS)
    return float(max(abs(_spearman(np.roll(sig, int(s)), tgt)) for s in shifts))


def block_bootstrap_ci(
    sig: np.ndarray, tgt: np.ndarray, rng: np.random.Generator, bar_s: int
) -> tuple[float, float]:
    block = max(5, BLOCK_SECONDS // bar_s)
    n = len(sig)
    if n < block * 5:
        return (float("nan"), float("nan"))
    rx, ry = rankdata(sig).astype(float), rankdata(tgt).astype(float)
    nb, pool, offs = n // block, n - block, np.arange(block)
    stats = np.empty(N_BOOT)
    for b in range(N_BOOT):
        idx = (rng.integers(0, pool, size=nb)[:, None] + offs[None, :]).ravel()
        a, c = rx[idx], ry[idx]
        a, c = a - a.mean(), c - c.mean()
        den = np.sqrt((a * a).sum() * (c * c).sum())
        stats[b] = (a * c).sum() / den if den > 0 else np.nan
    stats = stats[np.isfinite(stats)]
    if stats.size < N_BOOT // 2:
        return (float("nan"), float("nan"))
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def bh_fdr(pvals: list[float], q: float = FDR_Q) -> list[bool]:
    m = len(pvals)
    order = np.argsort(pvals)
    thresh = [(i + 1) / m * q for i in range(m)]
    reject = [False] * m
    kmax = -1
    for i, oi in enumerate(order):
        if pvals[oi] <= thresh[i]:
            kmax = i
    for i, oi in enumerate(order):
        if i <= kmax:
            reject[oi] = True
    return reject


def main() -> int:
    rng = np.random.default_rng(SEED)
    rows: list[dict] = []
    precond: dict[str, float] = {}

    for sym in SYMBOLS:
        for date in DISCOVERY_DATES + VALIDATION_DATES:
            for bar in BARS:
                df = load_bars(sym, date, bar)
                if df is None or len(df) < WINDOW * 5:
                    continue
                dead = dead_window_fraction(df)
                precond[f"{sym}|{date}|{bar}s"] = round(dead, 4)
                invalid = dead > DEAD_MAX

                for signame in SIGNALS:
                    try:
                        sig = SIGNAL_FN[signame](df)
                    except Exception as exc:  # a signal that cannot run is not a null
                        rows.append(
                            {"symbol": sym, "date": date, "bar_s": bar, "signal": signame,
                             "outcome": "SIGNAL_ERROR", "error": repr(exc)[:80]}
                        )
                        continue
                    if len(sig) < WINDOW * 5:
                        continue

                    for h in HORIZONS:
                        tgt = df["mid_returns"].shift(-h)
                        j = pd.concat([sig.rename("s"), tgt.rename("t")], axis=1).dropna()
                        if len(j) < 500:
                            continue
                        x, y = j["s"].to_numpy(), j["t"].to_numpy()
                        ic = _spearman(x, y)
                        nf = noise_floor(x, y, rng, bar)
                        # kappa's precondition can fail; the others do not depend on it
                        cell_invalid = invalid and signame == "kappa_forman"
                        rows.append(
                            {
                                "symbol": sym, "date": date, "bar_s": bar, "signal": signame,
                                "horizon": h, "split": "discovery" if date in DISCOVERY_DATES else "validation",
                                "n": int(len(j)),
                                "ic": None if not np.isfinite(ic) else round(float(ic), 6),
                                "noise_floor": None if not np.isfinite(nf) else round(float(nf), 6),
                                "dead_frac": round(dead, 4),
                                "outcome": "INSTRUMENT_INVALID" if cell_invalid
                                else ("CANDIDATE" if np.isfinite(ic) and np.isfinite(nf) and abs(ic) > nf
                                      else "NULL"),
                            }
                        )
            print(f"  {sym} {date} done ({len(rows)} tests so far)", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "grid.json").write_text(
        json.dumps({"precondition_map": precond, "tests": rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n{len(rows)} tests -> {(OUT / 'grid.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
