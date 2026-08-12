"""Regime-Conditional Ricci experiment on Askar's 14-asset L2 panel.

Implements CLAUDE_CODE_TASK_regime_experiment.md end-to-end:

  Module 1 — unsupervised regime detection via GMM on 5 graph-topology
             features (eigen_gap, ricci_mean, delta_ricci, fiedler,
             graph_density). GMM is fit on TRAIN bars only; labels are
             then predicted globally and mapped to the four canonical
             GeoSync phase names {COHERENT, TENSION, FRACTURE,
             DISPERSED} by ranking clusters on a stress score.

  Module 2 — regime-conditional IC. Computes IC(combo, fwd_return)
             restricted to each phase, plus local-IC / eigen_gap
             correlation, plus the phase transition matrix.

  Module 3 — three adaptive-signal variants, all evaluated with the
             same train/test split as optimal_universe:
               A. hard gate: trade only in {TENSION, FRACTURE}
               B. eigen-gap continuous weight (sigmoid of z(eigen_gap))
               C. ricci + momentum stack with train-fit weights

  Module 4 — universe sensitivity: re-runs the baseline combo on four
             alternative compositions (FX-only, macro, crisis-focused,
             broad daily from data/askar_full).

  Module 5 — threshold / window sensitivity grid on train only.

  Final verdict — SIGNAL_FOUND / REGIME_CONDITIONAL / WEAK / NO_SIGNAL.

Output: results/askar_regime_experiment.json
        results/askar_regime_variants_equity.png

Scientific framing: Sandhu 2016, Wang 2023, MDPI 2026 — Forman-Ricci
is a fragility indicator, not a directional one; it earns alpha where
cross-asset topology is under geometric stress.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.mixture import GaussianMixture

from research.askar.optimal_universe import (
    BARS_PER_YEAR_HOURLY,
    DATA_DIR,
    SPLIT_DATE,
    THRESHOLD,
    backtest,
    compute_signal,
    expanding_quintile,
    load_universe,
    permutation_test,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "results"
FULL_PANEL_DIR = REPO_ROOT / "data" / "askar_full"

WINDOW_HOURLY = 480  # same as baseline
N_PHASES = 4
MIN_FRACTURE_TENSION_SHARE = 0.15  # Module 1 falsification threshold

VARIANT_COST_BPS = 1.0  # hourly, tight spreads

PHASE_NAMES = ("DISPERSED", "COHERENT", "TENSION", "FRACTURE")
ACTIVE_PHASES = ("TENSION", "FRACTURE")

N_PERMUTATIONS = 300


# -------------------------------------------------------------------- #
# Module 1 — feature extraction and regime detection
# -------------------------------------------------------------------- #


@dataclass
class RegimeState:
    features: pd.DataFrame  # index = bars, columns = feature names
    labels: pd.Series  # same index; string phase names
    gmm: GaussianMixture
    proportions: dict[str, float]
    phase_map: dict[int, str]


def extract_features(returns_df: pd.DataFrame, window: int, threshold: float) -> pd.DataFrame:
    """Compute per-bar topological features from a rolling correlation window.

    Returns a DataFrame with columns:
        eigen_gap      = λ₁ − λ₂ of the correlation matrix
        ricci_mean     = mean Forman-Ricci over active edges
        delta_ricci    = temporal first difference of ricci_mean
        fiedler        = λ₂ of the (unnormalised) graph Laplacian
        graph_density  = active_edges / max_edges
    """
    arr = returns_df.to_numpy()
    n, k = arr.shape
    max_edges = k * (k - 1) / 2.0

    eigen_gap: list[float] = []
    ricci_mean: list[float] = []
    delta_ricci: list[float] = []
    fiedler: list[float] = []
    density: list[float] = []
    prev_rm: float | None = None

    for i in range(window, n):
        w = arr[i - window : i]
        corr = np.corrcoef(w.T)
        # Spectral features computed from |corr| (signed correlations also
        # reshape the graph but the magnitude is what matters for stress).
        abs_corr = np.abs(corr)
        np.fill_diagonal(corr, 0.0)
        # Eigen-gap on correlation matrix with diagonal restored
        corr_eig = abs_corr.copy()
        np.fill_diagonal(corr_eig, 1.0)
        eigs = np.linalg.eigvalsh(corr_eig)
        eigs_sorted = np.sort(eigs)[::-1]
        eig_gap = float(eigs_sorted[0] - eigs_sorted[1])

        adj = (abs_corr > threshold).astype(float)
        np.fill_diagonal(adj, 0.0)
        deg = adj.sum(axis=1)
        active_edges = int(adj.sum() / 2)
        density.append(active_edges / max_edges if max_edges > 0 else 0.0)

        # Ricci mean over active edges only
        rics = [4.0 - deg[u] - deg[v] for u in range(k) for v in range(u + 1, k) if adj[u, v] > 0]
        rm = float(np.mean(rics)) if rics else 0.0
        ricci_mean.append(rm)
        delta_ricci.append(0.0 if prev_rm is None else rm - prev_rm)
        prev_rm = rm

        # Fiedler value of the unnormalised Laplacian L = D − A
        lap = np.diag(deg) - adj
        lap_eigs = np.linalg.eigvalsh(lap)
        lap_eigs_sorted = np.sort(lap_eigs)
        # Second smallest eigenvalue (index 1) is the Fiedler value
        fiedler.append(float(lap_eigs_sorted[1]) if k >= 2 else 0.0)

        eigen_gap.append(eig_gap)

    idx = returns_df.index[window:n]
    return pd.DataFrame(
        {
            "eigen_gap": eigen_gap,
            "ricci_mean": ricci_mean,
            "delta_ricci": delta_ricci,
            "fiedler": fiedler,
            "graph_density": density,
        },
        index=idx,
    )


def _assign_phase_names(gmm: GaussianMixture, feature_names: list[str]) -> dict[int, str]:
    """Bijective cluster → phase mapping via linear assignment.

    Phases live in the (eigen_gap_z, fiedler_z, |delta_ricci|_z) space.
    Four canonical archetypes (all in z-space, so ±1 are 1-σ deviations
    from the training mean):

        DISPERSED:  (−1, +0.5,  0)   weak compression, still connected,
                                     no topological shock
        COHERENT:   (+1, +1  ,  0)   compressed *and* connected (ordered)
        TENSION:    (+1, −1  , +0.5) compressing + fragmenting
        FRACTURE:   (−0.5,−1 , +1.5) collapsed + extreme |delta_ricci|

    For n clusters = 4 we build the 4×4 squared-distance matrix between
    centroids and archetypes and solve a linear-sum assignment so every
    phase is used exactly once. This avoids the degenerate "one cluster
    absorbs 80 % of bars and steals the FRACTURE label" behaviour that a
    pure ranking produces on persistently-stressed panels.
    """
    from scipy.optimize import linear_sum_assignment

    idx = {name: i for i, name in enumerate(feature_names)}
    eg_i = idx["eigen_gap"]
    fd_i = idx["fiedler"]
    dr_i = idx["delta_ricci"]

    archetypes = {
        "DISPERSED": np.array([-1.0, 0.5, 0.0]),
        "COHERENT": np.array([1.0, 1.0, 0.0]),
        "TENSION": np.array([1.0, -1.0, 0.5]),
        "FRACTURE": np.array([-0.5, -1.0, 1.5]),
    }
    names = list(PHASE_NAMES)  # canonical ordering

    means = gmm.means_
    n_clusters = means.shape[0]
    # Centroid vectors in (eigen_gap, fiedler, |delta_ricci|) z-space.
    centroids = np.stack(
        [np.array([means[c, eg_i], means[c, fd_i], abs(means[c, dr_i])]) for c in range(n_clusters)]
    )

    cost = np.zeros((n_clusters, len(names)))
    for c in range(n_clusters):
        for j, phase in enumerate(names):
            diff = centroids[c] - archetypes[phase]
            cost[c, j] = float(np.dot(diff, diff))

    row_ind, col_ind = linear_sum_assignment(cost)
    mapping: dict[int, str] = {}
    for c, j in zip(row_ind, col_ind):
        mapping[int(c)] = names[int(j)]
    return mapping


def detect_regimes(
    features: pd.DataFrame,
    split_date: pd.Timestamp,
    n_components: int = N_PHASES,
    seed: int = 42,
) -> RegimeState:
    """Fit GMM on features[index < split_date], predict for all bars.

    Features are standardised using TRAIN-only statistics so the GMM
    never sees test-period scale information.
    """
    feature_names = list(features.columns)
    train_mask = features.index < split_date
    train = features.loc[train_mask]

    mu = train.mean(axis=0)
    sd = train.std(axis=0) + 1e-8
    train_std = (train - mu) / sd
    all_std = (features - mu) / sd

    gmm = GaussianMixture(
        n_components=n_components,
        covariance_type="full",
        random_state=seed,
        max_iter=300,
        reg_covar=1e-5,
    )
    gmm.fit(train_std.to_numpy())
    labels_int: np.ndarray = gmm.predict(all_std.to_numpy())

    phase_map = _assign_phase_names(gmm, feature_names)
    labels_named = pd.Series(
        [phase_map[int(x)] for x in labels_int],
        index=features.index,
        dtype=object,
    )

    counts = labels_named.value_counts(normalize=True)
    proportions = {name: float(counts.get(name, 0.0)) for name in PHASE_NAMES}

    return RegimeState(
        features=features,
        labels=labels_named,
        gmm=gmm,
        proportions=proportions,
        phase_map=phase_map,
    )


def regime_statistics(
    regime: RegimeState,
    fwd_return: pd.Series,
) -> dict[str, Any]:
    """Phase proportions, mean fwd return per phase, mean duration,
    and transition matrix."""
    labels = regime.labels.reindex(fwd_return.index).dropna()
    fwd = fwd_return.reindex(labels.index)

    mean_ret = {
        name: float(fwd[labels == name].mean()) if (labels == name).any() else 0.0
        for name in PHASE_NAMES
    }

    # Mean duration (bars) in each phase — average run length of identical
    # consecutive labels.
    run_lengths: dict[str, list[int]] = {n: [] for n in PHASE_NAMES}
    prev = None
    run = 0
    for lab in labels.to_numpy():
        if lab == prev:
            run += 1
        else:
            if prev is not None:
                run_lengths[str(prev)].append(run)
            prev = lab
            run = 1
    if prev is not None:
        run_lengths[str(prev)].append(run)
    mean_duration = {
        name: float(np.mean(run_lengths[name])) if run_lengths[name] else 0.0
        for name in PHASE_NAMES
    }

    # Transition matrix P(next | current)
    from_to: dict[str, dict[str, int]] = {n: {m: 0 for m in PHASE_NAMES} for n in PHASE_NAMES}
    arr = labels.to_numpy()
    for a, b in zip(arr[:-1], arr[1:]):
        from_to[str(a)][str(b)] += 1
    trans_matrix: dict[str, dict[str, float]] = {}
    for src in PHASE_NAMES:
        total = sum(from_to[src].values())
        if total == 0:
            trans_matrix[src] = {dst: 0.0 for dst in PHASE_NAMES}
        else:
            trans_matrix[src] = {dst: round(from_to[src][dst] / total, 4) for dst in PHASE_NAMES}

    return {
        "proportions": {k: round(v, 4) for k, v in regime.proportions.items()},
        "mean_fwd_return": {k: round(v, 6) for k, v in mean_ret.items()},
        "mean_duration_bars": {k: round(v, 2) for k, v in mean_duration.items()},
        "transition_matrix": trans_matrix,
    }


# -------------------------------------------------------------------- #
# Module 2 — regime-conditional IC
# -------------------------------------------------------------------- #


def regime_conditional_ic(
    combo: pd.Series,
    fwd_return: pd.Series,
    labels: pd.Series,
) -> dict[str, Any]:
    idx = combo.index.intersection(fwd_return.index).intersection(labels.index)
    c = combo.loc[idx]
    y = fwd_return.loc[idx]
    lab = labels.loc[idx]

    result: dict[str, Any] = {}
    for name in PHASE_NAMES:
        mask = (lab == name) & c.notna() & y.notna()
        n_bars = int(mask.sum())
        if n_bars < 50:
            result[name] = {
                "IC": float("nan"),
                "n_bars": n_bars,
                "pct_of_time": round(n_bars / max(1, len(idx)), 4),
            }
            continue
        rho, _ = spearmanr(c[mask], y[mask])
        result[name] = {
            "IC": round(float(rho), 4),
            "n_bars": n_bars,
            "pct_of_time": round(n_bars / len(idx), 4),
        }
    return result


def local_ic_vs_eigen_gap(
    combo: pd.Series,
    fwd_return: pd.Series,
    eigen_gap: pd.Series,
    window: int = 60,
) -> float:
    """Spearman(local_IC_W, eigen_gap). Positive → signal stronger in compressed graph."""
    idx = combo.index.intersection(fwd_return.index).intersection(eigen_gap.index)
    c = combo.loc[idx].to_numpy()
    y = fwd_return.loc[idx].to_numpy()
    e = eigen_gap.loc[idx].to_numpy()

    local_ic = np.full(len(c), np.nan)
    for i in range(window, len(c)):
        cw = c[i - window : i]
        yw = y[i - window : i]
        mask = np.isfinite(cw) & np.isfinite(yw)
        if mask.sum() < 30:
            continue
        rho, _ = spearmanr(cw[mask], yw[mask])
        local_ic[i] = rho

    mask = np.isfinite(local_ic) & np.isfinite(e)
    if mask.sum() < 50:
        return float("nan")
    rho, _ = spearmanr(local_ic[mask], e[mask])
    return round(float(rho), 4)


# -------------------------------------------------------------------- #
# Module 3 — three signal variants
# -------------------------------------------------------------------- #


def _sharpe(s: pd.Series, bars_per_year: float) -> float:
    if len(s) == 0 or s.std() == 0 or not np.isfinite(s.std()):
        return 0.0
    return float(s.mean() / (s.std() + 1e-8) * np.sqrt(bars_per_year))


def _maxdd(s: pd.Series) -> float:
    if len(s) == 0:
        return 0.0
    cum = s.cumsum()
    return float((cum - cum.cummax()).min())


def _variant_report(
    strat: pd.Series,
    signal: pd.Series,
    fwd_return: pd.Series,
    split_date: pd.Timestamp,
    bars_per_year: float,
) -> dict[str, Any]:
    train_mask = strat.index < split_date
    test_mask = strat.index >= split_date

    def _ic(sig: pd.Series, y: pd.Series) -> float:
        mask = sig.notna() & y.notna()
        if mask.sum() < 50:
            return float("nan")
        rho, _ = spearmanr(sig[mask], y[mask])
        return float(rho)

    ic_train = _ic(signal[train_mask], fwd_return[train_mask])
    ic_test = _ic(signal[test_mask], fwd_return[test_mask])
    sharpe_tr = _sharpe(strat[train_mask], bars_per_year)
    sharpe_te = _sharpe(strat[test_mask], bars_per_year)
    maxdd_te = _maxdd(strat[test_mask])

    _ic_perm, p_perm, sigma_perm = permutation_test(
        signal[test_mask], fwd_return[test_mask], n=N_PERMUTATIONS, seed=42
    )

    return {
        "IC_train": round(float(ic_train), 4),
        "IC_test": round(float(ic_test), 4),
        "sharpe_train": round(sharpe_tr, 3),
        "sharpe_test": round(sharpe_te, 3),
        "maxdd_test": round(maxdd_te, 4),
        "permutation_p": round(float(p_perm), 4),
        "permutation_sigma": round(float(sigma_perm), 2),
    }


def variant_A_regime_gate(
    df_sig: pd.DataFrame,
    labels: pd.Series,
    split_date: pd.Timestamp,
    bars_per_year: float,
    cost_bps: float = VARIANT_COST_BPS,
) -> tuple[dict[str, Any], pd.Series]:
    """Trade only when phase ∈ {TENSION, FRACTURE}."""
    quintile = expanding_quintile(df_sig["combo"])
    active = labels.reindex(df_sig.index).isin(list(ACTIVE_PHASES)).astype(float)
    pos = quintile * active
    cost = pos.diff().abs().fillna(0.0) * cost_bps / 10_000.0
    strat = (pos.shift(1) * df_sig["fwd_return"] - cost).fillna(0.0)
    report = _variant_report(
        strat, df_sig["combo"], df_sig["fwd_return"], split_date, bars_per_year
    )
    report["mean_active_share"] = round(float(active.mean()), 4)
    return report, strat


def variant_B_eigen_weight(
    df_sig: pd.DataFrame,
    eigen_gap: pd.Series,
    split_date: pd.Timestamp,
    bars_per_year: float,
    cost_bps: float = VARIANT_COST_BPS,
) -> tuple[dict[str, Any], pd.Series]:
    """position = quintile × sigmoid((eigen_gap − median_train) / std_train)."""
    e = eigen_gap.reindex(df_sig.index)
    e_train = e.loc[df_sig.index < split_date]
    med = float(e_train.median())
    std = float(e_train.std()) + 1e-8
    z = (e - med) / std
    weight = pd.Series(1.0 / (1.0 + np.exp(-z.to_numpy())), index=e.index)
    weight = weight.fillna(0.0)

    quintile = expanding_quintile(df_sig["combo"])
    pos = quintile * weight
    cost = pos.diff().abs().fillna(0.0) * cost_bps / 10_000.0
    strat = (pos.shift(1) * df_sig["fwd_return"] - cost).fillna(0.0)
    report = _variant_report(
        strat, df_sig["combo"], df_sig["fwd_return"], split_date, bars_per_year
    )
    report["mean_eigen_weight_test"] = round(float(weight[df_sig.index >= split_date].mean()), 4)
    return report, strat


def variant_C_momentum_stack(
    df_sig: pd.DataFrame,
    target_returns: pd.Series,
    split_date: pd.Timestamp,
    bars_per_year: float,
    cost_bps: float = VARIANT_COST_BPS,
) -> tuple[dict[str, Any], pd.Series]:
    """Stack = w_r · z(combo) + w_m · z(momentum_20); weights fit on train IC."""
    mom = target_returns.rolling(20).sum()
    idx = df_sig.index.intersection(mom.index)
    df = df_sig.loc[idx].copy()
    df["momentum_20"] = mom.loc[idx]

    train = df[df.index < split_date]
    z_combo_train = (train["combo"] - train["combo"].mean()) / (train["combo"].std() + 1e-8)
    z_mom_train = (train["momentum_20"] - train["momentum_20"].mean()) / (
        train["momentum_20"].std() + 1e-8
    )
    # Per-component train ICs give the stacking weights (shrink to [-1,1]).
    ic_combo, _ = spearmanr(
        z_combo_train.dropna(), train["fwd_return"].loc[z_combo_train.dropna().index]
    )
    ic_mom, _ = spearmanr(z_mom_train.dropna(), train["fwd_return"].loc[z_mom_train.dropna().index])
    ic_combo_f = float(ic_combo) if np.isfinite(ic_combo) else 0.0
    ic_mom_f = float(ic_mom) if np.isfinite(ic_mom) else 0.0
    total = abs(ic_combo_f) + abs(ic_mom_f) + 1e-8
    w_r = ic_combo_f / total
    w_m = ic_mom_f / total

    # Use the TRAIN-frozen z-score stats for both train and test.
    mu_c = float(train["combo"].mean())
    sd_c = float(train["combo"].std()) + 1e-8
    mu_m = float(train["momentum_20"].mean())
    sd_m = float(train["momentum_20"].std()) + 1e-8
    z_c = (df["combo"] - mu_c) / sd_c
    z_m = (df["momentum_20"] - mu_m) / sd_m
    stack = w_r * z_c + w_m * z_m

    quintile = expanding_quintile(stack)
    cost = quintile.diff().abs().fillna(0.0) * cost_bps / 10_000.0
    strat = (quintile.shift(1) * df["fwd_return"] - cost).fillna(0.0)

    report = _variant_report(strat, stack, df["fwd_return"], split_date, bars_per_year)
    report["w_ricci"] = round(w_r, 4)
    report["w_momentum"] = round(w_m, 4)
    report["train_IC_combo"] = round(ic_combo_f, 4)
    report["train_IC_momentum"] = round(ic_mom_f, 4)
    return report, strat


# -------------------------------------------------------------------- #
# Module 4 — universe sensitivity
# -------------------------------------------------------------------- #


SUB_UNIVERSES: dict[str, tuple[str, list[str]]] = {
    # Each entry: (target_filename, list_of_filenames_in_subset)
    "U1_fx_only": (
        "EURUSD_GMT+0_NO-DST.parquet",
        [
            "EURUSD_GMT+0_NO-DST.parquet",
            "AUDUSD_GMT+0_NO-DST.parquet",
            "USDCAD_GMT+0_NO-DST.parquet",
            "EURGBP_GMT+0_NO-DST.parquet",
        ],
    ),
    "U2_macro": (
        "USA_500_Index_GMT+0_NO-DST.parquet",
        [
            "USA_500_Index_GMT+0_NO-DST.parquet",
            "SPDR_Gold_Shares_ETF_GMT+0_NO-DST.parquet",
            "US_Brent_Crude_Oil_GMT+0_NO-DST.parquet",
            "iShares_20+_Year_Treasury_Bond_ETF_GMT+0_NO-DST.parquet",
            "Euro_Bund_GMT+0_NO-DST.parquet",
            "EURUSD_GMT+0_NO-DST.parquet",
            "AUDUSD_GMT+0_NO-DST.parquet",
            "USDCAD_GMT+0_NO-DST.parquet",
        ],
    ),
    "U3_crisis": (
        "USA_500_Index_GMT+0_NO-DST.parquet",
        [
            "USA_500_Index_GMT+0_NO-DST.parquet",
            "SPDR_Gold_Shares_ETF_GMT+0_NO-DST.parquet",
            "US_Brent_Crude_Oil_GMT+0_NO-DST.parquet",
            "iShares_20+_Year_Treasury_Bond_ETF_GMT+0_NO-DST.parquet",
            "Euro_Bund_GMT+0_NO-DST.parquet",
            "iShares_MSCI_Emerging_Markets_ETF_GMT+0_NO-DST.parquet",
            "China_A50_Index_GMT+0_NO-DST.parquet",
            "EURUSD_GMT+0_NO-DST.parquet",
            "AUDUSD_GMT+0_NO-DST.parquet",
            "USDCAD_GMT+0_NO-DST.parquet",
            "EURGBP_GMT+0_NO-DST.parquet",
        ],
    ),
}


def _load_sub_universe(files: list[str], target: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load a subset of the 14-asset archive as hourly returns."""
    series: dict[str, pd.Series] = {}
    for f in files:
        df = pd.read_parquet(DATA_DIR / f)
        df = df.sort_values("ts").drop_duplicates(subset="ts").set_index("ts")
        close = df["close"].astype(float)
        series[f] = close[
            (close.index >= pd.Timestamp("2017-12-01"))
            & (close.index <= pd.Timestamp("2026-02-20"))
        ]

    panel = pd.DataFrame(series).sort_index()
    panel = panel[files]  # preserve ordering, target first
    assert panel.columns[0] == target

    non_target = [c for c in panel.columns if c != target]
    panel_ff = panel.copy()
    panel_ff[non_target] = panel_ff[non_target].ffill(limit=36)
    panel_ff = panel_ff.loc[panel[target].notna()].dropna()

    log_arr = np.log((panel_ff / panel_ff.shift(1)).to_numpy())
    returns = pd.DataFrame(log_arr, index=panel_ff.index, columns=panel_ff.columns).dropna()
    return panel_ff, returns


