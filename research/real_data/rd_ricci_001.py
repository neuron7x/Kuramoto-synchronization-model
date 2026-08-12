#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""RD-RICCI-001 — execute the preregistered real-data test.

Protocol: ``docs/research/PREREG_REAL_DATA_RICCI_2026-07-13.md``, sealed before
any result existed (commit 523dfb67).

The instrument (``research/kernels/ricci_on_spread.py``) is used unmodified. This
file is the *protocol*, not the instrument: it fixes the horizons, the split, the
null models and the uncertainty estimator that the kernel does not carry.

Two deliberate departures from the kernel's own reporting, both preregistered:

* The kernel's permutation p-value is recorded but **not used for the decision**.
  Permuting one series destroys its autocorrelation, so the resulting null is far
  too narrow — it is anti-conservative for two serially correlated series. The
  decision uses a **moving-block bootstrap** (block 300 s) instead.
* The kernel's ``BREAKTHROUGH if IC >= 0.08`` threshold is not adopted. It has no
  derivation anywhere in the corpus.

Output: ``artifacts/research/rd_ricci_001/results.json``.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from research.kernels.ricci_on_spread import compute_ricci_features

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "real" / "prepared"
OUT = ROOT / "artifacts" / "research" / "rd_ricci_001"

# --- preregistered constants (do not change without an amendment) -------------
HORIZONS = (1, 2, 5, 10, 30, 60)
WINDOW = 60
THRESHOLD = 0.30
BLOCK = 300          # 5 minutes, in 1-second bars
N_BOOT = 2000
SEED = 42
ALPHA = 0.05
DISCOVERY = "2024-02"
VALIDATION = "2024-03"


@dataclass
class SessionResult:
    session: str
    split: str
    bars: int
    dead_node_windows: int
    dead_node_frac: float
    ic: dict[str, float]


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 30:
        return float("nan")
    r = spearmanr(x, y).statistic
    return float(r) if np.isfinite(r) else float("nan")


def _block_bootstrap_ci(
    x: np.ndarray, y: np.ndarray, rng: np.random.Generator
) -> tuple[float, float]:
    """Moving-block bootstrap CI for Spearman IC.

    A naive permutation or i.i.d. bootstrap destroys the serial correlation of both
    series and yields an interval that is far too tight. Resampling *blocks* keeps
    the local dependence structure intact, which is the whole point when both the
    signal and the target are strongly autocorrelated.
    """
    n = len(x)
    if n < BLOCK * 3:
        return (float("nan"), float("nan"))
    # Spearman == Pearson on ranks. Ranking once and bootstrapping the ranks is the
    # standard implementation and is ~200x faster than re-running scipy's spearmanr
    # inside the loop (96,000 calls on 86k-point arrays is not a viable budget).
    from scipy.stats import rankdata

    rx = rankdata(x).astype(np.float64)
    ry = rankdata(y).astype(np.float64)
    n_blocks = n // BLOCK
    starts_pool = n - BLOCK
    offs = np.arange(BLOCK)
    stats = np.empty(N_BOOT)
    for b in range(N_BOOT):
        starts = rng.integers(0, starts_pool, size=n_blocks)
        idx = (starts[:, None] + offs[None, :]).ravel()
        a = rx[idx]
        c = ry[idx]
        a = a - a.mean()
        c = c - c.mean()
        den = np.sqrt((a * a).sum() * (c * c).sum())
        stats[b] = (a * c).sum() / den if den > 0 else np.nan
    stats = stats[np.isfinite(stats)]
    if stats.size < N_BOOT // 2:
        return (float("nan"), float("nan"))
    return (float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5)))


def _dead_node_fraction(feat: pd.DataFrame) -> tuple[int, float]:
    """Windows in which at least one feature has zero variance.

    On a liquid crypto perpetual the top-of-book spread is pinned at one tick, so
    `spread` and `dspread` are constant over many 60-bar windows. The correlation
    matrix then has a NaN row. `core/physics/forman_ricci.py` deliberately passes
    that NaN through and counts it (`nonfinite_input_count`); the kernel's
    `np.nan_to_num(..., nan=0.0)` erases the count before the core ever sees it.
    The curvature is unaffected (verified: |Δκ| = 0 exactly, because an excluded
    edge and a below-threshold edge are the same edge), but the operator loses the
    only signal that the graph had a dead node.
    """
    from numpy.lib.stride_tricks import sliding_window_view

    v = feat.to_numpy(dtype=float)
    if len(v) < WINDOW:
        return 0, 0.0
    var = sliding_window_view(v, WINDOW, axis=0).var(axis=2)
    dead = (var < 1e-30).any(axis=1)
    return int(dead.sum()), float(dead.mean())


