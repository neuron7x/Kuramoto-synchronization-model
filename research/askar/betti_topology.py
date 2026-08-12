"""Betti-1 topology signal on Askar's 57-asset extended hourly panel.

Topologically distinct from Forman-Ricci (PR #194/#197): Ricci is a
local per-edge curvature, B₁ is a global invariant counting
independent cycles in the 1-skeleton of the Vietoris-Rips complex
built from the rolling correlation graph.

Grounding: Gidea & Katz (2018) "Topological data analysis of financial
time series" — Betti-1 shows documented pre-crash lift 10-20 days
ahead of equity index drawdowns, which lines up with the 10-30 bar
lead-capture window we track in the stress-detector gate.

Formula (1-skeleton, O(edges) per bar, numpy + scipy only):

    B₁(t) = |E(t)| − |V| + k(t)

  where
    E(t) = set of edges with |corr(returns[t−W:t])| > threshold
    V    = 57 (number of panel assets, constant)
    k(t) = number of connected components of the adjacency matrix
           (scipy.sparse.csgraph.connected_components)

Same 3-D gate as ricci_wide_panel_final:
    DETECT       IC(B₁, fwd_SPX_1h) ≥ 0.08 AND permutation p < 0.10
    DISCRIMINATE |corr(B₁, mom_20)| < 0.15 AND |corr(B₁, vol_10)| < 0.15
    DELIVER      alerts(B₁ > expanding Q90) lead ≥ 60 % of
                 future 20-bar cumulative SPX drawdown events (< −5 %)

Output: results/betti1_verdict.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.sparse.csgraph import connected_components
from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENDED_PANEL_PATH = REPO_ROOT / "data" / "askar_full" / "panel_hourly_extended.parquet"
VERDICT_PATH = REPO_ROOT / "results" / "betti1_verdict.json"

WINDOW = 60
THRESHOLD = 0.30
MOMENTUM_WINDOW = 20
VOL_WINDOW = 10
PERMUTATIONS = 500
LEAD_FWD_WINDOW = 20
LEAD_LOOKBACK_MAX = 30
LEAD_LOOKBACK_MIN = 10
DRAWDOWN_THRESHOLD = -0.05

IC_GATE = 0.08
P_GATE = 0.10
CORR_FACTOR_GATE = 0.15
LEAD_CAPTURE_GATE = 0.60

TARGET_COL = "USA_500_Index"
VIX_LIKE = "VIX"
HYG_LIKE = "High_Yield"


# -------------------------------------------------------------------- #
# Core computation: B₁ = |E| − |V| + k
# -------------------------------------------------------------------- #


def compute_betti1(
    returns: pd.DataFrame,
    window: int = WINDOW,
    threshold: float = THRESHOLD,
) -> pd.Series:
    """Rolling first Betti number of the thresholded correlation graph.

    B₁ is the dimension of the 1-cycle space of the 1-skeleton:
        B₁ = |E| − |V| + k
    where k is the number of connected components. Computed in
    O(edges) per bar via scipy.sparse.csgraph.connected_components.
    """
    vals = returns.to_numpy(dtype=float)
    n_bars, n_assets = vals.shape
    out = pd.Series(np.nan, index=returns.index, dtype=float)
    if n_bars < window or n_assets < 2:
        return out

    for t in range(window - 1, n_bars):
        w = vals[t - window + 1 : t + 1]
        corr = np.corrcoef(w, rowvar=False)
        corr = np.nan_to_num(corr, nan=0.0)
        adj = (np.abs(corr) > threshold).astype(int)
        np.fill_diagonal(adj, 0)
        edges = int(adj.sum() // 2)
        n_comp_raw, _ = connected_components(adj, directed=False)
        n_comp = int(n_comp_raw)
        out.iloc[t] = float(edges - n_assets + n_comp)
    return out


# -------------------------------------------------------------------- #
# Statistical primitives (inline, zero-dependency beyond scipy)
# -------------------------------------------------------------------- #


def _scorr(a: pd.Series, b: pd.Series) -> float:
    frame = pd.concat([a, b], axis=1).dropna()
    if len(frame) < 30:
        return 0.0
    rho, _ = spearmanr(frame.iloc[:, 0], frame.iloc[:, 1])
    return float(rho) if np.isfinite(rho) else 0.0


def _permutation_pvalue(
    signal: pd.Series,
    target: pd.Series,
    permutations: int = PERMUTATIONS,
    seed: int = 42,
) -> float:
    frame = pd.concat([signal, target], axis=1).dropna()
    if len(frame) < 30:
        return 1.0
    x = frame.iloc[:, 0].to_numpy(dtype=float)
    y = frame.iloc[:, 1].to_numpy(dtype=float)
    obs_raw = float(spearmanr(x, y).statistic)
    obs = abs(obs_raw) if np.isfinite(obs_raw) else 0.0
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(permutations):
        y_perm = rng.permutation(y)
        s_raw = float(spearmanr(x, y_perm).statistic)
        s = abs(s_raw) if np.isfinite(s_raw) else 0.0
        if s >= obs:
            count += 1
    return float((count + 1) / (permutations + 1))


def _lead_capture(b1: pd.Series, fwd_cum: pd.Series, threshold: float) -> tuple[float, int, int]:
    alerts = b1 > b1.expanding().quantile(0.90)
    drawdown_events = fwd_cum[fwd_cum < threshold]
    if len(drawdown_events) == 0:
        return 0.0, 0, 0
    captured = 0
    for ts in drawdown_events.index:
        loc = alerts.index.get_loc(ts)
        if not isinstance(loc, int):
            continue
        lo = max(0, int(loc) - LEAD_LOOKBACK_MAX)
        hi = max(0, int(loc) - LEAD_LOOKBACK_MIN)
        if hi > lo and bool(alerts.iloc[lo:hi].any()):
            captured += 1
    return float(captured / len(drawdown_events)), captured, int(len(drawdown_events))


# -------------------------------------------------------------------- #
# Orchestration
# -------------------------------------------------------------------- #


def run() -> dict[str, Any]:
    if not EXTENDED_PANEL_PATH.exists():
        raise FileNotFoundError(
            f"PRIME_ARCHITECT HALT: missing extended panel: {EXTENDED_PANEL_PATH}"
        )
    prices = pd.read_parquet(EXTENDED_PANEL_PATH)
    prices.index = pd.to_datetime(prices.index)
    prices = prices.sort_index()

    ratio = prices / prices.shift(1)
    log_arr = np.log(ratio.to_numpy())
    returns = (
        pd.DataFrame(log_arr, index=ratio.index, columns=ratio.columns)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )

    b1 = compute_betti1(returns, window=WINDOW, threshold=THRESHOLD)
    target = returns[TARGET_COL].shift(-1)

    momentum_20 = returns[TARGET_COL].rolling(MOMENTUM_WINDOW).sum()
    vol_10 = returns[TARGET_COL].rolling(VOL_WINDOW).std()

    vix_frame = returns.filter(like=VIX_LIKE)
    hyg_frame = returns.filter(like=HYG_LIKE)
    vix_ret = (
        vix_frame.mean(axis=1)
        if vix_frame.shape[1] > 0
        else pd.Series(np.nan, index=returns.index, dtype=float)
    )
    hyg_ret = (
        hyg_frame.mean(axis=1)
        if hyg_frame.shape[1] > 0
        else pd.Series(np.nan, index=returns.index, dtype=float)
    )

    ic = _scorr(b1, target)
    p_value = _permutation_pvalue(b1, target, permutations=PERMUTATIONS)
    corr_m = _scorr(b1, momentum_20)
    corr_v = _scorr(b1, vol_10)
    corr_vix = _scorr(b1, vix_ret)
    corr_hyg = _scorr(b1, hyg_ret)

    fwd_cum = returns[TARGET_COL].rolling(LEAD_FWD_WINDOW).sum().shift(-LEAD_FWD_WINDOW)
    lead_capture, captured_n, event_n = _lead_capture(b1, fwd_cum, DRAWDOWN_THRESHOLD)

    detect = bool(np.isfinite(ic) and ic >= IC_GATE and p_value < P_GATE)
    discriminate = bool(
        np.isfinite(corr_m)
        and np.isfinite(corr_v)
        and abs(corr_m) < CORR_FACTOR_GATE
        and abs(corr_v) < CORR_FACTOR_GATE
    )
    deliver = bool(lead_capture >= LEAD_CAPTURE_GATE)
    final_pass = detect and discriminate and deliver

    verdict = {
        "substrate": {
            "source": str(EXTENDED_PANEL_PATH.relative_to(REPO_ROOT)),
            "n_assets": int(returns.shape[1]),
            "n_bars": int(len(returns)),
            "first_ts": str(returns.index.min()),
            "last_ts": str(returns.index.max()),
            "window": WINDOW,
            "threshold": THRESHOLD,
            "permutations": PERMUTATIONS,
        },
        "b1_stats": {
            "mean": float(b1.dropna().mean()) if b1.notna().any() else None,
            "median": float(b1.dropna().median()) if b1.notna().any() else None,
            "p05": float(b1.dropna().quantile(0.05)) if b1.notna().any() else None,
            "p95": float(b1.dropna().quantile(0.95)) if b1.notna().any() else None,
            "max": float(b1.dropna().max()) if b1.notna().any() else None,
        },
        "IC": round(float(ic), 6),
        "p_value": round(float(p_value), 6),
        "corr_momentum": round(float(corr_m), 6),
        "corr_vol": round(float(corr_v), 6),
        "corr_vix": round(float(corr_vix), 6),
        "corr_hyg": round(float(corr_hyg), 6),
        "lead_capture": round(float(lead_capture), 6),
        "lead_capture_detail": {
            "captured": captured_n,
            "drawdown_events": event_n,
            "drawdown_threshold": DRAWDOWN_THRESHOLD,
            "fwd_window": LEAD_FWD_WINDOW,
            "lookback_bars": [LEAD_LOOKBACK_MIN, LEAD_LOOKBACK_MAX],
        },
        "DETECT": "PASS" if detect else "FAIL",
        "DISCRIMINATE": "PASS" if discriminate else "FAIL",
        "DELIVER": "PASS" if deliver else "FAIL",
        "FINAL": "SIGNAL_READY" if final_pass else "REJECT",
    }

    VERDICT_PATH.parent.mkdir(parents=True, exist_ok=True)
    VERDICT_PATH.write_text(json.dumps(verdict, indent=2))
    print(json.dumps(verdict, indent=2))
    return verdict


if __name__ == "__main__":
    run()