def run_universe_sensitivity(split_date: pd.Timestamp) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for tag, (target, files) in SUB_UNIVERSES.items():
        _prices, returns = _load_sub_universe(files, target)
        if len(returns) < WINDOW_HOURLY + 100:
            out[tag] = {"IC_test": None, "reason": "insufficient_bars"}
            continue
        # Baseline combo on this subset, then quintile backtest
        sig = compute_signal(returns, WINDOW_HOURLY, THRESHOLD)
        if len(sig) < 200:
            out[tag] = {"IC_test": None, "reason": "signal_too_short"}
            continue
        block, _ = backtest(
            sig,
            split_date,
            cost_bps=VARIANT_COST_BPS,
            bars_per_year=BARS_PER_YEAR_HOURLY,
            vol_condition=True,
        )
        out[tag] = {
            "n_assets": len(files),
            "target": target,
            "n_signal_bars": int(len(sig)),
            "IC_test": block["IC_test"],
            "IC_train": block["IC_train"],
            "sharpe_test": block["sharpe_test"],
            "maxdd_test": block["maxdd_test"],
        }

    # U4 — broad daily panel from data/askar_full (53 assets)
    broad_path = FULL_PANEL_DIR / "panel_daily.parquet"
    if broad_path.exists():
        broad = pd.read_parquet(broad_path)
        broad.index = pd.to_datetime(broad.index)
        log_arr = np.log((broad / broad.shift(1)).to_numpy())
        ret_broad = pd.DataFrame(log_arr, index=broad.index, columns=broad.columns).dropna()
        # Target must be first column — reorder SPY first if present.
        preferred = "SPDR_S_P_500_ETF"
        if preferred in ret_broad.columns:
            other = [c for c in ret_broad.columns if c != preferred]
            ret_broad = ret_broad[[preferred] + other]
        sig = compute_signal(ret_broad, 60, THRESHOLD)
        block, _ = backtest(
            sig,
            split_date,
            cost_bps=5.0,
            bars_per_year=252.0,
            vol_condition=True,
        )
        out["U4_broad_daily"] = {
            "n_assets": int(ret_broad.shape[1]),
            "target": ret_broad.columns[0],
            "n_signal_bars": int(len(sig)),
            "IC_test": block["IC_test"],
            "IC_train": block["IC_train"],
            "sharpe_test": block["sharpe_test"],
            "maxdd_test": block["maxdd_test"],
        }
    else:
        out["U4_broad_daily"] = {"IC_test": None, "reason": "panel_daily_missing"}
    return out


