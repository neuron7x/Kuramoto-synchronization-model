"""GeoSync Optimal Universe validation on Askar's L2 archive — 14 assets fixed.

Follows ``CLAUDE_CODE_TASK_askar_optimal.md`` literally:

* Fixed 14-asset universe (USA_500 anchor, gold, 4 FX, 2 bonds, oil,
  soybean, EM/Japan/China equities, US real estate).
* Daily-resample run (W=60, θ=0.30, 5 bps) is the apples-to-apples
  replication of the GeoSync baseline (IC=0.106, Sharpe=1.74).
* Hourly-native run (W=480, 1 bps) is new territory.
* Walk-forward cut: train < 2023-07-01, test ≥ 2023-07-01 (2.4 yr OOS).
* 2022 crisis block sits inside the train window — we report it as a
  train diagnostic, not out-of-sample alpha.
* Signal formula is identical to the task brief:
      Ric_F(u,v)    = 4 − deg(u) − deg(v)
      ricci_mean(t) = mean Ric_F over active edges in the corr graph
      delta_Ricci(t) = ricci_mean(t) − ricci_mean(t − 1)  # temporal diff
      combo(t)      = z(delta_Ricci, W) − 0.5 · z(ricci_mean, W)

Run::

    python research/askar/optimal_universe.py

Outputs::

    results/askar_optimal_result.json
    results/askar_optimal_daily_equity.png
    results/askar_optimal_hourly_equity.png
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
DATA_DIR = REPO_ROOT / "data" / "askar" / "archive"
RESULTS_DIR = REPO_ROOT / "results"

# --- Universe specification (fixed by task brief) ---
UNIVERSE: tuple[tuple[str, str], ...] = (
    ("USA_500_Index_GMT+0_NO-DST.parquet", "equity_anchor"),
    ("SPDR_Gold_Shares_ETF_GMT+0_NO-DST.parquet", "gold"),
    ("EURUSD_GMT+0_NO-DST.parquet", "fx"),
    ("AUDUSD_GMT+0_NO-DST.parquet", "fx"),
    ("USDCAD_GMT+0_NO-DST.parquet", "fx"),
    ("EURGBP_GMT+0_NO-DST.parquet", "fx"),
    ("iShares_20+_Year_Treasury_Bond_ETF_GMT+0_NO-DST.parquet", "bonds"),
    ("Euro_Bund_GMT+0_NO-DST.parquet", "bonds"),
    ("US_Brent_Crude_Oil_GMT+0_NO-DST.parquet", "oil"),
    ("Soybean_GMT+0_NO-DST.parquet", "agri"),
    ("iShares_MSCI_Emerging_Markets_ETF_GMT+0_NO-DST.parquet", "equity_em"),
    ("iShares_MSCI_Japan_ETF_GMT+0_NO-DST.parquet", "equity_japan"),
    ("iShares_U.S._Real_Estate_ETF_GMT+0_NO-DST.parquet", "real_estate"),
    ("China_A50_Index_GMT+0_NO-DST.parquet", "equity_china"),
)
TARGET_FILENAME = UNIVERSE[0][0]  # USA_500 anchor
N_UNIVERSE = 14

OVERLAP_START = pd.Timestamp("2017-12-01")
OVERLAP_END = pd.Timestamp("2026-02-20")
SPLIT_DATE = pd.Timestamp("2023-07-01")
CRISIS_LO = pd.Timestamp("2022-01-01")
CRISIS_HI = pd.Timestamp("2023-01-01")

# Signal & backtest knobs
THRESHOLD = 0.30
WINDOW_DAILY = 60
WINDOW_HOURLY = 480
COST_DAILY_BPS = 5.0
COST_HOURLY_BPS = 1.0

# Annualisation factors
BARS_PER_YEAR_DAILY = 252.0
BARS_PER_YEAR_HOURLY = 252.0 * 8.0  # 8 trading hours / day, per spec

N_PERMUTATIONS = 1000
N_WALKFORWARD_FOLDS = 5

BASELINE_YFINANCE_IC = 0.106


# -------------------------------------------------------------------- #
# Data loading
# -------------------------------------------------------------------- #


@dataclass
class LoadedUniverse:
    prices_hourly: pd.DataFrame
    returns_hourly: pd.DataFrame
    prices_daily: pd.DataFrame
    returns_daily: pd.DataFrame


def load_universe(
    data_dir: Path = DATA_DIR,
    start: pd.Timestamp = OVERLAP_START,
    end: pd.Timestamp = OVERLAP_END,
) -> LoadedUniverse:
    """Load the 14-asset panel and produce aligned hourly + daily frames."""
    series: dict[str, pd.Series] = {}
    for filename, _label in UNIVERSE:
        path = data_dir / filename
        df = pd.read_parquet(path)
        df = df.sort_values("ts").drop_duplicates(subset="ts").set_index("ts")
        close = df["close"].astype(float)
        close = close[(close.index >= start) & (close.index <= end)]
        # Column name is the filename so column ordering == UNIVERSE ordering.
        series[filename] = close

    prices_hourly_raw = pd.DataFrame(series).sort_index()
    # Keep strict ordering: first column MUST be the target asset.
    prices_hourly_raw = prices_hourly_raw[[f for f, _ in UNIVERSE]]
    # Session asynchrony fix: asset sessions don't overlap perfectly
    # (e.g. China_A50 closes before US ETFs open), so a strict inner-join
    # .dropna() kills multi-day blocks whenever any single asset has a
    # session gap. Every non-target column is forward-filled up to 36
    # hours — covers long holidays and Asian→US session handoffs without
    # ever looking into the future — while the target column is left
    # UNTOUCHED. We then anchor the panel on the *raw* target timestamps
    # (where USA_500 was genuinely live) so no bar is kept just because
    # the anchor was stale-filled; only those timestamps that still have
    # every non-target asset present (live or carried) survive .dropna().
    non_target_cols = [f for f, _ in UNIVERSE if f != TARGET_FILENAME]
    prices_hourly_ff = prices_hourly_raw.copy()
    prices_hourly_ff[non_target_cols] = prices_hourly_ff[non_target_cols].ffill(limit=36)
    anchor_mask = prices_hourly_raw[TARGET_FILENAME].notna()
    prices_hourly = prices_hourly_ff.loc[anchor_mask].dropna()

    assert (
        prices_hourly.shape[1] == N_UNIVERSE
    ), f"expected {N_UNIVERSE} columns, got {prices_hourly.shape[1]}"
    assert prices_hourly.columns[0] == TARGET_FILENAME, "target asset must be first column"

    log_arr_h = np.log((prices_hourly / prices_hourly.shift(1)).to_numpy())
    returns_hourly = pd.DataFrame(
        log_arr_h, index=prices_hourly.index, columns=prices_hourly.columns
    ).dropna()

    # Daily resample — use last close of day, then drop any remaining NaN rows.
    prices_daily = prices_hourly.resample("1D").last().dropna()

    # Compute daily log-returns on the *unfiltered* price frame so every
    # return connects genuinely adjacent daily closes. Then drop the
    # returns whose underlying timestamp gap exceeds 5 calendar days —
    # those rows are the ones that blend multiple sessions into one bar
    # and poison the rolling z-score. Applying the filter to returns (not
    # to prices) means the filtered return is physically removed rather
    # than being re-created by bridging shift(1) over the discarded row.
    log_arr_d = np.log((prices_daily / prices_daily.shift(1)).to_numpy())
    returns_daily_all = pd.DataFrame(
        log_arr_d, index=prices_daily.index, columns=prices_daily.columns
    ).dropna()
    ret_gap_days = pd.Series(returns_daily_all.index).diff().dt.days.to_numpy()
    # First return has NaN gap (no previous row); keep it — it's not
    # bridging a hole, it's just the start of the sample.
    keep_returns = np.array([True if (g != g) else bool(g <= 5) for g in ret_gap_days], dtype=bool)
    returns_daily = returns_daily_all.loc[keep_returns]

    print(
        f"Universe: {returns_hourly.shape[1]} assets | "
        f"hourly {returns_hourly.shape[0]} bars "
        f"({returns_hourly.index[0]} -> {returns_hourly.index[-1]})"
    )
    print(
        f"Daily: {returns_daily.shape[0]} bars "
        f"({returns_daily.index[0]} -> {returns_daily.index[-1]})"
    )

    return LoadedUniverse(
        prices_hourly=prices_hourly,
        returns_hourly=returns_hourly,
        prices_daily=prices_daily,
        returns_daily=returns_daily,
    )


# -------------------------------------------------------------------- #
# Signal
# -------------------------------------------------------------------- #


def compute_signal(
    returns_df: pd.DataFrame, window: int, threshold: float = THRESHOLD
) -> pd.DataFrame:
    """Forman-Ricci based combo signal per the task brief.

    delta_Ricci is the *temporal* first difference of ricci_mean, not the
    cross-sectional (target − mean) version used in full_validation.py.
    """
    arr = returns_df.to_numpy()
    n, _k = arr.shape
    ricci_mean_series: list[float] = []
    delta_series: list[float] = []
    prev_rm: float | None = None
    fwd_col_idx = 0  # target = first column (USA_500)

    for i in range(window, n):
        w = arr[i - window : i]
        corr = np.corrcoef(w.T)
        np.fill_diagonal(corr, 0.0)
        adj = (np.abs(corr) > threshold).astype(float)
        deg = adj.sum(axis=1)
        rics: list[float] = [
            4.0 - deg[u] - deg[v]
            for u in range(len(deg))
            for v in range(u + 1, len(deg))
            if adj[u, v] > 0
        ]
        rm = float(np.mean(rics)) if rics else 0.0
        ricci_mean_series.append(rm)
        delta_series.append(0.0 if prev_rm is None else rm - prev_rm)
        prev_rm = rm

    df = pd.DataFrame(
        {
            "ricci_mean": ricci_mean_series,
            "delta_ricci": delta_series,
            "fwd_return": arr[window:n, fwd_col_idx],
        },
        index=returns_df.index[window:n],
    )

    roll = df["delta_ricci"].rolling(window)
    df["z_delta"] = (df["delta_ricci"] - roll.mean()) / (roll.std() + 1e-8)
    roll_m = df["ricci_mean"].rolling(window)
    df["z_mean"] = (df["ricci_mean"] - roll_m.mean()) / (roll_m.std() + 1e-8)
    df["combo"] = df["z_delta"] - 0.5 * df["z_mean"]
    return df.dropna()


# -------------------------------------------------------------------- #
# Backtest primitives
# -------------------------------------------------------------------- #


def expanding_quintile(combo: pd.Series, min_history: int = 50) -> pd.Series:
    """No-lookahead expanding-window quintile positioning."""
    pos = pd.Series(0.0, index=combo.index, dtype=float)
    vals = combo.to_numpy()
    for i in range(len(vals)):
        if i < min_history or not np.isfinite(vals[i]):
            continue
        hist = vals[:i]
        hist = hist[np.isfinite(hist)]
        if len(hist) < min_history:
            continue
        q_low = float(np.quantile(hist, 0.20))
        q_high = float(np.quantile(hist, 0.80))
        v = float(vals[i])
        if v >= q_high:
            pos.iloc[i] = 1.0
        elif v <= q_low:
            pos.iloc[i] = -1.0
    return pos


VOL_WINDOW = 20


def vol_weight(
    target_returns: pd.Series,
    split_date: pd.Timestamp,
    window: int = VOL_WINDOW,
) -> pd.Series:
    """Regime-aware position multiplier ∈ [0, 1].

    The Ricci-delta signal is known to be quiet in low-vol/DISPERSED
    regimes and active in high-vol/TENSION regimes. We therefore scale
    every quintile position by a smooth function of realised volatility:

        vol_weight(t) = tanh( realised_vol_20(t) / median_vol_train )

    * Shift by one bar to avoid using the current bar's own return.
    * `median_vol_train` is a scalar **computed on train only** — this is
      critical to preserve no-lookahead. The denominator is frozen before
      the test window begins.
    * In low-vol (vol ≪ median) → weight → 0, the strategy goes flat and
      does not bleed cost + variance into the equity curve.
    * In high-vol (vol ≫ median) → weight → 1, the strategy takes full
      quintile exposure.
    """
    # Use the absolute log-return's rolling std; shift(1) so the weight
    # at bar t depends only on data up to t-1.
    realised = target_returns.rolling(window).std().shift(1)
    train_median = float(realised.loc[realised.index < split_date].median())
    if not np.isfinite(train_median) or train_median <= 0.0:
        # Degenerate train slice — fall back to a neutral multiplier.
        return pd.Series(1.0, index=target_returns.index, dtype=float)
    weight_arr = np.tanh(realised.to_numpy() / train_median)
    weight = pd.Series(weight_arr, index=realised.index, dtype=float)
    return weight.fillna(0.0)


def backtest(
    df_sig: pd.DataFrame,
    split_date: pd.Timestamp,
    cost_bps: float,
    bars_per_year: float,
    vol_condition: bool = True,
) -> tuple[dict[str, Any], pd.Series]:
    train_mask = df_sig.index < split_date
    test_mask = df_sig.index >= split_date
    train = df_sig[train_mask]
    test = df_sig[test_mask]

    def _ic(sig: pd.Series, y: pd.Series) -> float:
        mask = sig.notna() & y.notna()
        if mask.sum() < 50:
            return float("nan")
        rho, _ = spearmanr(sig[mask], y[mask])
        return float(rho)

    ic_train = _ic(train["combo"], train["fwd_return"])
    ic_test = _ic(test["combo"], test["fwd_return"])

    quintile = expanding_quintile(df_sig["combo"])
    if vol_condition:
        w = vol_weight(df_sig["fwd_return"], split_date, VOL_WINDOW)
        w = w.reindex(df_sig.index).fillna(0.0)
        pos = quintile * w
    else:
        pos = quintile

    cost = pos.diff().abs().fillna(0.0) * cost_bps / 10_000.0
    ret = pos.shift(1) * df_sig["fwd_return"] - cost
    ret = ret.fillna(0.0)

    train_ret = ret[train_mask]
    test_ret = ret[test_mask]

    def _sharpe(s: pd.Series) -> float:
        if len(s) == 0 or s.std() == 0 or not np.isfinite(s.std()):
            return 0.0
        return float(s.mean() / (s.std() + 1e-8) * np.sqrt(bars_per_year))

    sharpe_test = _sharpe(test_ret)
    sharpe_train = _sharpe(train_ret)
    cum_test = test_ret.cumsum()
    maxdd = float((cum_test - cum_test.cummax()).min())

    crisis_mask = (ret.index >= CRISIS_LO) & (ret.index < CRISIS_HI)
    crisis_return = float(ret[crisis_mask].sum())

    overfit_ratio = (
        round(float(sharpe_test / (sharpe_train + 1e-8)), 3) if sharpe_train != 0 else float("nan")
    )

    # Vol-weight diagnostics — mean multiplier on train vs test shows
    # how much the regime gate actually suppressed positions where Ricci
    # was supposed to stay silent. With vol_condition off we report 1.0
    # so downstream consumers can still rely on the key being present.
    if vol_condition:
        diag_weight = vol_weight(df_sig["fwd_return"], split_date, VOL_WINDOW)
        mean_w_train = float(diag_weight[train_mask].mean())
        mean_w_test = float(diag_weight[test_mask].mean())
    else:
        mean_w_train = 1.0
        mean_w_test = 1.0

    block = {
        "IC_train": round(ic_train, 4),
        "IC_test": round(ic_test, 4),
        "sharpe_train": round(sharpe_train, 3),
        "sharpe_test": round(sharpe_test, 3),
        "maxdd_test": round(maxdd, 4),
        "crisis_2022": round(crisis_return, 4),
        "overfit_ratio": overfit_ratio,
        "vol_conditioned": bool(vol_condition),
        "mean_vol_weight_train": round(mean_w_train, 3),
        "mean_vol_weight_test": round(mean_w_test, 3),
        "n_train": int(train_mask.sum()),
        "n_test": int(test_mask.sum()),
    }
    return block, ret


# -------------------------------------------------------------------- #
# Permutation / orthogonality / walk-forward
# -------------------------------------------------------------------- #


def permutation_test(
    combo: pd.Series, fwd: pd.Series, n: int = N_PERMUTATIONS, seed: int = 42
) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    mask = combo.notna() & fwd.notna()
    c = combo[mask].to_numpy(dtype=float)
    y = fwd[mask].to_numpy(dtype=float)
    real_ic, _ = spearmanr(c, y)
    nulls: list[float] = []
    for _ in range(n):
        shuffled = rng.permutation(c)
        rho, _ = spearmanr(shuffled, y)
        nulls.append(float(rho))
    arr = np.asarray(nulls, dtype=float)
    p = float(np.mean(arr >= float(real_ic)))
    sigma = float((float(real_ic) - arr.mean()) / (arr.std() + 1e-8))
    return round(float(real_ic), 4), round(p, 4), round(sigma, 2)


def orthogonality(df_sig: pd.DataFrame, target_returns: pd.Series) -> dict[str, float]:
    """Compute corr(combo, momentum_20) and corr(combo, vol_10). Full period."""
    momentum = target_returns.rolling(20).sum()
    vol = target_returns.rolling(10).std()

    def _corr(a: pd.Series, b: pd.Series) -> float:
        common = a.index.intersection(b.index)
        ma = a.loc[common].dropna()
        mb = b.loc[common].dropna()
        common2 = ma.index.intersection(mb.index)
        if len(common2) < 50:
            return float("nan")
        rho, _ = spearmanr(ma.loc[common2], mb.loc[common2])
        return float(rho)

    return {
        "corr_momentum": round(_corr(df_sig["combo"], momentum), 4),
        "corr_vol": round(_corr(df_sig["combo"], vol), 4),
    }


def walkforward_5fold(
    df_sig: pd.DataFrame,
    bars_per_year: float,
    vol_condition: bool = True,
) -> list[dict[str, Any]]:
    """Split combo into 5 expanding-window test blocks and report IC/Sharpe.

    Per-fold positions use the same expanding-quintile rule as the
    main backtest, and (when ``vol_condition=True``) are multiplied by
    the same ``tanh(vol / median_train)`` regime gate, with the
    ``median_train`` frozen from each fold's own training window — no
    lookahead across folds.
    """
    n = len(df_sig)
    fold_size = n // (N_WALKFORWARD_FOLDS + 1)
    folds: list[dict[str, Any]] = []
    quintile = expanding_quintile(df_sig["combo"])
    for k in range(N_WALKFORWARD_FOLDS):
        test_start = fold_size * (k + 1)
        test_end = min(n, fold_size * (k + 2))
        if test_end - test_start < 20:
            continue
        test = df_sig.iloc[test_start:test_end]
        mask_te = test["combo"].notna() & test["fwd_return"].notna()
        if mask_te.sum() < 20:
            continue
        ic_te, _ = spearmanr(test.loc[mask_te, "combo"], test.loc[mask_te, "fwd_return"])
        fold_split = df_sig.index[test_start]
        if vol_condition:
            w = vol_weight(df_sig["fwd_return"], fold_split, VOL_WINDOW)
            fold_pos = quintile * w.reindex(df_sig.index).fillna(0.0)
            fold_mean_w_test = float(
                w.iloc[test_start:test_end].mean() if test_end > test_start else 0.0
            )
        else:
            fold_pos = quintile
            fold_mean_w_test = 1.0
        strat_full = (fold_pos.shift(1) * df_sig["fwd_return"]).fillna(0.0)
        test_ret = strat_full.iloc[test_start:test_end]
        sharpe_val = (
            float(test_ret.mean() / (test_ret.std() + 1e-8) * np.sqrt(bars_per_year))
            if test_ret.std() > 0
            else 0.0
        )
        folds.append(
            {
                "fold": k + 1,
                "test_start": str(test.index[0]),
                "test_end": str(test.index[-1]),
                "IC": round(float(ic_te), 4),
                "sharpe": round(sharpe_val, 3),
                "mean_vol_weight": round(fold_mean_w_test, 3),
                "n_test": int(test_end - test_start),
            }
        )
    return folds


# -------------------------------------------------------------------- #
# Plots
# -------------------------------------------------------------------- #


def plot_equity(runs: list[tuple[str, pd.Series]], title: str, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 5))
    for label, series in runs:
        cum = series.cumsum()
        ax.plot(
            cum.index,
            np.asarray(cum.to_numpy(), dtype=float),
            label=label,
            linewidth=1.2,
        )
    ax.axhline(0.0, color="black", lw=0.5)
    ax.set_title(title)
    ax.set_ylabel("cumulative log-return")
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    RESULTS_DIR.mkdir(exist_ok=True, parents=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)


# -------------------------------------------------------------------- #
# Orchestration
# -------------------------------------------------------------------- #


def _variant_block(
    returns_df: pd.DataFrame,
    window: int,
    cost_bps: float,
    bars_per_year: float,
    tag: str,
) -> tuple[dict[str, Any], pd.Series, pd.DataFrame]:
    print(f"[{tag}] compute signal (W={window}, θ={THRESHOLD})...")
    df_sig = compute_signal(returns_df, window=window, threshold=THRESHOLD)
    block, strat = backtest(df_sig, SPLIT_DATE, cost_bps=cost_bps, bars_per_year=bars_per_year)
    ic_perm, p_perm, sigma_perm = permutation_test(
        df_sig[df_sig.index >= SPLIT_DATE]["combo"],
        df_sig[df_sig.index >= SPLIT_DATE]["fwd_return"],
    )
    ortho = orthogonality(df_sig, returns_df.iloc[:, 0])
    block.update(
        {
            "permutation_p": p_perm,
            "permutation_sigma": sigma_perm,
            "permutation_ic": ic_perm,
            "corr_momentum": ortho["corr_momentum"],
            "corr_vol": ortho["corr_vol"],
            "vs_baseline_delta_IC": round(float(block["IC_test"]) - BASELINE_YFINANCE_IC, 4),
        }
    )
    return block, strat, df_sig


def verdict_from_daily(ic_test: float) -> str:
    if ic_test > BASELINE_YFINANCE_IC:
        return "IMPROVEMENT"
    if abs(ic_test - BASELINE_YFINANCE_IC) < 0.02:
        return "SAME"
    if ic_test < 0.08:
        return "DEGRADED"
    return "SAME"


def run() -> dict[str, Any]:
    u = load_universe()

    # --- DAILY (apples-to-apples) ---
    daily_block, daily_strat, daily_sig = _variant_block(
        u.returns_daily,
        WINDOW_DAILY,
        COST_DAILY_BPS,
        BARS_PER_YEAR_DAILY,
        "daily",
    )

    # --- HOURLY ---
    hourly_block, hourly_strat, hourly_sig = _variant_block(
        u.returns_hourly,
        WINDOW_HOURLY,
        COST_HOURLY_BPS,
        BARS_PER_YEAR_HOURLY,
        "hourly",
    )

    # --- Walk-forward (daily — apples-to-apples) ---
    walkforward = walkforward_5fold(daily_sig, BARS_PER_YEAR_DAILY)
    folds_positive = sum(1 for f in walkforward if f["IC"] > 0)

    # --- Verdict (daily only, per spec) ---
    verdict = verdict_from_daily(daily_block["IC_test"])

    # --- Equity plots ---
    plot_equity(
        [
            (
                f"combo daily  IC={daily_block['IC_test']:+.4f}",
                daily_strat[daily_strat.index >= SPLIT_DATE],
            ),
            (
                "USA_500 buy&hold",
                u.returns_daily.iloc[:, 0][u.returns_daily.index >= SPLIT_DATE].fillna(0.0),
            ),
        ],
        "Askar optimal universe — daily (test period)",
        RESULTS_DIR / "askar_optimal_daily_equity.png",
    )
    plot_equity(
        [
            (
                f"combo hourly  IC={hourly_block['IC_test']:+.4f}",
                hourly_strat[hourly_strat.index >= SPLIT_DATE],
            ),
            (
                "USA_500 buy&hold (hourly)",
                u.returns_hourly.iloc[:, 0][u.returns_hourly.index >= SPLIT_DATE].fillna(0.0),
            ),
        ],
        "Askar optimal universe — hourly (test period)",
        RESULTS_DIR / "askar_optimal_hourly_equity.png",
    )

    # --- JSON report ---
    hourly_lite = {
        "IC_train": hourly_block["IC_train"],
        "IC_test": hourly_block["IC_test"],
        "sharpe_test": hourly_block["sharpe_test"],
        "permutation_p": hourly_block["permutation_p"],
        "permutation_sigma": hourly_block["permutation_sigma"],
        "crisis_2022": hourly_block["crisis_2022"],
        "n_train": hourly_block["n_train"],
        "n_test": hourly_block["n_test"],
    }

    report: dict[str, Any] = {
        "universe": "14 assets — Askar L2 optimal",
        "universe_assets": [{"file": f, "label": lab} for f, lab in UNIVERSE],
        "baseline_yfinance_IC": BASELINE_YFINANCE_IC,
        "overlap_start": str(OVERLAP_START.date()),
        "overlap_end": str(OVERLAP_END.date()),
        "split_date": str(SPLIT_DATE.date()),
        "daily": daily_block,
        "hourly": hourly_lite,
        "walkforward_5fold": walkforward,
        "walkforward_folds_positive_IC": int(folds_positive),
        "verdict": verdict,
    }

    RESULTS_DIR.mkdir(exist_ok=True, parents=True)
    out = RESULTS_DIR / "askar_optimal_result.json"
    with out.open("w") as f:
        json.dump(report, f, indent=2)

    print(json.dumps({k: v for k, v in report.items() if k != "universe_assets"}, indent=2))
    return report


if __name__ == "__main__":
    run()
