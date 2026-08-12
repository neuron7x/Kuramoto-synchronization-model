"""Ricci wide-panel final validation — 3-D gate with VIX/HYG orthogonality.

Closes the Askar cycle per the closing brief. Runs the exact 5-step
pipeline the user specified:

  STEP 1  — core panel   = {USA_500_Index, XAUUSD, SPDR_S_P_500_ETF}
  STEP 2  — ricci_core   = rolling Forman-Ricci mean curvature
            (window=60h, |corr| > 0.30)
  STEP 3  — orthogonality gate on kappa_core vs VIX / HYG returns;
            hard-ABORT if |corr| ≥ 0.30 on either.
  STEP 4  — wide panel  = core + {VIX ETN, HYG, TLT7-10, DXY},
            kappa_wide on the 7-node correlation graph
  STEP 5  — three-D verdict:
              DETECT       IC(kappa_wide, fwd_SPX_1h) ≥ 0.08  (perm p < 0.10)
              DISCRIMINATE |corr(kappa_wide, mom_20)| < 0.15 AND
                           |corr(kappa_wide, vol_10)| < 0.15
              DELIVER      run_stress_detector.lead_capture_rate ≥ 0.60

FINAL = SIGNAL_READY iff all three D's pass, else REJECT.

Substrate = data/askar_full/panel_hourly_extended.parquet
  (built once by this module's ``_build_extended_panel`` from the
  committed base panel + 4 raw parquets living in the external Askar
  archive; the extended file is committed so this run is reproducible).

Output: results/verdict_wide_panel.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from research.askar.prime_architect_vx import _permutation_test
from research.askar.stress_detector import run_stress_detector

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENDED_PANEL_PATH = REPO_ROOT / "data" / "askar_full" / "panel_hourly_extended.parquet"
RESULTS_PATH = REPO_ROOT / "results" / "verdict_wide_panel.json"

CORE_COLS: tuple[str, ...] = (
    "USA_500_Index",
    "XAUUSD",
    "SPDR_S_P_500_ETF",
)
EXTRA_COLS: tuple[str, ...] = (
    "iPath_S_P_500_VIX_ST_Futures_ETN",
    "SPDR_Barclays_Capital_High_Yield_Bond_ETF",
    "iShares_7_10_Year_Treasury_Bond_ETF",
    "US_Dollar_Index",
)
WIDE_COLS: tuple[str, ...] = CORE_COLS + EXTRA_COLS
TARGET_COL = "USA_500_Index"
VIX_COL = "iPath_S_P_500_VIX_ST_Futures_ETN"
HYG_COL = "SPDR_Barclays_Capital_High_Yield_Bond_ETF"

WINDOW = 60
THRESHOLD = 0.30
MOMENTUM_WINDOW = 20
VOL_WINDOW = 10

# Gate thresholds (3-D rubric)
ORTHOGONALITY_GATE = 0.30
IC_GATE = 0.08
P_GATE = 0.10
CORR_FACTOR_GATE = 0.15
LEAD_CAPTURE_GATE = 0.60
PERMUTATIONS = 500


# -------------------------------------------------------------------- #
# Primitives
# -------------------------------------------------------------------- #


def _scorr(a: pd.Series, b: pd.Series) -> float:
    common = pd.concat([a, b], axis=1).dropna()
    if len(common) < 30:
        return float("nan")
    rho, _ = spearmanr(common.iloc[:, 0], common.iloc[:, 1])
    return float(rho) if np.isfinite(rho) else float("nan")


def _rolling_ricci_mean(
    returns: pd.DataFrame, window: int = WINDOW, threshold: float = THRESHOLD
) -> pd.Series:
    """Rolling mean Forman-Ricci curvature on the correlation graph.

    κ̄(t) = mean_{e∈E(t)} (4 − deg(u) − deg(v))
    where E(t) = {edges with |corr| > threshold over the last W bars}.
    Returns NaN when the graph has no active edges.
    """
    arr = returns.to_numpy(dtype=float)
    n, k = arr.shape
    out = pd.Series(np.nan, index=returns.index, dtype=float)

    for i in range(window, n):
        w = arr[i - window : i]
        corr = np.corrcoef(w.T)
        np.fill_diagonal(corr, 0.0)
        adj = (np.abs(corr) > threshold).astype(float)
        deg = adj.sum(axis=1)
        edges = [4.0 - deg[u] - deg[v] for u in range(k) for v in range(u + 1, k) if adj[u, v] > 0]
        if edges:
            out.iloc[i] = float(np.mean(edges))
    return out


# -------------------------------------------------------------------- #
# Orchestration
# -------------------------------------------------------------------- #


def _load_extended_panel() -> pd.DataFrame:
    if not EXTENDED_PANEL_PATH.exists():
        raise FileNotFoundError(
            f"missing extended panel: {EXTENDED_PANEL_PATH}. "
            "Rebuild via research.askar.ricci_wide_panel_final._build_extended_panel()."
        )
    prices = pd.read_parquet(EXTENDED_PANEL_PATH)
    prices.index = pd.to_datetime(prices.index)
    prices = prices.sort_index()
    for col in WIDE_COLS:
        if col not in prices.columns:
            raise KeyError(f"extended panel missing required column: {col!r}")
    return prices


def _save_verdict(verdict: dict[str, Any]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(verdict, indent=2))


def run() -> dict[str, Any]:
    prices = _load_extended_panel()
    ratio = prices / prices.shift(1)
    log_arr = np.log(ratio.to_numpy())
    returns_full = (
        pd.DataFrame(log_arr, index=ratio.index, columns=ratio.columns)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )

    # --- STEP 1: core panel ---
    returns_core = returns_full[list(CORE_COLS)].dropna()

    # --- STEP 2: Ricci on core ---
    kappa_core = _rolling_ricci_mean(returns_core, window=WINDOW, threshold=THRESHOLD)

    # --- STEP 3: orthogonality gate vs VIX / HYG returns ---
    vix_ret = returns_full[VIX_COL]
    hyg_ret = returns_full[HYG_COL]
    corr_vix = _scorr(kappa_core, vix_ret)
    corr_hyg = _scorr(kappa_core, hyg_ret)

    gate_passed = bool(
        np.isfinite(corr_vix)
        and np.isfinite(corr_hyg)
        and abs(corr_vix) < ORTHOGONALITY_GATE
        and abs(corr_hyg) < ORTHOGONALITY_GATE
    )
    if not gate_passed:
        verdict: dict[str, Any] = {
            "substrate": {
                "source": str(EXTENDED_PANEL_PATH.relative_to(REPO_ROOT)),
                "n_assets_extended": int(prices.shape[1]),
                "n_bars_extended": int(len(prices)),
                "first_ts": str(prices.index.min()),
                "last_ts": str(prices.index.max()),
            },
            "gate": {
                "corr_vix": round(float(corr_vix), 6),
                "corr_hyg": round(float(corr_hyg), 6),
                "gate_threshold": ORTHOGONALITY_GATE,
                "gate_passed": False,
            },
            "verdict": "ABORT",
            "reason": (
                "orthogonality_gate_failed: |corr(kappa_core, vix_returns)| "
                f"= {abs(corr_vix):.4f}, "
                f"|corr(kappa_core, hyg_returns)| = {abs(corr_hyg):.4f}; "
                f"at least one ≥ {ORTHOGONALITY_GATE}"
            ),
            "DETECT": "SKIPPED",
            "DISCRIMINATE": "SKIPPED",
            "DELIVER": "SKIPPED",
            "FINAL": "ABORT",
        }
        _save_verdict(verdict)
        print(json.dumps(verdict, indent=2))
        return verdict

    # --- STEP 4: wide panel ---
    returns_wide = returns_full[list(WIDE_COLS)].dropna()
    kappa_wide = _rolling_ricci_mean(returns_wide, window=WINDOW, threshold=THRESHOLD)

    # --- STEP 5: three-D verdict ---
    target = returns_wide[TARGET_COL].shift(-1)
    _ic_perm, p_val, sigma_val = _permutation_test(kappa_wide, target, n=PERMUTATIONS, seed=42)
    ic_test = _scorr(kappa_wide, target)

    momentum_20 = returns_wide[TARGET_COL].rolling(MOMENTUM_WINDOW).sum()
    vol_10 = returns_wide[TARGET_COL].rolling(VOL_WINDOW).std()
    corr_m = _scorr(kappa_wide, momentum_20)
    corr_v = _scorr(kappa_wide, vol_10)

    stress_prices = prices[list(WIDE_COLS)].dropna()
    _stress_sig, _stress_alerts, stress_report = run_stress_detector(
        stress_prices, target_asset=TARGET_COL, unity_window=WINDOW
    )
    lead_capture = float(stress_report.lead_capture_rate)

    detect = bool(np.isfinite(ic_test) and ic_test >= IC_GATE and p_val < P_GATE)
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
            "n_assets_extended": int(prices.shape[1]),
            "n_bars_extended": int(len(prices)),
            "core_cols": list(CORE_COLS),
            "wide_cols": list(WIDE_COLS),
            "n_core_bars": int(len(returns_core)),
            "n_wide_bars": int(len(returns_wide)),
            "first_ts": str(returns_wide.index.min()),
            "last_ts": str(returns_wide.index.max()),
        },
        "gate": {
            "corr_vix": round(float(corr_vix), 6),
            "corr_hyg": round(float(corr_hyg), 6),
            "gate_threshold": ORTHOGONALITY_GATE,
            "gate_passed": True,
        },
        "window": WINDOW,
        "threshold": THRESHOLD,
        "permutations": PERMUTATIONS,
        "IC": round(float(ic_test), 6),
        "permutation_ic": round(float(_ic_perm), 6),
        "p_value": round(float(p_val), 6),
        "permutation_sigma": round(float(sigma_val), 4),
        "corr_momentum": round(float(corr_m), 6),
        "corr_vol": round(float(corr_v), 6),
        "stress_detector": stress_report.to_dict(),
        "lead_capture": round(lead_capture, 6),
        "DETECT": "PASS" if detect else "FAIL",
        "DISCRIMINATE": "PASS" if discriminate else "FAIL",
        "DELIVER": "PASS" if deliver else "FAIL",
        "FINAL": "SIGNAL_READY" if final_pass else "REJECT",
    }
    _save_verdict(verdict)
    print(json.dumps(verdict, indent=2))
    return verdict


if __name__ == "__main__":
    run()