# -------------------------------------------------------------------- #
# Module 5 — threshold / window sensitivity on train
# -------------------------------------------------------------------- #


def run_threshold_sensitivity(
    returns: pd.DataFrame,
    split_date: pd.Timestamp,
) -> dict[str, Any]:
    thresholds = (0.20, 0.25, 0.30, 0.35, 0.40)
    windows = (60, 90, 120, 160)
    grid: list[dict[str, Any]] = []
    for w in windows:
        for th in thresholds:
            sig = compute_signal(returns, w, th)
            train = sig[sig.index < split_date]
            mask = train["combo"].notna() & train["fwd_return"].notna()
            if mask.sum() < 50:
                continue
            rho, _ = spearmanr(train.loc[mask, "combo"], train.loc[mask, "fwd_return"])
            grid.append({"window": w, "threshold": th, "IC_train": round(float(rho), 4)})
    # Best train config
    if not grid:
        return {"grid": [], "best_train_config": None, "default_config_rank": None}
    sorted_grid = sorted(grid, key=lambda r: -r["IC_train"])
    best = sorted_grid[0]
    default_rank = next(
        (
            i + 1
            for i, row in enumerate(sorted_grid)
            if row["window"] == 120 and abs(row["threshold"] - 0.30) < 1e-9
        ),
        None,
    )
    return {
        "grid": grid,
        "best_train_config": best,
        "default_config_rank": default_rank,
    }


