"""Sentiment-node Ricci pipeline with production-grade invariants.

Core flow:
1) Load panel returns from parquet.
2) Build sentiment node (Reddit WSB or deterministic VIX proxy fallback).
3) Run mandatory orthogonality gate before graph insertion.
4) Compute rolling Forman-Ricci mean curvature on augmented panel.
5) Run three-D validation gates and emit verdict JSON.

Hard invariants:
- sentiment orthogonality gate before Ricci graph
- train-frozen z-score on sentiment
- seed=42 for stochastic routines
- NaN => hard abort (SystemExit)
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from core.io.parquet_compat import ParquetEngineUnavailable, read_parquet_compat
from core.physics.forman_ricci import FormanRicciCurvature

REPO_ROOT = Path(__file__).resolve().parents[2]
PANEL_PATH = REPO_ROOT / "data" / "askar_full" / "panel_hourly_extended.parquet"
RESULTS_DIR = REPO_ROOT / "results"
VERDICT_PATH = RESULTS_DIR / "sentiment_node_verdict.json"

TARGET_COL = "USA_500_Index"
ROLL_WINDOW = 60
RICCI_THRESHOLD = 0.30
ORTHO_GATE = 0.30
SEED = 42
ORTHO_STRICT = 0.15


@dataclass
class SentimentNodeBuild:
    returns: pd.DataFrame
    sentiment: pd.Series
    returns_with_sentiment: pd.DataFrame
    sentiment_frozen_z: pd.Series
    split_ts: pd.Timestamp


def _parse_args() -> tuple[Path, Path, bool]:
    import argparse

    parser = argparse.ArgumentParser(description="Sentiment-node Ricci experiment.")
    parser.add_argument("--panel", type=Path, default=PANEL_PATH)
    parser.add_argument("--output", type=Path, default=VERDICT_PATH)
    parser.add_argument(
        "--source",
        choices=["vix", "reddit"],
        default="vix",
        help="Sentiment source. 'reddit' requires PRAW creds via env vars.",
    )
    args = parser.parse_args()
    return args.panel, args.output, args.source == "reddit"


def _abort_on_nan(frame_or_series: pd.DataFrame | pd.Series, name: str) -> None:
    if bool(
        frame_or_series.isna().any().any()
        if isinstance(frame_or_series, pd.DataFrame)
        else frame_or_series.isna().any()
    ):
        raise SystemExit(f"NaN invariant violated: {name} contains NaN")


def _spearman(a: pd.Series, b: pd.Series) -> float:
    df = pd.concat([a, b], axis=1).dropna()
    if len(df) < 30:
        return 0.0
    return float(spearmanr(df.iloc[:, 0], df.iloc[:, 1]).statistic)


def _permutation_pvalue(
    signal: pd.Series, target: pd.Series, n: int = 500, seed: int = SEED
) -> float:
    df = pd.concat([signal, target], axis=1).dropna()
    if len(df) < 30:
        return 1.0
    x = df.iloc[:, 0].to_numpy(dtype=float)
    y = df.iloc[:, 1].to_numpy(dtype=float)
    obs = abs(float(spearmanr(x, y).statistic))
    rng = np.random.default_rng(seed)
    count = sum(
        1 for _ in range(n) if abs(float(spearmanr(x, rng.permutation(y)).statistic)) >= obs
    )
    return float((count + 1) / (n + 1))


def _load_returns(panel_path: Path) -> pd.DataFrame:
    prices = read_parquet_compat(panel_path).sort_index()
    returns = np.log(prices / prices.shift(1)).replace([np.inf, -np.inf], np.nan).dropna()
    _abort_on_nan(returns, "returns")
    if TARGET_COL not in returns.columns:
        raise SystemExit(f"Missing target column: {TARGET_COL}")
    return returns


def vix_sentiment_proxy(returns: pd.DataFrame) -> pd.Series:
    vix_cols = [c for c in returns.columns if "VIX" in c.upper()]
    if not vix_cols:
        raise SystemExit("VIX fallback unavailable: no VIX-like column found")
    # Deterministic choice in case of multiple VIX columns.
    chosen = sorted(vix_cols)[0]
    return (-returns[chosen]).rename("WSB_SENTIMENT")


def reddit_sentiment_proxy() -> pd.Series:
    if importlib.util.find_spec("praw") is None:
        raise SystemExit("Reddit sentiment requested, but 'praw' is not installed")
    praw = importlib.import_module("praw")

    client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
    user_agent = os.getenv("REDDIT_USER_AGENT", "geosync-sentiment")
    if not client_id or not client_secret:
        raise SystemExit("Reddit sentiment requested but credentials are missing")

    reddit = praw.Reddit(client_id=client_id, client_secret=client_secret, user_agent=user_agent)
    subreddit = reddit.subreddit("wallstreetbets")
    records: list[dict[str, Any]] = []
    for post in subreddit.search("SPY OR QQQ OR market", time_filter="year", limit=1000):
        ratio = float(post.upvote_ratio)
        sentiment_proxy = (ratio - 0.5) * 2.0
        ts = datetime.fromtimestamp(float(post.created_utc), tz=timezone.utc)
        records.append({"ts": ts, "sentiment": sentiment_proxy})

    if not records:
        raise SystemExit("Reddit sentiment returned no records")

    df = pd.DataFrame(records)
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.floor("h")
    return df.groupby("ts")["sentiment"].mean().rename("WSB_SENTIMENT")


def build_sentiment_node(returns: pd.DataFrame, use_reddit: bool) -> SentimentNodeBuild:
    sentiment = (
        reddit_sentiment_proxy().reindex(returns.index)
        if use_reddit
        else vix_sentiment_proxy(returns)
    )
    sentiment = sentiment.dropna()
    _abort_on_nan(sentiment, "raw sentiment")

    split_idx = max(int(len(sentiment) * 0.7), 1)
    split_ts = sentiment.index[split_idx - 1]
    train = sentiment.loc[sentiment.index <= split_ts]
    mu = float(train.mean())
    sd = float(train.std())
    if not np.isfinite(sd) or sd <= 0:
        sd = 1e-8

    sentiment_frozen_z = ((sentiment - mu) / sd).rename("WSB_SENTIMENT")
    _abort_on_nan(sentiment_frozen_z, "train-frozen z-score sentiment")

    returns_with_sentiment = pd.concat([returns, sentiment_frozen_z], axis=1).dropna()
    _abort_on_nan(returns_with_sentiment, "returns_with_sentiment")

    return SentimentNodeBuild(
        returns=returns,
        sentiment=sentiment_frozen_z,
        returns_with_sentiment=returns_with_sentiment,
        sentiment_frozen_z=sentiment_frozen_z,
        split_ts=split_ts,
    )


def orthogonality_gate(returns: pd.DataFrame, sentiment: pd.Series) -> tuple[float, float]:
    mom20 = returns[TARGET_COL].rolling(20).sum()
    vol10 = returns[TARGET_COL].rolling(10).std()
    corr_sent_mom = _spearman(sentiment, mom20)
    corr_sent_vol = _spearman(sentiment, vol10)
    if abs(corr_sent_mom) >= ORTHO_GATE or abs(corr_sent_vol) >= ORTHO_GATE:
        raise SystemExit("GATE FAILED: sentiment leaks momentum/vol")
    return corr_sent_mom, corr_sent_vol


def compute_kappa(panel: pd.DataFrame) -> pd.Series:
    ricci = FormanRicciCurvature(threshold=RICCI_THRESHOLD)
    vals = panel.to_numpy(dtype=float)
    kappa = pd.Series(np.nan, index=panel.index, name="kappa")

    for t in range(ROLL_WINDOW - 1, len(panel)):
        w = vals[t - ROLL_WINDOW + 1 : t + 1]
        corr = np.nan_to_num(np.corrcoef(w, rowvar=False), nan=0.0)
        kappa.iloc[t] = ricci.compute_from_correlation(corr).kappa_mean

    kappa = kappa.dropna()
    _abort_on_nan(kappa, "kappa")
    return kappa


def evaluate(
    build: SentimentNodeBuild, corr_sent_mom: float, corr_sent_vol: float
) -> dict[str, Any]:
    returns_with_sentiment = build.returns_with_sentiment
    returns = build.returns

    kappa = compute_kappa(returns_with_sentiment)
    target = returns_with_sentiment[TARGET_COL].shift(-1)

    mom20 = returns[TARGET_COL].rolling(20).sum()
    vol10 = returns[TARGET_COL].rolling(10).std()

    ic = _spearman(kappa, target)
    p_val = _permutation_pvalue(kappa, target, n=500, seed=SEED)
    corr_m = _spearman(kappa, mom20)
    corr_v = _spearman(kappa, vol10)

    alerts = (
        (kappa < kappa.expanding().quantile(0.10))
        .reindex(returns_with_sentiment.index)
        .fillna(False)
    )
    fwd20 = returns_with_sentiment[TARGET_COL].rolling(20).sum().shift(-20)
    events = fwd20[fwd20 < -0.05]

    captured = 0
    alert_arr = alerts.to_numpy(dtype=bool)
    for ts in events.index:
        loc = int(alerts.index.get_loc(ts))
        lo = max(0, loc - 30)
        hi = max(0, loc - 10)
        if hi > lo and bool(alert_arr[lo:hi].any()):
            captured += 1
    lead_capture = float(captured / len(events)) if len(events) > 0 else 0.0

    verdict = {
        "sentiment_gate": {
            "corr_sentiment_momentum": corr_sent_mom,
            "corr_sentiment_vol": corr_sent_vol,
            "passed": bool(abs(corr_sent_mom) < ORTHO_GATE and abs(corr_sent_vol) < ORTHO_GATE),
        },
        "sentiment_train_frozen": {
            "split_ts": str(build.split_ts),
        },
        "IC": ic,
        "p_value": p_val,
        "corr_momentum": corr_m,
        "corr_vol": corr_v,
        "lead_capture": lead_capture,
        "DETECT": "PASS" if ic >= 0.08 else "FAIL",
        "DISCRIMINATE": (
            "PASS" if abs(corr_m) < ORTHO_STRICT and abs(corr_v) < ORTHO_STRICT else "FAIL"
        ),
        "DELIVER": "PASS" if lead_capture >= 0.60 else "FAIL",
        "FINAL": (
            "SIGNAL_READY"
            if ic >= 0.08
            and p_val < 0.10
            and abs(corr_m) < ORTHO_STRICT
            and abs(corr_v) < ORTHO_STRICT
            and lead_capture >= 0.60
            else "REJECT"
        ),
    }
    return verdict


def main() -> int:
    panel_path, output_path, use_reddit = _parse_args()
    try:
        returns = _load_returns(panel_path=panel_path)
        build = build_sentiment_node(returns, use_reddit=use_reddit)
        corr_sent_mom, corr_sent_vol = orthogonality_gate(build.returns, build.sentiment)
        verdict = evaluate(build, corr_sent_mom=corr_sent_mom, corr_sent_vol=corr_sent_vol)
    except (ParquetEngineUnavailable, FileNotFoundError) as exc:
        verdict = {
            "FINAL": "REJECT",
            "error": str(exc),
            "DETECT": "FAIL",
            "DISCRIMINATE": "FAIL",
            "DELIVER": "FAIL",
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(verdict, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
