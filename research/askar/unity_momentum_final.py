"""Unity + momentum ensemble — closing sprint of Askar validation.

Across PRs #190 / #191 / #192, exactly one signal on Askar's 53-asset
daily universe produced a positive test Sharpe: Unity = λ₁(corr) / N.
It sits at MARGINAL (IC_test = 0.051, Sharpe = +0.93, permutation
p ≈ 0.054). Momentum alone is statistically alive on the same panel
(IC_test ≈ 0.14, p ≈ 0). The theory says these two signals are
orthogonal — Unity measures how much variance the top mode absorbs,
momentum measures directional drift — so stacking them should push
the ensemble past the 0.08 institutional floor *if* orthogonality
holds and Unity carries real weight.

This module closes the loop with four sequential tests:

  TEST 1 — orthogonality gate
           If |spearmanr(unity, momentum_20)| > 0.30 the ensemble is
           mathematically meaningless and the whole run aborts with
           reason="orthogonality_gate_failed".

  TEST 2 — 5-fold walk-forward on Unity alone
           Fit sign and z-score stats on each fold's own training
           window, measure IC on the held-out block. Promotion gate:
           pass_rate ≥ 0.6 (≥ 3 / 5 positive IC folds) AND the last
           fold is positive AND all fold signs agree.

  TEST 3 — Unity + momentum ensemble
           Weights fit on the walk-forward train (2017-12-01 →
           2023-07-01). Grid scan over w_unity ∈ {0.10, 0.20, 0.30,
           0.40, 0.50}, w_momentum = 1 - w_unity. Pick the grid point
           with the best train IC, freeze both weights, apply to
           test without refit. If w_unity < 0.05 the ensemble
           collapses to pure momentum and is DISQUALIFIED.

  TEST 4 — side-by-side verdict
           Reports Unity standalone, momentum standalone and the
           ensemble against the GeoSync yfinance baseline
           (IC = 0.106, Sharpe = 1.737), runs the verdict routing,
           and drafts an Askar message when SIGNAL_FOUND.

Outputs:
    results/askar_unity_momentum_result.json
    results/askar_unity_momentum_equity.png
    results/askar_walk_forward_unity.json

Run: python research/askar/unity_momentum_final.py
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from research.askar.daily_53_experiment import (
    BARS_PER_YEAR_DAILY,
    BASELINE_YFINANCE_IC,
    SPLIT_DATE,
    DailyPanel,
    compute_unity_series,
    load_daily_panel,
)
from research.askar.optimal_universe import (
    expanding_quintile,
    permutation_test,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "results"

# Signal knobs — frozen for the closing sprint.
UNITY_WINDOW = 60
MOMENTUM_WINDOW = 20
VOL_WINDOW = 10
Z_WINDOW = 60
COST_BPS = 5.0

# Ensemble grid and thresholds.
W_UNITY_GRID: tuple[float, ...] = (0.10, 0.20, 0.30, 0.40, 0.50)
W_UNITY_DISQUAL_THRESHOLD = 0.05
# Secondary disqualification: even if w_unity clears the 0.05 spec rule,
# an ensemble that ends up > 95 % Spearman-correlated with raw momentum is
# indistinguishable from pure momentum as a tradable signal — the grid
# scan hit its Unity floor and Unity's contribution is mathematically
# swamped. We flag that case and downgrade the verdict accordingly.
CORR_ENSEMBLE_VS_MOMENTUM_CEIL = 0.95
CORR_GATE = 0.30

# Walk-forward configuration.
N_WALKFORWARD_FOLDS = 5

# Permutation and routing thresholds.
N_PERMUTATIONS = 1000
SIGNAL_IC_THRESHOLD = 0.08
SIGNAL_P_THRESHOLD = 0.10
MARGINAL_IC_FLOOR = 0.05
PASS_RATE_THRESHOLD = 0.6

# Baseline for the report.
BASELINE_YFINANCE_SHARPE = 1.737

# Crisis window — stays inside train, reported as a diagnostic.
CRISIS_2022_LO = pd.Timestamp("2022-01-01")
CRISIS_2022_HI = pd.Timestamp("2023-01-01")


# -------------------------------------------------------------------- #
# Utilities
# -------------------------------------------------------------------- #


def _ic(signal: pd.Series, y: pd.Series) -> float:
    mask = signal.notna() & y.notna()
    if mask.sum() < 30:
        return float("nan")
    rho, _ = spearmanr(signal[mask], y[mask])
    return float(rho)


def _sharpe(s: pd.Series, bars_per_year: float) -> float:
    if len(s) == 0 or s.std() == 0 or not np.isfinite(s.std()):
        return 0.0
    return float(s.mean() / (s.std() + 1e-8) * np.sqrt(bars_per_year))


def _rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    mu = series.rolling(window).mean()
    sd = series.rolling(window).std()
    return (series - mu) / (sd + 1e-8)


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


# -------------------------------------------------------------------- #
# TEST 1 — orthogonality gate
# -------------------------------------------------------------------- #


def orthogonality_gate(unity: pd.Series, target_returns: pd.Series) -> dict[str, Any]:
    """Compute corr(unity, momentum_20) and corr(unity, vol_10).

    The gate is passed if |corr_unity_momentum| ≤ CORR_GATE. Correlations
    are computed on the *full period intersection* so no train/test leak
    can enter the gate decision.
    """
    momentum_20 = target_returns.rolling(MOMENTUM_WINDOW).sum()
    vol_10 = target_returns.rolling(VOL_WINDOW).std()

    common = unity.index.intersection(momentum_20.index).intersection(vol_10.index)
    u = unity.loc[common].dropna()
    m = momentum_20.loc[u.index].dropna()
    v = vol_10.loc[u.index].dropna()

    common_um = u.index.intersection(m.index)
    common_uv = u.index.intersection(v.index)

    corr_um, _ = spearmanr(u.loc[common_um], m.loc[common_um])
    corr_uv, _ = spearmanr(u.loc[common_uv], v.loc[common_uv])

    corr_um_f = float(corr_um)
    corr_uv_f = float(corr_uv)

    return {
        "corr_unity_momentum": round(corr_um_f, 4),
        "corr_unity_vol": round(corr_uv_f, 4),
        "gate_threshold": CORR_GATE,
        "gate_passed": bool(abs(corr_um_f) <= CORR_GATE),
        "n_common_bars": int(len(common_um)),
    }


# -------------------------------------------------------------------- #
# TEST 2 — 5-fold walk-forward on Unity alone
# -------------------------------------------------------------------- #


@dataclass
class WalkForwardFold:
    fold: int
    test_start: str
    test_end: str
    IC_train: float
    IC_test: float
    sign: float
    n_train: int
    n_test: int


def walk_forward_unity(panel: DailyPanel, n_folds: int = N_WALKFORWARD_FOLDS) -> dict[str, Any]:
    """Walk-forward 5-fold IC stability test for Unity standalone.

    Each fold fits the z-score stats AND the sign on its own training
    window (bars strictly before the fold's test start) and evaluates IC
    on the held-out block only. No information from any later fold leaks
    backwards.
    """
    unity_df = compute_unity_series(panel.returns, window=UNITY_WINDOW)
    if len(unity_df) < 300:
        return {"folds": [], "error": "insufficient_data"}

    n = len(unity_df)
    fold_size = n // (n_folds + 1)  # first block is an expanding warmup

    folds: list[WalkForwardFold] = []
    for k in range(n_folds):
        train_end = fold_size * (k + 1)
        test_start = train_end
        test_end = min(n, fold_size * (k + 2))
        if test_end - test_start < 20:
            continue

        train = unity_df.iloc[:train_end]
        test = unity_df.iloc[test_start:test_end]

        mu = float(train["unity"].mean())
        sd = float(train["unity"].std()) + 1e-8
        z_train = (train["unity"] - mu) / sd
        z_test = (test["unity"] - mu) / sd

        ic_train = _ic(z_train, train["fwd_return"])
        sign_f = 1.0 if (np.isfinite(ic_train) and ic_train >= 0.0) else -1.0
        sig_test = sign_f * z_test
        ic_test = _ic(sig_test, test["fwd_return"])

        folds.append(
            WalkForwardFold(
                fold=k + 1,
                test_start=str(test.index[0]),
                test_end=str(test.index[-1]),
                IC_train=round(float(ic_train), 4),
                IC_test=round(float(ic_test), 4),
                sign=sign_f,
                n_train=int(train_end),
                n_test=int(test_end - test_start),
            )
        )

    fold_records = [f.__dict__ for f in folds]
    fold_ics = [f.IC_test for f in folds]
    fold_signs = [f.sign for f in folds]
    positive = [1 for ic in fold_ics if ic > 0]
    positive_count = len(positive)
    pass_rate = positive_count / len(folds) if folds else 0.0
    sign_consistent = bool(len(set(fold_signs)) == 1) if folds else False
    last_fold_positive = bool(folds[-1].IC_test > 0) if folds else False
    promoted = bool(pass_rate >= PASS_RATE_THRESHOLD and last_fold_positive and sign_consistent)

    return {
        "folds": fold_records,
        "fold_ics": fold_ics,
        "fold_signs": fold_signs,
        "positive_count": positive_count,
        "pass_rate": round(pass_rate, 4),
        "sign_consistent": sign_consistent,
        "last_fold_positive": last_fold_positive,
        "promoted": promoted,
    }


# -------------------------------------------------------------------- #
# TEST 3 — Unity + momentum ensemble
# -------------------------------------------------------------------- #


def run_ensemble(
    panel: DailyPanel,
) -> tuple[dict[str, Any], pd.Series, pd.DataFrame]:
    unity_df = compute_unity_series(panel.returns, window=UNITY_WINDOW)
    target_returns = panel.returns.iloc[:, 0]
    momentum = target_returns.rolling(MOMENTUM_WINDOW).sum()

    df = unity_df.copy()
    df["momentum_20"] = momentum.reindex(df.index)
    df = df.dropna(subset=["unity", "momentum_20", "fwd_return"])

    # Train-frozen z-scores for BOTH components. Unity has slow drift
    # (the correlation matrix does not shuffle bar-to-bar), so a rolling
    # 60-bar z-score collapses it to fast noise and flips its sign
    # relative to the train-frozen version we validated in PR #192. We
    # therefore fit mu/sd once on the training window and reuse the same
    # scalars over train AND test — matches the walk-forward basis and
    # preserves Unity's real variation.
    train_pre = df[df.index < SPLIT_DATE]
    mu_u = float(train_pre["unity"].mean())
    sd_u = float(train_pre["unity"].std()) + 1e-8
    mu_m = float(train_pre["momentum_20"].mean())
    sd_m = float(train_pre["momentum_20"].std()) + 1e-8
    df["z_unity"] = (df["unity"] - mu_u) / sd_u
    df["z_momentum"] = (df["momentum_20"] - mu_m) / sd_m
    df = df.dropna(subset=["z_unity", "z_momentum"])

    train = df[df.index < SPLIT_DATE]

    # Train-only grid scan
    best_w_u = W_UNITY_GRID[0]
    best_ic_train_grid = -float("inf")
    for w_u in W_UNITY_GRID:
        w_m = 1.0 - w_u
        blend = w_u * train["z_unity"] + w_m * train["z_momentum"]
        ic_t = _ic(blend, train["fwd_return"])
        if np.isfinite(ic_t) and ic_t > best_ic_train_grid:
            best_ic_train_grid = float(ic_t)
            best_w_u = w_u
    best_w_m = 1.0 - best_w_u
    # Primary disqualification: spec w_unity < 0.05 rule.
    disq_by_weight = bool(best_w_u < W_UNITY_DISQUAL_THRESHOLD)
    # Secondary disqualification: grid scan hit its floor AND the resulting
    # ensemble is essentially momentum (recorded below after the corr is
    # measured). This catches the case where the spec's threshold is too
    # lenient — w_unity = 0.10 passes the nominal rule but the ensemble
    # ends up 98 % correlated with raw momentum, so Unity contributes
    # nothing measurable and the signal is not "ours".

    ensemble = best_w_u * df["z_unity"] + best_w_m * df["z_momentum"]

    train_mask = df.index < SPLIT_DATE
    test_mask = df.index >= SPLIT_DATE

    ic_train_ens = _ic(ensemble[train_mask], train["fwd_return"])
    ic_test_ens = _ic(ensemble[test_mask], df.loc[test_mask, "fwd_return"])
    ic_test_unity = _ic(df.loc[test_mask, "z_unity"], df.loc[test_mask, "fwd_return"])
    ic_test_mom = _ic(df.loc[test_mask, "z_momentum"], df.loc[test_mask, "fwd_return"])

    # Correlation between ensemble and raw momentum (for spec reporting).
    corr_ens_mom_raw, _ = spearmanr(ensemble.to_numpy(), df["z_momentum"].to_numpy())
    corr_ens_mom = float(corr_ens_mom_raw)

    # Permutation test with 1000 shuffles.
    _ic_perm, p_val, sigma_val = permutation_test(
        ensemble[test_mask],
        df.loc[test_mask, "fwd_return"],
        n=N_PERMUTATIONS,
        seed=42,
    )

    # Quintile backtest on the full-series ensemble.
    quintile = expanding_quintile(ensemble)
    cost = quintile.diff().abs().fillna(0.0) * COST_BPS / 10_000.0
    strat = (quintile.shift(1) * df["fwd_return"] - cost).fillna(0.0)

    test_strat = strat[test_mask]
    train_strat = strat[train_mask]
    sharpe_test = _sharpe(test_strat, BARS_PER_YEAR_DAILY)
    sharpe_train = _sharpe(train_strat, BARS_PER_YEAR_DAILY)
    cum_test = test_strat.cumsum()
    maxdd = float((cum_test - cum_test.cummax()).min())

    overfit_ratio: float | None
    if sharpe_train != 0:
        overfit_ratio = round(float(sharpe_test / (sharpe_train + 1e-8)), 3)
    else:
        overfit_ratio = None

    crisis_mask = (strat.index >= CRISIS_2022_LO) & (strat.index < CRISIS_2022_HI)
    crisis_return = float(strat[crisis_mask].sum())

    report = {
        "w_unity": round(float(best_w_u), 4),
        "w_momentum": round(float(best_w_m), 4),
        "IC_train_ensemble": round(float(ic_train_ens), 4),
        "IC_train_grid_peak": round(float(best_ic_train_grid), 4),
        "IC_test_ensemble": round(float(ic_test_ens), 4),
        "IC_test_unity_alone": round(float(ic_test_unity), 4),
        "IC_test_momentum_alone": round(float(ic_test_mom), 4),
        "sharpe_train": round(sharpe_train, 3),
        "sharpe_test": round(sharpe_test, 3),
        "maxdd_test": round(maxdd, 4),
        "overfit_ratio": overfit_ratio,
        "permutation_p": round(float(p_val), 4),
        "permutation_sigma": round(float(sigma_val), 2),
        "crisis_2022": round(crisis_return, 4),
        "corr_ensemble_vs_momentum": round(corr_ens_mom, 4),
        "disqualified_by_weight": disq_by_weight,
        "effectively_momentum": bool(
            best_w_u == W_UNITY_GRID[0] and abs(corr_ens_mom) >= CORR_ENSEMBLE_VS_MOMENTUM_CEIL
        ),
        "disqualified": bool(
            disq_by_weight
            or (best_w_u == W_UNITY_GRID[0] and abs(corr_ens_mom) >= CORR_ENSEMBLE_VS_MOMENTUM_CEIL)
        ),
        "disqual_threshold": W_UNITY_DISQUAL_THRESHOLD,
        "disqual_corr_ceil": CORR_ENSEMBLE_VS_MOMENTUM_CEIL,
        "w_unity_grid": list(W_UNITY_GRID),
        "n_train_bars": int(train_mask.sum()),
        "n_test_bars": int(test_mask.sum()),
    }
    return report, strat, df


# -------------------------------------------------------------------- #
# TEST 4 — standalone diagnostics for Unity and momentum
# -------------------------------------------------------------------- #


def unity_standalone(df: pd.DataFrame) -> dict[str, Any]:
    """Unity alone on the same enriched df, train-selected sign."""
    train_mask = df.index < SPLIT_DATE
    test_mask = df.index >= SPLIT_DATE
    z = df["z_unity"]
    ic_train = _ic(z[train_mask], df.loc[train_mask, "fwd_return"])
    sign_f = 1.0 if (np.isfinite(ic_train) and ic_train >= 0.0) else -1.0
    signal = sign_f * z
    ic_test = _ic(signal[test_mask], df.loc[test_mask, "fwd_return"])

    quintile = expanding_quintile(signal)
    cost = quintile.diff().abs().fillna(0.0) * COST_BPS / 10_000.0
    strat = (quintile.shift(1) * df["fwd_return"] - cost).fillna(0.0)
    sharpe_test = _sharpe(strat[test_mask], BARS_PER_YEAR_DAILY)

    _icp, p_val, _sigma = permutation_test(
        signal[test_mask],
        df.loc[test_mask, "fwd_return"],
        n=N_PERMUTATIONS,
        seed=17,
    )

    return {
        "sign": sign_f,
        "IC_train": round(float(ic_train), 4),
        "IC_test": round(float(ic_test), 4),
        "sharpe_test": round(sharpe_test, 3),
        "permutation_p": round(float(p_val), 4),
    }


def momentum_standalone(df: pd.DataFrame) -> dict[str, Any]:
    """Momentum_20 alone on the same enriched df, train-selected sign."""
    train_mask = df.index < SPLIT_DATE
    test_mask = df.index >= SPLIT_DATE
    z = df["z_momentum"]
    ic_train = _ic(z[train_mask], df.loc[train_mask, "fwd_return"])
    sign_f = 1.0 if (np.isfinite(ic_train) and ic_train >= 0.0) else -1.0
    signal = sign_f * z
    ic_test = _ic(signal[test_mask], df.loc[test_mask, "fwd_return"])

    quintile = expanding_quintile(signal)
    cost = quintile.diff().abs().fillna(0.0) * COST_BPS / 10_000.0
    strat = (quintile.shift(1) * df["fwd_return"] - cost).fillna(0.0)
    sharpe_test = _sharpe(strat[test_mask], BARS_PER_YEAR_DAILY)

    _icp, p_val, _sigma = permutation_test(
        signal[test_mask],
        df.loc[test_mask, "fwd_return"],
        n=N_PERMUTATIONS,
        seed=29,
    )

    return {
        "sign": sign_f,
        "IC_train": round(float(ic_train), 4),
        "IC_test": round(float(ic_test), 4),
        "sharpe_test": round(sharpe_test, 3),
        "permutation_p": round(float(p_val), 4),
    }


# -------------------------------------------------------------------- #
# Plot
# -------------------------------------------------------------------- #


def plot_equity(runs: list[tuple[str, pd.Series]], out: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 5))
    for label, s in runs:
        cum = s.cumsum()
        ax.plot(
            cum.index,
            np.asarray(cum.to_numpy(), dtype=float),
            label=label,
            linewidth=1.2,
        )
    ax.axhline(0.0, color="black", lw=0.5)
    ax.set_title(title)
    ax.set_ylabel("cumulative log-return (after costs)")
    ax.legend(loc="best", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    RESULTS_DIR.mkdir(exist_ok=True, parents=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)


# -------------------------------------------------------------------- #
# Orchestration
# -------------------------------------------------------------------- #


def _verdict(
    ensemble: dict[str, Any],
    walk_forward: dict[str, Any],
    unity_only: dict[str, Any],
) -> str:
    """Verdict routing with effective-momentum guard.

    The ensemble is DISQUALIFIED when:
      a) w_unity < 0.05 (spec rule), OR
      b) the grid scan hit its w_unity floor AND the final ensemble is
         > 95 % Spearman-correlated with raw momentum — Unity is
         mathematically swamped and the blend is a momentum costume.

    When the ensemble is disqualified we still check whether Unity
    standalone clears the MARGINAL floor with a promoted walk-forward
    record. If it does, the honest verdict is MARGINAL (Unity is real
    but cannot be stacked with momentum on this panel). Otherwise it is
    DISQUALIFIED.
    """
    disq = bool(ensemble.get("disqualified"))
    unity_ic = float(unity_only.get("IC_test", float("nan")))
    unity_promoted = bool(walk_forward.get("promoted"))

    if disq:
        if np.isfinite(unity_ic) and unity_ic >= MARGINAL_IC_FLOOR and unity_promoted:
            return "MARGINAL"
        return "DISQUALIFIED"

    ic = float(ensemble.get("IC_test_ensemble", float("nan")))
    p = float(ensemble.get("permutation_p", 1.0))
    if np.isfinite(ic) and ic >= SIGNAL_IC_THRESHOLD and p < SIGNAL_P_THRESHOLD:
        if unity_promoted:
            return "SIGNAL_FOUND"
        return "MARGINAL"
    if np.isfinite(ic) and ic >= MARGINAL_IC_FLOOR:
        return "MARGINAL"
    return "NO_SIGNAL"


def _askar_message(
    ensemble: dict[str, Any],
    walk_forward: dict[str, Any],
    orthogonality: dict[str, Any],
) -> str:
    ic = float(ensemble["IC_test_ensemble"])
    sharpe = float(ensemble["sharpe_test"])
    maxdd_pct = float(ensemble["maxdd_test"]) * 100.0
    pos_n = int(walk_forward.get("positive_count", 0))
    total_n = len(walk_forward.get("folds", [])) or N_WALKFORWARD_FOLDS
    corr_ens_mom = float(ensemble["corr_ensemble_vs_momentum"])
    w_unity = float(ensemble["w_unity"])
    above_below = "above" if ic > BASELINE_YFINANCE_IC else "below"

    return (
        "Tested dimensionality collapse signal (λ₁/N) + 20-day momentum "
        "on your 53-asset L2 daily universe (2017-2026).\n\n"
        f"Ensemble IC = {ic:+.4f}, Sharpe = {sharpe:+.3f}, "
        f"MaxDD = {maxdd_pct:+.2f}%.\n"
        f"Walk-forward: {pos_n}/{total_n} folds positive, sign "
        f"consistent = {walk_forward.get('sign_consistent')}.\n\n"
        f"Signal–raw-momentum correlation = {corr_ens_mom:+.4f} "
        f"(orthogonality-gate check = {orthogonality.get('gate_passed')}).\n"
        f"Unity component weight = {w_unity:.2f} — genuine contribution "
        "(> 0.05 disqualification floor).\n\n"
        f"GeoSync baseline (yfinance): IC=0.106, Sharpe=1.737.\n"
        f"Your data: IC={ic:+.4f} — {above_below} baseline.\n\n"
        "Next step: live paper trading via evidence rail. Do you have "
        "VIX / HYG / LQD / MOVE in your archive? Adding them would "
        "sharpen the regime-detection layer."
    )


def run() -> dict[str, Any]:
    panel = load_daily_panel()
    target_returns = panel.returns.iloc[:, 0]
    unity_series = compute_unity_series(panel.returns, window=UNITY_WINDOW)["unity"]

    print("[TEST 1] orthogonality gate")
    ortho = orthogonality_gate(unity_series, target_returns)
    print(
        f"[TEST 1] corr(unity,mom)={ortho['corr_unity_momentum']:+.4f}  "
        f"corr(unity,vol)={ortho['corr_unity_vol']:+.4f}  "
        f"gate_passed={ortho['gate_passed']}"
    )

    if not ortho["gate_passed"]:
        # Abort and emit a truthful report without the downstream work.
        short_report: dict[str, Any] = {
            "orthogonality": ortho,
            "walk_forward_unity": {"skipped": True, "reason": "gate_failed"},
            "ensemble_unity_momentum": {
                "skipped": True,
                "reason": "gate_failed",
            },
            "unity_standalone": {"skipped": True, "reason": "gate_failed"},
            "momentum_standalone": {"skipped": True, "reason": "gate_failed"},
            "baseline_geosync_yfinance": {
                "IC_test": BASELINE_YFINANCE_IC,
                "sharpe_test": BASELINE_YFINANCE_SHARPE,
            },
            "verdict": "DISQUALIFIED",
            "askar_message": "",
        }
        RESULTS_DIR.mkdir(exist_ok=True, parents=True)
        (RESULTS_DIR / "askar_unity_momentum_result.json").write_text(
            json.dumps(_to_json_safe(short_report), indent=2)
        )
        return short_report

    print("[TEST 2] walk-forward 5-fold on Unity")
    walk_forward = walk_forward_unity(panel, n_folds=N_WALKFORWARD_FOLDS)
    if walk_forward.get("folds"):
        print(
            "[TEST 2] "
            f"folds={[f['IC_test'] for f in walk_forward['folds']]}  "
            f"pass_rate={walk_forward['pass_rate']:.2f}  "
            f"sign_consistent={walk_forward['sign_consistent']}  "
            f"promoted={walk_forward['promoted']}"
        )
    (RESULTS_DIR).mkdir(exist_ok=True, parents=True)
    (RESULTS_DIR / "askar_walk_forward_unity.json").write_text(
        json.dumps(_to_json_safe(walk_forward), indent=2)
    )

    print("[TEST 3] ensemble Unity + momentum")
    ensemble, strat_ens, enriched_df = run_ensemble(panel)
    print(
        f"[TEST 3] w_u={ensemble['w_unity']:.2f}  "
        f"w_m={ensemble['w_momentum']:.2f}  "
        f"IC_test={ensemble['IC_test_ensemble']:+.4f}  "
        f"Sharpe={ensemble['sharpe_test']:+.3f}  "
        f"perm_p={ensemble['permutation_p']:.4f}  "
        f"disqualified={ensemble['disqualified']}"
    )

    print("[TEST 4] standalone diagnostics")
    unity_only = unity_standalone(enriched_df)
    momentum_only = momentum_standalone(enriched_df)
    print(
        f"[TEST 4] unity_alone IC={unity_only['IC_test']:+.4f}  "
        f"mom_alone IC={momentum_only['IC_test']:+.4f}"
    )

    verdict = _verdict(ensemble, walk_forward, unity_only)
    askar_message = (
        _askar_message(ensemble, walk_forward, ortho) if verdict == "SIGNAL_FOUND" else ""
    )

    # Equity-curve plot
    test_mask = enriched_df.index >= SPLIT_DATE
    buy_hold = panel.returns[panel.target].loc[panel.returns.index >= SPLIT_DATE].fillna(0.0)
    plot_equity(
        [
            (
                f"ensemble IC={ensemble['IC_test_ensemble']:+.4f}  w_u={ensemble['w_unity']:.2f}",
                strat_ens[test_mask],
            ),
            (f"{panel.target} buy&hold", buy_hold),
        ],
        RESULTS_DIR / "askar_unity_momentum_equity.png",
        "Askar — Unity + momentum ensemble (test period, after costs)",
    )

    report: dict[str, Any] = {
        "orthogonality": ortho,
        "walk_forward_unity": walk_forward,
        "ensemble_unity_momentum": ensemble,
        "unity_standalone": unity_only,
        "momentum_standalone": momentum_only,
        "baseline_geosync_yfinance": {
            "IC_test": BASELINE_YFINANCE_IC,
            "sharpe_test": BASELINE_YFINANCE_SHARPE,
        },
        "verdict": verdict,
        "askar_message": askar_message,
    }

    RESULTS_DIR.mkdir(exist_ok=True, parents=True)
    (RESULTS_DIR / "askar_unity_momentum_result.json").write_text(
        json.dumps(_to_json_safe(report), indent=2)
    )

    # Printable summary
    printable = {
        "orthogonality": ortho,
        "walk_forward": {
            "pass_rate": walk_forward.get("pass_rate"),
            "sign_consistent": walk_forward.get("sign_consistent"),
            "positive_count": walk_forward.get("positive_count"),
            "fold_ics": walk_forward.get("fold_ics"),
            "fold_signs": walk_forward.get("fold_signs"),
            "promoted": walk_forward.get("promoted"),
        },
        "ensemble": ensemble,
        "unity_alone": unity_only,
        "momentum_alone": momentum_only,
        "verdict": verdict,
    }
    print(json.dumps(_to_json_safe(printable), indent=2))
    return report


if __name__ == "__main__":
    run()
