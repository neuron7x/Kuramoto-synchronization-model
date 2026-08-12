"""Task 2 — OFI_Unity live microstructure kernel.

Honest-first implementation:
- computes OFI unity when bid/ask data exists,
- emits deterministic REJECT artifacts when sources/dependencies are unavailable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

SEED = 42
WINDOW = 60


@dataclass(frozen=True)
class SourceResult:
    source: str
    status: str
    reason: str
    rows: int


def ofi_unity_kernel(l2_df: pd.DataFrame, window: int = WINDOW) -> pd.Series:
    bid_cols = sorted([c for c in l2_df.columns if "bid" in str(c).lower()])
    ask_cols = [
        c.replace("bid", "ask") for c in bid_cols if c.replace("bid", "ask") in l2_df.columns
    ]
    if not bid_cols or len(ask_cols) != len(bid_cols):
        raise ValueError("Bid/ask columns are required for OFI unity kernel")
    if l2_df[bid_cols + ask_cols].isna().any().any():
        raise ValueError("NaN values are not allowed in OFI unity inputs")
    n = len(bid_cols)
    values = l2_df[bid_cols + ask_cols].to_numpy(dtype=float)
    unity: list[float] = []
    for t in range(window, len(l2_df)):
        w = values[t - window : t]
        ofi = np.zeros((window, n))
        for i in range(n):
            ofi[:, i] = w[:, i] - w[:, i + n]
        c = np.corrcoef(ofi.T) if n > 1 else np.array([[1.0]])
        c = np.nan_to_num(c, nan=0.0)
        eigenvalues = np.linalg.eigvalsh(c)
        unity.append(max(float(eigenvalues[-1]), 0.0) / n)
    return pd.Series(unity, index=l2_df.index[window:], name="unity")


def _perm_pvalue(x: np.ndarray, y: np.ndarray, n: int = 500, seed: int = SEED) -> float:
    obs = abs(_safe_spearman(x, y))
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(n):
        corr = abs(_safe_spearman(x, rng.permutation(y)))
        if corr >= obs:
            count += 1
    return float((count + 1) / (n + 1))


def _safe_spearman(x: np.ndarray | pd.Series, y: np.ndarray | pd.Series) -> float:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        val = float(spearmanr(x, y).statistic)
    return 0.0 if not np.isfinite(val) else val


def validate_unity(unity: pd.Series, target: pd.Series) -> dict[str, Any]:
    df = pd.concat([unity.rename("u"), target.rename("y")], axis=1, sort=False).dropna()
    if len(df) < 50:
        return {
            "IC": 0.0,
            "p_value": 1.0,
            "corr_momentum": 0.0,
            "corr_vol": 0.0,
            "lead_capture": 0.0,
            "DETECT": "FAIL",
            "DISCRIMINATE": "FAIL",
            "DELIVER": "FAIL",
            "FINAL": "REJECT",
            "reason": "insufficient_observations",
        }

    x = df["u"].to_numpy()
    y = df["y"].to_numpy()
    ic = _safe_spearman(x, y)
    p_val = _perm_pvalue(x, y)

    mom = target.rolling(20).sum().reindex(df.index)
    vol = target.rolling(10).std().reindex(df.index)
    corr_m = _safe_spearman(df["u"], mom)
    corr_v = _safe_spearman(df["u"], vol)

    alerts = unity < unity.expanding().quantile(0.8)
    dd = target.rolling(20).sum().shift(-20)
    events = dd[dd < -0.05]
    captured = 0
    for ts in events.index:
        if ts not in alerts.index:
            continue
        loc = alerts.index.get_loc(ts)
        lo = max(0, loc - 30)
        hi = max(0, loc - 10)
        if hi > lo and alerts.iloc[lo:hi].any():
            captured += 1
    lead_capture = float(captured / len(events)) if len(events) else 0.0

    return {
        "IC": round(ic, 4),
        "p_value": round(p_val, 4),
        "corr_momentum": round(corr_m, 4),
        "corr_vol": round(corr_v, 4),
        "lead_capture": round(lead_capture, 4),
        "DETECT": "PASS" if ic >= 0.08 else "FAIL",
        "DISCRIMINATE": "PASS" if abs(corr_m) < 0.15 and abs(corr_v) < 0.15 else "FAIL",
        "DELIVER": "PASS" if lead_capture >= 0.60 else "FAIL",
        "FINAL": (
            "SIGNAL_READY"
            if ic >= 0.08
            and p_val < 0.10
            and abs(corr_m) < 0.15
            and abs(corr_v) < 0.15
            and lead_capture >= 0.60
            else "REJECT"
        ),
    }


def _load_source_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return pd.read_csv(path, index_col=0, parse_dates=True)


def run(source: str, input_csv: Path | None, output: Path) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    lineage = {"source": source, "timestamp_utc": now}

    try:
        if input_csv is None:
            raise FileNotFoundError("input_csv not provided")
        df = _load_source_csv(input_csv)
        unity = ofi_unity_kernel(df, window=WINDOW)
        if "mid_returns" not in df.columns:
            # Silently falling back to df.columns[0] measured IC against a price
            # LEVEL, not a forward return — a meaningless verdict presented as
            # SIGNAL_READY/REJECT. Require the return column explicitly.
            raise ValueError("ofi_unity_live requires a 'mid_returns' column in the input CSV")
        verdict = validate_unity(unity, df["mid_returns"].shift(-1))
        verdict["lineage"] = lineage
    except Exception as exc:
        verdict = {
            "IC": 0.0,
            "p_value": 1.0,
            "corr_momentum": 0.0,
            "corr_vol": 0.0,
            "lead_capture": 0.0,
            "DETECT": "FAIL",
            "DISCRIMINATE": "FAIL",
            "DELIVER": "FAIL",
            "FINAL": "REJECT",
            "reason": str(exc),
            "lineage": lineage,
        }

    payload = json.dumps(verdict, sort_keys=True)
    verdict["replay_hash"] = hashlib.sha256(payload.encode()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(verdict, indent=2, sort_keys=True), encoding="utf-8")
    return verdict


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OFI unity live kernel")
    parser.add_argument("--source", choices=["dukascopy", "oanda", "databento"], required=True)
    parser.add_argument("--input-csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    verdict = run(source=args.source, input_csv=args.input_csv, output=args.output)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