def _nulls(kappa: np.ndarray, target: np.ndarray, rng: np.random.Generator) -> dict[str, float]:
    """N1–N4 from the preregistration. Each returns |IC| under that null."""
    n = len(kappa)
    out: dict[str, float] = {}

    # N1 — shuffle kappa (destroys alignment, keeps marginals)
    out["N1_shuffle_kappa"] = abs(_spearman(rng.permutation(kappa), target))

    # N2 — circular shift of kappa by >= 1 h (PRESERVES autocorrelation of both).
    #      This is the decisive control: it is the only null under which two
    #      autocorrelated series keep everything except their alignment.
    shifts = rng.integers(3600, max(3601, n - 3600), size=20)
    out["N2_circshift_kappa"] = float(
        np.median([abs(_spearman(np.roll(kappa, int(s)), target)) for s in shifts])
    )

    # N3 — AR(1) surrogate of the target, fitted per session
    t = target - target.mean()
    phi = float(np.corrcoef(t[:-1], t[1:])[0, 1]) if n > 2 else 0.0
    phi = float(np.clip(phi, -0.99, 0.99))
    e = rng.normal(0.0, float(np.std(t)) * np.sqrt(max(1e-12, 1 - phi**2)), size=n)
    sur = np.empty(n)
    sur[0] = e[0]
    for i in range(1, n):
        sur[i] = phi * sur[i - 1] + e[i]
    out["N3_ar1_surrogate_target"] = abs(_spearman(kappa, sur))

    # N4 — a smooth slow variable with kappa's own autocorrelation, carrying no info
    k = kappa - kappa.mean()
    phi_k = float(np.corrcoef(k[:-1], k[1:])[0, 1]) if n > 2 else 0.0
    phi_k = float(np.clip(phi_k, -0.99, 0.99))
    e2 = rng.normal(0.0, 1.0, size=n)
    fake = np.empty(n)
    fake[0] = e2[0]
    for i in range(1, n):
        fake[i] = phi_k * fake[i - 1] + e2[i]
    out["N4_random_smooth_feature"] = abs(_spearman(fake, target))
    return out


def holm_bonferroni(pvals: list[float], alpha: float = ALPHA) -> list[bool]:
    m = len(pvals)
    order = np.argsort(pvals)
    reject = [False] * m
    for rank, i in enumerate(order):
        if pvals[i] <= alpha / (m - rank):
            reject[i] = True
        else:
            break
    return reject


RAW = ROOT / "data" / "real" / "binance_bookticker"


def prepare() -> list[Path]:
    """Add `mid_returns` — the kernel's declared input contract.

    Kept out of the ingest on purpose: the ingested file holds only what the venue
    published (bid, ask, sizes). A derived column stored next to raw bytes is a
    place for drift to hide. Here it is recomputed from the raw file every run.
    """
    DATA.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for src in sorted(RAW.glob("*-bookticker-1000ms.csv")):
        dst = DATA / src.name
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            df = pd.read_csv(src)
            mid = (df["bid_close"] + df["ask_close"]) / 2.0
            df["mid_returns"] = np.log(mid / mid.shift(1))
            df.to_csv(dst, index=False)
        out.append(dst)
    return out


def main() -> int:
    rng = np.random.default_rng(SEED)
    files = prepare()
    if not files:
        print("no ingested sessions found", file=sys.stderr)
        return 1

    sessions: list[SessionResult] = []
    nulls_all: dict[str, dict[str, float]] = {}
    ci_all: dict[str, dict[str, list[float]]] = {}

    for f in files:
        name = f.stem.replace("-bookticker-1000ms", "")
        split = DISCOVERY if DISCOVERY in name else VALIDATION
        feat, kappa = compute_ricci_features(f, window=WINDOW, threshold=THRESHOLD)
        dead_n, dead_f = _dead_node_fraction(feat)

        ics: dict[str, float] = {}
        cis: dict[str, list[float]] = {}
        for h in HORIZONS:
            tgt = feat["mid_r"].shift(-h)
            j = pd.concat([kappa, tgt], axis=1).dropna()
            x = j.iloc[:, 0].to_numpy()
            y = j.iloc[:, 1].to_numpy()
            ics[str(h)] = _spearman(x, y)
            lo, hi = _block_bootstrap_ci(x, y, rng)
            cis[str(h)] = [lo, hi]

        # nulls at the single horizon the kernel itself uses (h = 1)
        tgt1 = feat["mid_r"].shift(-1)
        j1 = pd.concat([kappa, tgt1], axis=1).dropna()
        nulls_all[name] = _nulls(j1.iloc[:, 0].to_numpy(), j1.iloc[:, 1].to_numpy(), rng)
        ci_all[name] = cis

        sessions.append(
            SessionResult(
                session=name,
                split=split,
                bars=int(len(feat)),
                dead_node_windows=dead_n,
                dead_node_frac=round(dead_f, 4),
                ic={k: (round(v, 5) if np.isfinite(v) else None) for k, v in ics.items()},
            )
        )
        print(
            f"  {name:22s} [{split}]  bars={len(feat):>7,}  "
            f"dead={dead_f*100:5.2f}%  IC(h=1)={ics['1']:+.5f}",
            flush=True,
        )

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "protocol": "docs/research/PREREG_REAL_DATA_RICCI_2026-07-13.md",
        "instrument": "research/kernels/ricci_on_spread.py (unmodified)",
        "seed": SEED,
        "horizons": list(HORIZONS),
        "block_bootstrap": {"block_bars": BLOCK, "resamples": N_BOOT},
        "sessions": [asdict(s) for s in sessions],
        "bootstrap_ci": ci_all,
        "nulls_h1": nulls_all,
    }
    (OUT / "results.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {(OUT / 'results.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
