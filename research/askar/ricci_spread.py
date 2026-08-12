"""Ricci Spread pair-trading study on Askar's OTS Capital L2 hourly data.

Hypothesis: Forman-Ricci curvature on a multi-asset correlation graph
captures topological stress differently for equity (SPY) vs gold (XAUUSD).
The spread between per-asset Ricci contributions is expected to carry
independent information vs. single-asset baseline.

Run:
    python research/askar/ricci_spread.py
Outputs:
    results/askar_ricci_spread_result.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "askar"
RESULTS_DIR = REPO_ROOT / "results"

WINDOW = 120  # 5 trading days of hourly data
THRESHOLD = 0.30  # correlation-edge threshold (same as GeoSync baseline)
COST_BPS = 5  # 5 bps per round-trip turnover unit
N_PERMUTATIONS = 500
TRADING_HOURS_PER_YEAR = 252 * 8


# -------------------------------------------------------------------- #
# Data loading
# -------------------------------------------------------------------- #


def load_askar(path: Path) -> pd.Series:
    df = pd.read_parquet(path)
    df = df.sort_values("ts").set_index("ts")
    df = df[df.index >= pd.Timestamp("2017-01-01")]
    return df["close"].rename(path.stem)


def load_prices() -> pd.DataFrame:
    spy = load_askar(DATA_DIR / "SPDR_S_P_500_ETF_GMT_0_NO-DST.parquet")
    gold = load_askar(DATA_DIR / "XAUUSD_GMT_0_NO-DST.parquet")
    usa = load_askar(DATA_DIR / "USA_500_Index_GMT_0_NO-DST.parquet")
    prices = pd.DataFrame({"SPY": spy, "GOLD": gold, "USA500": usa}).dropna()
    return prices


# -------------------------------------------------------------------- #
# Forman-Ricci per asset
# -------------------------------------------------------------------- #


def forman_ricci_per_asset(
    returns_window: pd.DataFrame, threshold: float
) -> tuple[dict[str, float], float]:
    """Mean Forman-Ricci contribution per node.

    For edge e = (u, v):  Ric_F(e) = 4 - deg(u) - deg(v)
    Per-asset score = mean over edges incident to that asset.
    """
    corr = np.corrcoef(returns_window.T)
    np.fill_diagonal(corr, 0.0)
    adj = (np.abs(corr) > threshold).astype(float)
    deg = adj.sum(axis=1)
    cols = list(returns_window.columns)

    per_asset: dict[str, float] = {}
    for i, name in enumerate(cols):
        edges = [4 - deg[i] - deg[j] for j in range(len(cols)) if adj[i, j] > 0]
        per_asset[name] = float(np.mean(edges)) if edges else 0.0
    return per_asset, float(deg.mean())


# -------------------------------------------------------------------- #
# Signal & backtest
# -------------------------------------------------------------------- #


def build_signal(
    returns: pd.DataFrame,
    target: str = "SPY",
    counterpart: str = "GOLD",
) -> pd.DataFrame:
    """Build Ricci-spread signal dataframe for (target, counterpart) pair.

    target      — asset whose forward return we forecast (1h, 4h)
    counterpart — the "other leg" of the Ricci spread
    """
    signals: list[dict[str, Any]] = []
    fwd_4h = returns[target].rolling(4).sum().shift(-3)  # sum of next 4 bars

    for i in range(WINDOW, len(returns) - 1):
        w = returns.iloc[i - WINDOW : i]
        per_asset, _mean_deg = forman_ricci_per_asset(w, THRESHOLD)
        ricci_t = per_asset.get(target, 0.0)
        ricci_c = per_asset.get(counterpart, 0.0)
        signals.append(
            {
                "ts": returns.index[i],
                "ricci_target": ricci_t,
                "ricci_counterpart": ricci_c,
                "ricci_spread": ricci_t - ricci_c,
                "ricci_mean": float(np.mean(list(per_asset.values()))),
                "fwd_return_1h": float(returns[target].iloc[i]),
                "fwd_return_4h": float(fwd_4h.iloc[i]) if i < len(fwd_4h) else np.nan,
            }
        )
    return pd.DataFrame(signals).set_index("ts")


def z_score(series: pd.Series, window: int) -> pd.Series:
    mu = series.rolling(window).mean()
    sd = series.rolling(window).std()
    return (series - mu) / (sd + 1e-8)


def quintile_position(signal: pd.Series, min_history: int = 50) -> pd.Series:
    """Expanding-window quintile positioning — no lookahead.

    Position at time t is based only on signal[:t] quantiles.
    """
    positions = pd.Series(0.0, index=signal.index, dtype=float)
    values = signal.values
    for i in range(len(signal)):
        if i < min_history or not np.isfinite(values[i]):
            positions.iloc[i] = 0.0
            continue
        hist = values[:i]
        hist = hist[np.isfinite(hist)]
        if len(hist) < min_history:
            positions.iloc[i] = 0.0
            continue
        q_low = np.quantile(hist, 0.20)
        q_high = np.quantile(hist, 0.80)
        v = values[i]
        if v >= q_high:
            positions.iloc[i] = 1.0
        elif v <= q_low:
            positions.iloc[i] = -1.0
        else:
            positions.iloc[i] = 0.0
    return positions


def permutation_test(
    signal: pd.Series, fwd_returns: pd.Series, n: int = N_PERMUTATIONS, seed: int = 42
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    sig_clean = signal.dropna()
    common = sig_clean.index.intersection(fwd_returns.dropna().index)
    sig_arr: np.ndarray = np.asarray(sig_clean.loc[common].to_numpy(), dtype=float)
    rets_arr: np.ndarray = np.asarray(fwd_returns.loc[common].to_numpy(), dtype=float)
    real_ic, _ = spearmanr(sig_arr, rets_arr)
    null_ics: list[float] = []
    for _ in range(n):
        shuffled = rng.permutation(sig_arr)
        ic, _ = spearmanr(shuffled, rets_arr)
        null_ics.append(float(ic))
    null_arr = np.asarray(null_ics)
    p = float(np.mean(null_arr >= float(real_ic)))
    return float(real_ic), p


# -------------------------------------------------------------------- #
# Main pipeline
# -------------------------------------------------------------------- #


def run_pair(
    returns: pd.DataFrame,
    target: str,
    counterpart: str,
    tag: str,
) -> dict[str, Any]:
    df_sig = build_signal(returns, target=target, counterpart=counterpart)
    print(f"[{tag}] Signal: {len(df_sig)} bars  target={target}  counterpart={counterpart}")

    df_sig["z_spread"] = z_score(df_sig["ricci_spread"], WINDOW)
    df_sig["z_mean"] = z_score(df_sig["ricci_mean"], WINDOW)
    df_sig["combo"] = df_sig["z_spread"] - 0.5 * df_sig["z_mean"]
    df_sig["baseline"] = df_sig["z_mean"] * -1.0

    split = int(len(df_sig) * 0.70)
    train = df_sig.iloc[:split]
    test = df_sig.iloc[split:]

    tr_mask = train["combo"].notna() & train["fwd_return_1h"].notna()
    te_mask = test["combo"].notna() & test["fwd_return_1h"].notna()
    ic_train, _ = spearmanr(train.loc[tr_mask, "combo"], train.loc[tr_mask, "fwd_return_1h"])
    ic_test, _ = spearmanr(test.loc[te_mask, "combo"], test.loc[te_mask, "fwd_return_1h"])

    # Baseline
    te_mask_b = test["baseline"].notna() & test["fwd_return_1h"].notna()
    ic_baseline, _ = spearmanr(
        test.loc[te_mask_b, "baseline"], test.loc[te_mask_b, "fwd_return_1h"]
    )

    # Backtest with expanding-window quintile position on full series
    positions = quintile_position(df_sig["combo"])
    trades = positions.diff().abs().fillna(0.0)
    strat = positions.shift(1) * df_sig["fwd_return_1h"] - trades * COST_BPS / 10_000.0
    strat = strat.fillna(0.0)

    train_strat = strat.iloc[:split]
    test_strat = strat.iloc[split:]

    def sharpe(s: pd.Series) -> float:
        if s.std() == 0 or not np.isfinite(s.std()):
            return 0.0
        return float(s.mean() / s.std() * np.sqrt(TRADING_HOURS_PER_YEAR))

    sharpe_train = sharpe(train_strat)
    sharpe_test = sharpe(test_strat)
    cum_test = test_strat.cumsum()
    maxdd_test = float((cum_test - cum_test.cummax()).min())

    ic_perm, p_val = permutation_test(
        test.loc[te_mask, "combo"],
        test.loc[te_mask, "fwd_return_1h"],
    )

    result: dict[str, Any] = {
        "tag": tag,
        "data_source": "Askar OTS Capital — L2 hourly",
        "assets": ["SPY", "GOLD", "USA500"],
        "target": f"{target} 1h forward return",
        "counterpart": counterpart,
        "window_hours": WINDOW,
        "threshold": THRESHOLD,
        "cost_bps": COST_BPS,
        "n_aligned_bars": int(len(returns)),
        "n_signal_bars": int(len(df_sig)),
        "n_train_bars": int(len(train)),
        "n_test_bars": int(len(test)),
        "IC_train": round(float(ic_train), 4),
        "IC_test": round(float(ic_test), 4),
        "IC_baseline_no_spread": round(float(ic_baseline), 4),
        "IC_delta_vs_baseline": round(float(ic_test) - float(ic_baseline), 4),
        "IC_permutation": round(float(ic_perm), 4),
        "train_sharpe": round(sharpe_train, 3),
        "test_sharpe": round(sharpe_test, 3),
        "test_maxdd": round(maxdd_test, 4),
        "permutation_p": round(float(p_val), 4),
        "overfit_ratio": (
            round(sharpe_test / (sharpe_train + 1e-8), 3) if sharpe_train != 0 else None
        ),
        "date_range": [
            str(returns.index[0]),
            str(returns.index[-1]),
        ],
    }

    spread_adds_value = (
        result["IC_test"] > result["IC_baseline_no_spread"]
        and result["IC_test"] > 0.05
        and result["permutation_p"] < 0.10
    )
    result["verdict"] = "SPREAD_ADDS_VALUE" if spread_adds_value else "NO_SPREAD_EDGE"

    # Persist the strategy equity curve so we can plot it.
    result["_strat_series"] = strat
    return result


def _plot_equity(results: list[dict[str, Any]], split_frac: float = 0.70) -> Path:
    """Plot cumulative PnL of every run_pair result. Returns saved path."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 5))
    for res in results:
        strat: pd.Series = res.pop("_strat_series")
        split = int(len(strat) * split_frac)
        test_strat = strat.iloc[split:]
        cum = test_strat.cumsum()
        label = (
            f"{res['tag']}  IC={res['IC_test']:+.4f}  "
            f"Sh={res['test_sharpe']:+.2f}  p={res['permutation_p']:.2f}"
        )
        ax.plot(
            cum.index,
            np.asarray(cum.to_numpy(), dtype=float),
            label=label,
            linewidth=1.2,
        )
    ax.axhline(0.0, color="black", lw=0.5)
    ax.set_title("Askar — Ricci Spread pair trading (test period, after costs)")
    ax.set_ylabel("cumulative log-return")
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.3)
    RESULTS_DIR.mkdir(exist_ok=True, parents=True)
    out = RESULTS_DIR / "askar_ricci_spread_equity.png"
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def run() -> dict[str, Any]:
    prices = load_prices()
    ratio = prices / prices.shift(1)
    # np.log on a DataFrame returns a DataFrame at runtime; typing stubs
    # report ndarray, so we round-trip through a pandas call.
    log_df = pd.DataFrame(np.log(ratio.to_numpy()), index=ratio.index, columns=ratio.columns)
    returns = log_df.dropna()
    print(f"Aligned: {len(returns)} hourly bars, {returns.index[0]} -> {returns.index[-1]}")

    primary = run_pair(returns, target="SPY", counterpart="GOLD", tag="SPY-GOLD")
    alt = run_pair(returns, target="SPY", counterpart="USA500", tag="SPY-USA500")

    # Equity curve plot (pops the series from each dict).
    plot_path = _plot_equity([primary, alt])

    report: dict[str, Any] = {
        "primary_SPY_vs_GOLD": primary,
        "alt_SPY_vs_USA500": alt,
        "equity_curve_png": str(plot_path.relative_to(REPO_ROOT)),
    }

    RESULTS_DIR.mkdir(exist_ok=True, parents=True)
    out = RESULTS_DIR / "askar_ricci_spread_result.json"
    with out.open("w") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