# -------------------------------------------------------------------- #
# Orchestration
# -------------------------------------------------------------------- #


def plot_variant_equities(runs: list[tuple[str, pd.Series]], out: Path, title: str) -> None:
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
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    RESULTS_DIR.mkdir(exist_ok=True, parents=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)


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
    u = load_universe()
    returns = u.returns_hourly
    fwd_target = returns.iloc[:, 0]
    print(f"Panel: {returns.shape}  {returns.index[0]} -> {returns.index[-1]}")

    # ----- Module 1: features + regime detection -----
    print("[M1] extracting topology features...")
    features = extract_features(returns, WINDOW_HOURLY, THRESHOLD)
    print(f"[M1] features: {features.shape}")
    regime = detect_regimes(features, SPLIT_DATE)
    stats = regime_statistics(regime, fwd_target.reindex(features.index).dropna())
    print(f"[M1] proportions: {stats['proportions']}")

    active_share = stats["proportions"].get("TENSION", 0.0) + stats["proportions"].get(
        "FRACTURE", 0.0
    )
    module1_ok = active_share >= MIN_FRACTURE_TENSION_SHARE

    # ----- Signal (combo) aligned to features -----
    df_sig = compute_signal(returns, WINDOW_HOURLY, THRESHOLD)
    common = df_sig.index.intersection(features.index)
    df_sig = df_sig.loc[common]
    features = features.loc[common]
    labels = regime.labels.loc[common]
    fwd = df_sig["fwd_return"]

    # ----- Module 2: regime-conditional IC -----
    print("[M2] regime-conditional IC...")
    ic_by_phase = regime_conditional_ic(df_sig["combo"], fwd, labels)
    ic_eigen_corr = local_ic_vs_eigen_gap(df_sig["combo"], fwd, features["eigen_gap"], window=120)

    # ----- Module 3: variants -----
    print("[M3] variants A / B / C...")
    bpy = BARS_PER_YEAR_HOURLY
    rep_A, strat_A = variant_A_regime_gate(df_sig, labels, SPLIT_DATE, bpy)
    rep_B, strat_B = variant_B_eigen_weight(df_sig, features["eigen_gap"], SPLIT_DATE, bpy)
    rep_C, strat_C = variant_C_momentum_stack(df_sig, fwd, SPLIT_DATE, bpy)

    # Baseline (vol-conditioned, no regime gate) for comparison
    print("[M3] baseline...")
    base_block, base_strat = backtest(
        df_sig,
        SPLIT_DATE,
        cost_bps=VARIANT_COST_BPS,
        bars_per_year=bpy,
        vol_condition=True,
    )
    test_slice = df_sig[df_sig.index >= SPLIT_DATE]
    _base_ic_perm, base_p, base_sigma = permutation_test(
        test_slice["combo"], test_slice["fwd_return"], n=N_PERMUTATIONS, seed=42
    )
    baseline_report = {
        "IC_train": base_block["IC_train"],
        "IC_test": base_block["IC_test"],
        "sharpe_train": base_block["sharpe_train"],
        "sharpe_test": base_block["sharpe_test"],
        "maxdd_test": base_block["maxdd_test"],
        "permutation_p": round(float(base_p), 4),
        "permutation_sigma": round(float(base_sigma), 2),
    }

    variants: dict[str, dict[str, Any]] = {
        "baseline": baseline_report,
        "variant_A_regime_gate": rep_A,
        "variant_B_eigen_weight": rep_B,
        "variant_C_momentum_stack": rep_C,
    }

    def _ic_of(block: dict[str, Any]) -> float:
        raw = block.get("IC_test")
        if raw is None:
            return -999.0
        try:
            return float(raw)
        except (TypeError, ValueError):
            return -999.0

    def _perm_p_of(block: dict[str, Any]) -> float:
        raw = block.get("permutation_p")
        if raw is None:
            return 1.0
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 1.0

    # Winner by IC_test (missing / non-numeric fall to the bottom). Variant C
    # is only eligible to win if its Ricci component carries real weight —
    # otherwise it is a momentum-only strategy wearing a Ricci t-shirt.
    W_RICCI_FLOOR = 0.30

    def _variant_eligible(name: str, block: dict[str, Any]) -> bool:
        if name != "variant_C_momentum_stack":
            return True
        w_r = block.get("w_ricci")
        try:
            return float(w_r) >= W_RICCI_FLOOR if w_r is not None else False
        except (TypeError, ValueError):
            return False

    ranked = sorted(
        [(k, v) for k, v in variants.items() if _variant_eligible(k, v)],
        key=lambda kv: _ic_of(kv[1]),
        reverse=True,
    )
    winner = ranked[0][0] if ranked else "baseline"
    momentum_dominated = not _variant_eligible(
        "variant_C_momentum_stack", variants["variant_C_momentum_stack"]
    )

    # ----- Module 4: universe sensitivity -----
    print("[M4] universe sensitivity...")
    universes = run_universe_sensitivity(SPLIT_DATE)

    # ----- Module 5: threshold sensitivity -----
    print("[M5] threshold/window sensitivity...")
    sens = run_threshold_sensitivity(returns, SPLIT_DATE)

    # ----- Final verdict -----
    # Restrict the "best variant" search to eligible variants so the verdict
    # cannot silently inherit a momentum-dominated IC.
    eligible_blocks = [v for k, v in variants.items() if _variant_eligible(k, v)]
    ic_test_values: list[float] = [_ic_of(v) for v in eligible_blocks]
    ic_test_values = [v for v in ic_test_values if v > -998.0]
    best_variant_ic: float = max(ic_test_values) if ic_test_values else float("nan")
    best_variant_p: float = 1.0
    for v in eligible_blocks:
        if _ic_of(v) == best_variant_ic:
            best_variant_p = _perm_p_of(v)
            break

    ic_tension_raw = ic_by_phase.get("TENSION", {}).get("IC", float("nan"))
    ic_fracture_raw = ic_by_phase.get("FRACTURE", {}).get("IC", float("nan"))
    ic_tension = float(ic_tension_raw) if ic_tension_raw is not None else float("nan")
    ic_fracture = float(ic_fracture_raw) if ic_fracture_raw is not None else float("nan")
    stress_ic_sum: float = (ic_tension if np.isfinite(ic_tension) else 0.0) + (
        ic_fracture if np.isfinite(ic_fracture) else 0.0
    )

    baseline_ic_f = _ic_of(baseline_report)

    def _verdict() -> str:
        if np.isfinite(best_variant_ic) and best_variant_ic > 0.08 and best_variant_p < 0.05:
            return "SIGNAL_FOUND"
        if (
            stress_ic_sum > 0.10
            and np.isfinite(best_variant_ic)
            and best_variant_ic > baseline_ic_f
        ):
            return "REGIME_CONDITIONAL"
        if np.isfinite(best_variant_ic) and best_variant_ic < 0.02 and best_variant_p > 0.20:
            return "NO_SIGNAL"
        return "WEAK"

    verdict = _verdict()

    # ----- Recommendation -----
    recommendation: str
    if verdict == "SIGNAL_FOUND":
        recommendation = (
            f"Variant '{winner}' beats the 0.08 IC threshold on test with "
            f"permutation p < 0.05. Ready to discuss live deployment."
        )
    elif verdict == "REGIME_CONDITIONAL":
        recommendation = (
            "Ricci signal is regime-conditional crisis alpha: IC in "
            "TENSION+FRACTURE phases sums to "
            f"{stress_ic_sum:.4f}. Deploy behind a regime filter and add VIX "
            "/ credit spreads to sharpen the TENSION→FRACTURE transition."
        )
    elif verdict == "WEAK":
        recommendation = (
            "Signal is weak across all variants. Consider a larger "
            "universe or a different topological feature family (β₁, "
            "persistence, augmented Ricci)."
        )
    else:
        recommendation = (
            "No signal detected. Ricci-delta combo does not carry edge on "
            "this universe — redirect research."
        )

    # Plots
    plot_variant_equities(
        [
            (
                f"baseline IC={baseline_report['IC_test']:+.4f}",
                base_strat[base_strat.index >= SPLIT_DATE],
            ),
            (
                f"A gate   IC={rep_A['IC_test']:+.4f}",
                strat_A[strat_A.index >= SPLIT_DATE],
            ),
            (
                f"B eigen  IC={rep_B['IC_test']:+.4f}",
                strat_B[strat_B.index >= SPLIT_DATE],
            ),
            (
                f"C momstack IC={rep_C['IC_test']:+.4f}",
                strat_C[strat_C.index >= SPLIT_DATE],
            ),
        ],
        RESULTS_DIR / "askar_regime_variants_equity.png",
        "Askar regime experiment — variant equity curves (test period)",
    )

    report: dict[str, Any] = {
        "module_1_regime": {
            **stats,
            "falsification_threshold": MIN_FRACTURE_TENSION_SHARE,
            "active_share": round(active_share, 4),
            "module1_passes_falsification": bool(module1_ok),
            "phase_map": {str(k): v for k, v in regime.phase_map.items()},
        },
        "module_2_regime_ic": {
            "IC_per_phase": ic_by_phase,
            "IC_eigen_gap_correlation": ic_eigen_corr,
        },
        "module_3_variants": {
            **variants,
            "winner": winner,
            "variant_C_momentum_dominated": momentum_dominated,
            "w_ricci_floor": W_RICCI_FLOOR,
        },
        "module_4_universes": universes,
        "module_5_sensitivity": sens,
        "best_variant_IC_test": (
            round(float(best_variant_ic), 4) if np.isfinite(best_variant_ic) else None
        ),
        "stress_phase_ic_sum": round(float(stress_ic_sum), 4),
        "baseline_yfinance_IC": 0.106,
        "final_verdict": verdict,
        "recommendation_for_askar": recommendation,
    }

    RESULTS_DIR.mkdir(exist_ok=True, parents=True)
    out = RESULTS_DIR / "askar_regime_experiment.json"
    safe_report = _to_json_safe(report)
    out.write_text(json.dumps(safe_report, indent=2))

    # Printable summary (no universe_assets spam)
    printable = {
        "module_1": stats,
        "module_2": report["module_2_regime_ic"],
        "module_3": {k: v for k, v in variants.items() if k != "baseline"}
        | {"baseline": baseline_report, "winner": winner},
        "module_4": universes,
        "module_5_best": sens.get("best_train_config"),
        "best_variant_IC_test": report["best_variant_IC_test"],
        "stress_phase_ic_sum": report["stress_phase_ic_sum"],
        "final_verdict": verdict,
    }
    print(json.dumps(_to_json_safe(printable), indent=2))
    return report


if __name__ == "__main__":
    run()
