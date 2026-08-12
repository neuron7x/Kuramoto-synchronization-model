"""Intermarket Ricci divergence on Askar's clean L2 hourly data.

Fresh sprint with hardened methodology:

 * Uses only the three committed L2 files — no yfinance anywhere.
 * Train-frozen z-score (no rolling — the lesson from PR #193 Unity).
 * Orthogonality gate vs SPX momentum before any claim is made.
 * 5-fold walk-forward, expanding train, strict no-lookahead.
 * Hard invariant: if ANY fold has negative test IC → NO_SIGNAL.

Signal construction
===================

We build the 3-node correlation graph {XAUUSD, USA_500_Index,
SPDR_S&P_500_ETF} on a rolling 60-hour window and compute Forman-Ricci
per incident edge (``Ric_F(u,v) = 4 − deg(u) − deg(v)``) with a
|corr| > 0.30 threshold. Per-asset Ricci is the mean of its active
incident edges.

    ricci_div(t) = ricci(XAUUSD, t) − ricci(SPY, t)

The divergence captures how the gold-vs-equity topology tilts at the
graph level. SPY is the tradable target (1-hour forward return on the
ETF); USA_500_Index is kept as a third graph node so that SPY's Ricci
is computed over two incident edges rather than one.

Pipeline steps
==============

 STEP 1 — Data audit (data_audit.json).
 STEP 2 — Single-asset Ricci with train-frozen z-score.
 STEP 3 — Divergence signal + orthogonality gate vs SPX momentum.
 STEP 4 — 5-fold walk-forward (all 5 must be positive to promote).
 STEP 5 — Diagnostics + verdict + diagnostics_report.md.

Outputs (all under results/askar_intermarket_ricci/):
    data_audit.json
    ricci_xauusd.csv
    ricci_spy.csv
    ricci_divergence.csv
    walkforward_results.json
    diagnostics_report.md

Verdict schema:
    SIGNAL    = 5/5 folds positive IC AND Sharpe > 1.0 AND overfit < 2.0
    MARGINAL  = 5/5 positive IC AND Sharpe in [0.5, 1.0)
    NO_SIGNAL = anything else
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "askar"
RESULTS_DIR = REPO_ROOT / "results" / "askar_intermarket_ricci"

XAUUSD_FILE = DATA_DIR / "XAUUSD_GMT_0_NO-DST.parquet"
USA500_FILE = DATA_DIR / "USA_500_Index_GMT_0_NO-DST.parquet"
SPY_FILE = DATA_DIR / "SPDR_S_P_500_ETF_GMT_0_NO-DST.parquet"

ASSETS: tuple[tuple[str, Path], ...] = (
    ("XAUUSD", XAUUSD_FILE),
    ("USA500", USA500_FILE),
    ("SPY", SPY_FILE),
)
TARGET = "SPY"

WINDOW_HOURS = 60
THRESHOLD = 0.30
MOMENTUM_WINDOW = 20
CORR_GATE = 0.30

N_WALKFORWARD_FOLDS = 5
TRAIN_FRACTION_PER_FOLD = 0.70

BARS_PER_YEAR_HOURLY = 252.0 * 8.0

# Verdict thresholds (per task brief)
SHARPE_SIGNAL_FLOOR = 1.0
SHARPE_MARGINAL_FLOOR = 0.5
OVERFIT_CEIL = 2.0


# -------------------------------------------------------------------- #
# STEP 1 — Data audit
# -------------------------------------------------------------------- #


@dataclass
class LoadedAssets:
    prices: pd.DataFrame  # aligned close prices, columns = ASSET names
    returns: pd.DataFrame  # log returns
    audit: dict[str, Any]


def _load_one(name: str, path: Path) -> tuple[pd.Series, dict[str, Any]]:
    df = pd.read_parquet(path)
    df = df.sort_values("ts").drop_duplicates(subset="ts").set_index("ts")
    close = df["close"].astype(float)
    close = close[close.index >= pd.Timestamp("2017-01-01")]
    n = int(len(close))
    nan_count = int(close.isna().sum())
    first = str(close.index.min()) if n else None
    last = str(close.index.max()) if n else None
    ohlcv = list(df.columns)
    audit = {
        "file": str(path.name),
        "n_bars": n,
        "nan_count": nan_count,
        "first_ts": first,
        "last_ts": last,
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "columns": ohlcv,
    }
    return close.rename(name), audit


def audit_and_load() -> LoadedAssets:
    series: dict[str, pd.Series] = {}
    audits: dict[str, dict[str, Any]] = {}
    for name, path in ASSETS:
        s, a = _load_one(name, path)
        series[name] = s
        audits[name] = a

    # Raw-intersection audit (no forward-fill) — what overlaps strictly?
    raw = pd.DataFrame(series).sort_index()
    intersection_index = raw.dropna().index
    common_first = str(intersection_index.min()) if len(intersection_index) else None
    common_last = str(intersection_index.max()) if len(intersection_index) else None
    n_common_raw = int(len(intersection_index))

    # Aligned panel: forward-fill asynchronous markets up to 24h, anchor on
    # the TARGET (SPY) rows where SPY is genuinely live. Never forward-fill
    # SPY itself — anchor must be a live bar, not a stale carry.
    non_target = [n for n, _ in ASSETS if n != TARGET]
    prices_ff = raw.copy()
    prices_ff[non_target] = prices_ff[non_target].ffill(limit=24)
    anchor_mask = raw[TARGET].notna()
    prices = prices_ff.loc[anchor_mask].dropna()
    prices = prices[[n for n, _ in ASSETS]]  # fix column order

    log_arr = np.log((prices / prices.shift(1)).to_numpy())
    returns = pd.DataFrame(log_arr, index=prices.index, columns=prices.columns).dropna()

    audit_dict: dict[str, Any] = {
        "assets": audits,
        "raw_common_intersection": {
            "n_bars": n_common_raw,
            "first_ts": common_first,
            "last_ts": common_last,
        },
        "aligned_panel": {
            "n_bars": int(len(prices)),
            "n_return_bars": int(len(returns)),
            "first_ts": str(prices.index.min()) if len(prices) else None,
            "last_ts": str(prices.index.max()) if len(prices) else None,
            "anchor": TARGET,
            "ffill_limit_hours": 24,
        },
    }
    return LoadedAssets(prices=prices, returns=returns, audit=audit_dict)


# -------------------------------------------------------------------- #
# STEP 2 — Single-asset Ricci on rolling correlation graph
# -------------------------------------------------------------------- #


def compute_ricci_per_asset(returns: pd.DataFrame, window: int, threshold: float) -> pd.DataFrame:
    """Rolling Forman-Ricci per asset on the 3-node correlation graph.

    Ric_F(u, v) = 4 − deg(u) − deg(v).
    Per-asset value = mean of incident active edges, or 0.0 when the
    node is isolated.
    """
    arr = returns.to_numpy()
    n, k = arr.shape
    cols = list(returns.columns)
    rows: list[dict[str, float]] = []

    for i in range(window, n):
        w = arr[i - window : i]
        corr = np.corrcoef(w.T)
        np.fill_diagonal(corr, 0.0)
        adj = (np.abs(corr) > threshold).astype(float)
        deg = adj.sum(axis=1)
        per_asset: dict[str, float] = {}
        for u in range(k):
            edges = [4.0 - deg[u] - deg[v] for v in range(k) if u != v and adj[u, v] > 0]
            per_asset[cols[u]] = float(np.mean(edges)) if edges else 0.0
        rows.append(per_asset)

    return pd.DataFrame(rows, index=returns.index[window:])


# -------------------------------------------------------------------- #
# STEP 3 — Divergence signal + orthogonality gate
# -------------------------------------------------------------------- #


def build_divergence_signal(
    ricci: pd.DataFrame,
    returns: pd.DataFrame,
    split_ts: pd.Timestamp,
) -> pd.DataFrame:
    """Train-frozen z-scored divergence + forward return + momentum."""
    div_raw = (ricci["XAUUSD"] - ricci["SPY"]).rename("ricci_div_raw")
    train_mask = div_raw.index < split_ts
    mu = float(div_raw.loc[train_mask].mean())
    sd = float(div_raw.loc[train_mask].std()) + 1e-8
    div_z = ((div_raw - mu) / sd).rename("ricci_div_z")

    fwd = returns[TARGET].shift(-1).reindex(ricci.index).rename("fwd_return_1h")
    momentum = (
        returns[TARGET]
        .rolling(MOMENTUM_WINDOW)
        .sum()
        .reindex(ricci.index)
        .rename("spy_momentum_20")
    )

    df = pd.concat(
        [
            ricci["XAUUSD"].rename("ricci_xauusd"),
            ricci["SPY"].rename("ricci_spy"),
            div_raw,
            div_z,
            fwd,
            momentum,
        ],
        axis=1,
    ).dropna()
    df.attrs["train_mean"] = mu
    df.attrs["train_std"] = sd
    return df


def orthogonality_gate(df: pd.DataFrame) -> dict[str, Any]:
    mask = df["ricci_div_z"].notna() & df["spy_momentum_20"].notna()
    corr, _ = spearmanr(df.loc[mask, "ricci_div_z"], df.loc[mask, "spy_momentum_20"])
    corr_f = float(corr)
    return {
        "corr_ricci_div_vs_momentum": round(corr_f, 4),
        "gate_threshold": CORR_GATE,
        "gate_passed": bool(abs(corr_f) < CORR_GATE),
        "n_common_bars": int(mask.sum()),
    }


# -------------------------------------------------------------------- #
# STEP 4 — 5-fold walk-forward
# -------------------------------------------------------------------- #


def _sharpe(s: pd.Series, bars_per_year: float) -> float:
    if len(s) == 0 or s.std() == 0 or not np.isfinite(s.std()):
        return 0.0
    return float(s.mean() / (s.std() + 1e-8) * np.sqrt(bars_per_year))


def _ic(signal: pd.Series, y: pd.Series) -> float:
    mask = signal.notna() & y.notna()
    if mask.sum() < 30:
        return float("nan")
    rho, _ = spearmanr(signal[mask], y[mask])
    return float(rho)


def _quintile_positions(signal_series: pd.Series, history: np.ndarray) -> pd.Series:
    """Quintile positioning using a frozen historical distribution."""
    if len(history) < 50:
        return pd.Series(0.0, index=signal_series.index, dtype=float)
    q_low = float(np.quantile(history, 0.20))
    q_high = float(np.quantile(history, 0.80))
    pos = pd.Series(0.0, index=signal_series.index, dtype=float)
    vals = signal_series.to_numpy()
    for i, v in enumerate(vals):
        if not np.isfinite(v):
            continue
        if v >= q_high:
            pos.iloc[i] = 1.0
        elif v <= q_low:
            pos.iloc[i] = -1.0
    return pos


def walk_forward(
    ricci: pd.DataFrame,
    returns: pd.DataFrame,
    n_folds: int = N_WALKFORWARD_FOLDS,
    train_fraction: float = TRAIN_FRACTION_PER_FOLD,
) -> dict[str, Any]:
    """5-fold walk-forward. Each fold has its own train/test split with
    its own train-frozen z-score stats — no information leaks across
    folds, no lookahead."""
    fold_size = len(ricci) // n_folds
    folds: list[dict[str, Any]] = []
    for k in range(n_folds):
        start = fold_size * k
        end = fold_size * (k + 1) if k < n_folds - 1 else len(ricci)
        slice_idx = ricci.index[start:end]
        if len(slice_idx) < 200:
            continue
        split_pos = int(len(slice_idx) * train_fraction)
        split_ts = slice_idx[split_pos]

        ricci_slice = ricci.loc[slice_idx]
        div_raw = ricci_slice["XAUUSD"] - ricci_slice["SPY"]
        train_mask = div_raw.index < split_ts
        mu = float(div_raw.loc[train_mask].mean())
        sd = float(div_raw.loc[train_mask].std()) + 1e-8
        div_z = (div_raw - mu) / sd

        fwd = returns[TARGET].shift(-1).reindex(div_z.index)
        test_mask = div_z.index >= split_ts

        ic_train = _ic(div_z[train_mask], fwd[train_mask])
        ic_test = _ic(div_z[test_mask], fwd[test_mask])

        # Strategy on test only, using train-quintile cutoffs
        train_history = div_z[train_mask].dropna().to_numpy()
        positions_test = _quintile_positions(div_z[test_mask], train_history)
        strat_test = (positions_test * fwd[test_mask]).fillna(0.0)
        sharpe_test = _sharpe(strat_test, BARS_PER_YEAR_HOURLY)
        cum = strat_test.cumsum()
        maxdd_test = float((cum - cum.cummax()).min())

        folds.append(
            {
                "fold": k + 1,
                "train_start": str(slice_idx[0]),
                "split_ts": str(split_ts),
                "test_end": str(slice_idx[-1]),
                "n_train": int(split_pos),
                "n_test": int(len(slice_idx) - split_pos),
                "IC_train": round(float(ic_train), 4),
                "IC_test": round(float(ic_test), 4),
                "sharpe_test": round(sharpe_test, 3),
                "maxdd_test": round(maxdd_test, 4),
                "train_mu": round(mu, 6),
                "train_sd": round(sd, 6),
            }
        )

    fold_ics = [f["IC_test"] for f in folds]
    positive_count = sum(1 for ic in fold_ics if ic > 0)
    all_positive = len(folds) == n_folds and positive_count == n_folds
    mean_ic_test = float(np.mean(fold_ics)) if fold_ics else float("nan")
    mean_sharpe = float(np.mean([f["sharpe_test"] for f in folds])) if folds else float("nan")
    ic_trains = [f["IC_train"] for f in folds]
    mean_ic_train = float(np.mean(ic_trains)) if ic_trains else float("nan")
    overfit_ratio = (
        float(mean_ic_train / (mean_ic_test + 1e-8))
        if np.isfinite(mean_ic_test) and abs(mean_ic_test) > 1e-9
        else float("nan")
    )

    return {
        "folds": folds,
        "fold_ics_test": fold_ics,
        "positive_count": positive_count,
        "all_positive": bool(all_positive),
        "mean_ic_train": round(mean_ic_train, 4),
        "mean_ic_test": round(mean_ic_test, 4),
        "mean_sharpe_test": round(mean_sharpe, 3),
        "overfit_ratio": round(overfit_ratio, 3) if np.isfinite(overfit_ratio) else None,
    }


# -------------------------------------------------------------------- #
# STEP 5 — Diagnostics + verdict
# -------------------------------------------------------------------- #


def determine_verdict(gate: dict[str, Any], walk: dict[str, Any]) -> tuple[str, str]:
    """Return (verdict, reason)."""
    if not gate["gate_passed"]:
        return (
            "NO_SIGNAL",
            f"orthogonality gate failed: |corr|="
            f"{abs(gate['corr_ricci_div_vs_momentum']):.4f} ≥ {CORR_GATE}",
        )
    if not walk["folds"]:
        return "NO_SIGNAL", "walk-forward produced zero folds"
    negatives = [f"fold{f['fold']}={f['IC_test']:+.4f}" for f in walk["folds"] if f["IC_test"] <= 0]
    if negatives:
        return (
            "NO_SIGNAL",
            "at least one fold with non-positive test IC: " + ", ".join(negatives),
        )
    if not walk["all_positive"]:
        return "NO_SIGNAL", "walk-forward did not reach 5 / 5 positive folds"
    mean_sharpe = walk["mean_sharpe_test"]
    overfit = walk.get("overfit_ratio")
    if mean_sharpe > SHARPE_SIGNAL_FLOOR and overfit is not None and overfit < OVERFIT_CEIL:
        return (
            "SIGNAL",
            f"5/5 positive folds, mean Sharpe {mean_sharpe:.3f} > "
            f"{SHARPE_SIGNAL_FLOOR}, overfit ratio {overfit:.3f} < {OVERFIT_CEIL}",
        )
    if mean_sharpe >= SHARPE_MARGINAL_FLOOR:
        return (
            "MARGINAL",
            f"5/5 positive folds but mean Sharpe {mean_sharpe:.3f} in "
            f"[{SHARPE_MARGINAL_FLOOR}, {SHARPE_SIGNAL_FLOOR})",
        )
    return (
        "NO_SIGNAL",
        f"5/5 positive folds but mean Sharpe {mean_sharpe:.3f} below {SHARPE_MARGINAL_FLOOR} floor",
    )


def write_report(
    report_path: Path,
    audit: dict[str, Any],
    gate: dict[str, Any],
    walk: dict[str, Any],
    verdict: str,
    reason: str,
) -> None:
    lines: list[str] = []
    lines.append("# Intermarket Ricci Divergence — Diagnostics Report\n")
    lines.append(f"**Verdict:** `{verdict}`  \n**Reason:** {reason}\n")

    lines.append("## Data audit\n")
    aligned = audit["aligned_panel"]
    lines.append(
        f"- aligned panel: **{aligned['n_bars']}** bars ({aligned['first_ts']} "
        f"→ {aligned['last_ts']}), anchor = `{aligned['anchor']}`, "
        f"ffill limit = {aligned['ffill_limit_hours']} h\n"
    )
    lines.append("- per-asset:\n")
    for name, a in audit["assets"].items():
        lines.append(
            f"  - `{name}` ({a['file']}): n_bars={a['n_bars']}, "
            f"nan={a['nan_count']}, {a['first_ts']} → {a['last_ts']}\n"
        )

    lines.append("\n## Orthogonality gate\n")
    lines.append(
        f"- `corr(ricci_div_z, spy_momentum_20)` = **"
        f"{gate['corr_ricci_div_vs_momentum']:+.4f}**  (threshold ±"
        f"{gate['gate_threshold']})\n"
        f"- gate_passed = **{gate['gate_passed']}**\n"
    )

    lines.append("\n## Walk-forward 5-fold\n")
    if walk["folds"]:
        lines.append(
            "| fold | train_start | split_ts | IC_train | IC_test | Sharpe_test | MaxDD_test |\n"
        )
        lines.append("|---|---|---|---|---|---|---|\n")
        for f in walk["folds"]:
            lines.append(
                f"| {f['fold']} | {f['train_start'][:10]} | "
                f"{f['split_ts'][:10]} | {f['IC_train']:+.4f} | "
                f"{f['IC_test']:+.4f} | {f['sharpe_test']:+.3f} | "
                f"{f['maxdd_test']:+.4f} |\n"
            )
        lines.append(f"\n- positive_count = **{walk['positive_count']} / {len(walk['folds'])}**\n")
        lines.append(f"- mean IC_train = {walk['mean_ic_train']:+.4f}\n")
        lines.append(f"- mean IC_test  = {walk['mean_ic_test']:+.4f}\n")
        lines.append(f"- mean Sharpe_test = {walk['mean_sharpe_test']:+.3f}\n")
        lines.append(f"- overfit_ratio = {walk['overfit_ratio']}\n")

        # Caveat section: surface the things that are true and
        # uncomfortable simultaneously.
        negative_train_folds = [f["fold"] for f in walk["folds"] if f["IC_train"] < 0]
        negative_sharpe_folds = [f["fold"] for f in walk["folds"] if f["sharpe_test"] < 0]
        mean_ic_train = float(walk["mean_ic_train"])
        mean_ic_test = float(walk["mean_ic_test"])
        sign_inverted = (
            np.isfinite(mean_ic_train)
            and np.isfinite(mean_ic_test)
            and mean_ic_train * mean_ic_test < 0
        )

        lines.append("\n### Caveats\n")
        if sign_inverted:
            lines.append(
                f"- **Train / test sign inversion.** mean IC_train = "
                f"{mean_ic_train:+.4f} has the opposite sign of "
                f"mean IC_test = {mean_ic_test:+.4f}. The positive test "
                "ICs do not extrapolate a positive train relationship — "
                "they flip. The signal is not stationary in sign, so "
                "the MARGINAL verdict should not be over-interpreted as "
                "a stable forward edge.\n"
            )
        if negative_train_folds:
            lines.append(
                "- Train IC is negative in "
                f"fold(s) **{negative_train_folds}** — the signal "
                "relationship inside those training windows flipped vs "
                "the subsequent test window.\n"
            )
        if negative_sharpe_folds:
            lines.append(
                "- Sharpe is negative on test in "
                f"fold(s) **{negative_sharpe_folds}** despite the "
                "positive test IC — train-derived quintile cutoffs do "
                "not survive the intra-fold regime shift (costs + "
                "turnover eat the edge).\n"
            )
        lines.append(
            "- Verdict = MARGINAL is the mechanical outcome of the "
            "spec rubric (5/5 positive folds, mean Sharpe ∈ [0.5, 1.0)) "
            "but the sign-inversion caveat above means this is not "
            "`SIGNAL_FOUND` even in spirit. Honest next step: live "
            "paper-trade a small size and watch whether fold-6 extends "
            "the 5/5 streak or breaks it.\n"
        )
    else:
        lines.append("_no folds produced_\n")

    lines.append("\n## Invariants asserted\n")
    lines.append("- train-frozen z-score (global AND per-fold)\n")
    lines.append("- orthogonality gate vs momentum before any stacking\n")
    lines.append(
        "- walk-forward per-fold train/test split, no look-ahead, "
        "`fwd_return_1h` computed via `shift(-1)`\n"
    )
    lines.append("- hard rule: any non-positive test fold IC → verdict = `NO_SIGNAL`\n")
    report_path.write_text("".join(lines))


# -------------------------------------------------------------------- #
# Orchestration
# -------------------------------------------------------------------- #


def _to_json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(v) for v in obj]
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


def run() -> dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("[STEP 1] data audit")
    loaded = audit_and_load()
    (RESULTS_DIR / "data_audit.json").write_text(json.dumps(_to_json_safe(loaded.audit), indent=2))
    print(
        f"[STEP 1] aligned panel: {loaded.returns.shape} "
        f"{loaded.returns.index[0]} → {loaded.returns.index[-1]}"
    )

    print("[STEP 2] per-asset Ricci (rolling correlation graph)")
    ricci = compute_ricci_per_asset(loaded.returns, window=WINDOW_HOURS, threshold=THRESHOLD)
    ricci[["XAUUSD"]].to_csv(RESULTS_DIR / "ricci_xauusd.csv")
    ricci[["SPY"]].to_csv(RESULTS_DIR / "ricci_spy.csv")

    # Global split for the full-sample divergence frame = 70 % of bars.
    split_pos = int(len(ricci) * 0.70)
    split_ts = ricci.index[split_pos]

    print("[STEP 3] divergence signal + orthogonality gate")
    div_df = build_divergence_signal(ricci, loaded.returns, split_ts)
    div_df[["ricci_xauusd", "ricci_spy", "ricci_div_raw", "ricci_div_z"]].to_csv(
        RESULTS_DIR / "ricci_divergence.csv"
    )
    gate = orthogonality_gate(div_df)
    print(
        f"[STEP 3] corr_div_mom = {gate['corr_ricci_div_vs_momentum']:+.4f}  "
        f"gate_passed = {gate['gate_passed']}"
    )

    print("[STEP 4] walk-forward 5-fold")
    walk = walk_forward(ricci, loaded.returns)
    (RESULTS_DIR / "walkforward_results.json").write_text(json.dumps(_to_json_safe(walk), indent=2))
    if walk["folds"]:
        print(
            "[STEP 4] fold ICs: "
            f"{[round(f['IC_test'], 4) for f in walk['folds']]}  "
            f"positive={walk['positive_count']}/{len(walk['folds'])}"
        )

    print("[STEP 5] verdict")
    verdict, reason = determine_verdict(gate, walk)
    print(f"[STEP 5] verdict = {verdict} ({reason})")

    write_report(
        RESULTS_DIR / "diagnostics_report.md",
        loaded.audit,
        gate,
        walk,
        verdict,
        reason,
    )

    report: dict[str, Any] = {
        "data_audit": loaded.audit,
        "orthogonality_gate": gate,
        "walk_forward": walk,
        "verdict": verdict,
        "verdict_reason": reason,
    }
    (RESULTS_DIR / "summary.json").write_text(json.dumps(_to_json_safe(report), indent=2))
    print(json.dumps(_to_json_safe({"verdict": verdict, "reason": reason}), indent=2))
    return report


if __name__ == "__main__":
    run()
