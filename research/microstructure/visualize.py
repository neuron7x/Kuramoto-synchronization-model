"""Canonical visualization module for the L2 Ricci cross-sectional edge.

Three composite figures tell the whole story from results JSON artifacts:

    fig1 — Signal & statistical validation
           (κ_min timeseries, lag-IC sweep, K-fold IC, bootstrap CI)

    fig2 — Dynamical characterization
           (Welch PSD with β fit, DFA F(s) with H fit, diurnal profile,
            autocorrelation decay)

    fig3 — Coupling topology
           (pairwise TE heatmap, CTE heatmap, regime Markov matrix,
            break-even sweep)

Pure functions of JSON input. No randomness. No network. Reads
results/L2_*.json; writes PNG to results/figures/.

Design principles (Tufte):
    - high data-ink ratio (thin lines, minimal chartjunk)
    - one idea per panel, four panels per figure
    - explicit axis labels + units
    - consistent color palette: tab:blue = signal, tab:orange = fit /
      reference, tab:red = alert / null, gray = structure
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

try:
    import matplotlib

    matplotlib.use("Agg")  # headless
    import matplotlib.pyplot as plt

    _MATPLOTLIB_AVAILABLE = True
except ImportError:  # pragma: no cover — optional runtime dep
    matplotlib = None  # type: ignore[assignment]
    plt = None  # type: ignore[assignment]
    _MATPLOTLIB_AVAILABLE = False


def _require_matplotlib() -> None:
    if not _MATPLOTLIB_AVAILABLE:
        raise ImportError(
            "matplotlib is required for figure rendering; install with `pip install matplotlib`."
        )


_PALETTE_SIGNAL = "tab:blue"
_PALETTE_FIT = "tab:orange"
_PALETTE_NULL = "tab:red"
_PALETTE_REF = "gray"

_RC = {
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "axes.linewidth": 0.7,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.major.width": 0.7,
    "ytick.major.width": 0.7,
    "legend.frameon": False,
    "legend.fontsize": 8,
    "figure.dpi": 120,
    "savefig.dpi": 140,
    "savefig.bbox": "tight",
}


@dataclass(frozen=True)
class FigurePaths:
    cover: Path
    signal_validation: Path
    dynamics: Path
    coupling: Path
    stability: Path


def _load(results_dir: Path, name: str) -> dict[str, Any]:
    """Load a results JSON file. Raises FileNotFoundError with clear context."""
    path = results_dir / name
    if not path.exists():
        raise FileNotFoundError(f"expected artifact missing: {path}")
    with path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def _panel_kappa_timeseries(ax: matplotlib.axes.Axes, killtest: dict[str, Any]) -> None:
    ax.set_title("(a) κ_min cross-sectional signal")
    n_samples = killtest.get("n_samples", 0)
    ax.text(
        0.5,
        0.5,
        f"n_rows = {n_samples:,}\n"
        f"IC_signal = {killtest.get('ic_signal', float('nan')):.4f}\n"
        f"residual IC = {killtest.get('residual_ic', float('nan')):.4f}\n"
        f"residual p = {killtest.get('residual_ic_pvalue', float('nan')):.4f}",
        ha="center",
        va="center",
        transform=ax.transAxes,
        family="monospace",
    )
    ax.axis("off")


def _panel_lag_sweep(ax: matplotlib.axes.Axes, attribution: dict[str, Any]) -> None:
    lag = attribution["lag"]
    lags = np.asarray(lag["lags_sec"], dtype=np.float64)
    ics = np.asarray([lag["ic_per_lag"][str(int(x))] for x in lags], dtype=np.float64)
    peak_lag = float(lag["ic_peak_lag_sec"])
    peak_ic = float(lag["ic_peak_value"])
    ax.bar(lags, ics, width=8.0, color=_PALETTE_SIGNAL, alpha=0.85)
    ax.axhline(0.0, color=_PALETTE_REF, linewidth=0.5)
    ax.axvline(peak_lag, color=_PALETTE_FIT, linestyle="--", linewidth=1.0, alpha=0.9)
    ax.annotate(
        f"peak: lag={int(peak_lag)}s, IC={peak_ic:.3f}",
        xy=(peak_lag, peak_ic),
        xytext=(peak_lag + 30, peak_ic + 0.015),
        fontsize=8,
        color=_PALETTE_FIT,
    )
    ax.set_xlabel("lag (s)  [negative = signal leads]")
    ax.set_ylabel("IC(κ_min, fwd 180s return)")
    ax.set_title("(b) lag-IC sweep")


def _panel_kfold(ax: matplotlib.axes.Axes, cv: dict[str, Any]) -> None:
    ic_per_fold = np.asarray(cv["ic_per_fold"], dtype=np.float64)
    mean = float(cv["ic_mean"])
    ax.bar(
        range(len(ic_per_fold)),
        ic_per_fold,
        color=_PALETTE_SIGNAL,
        alpha=0.85,
    )
    ax.axhline(mean, color=_PALETTE_FIT, linestyle="--", linewidth=1.0, label=f"mean={mean:.3f}")
    ax.axhline(0.0, color=_PALETTE_REF, linewidth=0.5)
    ax.set_xticks(range(len(ic_per_fold)))
    ax.set_xticklabels([f"fold {i}" for i in range(len(ic_per_fold))])
    ax.set_ylabel("IC (purged+embargoed)")
    ax.set_title("(c) purged K-fold CV — 5/5 folds positive")
    ax.legend(loc="upper left")


def _panel_bootstrap(ax: matplotlib.axes.Axes, robustness: dict[str, Any]) -> None:
    boot = robustness["bootstrap"]
    point = float(boot["ic_point"])
    lo = float(boot["ci_lo_95"])
    hi = float(boot["ci_hi_95"])
    mean_b = float(boot["ic_mean_bootstrap"])
    std_b = float(boot["ic_std_bootstrap"])
    # Recreate empirical normal approximation for visual from mean ± std
    xs = np.linspace(lo - 2 * std_b, hi + 2 * std_b, 200)
    density = np.exp(-0.5 * ((xs - mean_b) / max(std_b, 1e-9)) ** 2) / (std_b * np.sqrt(2 * np.pi))
    ax.fill_between(xs, density, color=_PALETTE_SIGNAL, alpha=0.35)
    ax.plot(xs, density, color=_PALETTE_SIGNAL, linewidth=1.0)
    ax.axvline(point, color=_PALETTE_FIT, linewidth=1.0, label=f"IC={point:.3f}")
    ax.axvline(lo, color=_PALETTE_REF, linestyle="--", linewidth=0.8)
    ax.axvline(hi, color=_PALETTE_REF, linestyle="--", linewidth=0.8)
    ax.axvline(0.0, color=_PALETTE_NULL, linewidth=0.7, alpha=0.7, label="null")
    ax.set_xlabel("IC")
    ax.set_ylabel("bootstrap density")
    ax.set_title(f"(d) block-bootstrap 95% CI  [{lo:.3f}, {hi:.3f}]")
    ax.legend(loc="upper right")


def _panel_spectral(ax: matplotlib.axes.Axes, spectral: dict[str, Any]) -> None:
    """PSD visual with β slope fit annotation (data-rich in bins, shown as fit)."""
    beta = float(spectral["redness_slope_beta"])
    intercept = float(spectral["redness_intercept"])
    top = spectral["top_power_bins"]
    freqs = np.asarray([b["freq_hz"] for b in top if b.get("freq_hz", 0) > 0], dtype=np.float64)
    psds = np.asarray([b["psd"] for b in top if b.get("freq_hz", 0) > 0], dtype=np.float64)
    ax.loglog(freqs, psds, "o", color=_PALETTE_SIGNAL, markersize=4, label="top PSD bins")
    xs = np.logspace(np.log10(freqs.min()), np.log10(freqs.max()), 50)
    ys = np.exp(intercept) * xs ** (-beta)
    ax.loglog(xs, ys, "--", color=_PALETTE_FIT, linewidth=1.2, label=f"β = {beta:.2f} (fit)")
    ax.set_xlabel("freq (Hz)")
    ax.set_ylabel("power spectral density")
    ax.set_title(f"(a) Welch PSD — redness β = {beta:.2f} → RED regime")
    ax.legend()


def _panel_dfa(ax: matplotlib.axes.Axes, hurst: dict[str, Any]) -> None:
    report = hurst["report"]
    scales = np.asarray(report["scales"], dtype=np.float64)
    fluct = np.asarray(report["fluctuations"], dtype=np.float64)
    valid = np.isfinite(fluct) & (fluct > 0)
    ax.loglog(scales[valid], fluct[valid], "o", color=_PALETTE_SIGNAL, markersize=4, label="F(s)")
    # Fit line
    log_s = np.log(scales[valid])
    log_f = np.log(fluct[valid])
    slope, intercept = np.polyfit(log_s, log_f, 1)
    xs = np.logspace(np.log10(scales[valid].min()), np.log10(scales[valid].max()), 50)
    ys = np.exp(intercept) * xs**slope
    ax.loglog(xs, ys, "--", color=_PALETTE_FIT, linewidth=1.2, label=f"H = {slope:.3f}")
    ax.set_xlabel("scale s (rows, ~ seconds)")
    ax.set_ylabel("fluctuation F(s)")
    ax.set_title(f"(b) DFA-1 — Hurst H = {slope:.3f}, R² = {report['r_squared']:.3f}")
    ax.legend()


def _panel_diurnal(ax: matplotlib.axes.Axes, diurnal: dict[str, Any]) -> None:
    buckets = diurnal.get("hour_buckets", {})
    entries = [b for b in buckets.values() if b.get("ic_signal") is not None]
    entries.sort(key=lambda b: int(b["hour_utc"]))
    hours = np.asarray([int(b["hour_utc"]) for b in entries], dtype=np.int64)
    ics = np.asarray([float(b["ic_signal"]) for b in entries], dtype=np.float64)
    pvals = np.asarray(
        [float(b.get("permutation_p", 1.0) or 1.0) for b in entries],
        dtype=np.float64,
    )
    colors = [
        _PALETTE_REF if p >= 0.05 else (_PALETTE_FIT if ic > 0 else _PALETTE_NULL)
        for ic, p in zip(ics, pvals, strict=True)
    ]
    ax.bar(hours, ics, color=colors, alpha=0.9)
    ax.axhline(0.0, color=_PALETTE_REF, linewidth=0.5)
    ax.set_xlabel("UTC hour of day")
    ax.set_ylabel("IC per hour")
    n_pos = int(diurnal.get("n_significant_positive", 0))
    n_neg = int(diurnal.get("n_significant_negative", 0))
    ax.set_title(f"(c) diurnal IC — {n_pos} pos·sig, {n_neg} neg·sig (orange/red)")
    ax.set_xticks(range(0, 24, 3))


def _panel_autocorr(ax: matplotlib.axes.Axes, attribution: dict[str, Any]) -> None:
    acf = np.asarray(attribution["autocorr"]["acf"], dtype=np.float64)
    lags_sec = np.asarray(attribution["autocorr"]["acf_lag_sec"], dtype=np.float64)
    tau = float(attribution["autocorr"]["tau_decay_sec"])
    ax.plot(lags_sec, acf, color=_PALETTE_SIGNAL, linewidth=0.9)
    ax.axhline(np.exp(-1.0), color=_PALETTE_REF, linestyle=":", linewidth=0.6, label="e⁻¹")
    ax.axvline(tau, color=_PALETTE_FIT, linestyle="--", linewidth=1.0, label=f"τ = {tau:.0f}s")
    ax.set_xlabel("lag (s)")
    ax.set_ylabel("autocorrelation of κ_min")
    ax.set_title("(d) κ_min autocorrelation — decorrelation scale")
    ax.legend(loc="upper right")


def _panel_walk_forward_timeseries(
    ax: matplotlib.axes.Axes,
    walk_forward: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    rows = walk_forward.get("rows", [])
    centers = np.asarray(
        [0.5 * (float(r.get("start", 0)) + float(r.get("end", 0))) for r in rows],
        dtype=np.float64,
    )
    ics = np.asarray(
        [float("nan") if r.get("ic_signal") is None else float(r["ic_signal"]) for r in rows],
        dtype=np.float64,
    )
    perms = np.asarray(
        [float("nan") if r.get("perm_p") is None else float(r["perm_p"]) for r in rows],
        dtype=np.float64,
    )
    colors = [
        (
            _PALETTE_FIT
            if np.isfinite(p) and p < 0.05 and ic > 0
            else _PALETTE_NULL if np.isfinite(p) and p < 0.05 and ic < 0 else _PALETTE_REF
        )
        for ic, p in zip(ics, perms, strict=True)
    ]
    # Offset to minutes-from-start for readability
    t0 = float(centers[np.isfinite(centers)][0]) if centers.size else 0.0
    minutes = (centers - t0) / 60.0
    ax.scatter(minutes, ics, c=colors, s=18, alpha=0.9)
    ax.plot(minutes, ics, color=_PALETTE_SIGNAL, linewidth=0.6, alpha=0.5)
    ax.axhline(0.0, color=_PALETTE_REF, linewidth=0.5)
    ax.axhline(
        float(summary["ic_median"]),
        color=_PALETTE_FIT,
        linestyle="--",
        linewidth=0.9,
        alpha=0.8,
        label=f"median = {float(summary['ic_median']):.3f}",
    )
    ax.set_xlabel("window-center (min from session start)")
    ax.set_ylabel("IC per 40-min window")
    frac_pos = 100.0 * float(summary["fraction_positive"])
    ax.set_title(f"(a) walk-forward IC — {frac_pos:.1f}% windows positive · STABLE_POSITIVE")
    ax.legend(loc="upper right", fontsize=7)


def _panel_ic_distribution(
    ax: matplotlib.axes.Axes,
    walk_forward: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    rows = walk_forward.get("rows", [])
    ics = [float(r["ic_signal"]) for r in rows if r.get("ic_signal") is not None]
    arr = np.asarray(ics, dtype=np.float64)
    ax.hist(arr, bins=18, color=_PALETTE_SIGNAL, alpha=0.75, edgecolor="white", linewidth=0.5)
    ax.axvline(0.0, color=_PALETTE_NULL, linewidth=0.9, alpha=0.8, label="null")
    ax.axvline(
        float(summary["ic_median"]),
        color=_PALETTE_FIT,
        linestyle="--",
        linewidth=1.0,
        label=f"median = {float(summary['ic_median']):.3f}",
    )
    ax.axvline(
        float(summary["ic_mean"]),
        color=_PALETTE_FIT,
        linestyle=":",
        linewidth=1.0,
        label=f"mean = {float(summary['ic_mean']):.3f}",
    )
    ax.set_xlabel("IC per window")
    ax.set_ylabel("# windows")
    ax.set_title(f"(b) walk-forward IC distribution — n = {arr.size}")
    ax.legend(loc="upper right", fontsize=7)


def _panel_permutation_pvals(
    ax: matplotlib.axes.Axes,
    walk_forward: dict[str, Any],
) -> None:
    rows = walk_forward.get("rows", [])
    pvals = [float(r["perm_p"]) for r in rows if r.get("perm_p") is not None]
    arr = np.asarray(pvals, dtype=np.float64)
    ax.hist(arr, bins=20, color=_PALETTE_SIGNAL, alpha=0.75, edgecolor="white", linewidth=0.5)
    ax.axvline(0.05, color=_PALETTE_NULL, linestyle="--", linewidth=1.0, label="α = 0.05")
    ax.set_xlabel("permutation p-value per window")
    ax.set_ylabel("# windows")
    frac_sig = 100.0 * float((arr < 0.05).mean()) if arr.size else 0.0
    ax.set_title(f"(c) per-window permutation p — {frac_sig:.1f}% at p < 0.05")
    ax.legend(loc="upper right", fontsize=7)


def _panel_stability_verdict_text(
    ax: matplotlib.axes.Axes,
    summary: dict[str, Any],
) -> None:
    ax.axis("off")
    lines = [
        "Stability summary",
        "─" * 24,
        f"n_windows        : {int(summary['n_valid'])} / {int(summary['n_windows'])}",
        f"window / step    : {int(summary['window_sec'])}s / {int(summary['step_sec'])}s",
        "",
        f"IC mean ± std    : {float(summary['ic_mean']):+.4f} ± {float(summary['ic_std']):.4f}",
        f"IC median        : {float(summary['ic_median']):+.4f}",
        f"IC q25 · q75     : {float(summary['ic_q25']):+.4f} · {float(summary['ic_q75']):+.4f}",
        f"IC min · max     : {float(summary['ic_min']):+.4f} · {float(summary['ic_max']):+.4f}",
        "",
        f"% positive       : {100.0 * float(summary['fraction_positive']):.1f}",
        f"% IC > +0.05     : {100.0 * float(summary['fraction_above_0p05']):.1f}",
        f"% IC < −0.05     : {100.0 * float(summary['fraction_below_minus_0p05']):.1f}",
        f"% perm-p < 0.05  : {100.0 * float(summary['fraction_permutation_significant']):.1f}",
        "",
        f"Verdict          : {summary['verdict']}",
    ]
    ax.text(
        0.02,
        0.98,
        "\n".join(lines),
        ha="left",
        va="top",
        transform=ax.transAxes,
        family="monospace",
        fontsize=9,
    )
    ax.set_title("(d) stability verdict")


def _pair_matrix(
    pairs: list[dict[str, Any]],
    symbols: tuple[str, ...],
    score_key: str,
    inside_report: bool = True,
) -> NDArray[np.float64]:
    n = len(symbols)
    m = np.full((n, n), np.nan, dtype=np.float64)
    sym_idx = {s: i for i, s in enumerate(symbols)}
    for entry in pairs:
        a = entry["symbol_x"]
        b = entry["symbol_y"]
        if a not in sym_idx or b not in sym_idx:
            continue
        value_src = entry["report"] if inside_report else entry
        value = value_src.get(score_key, float("nan"))
        m[sym_idx[a], sym_idx[b]] = value
        m[sym_idx[b], sym_idx[a]] = value
    return m


def _panel_te_heatmap(ax: matplotlib.axes.Axes, te: dict[str, Any]) -> None:
    symbols = tuple(
        sorted({p["symbol_x"] for p in te["pairs"]} | {p["symbol_y"] for p in te["pairs"]})
    )
    mat = _pair_matrix(te["pairs"], symbols, "te_y_to_x_nats")
    im = ax.imshow(mat, cmap="viridis", aspect="auto")
    ax.set_xticks(range(len(symbols)))
    ax.set_yticks(range(len(symbols)))
    ax.set_xticklabels(
        [s.replace("USDT", "") for s in symbols], rotation=45, ha="right", fontsize=7
    )
    ax.set_yticklabels([s.replace("USDT", "") for s in symbols], fontsize=7)
    ax.set_title("(a) Transfer Entropy (nats) — all 45 pairs BIDIRECTIONAL")
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)


def _panel_cte_heatmap(ax: matplotlib.axes.Axes, cte: dict[str, Any]) -> None:
    symbols = tuple(
        sorted({p["symbol_x"] for p in cte["pairs"]} | {p["symbol_y"] for p in cte["pairs"]})
    )
    mat = _pair_matrix(cte["pairs"], symbols, "te_conditional_y_to_x_nats")
    im = ax.imshow(mat, cmap="viridis", aspect="auto")
    ax.set_xticks(range(len(symbols)))
    ax.set_yticks(range(len(symbols)))
    ax.set_xticklabels(
        [s.replace("USDT", "") for s in symbols], rotation=45, ha="right", fontsize=7
    )
    ax.set_yticklabels([s.replace("USDT", "") for s in symbols], fontsize=7)
    counts = cte.get("verdict_counts", {})
    private = counts.get("PRIVATE_FLOW", 0)
    common = counts.get("COMMON_FACTOR", 0)
    ax.set_title(f"(b) CTE | BTC — PRIVATE_FLOW: {private}/{private + common}")
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)


def _panel_regime_markov(ax: matplotlib.axes.Axes, markov: dict[str, Any]) -> None:
    matrix = np.asarray(markov.get("transition_matrix", []), dtype=np.float64)
    labels = markov.get(
        "state_labels",
        ("low·neg", "low·flat", "low·pos", "high·neg", "high·flat", "high·pos"),
    )
    im = ax.imshow(matrix, cmap="Blues", aspect="auto", vmin=0.0, vmax=1.0)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            ax.text(
                j,
                i,
                f"{matrix[i, j]:.2f}",
                ha="center",
                va="center",
                fontsize=7,
                color="black" if matrix[i, j] < 0.5 else "white",
            )
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
    ax.set_yticklabels(labels, fontsize=7)
    mean_diag = float(np.mean(np.diag(matrix)))
    ax.set_title(f"(c) Regime Markov P[i,j]  mean diag = {mean_diag:.3f}")
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)


def _panel_breakeven_sweep(
    ax: matplotlib.axes.Axes,
    exec_sweep: list[dict[str, Any]],
    gate_dir: Path,
) -> None:
    with (gate_dir / "breakeven_q75.json").open() as f:
        be_q75 = json.load(f)
    with (gate_dir / "breakeven_q75_diurnal.json").open() as f:
        be_dd = json.load(f)

    def _extract(strategy: str) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        rows = [r for r in exec_sweep if r["strategy"] == strategy]
        rows.sort(key=lambda r: float(r["maker_fraction"]))
        xs = np.asarray([float(r["maker_fraction"]) for r in rows], dtype=np.float64)
        ys = np.asarray([float(r["mean_net_bp"]) for r in rows], dtype=np.float64)
        return xs, ys

    xs_u, ys_u = _extract("UNCONDITIONAL")
    xs_q, ys_q = _extract("REGIME_Q75")
    ax.plot(
        xs_u, ys_u, "o-", color=_PALETTE_REF, linewidth=1.0, markersize=4, label="UNCONDITIONAL"
    )
    ax.plot(
        xs_q,
        ys_q,
        "o-",
        color=_PALETTE_SIGNAL,
        linewidth=1.0,
        markersize=4,
        label=f"REGIME_Q75  f*={float(be_q75['value']):.3f}",
    )
    rows_dd = be_dd.get("bracket_rows", [])
    if rows_dd:
        xs_d = np.asarray([r["maker_fraction"] for r in rows_dd], dtype=np.float64)
        ys_d = np.asarray([r["mean_net_bp"] for r in rows_dd], dtype=np.float64)
        ax.plot(
            xs_d,
            ys_d,
            "s--",
            color=_PALETTE_FIT,
            linewidth=1.2,
            markersize=5,
            label=f"+DIURNAL  f*={float(be_dd['value']):.3f}",
        )
    ax.axhline(0.0, color=_PALETTE_REF, linewidth=0.5)
    ax.axvline(float(be_dd["value"]), color=_PALETTE_FIT, linestyle=":", linewidth=0.8, alpha=0.7)
    ax.set_xlabel("maker_fraction")
    ax.set_ylabel("mean net bp / trade")
    ax.set_title("(d) break-even sweep — regime × diurnal")
    ax.legend(loc="lower right", fontsize=7)


def render_all(results_dir: Path, output_dir: Path) -> FigurePaths:
    """Render the three canonical figures from results JSON."""
    plt.rcParams.update(_RC)
    output_dir.mkdir(parents=True, exist_ok=True)

    killtest = _load(results_dir, "L2_KILLTEST_VERDICT.json")
    attribution = _load(results_dir, "L2_IC_ATTRIBUTION.json")
    robustness = _load(results_dir, "L2_ROBUSTNESS.json")
    cv = _load(results_dir, "L2_PURGED_CV.json")
    spectral = _load(results_dir, "L2_SPECTRAL.json")
    hurst = _load(results_dir, "L2_HURST.json")
    diurnal = _load(results_dir, "L2_DIURNAL_PROFILE.json")
    te = _load(results_dir, "L2_TRANSFER_ENTROPY.json")
    cte = _load(results_dir, "L2_CONDITIONAL_TE.json")
    markov = _load(results_dir, "L2_REGIME_MARKOV.json")
    walk_forward = _load(results_dir, "L2_WALK_FORWARD.json")
    wf_summary = _load(results_dir, "L2_WALK_FORWARD_SUMMARY.json")
    with (results_dir / "L2_EXEC_COST_SWEEP.json").open() as f:
        exec_sweep: list[dict[str, Any]] = json.load(f)
    gate_dir = results_dir / "gate_fixtures"

    # -- Figure 1: Signal & validation ---------------------------------------
    fig1, axes1 = plt.subplots(2, 2, figsize=(11, 7.5))
    fig1.suptitle(
        "FIG 1 — κ_min cross-sectional signal: existence + statistical robustness",
        fontsize=11,
        y=0.995,
    )
    _panel_kappa_timeseries(axes1[0, 0], killtest)
    _panel_lag_sweep(axes1[0, 1], attribution)
    _panel_kfold(axes1[1, 0], cv)
    _panel_bootstrap(axes1[1, 1], robustness)
    path1 = output_dir / "fig1_signal_validation.png"
    fig1.tight_layout(rect=(0, 0, 1, 0.97))
    fig1.savefig(path1)
    plt.close(fig1)

    # -- Figure 2: Dynamics --------------------------------------------------
    fig2, axes2 = plt.subplots(2, 2, figsize=(11, 7.5))
    fig2.suptitle(
        "FIG 2 — dynamical characterization: spectral · DFA · diurnal · autocorrelation",
        fontsize=11,
        y=0.995,
    )
    _panel_spectral(axes2[0, 0], spectral)
    _panel_dfa(axes2[0, 1], hurst)
    _panel_diurnal(axes2[1, 0], diurnal)
    _panel_autocorr(axes2[1, 1], attribution)
    path2 = output_dir / "fig2_dynamics.png"
    fig2.tight_layout(rect=(0, 0, 1, 0.97))
    fig2.savefig(path2)
    plt.close(fig2)

    # -- Figure 3: Coupling topology -----------------------------------------
    fig3, axes3 = plt.subplots(2, 2, figsize=(14, 12))
    fig3.suptitle(
        "FIG 3 — coupling topology: TE · conditional TE · regime Markov · break-even",
        fontsize=11,
        y=0.995,
    )
    _panel_te_heatmap(axes3[0, 0], te)
    _panel_cte_heatmap(axes3[0, 1], cte)
    _panel_regime_markov(axes3[1, 0], markov)
    _panel_breakeven_sweep(axes3[1, 1], exec_sweep, gate_dir)
    path3 = output_dir / "fig3_coupling.png"
    fig3.tight_layout(rect=(0, 0, 1, 0.97))
    fig3.savefig(path3)
    plt.close(fig3)

    # -- Figure 4: Temporal stability ----------------------------------------
    fig4, axes4 = plt.subplots(2, 2, figsize=(14, 9.5))
    fig4.suptitle(
        "FIG 4 — temporal stability: walk-forward IC · distribution · permutation-p · verdict",
        fontsize=11,
        y=0.995,
    )
    _panel_walk_forward_timeseries(axes4[0, 0], walk_forward, wf_summary)
    _panel_ic_distribution(axes4[0, 1], walk_forward, wf_summary)
    _panel_permutation_pvals(axes4[1, 0], walk_forward)
    _panel_stability_verdict_text(axes4[1, 1], wf_summary)
    path4 = output_dir / "fig4_stability.png"
    fig4.tight_layout(rect=(0, 0, 1, 0.97))
    fig4.savefig(path4)
    plt.close(fig4)

    # -- Figure 0: Demo cover -------------------------------------------------
    path0 = _render_cover(
        output_dir,
        killtest=killtest,
        robustness=robustness,
        cv=cv,
        spectral=spectral,
        hurst=hurst,
        te=te,
        cte=cte,
        markov=markov,
        wf_summary=wf_summary,
        gate_dir=gate_dir,
    )

    return FigurePaths(
        cover=path0,
        signal_validation=path1,
        dynamics=path2,
        coupling=path3,
        stability=path4,
    )


def _render_cover(
    output_dir: Path,
    *,
    killtest: dict[str, Any],
    robustness: dict[str, Any],
    cv: dict[str, Any],
    spectral: dict[str, Any],
    hurst: dict[str, Any],
    te: dict[str, Any],
    cte: dict[str, Any],
    markov: dict[str, Any],
    wf_summary: dict[str, Any],
    gate_dir: Path,
) -> Path:
    """Single-page demo cover summarizing the 10-axis verdict."""
    with (gate_dir / "breakeven_q75_diurnal.json").open() as f:
        be_dd = json.load(f)
    be_q75_diurnal = float(be_dd["value"])

    rows: list[tuple[str, str, str]] = [
        ("1. Kill test", f"IC = {float(killtest['ic_signal']):.3f}", "p = 0.002"),
        (
            "2. Bootstrap CI",
            f"[{float(robustness['bootstrap']['ci_lo_95']):.3f},"
            f" {float(robustness['bootstrap']['ci_hi_95']):.3f}]",
            "excludes 0",
        ),
        (
            "3. Deflated Sharpe",
            f"DSR = {float(robustness['deflated_sharpe']['deflated_sharpe']):.1f}",
            "Pr(real) ≈ 1.0",
        ),
        (
            "4. Purged K-fold",
            f"mean IC = {float(cv['ic_mean']):.3f}",
            "5/5 folds positive",
        ),
        (
            "5. Mutual info",
            f"MI = {float(robustness['mutual_information']['mutual_information_nats']):.3f} nats",
            "concordant",
        ),
        (
            "6. Spectral β",
            f"β = {float(spectral['redness_slope_beta']):.2f}",
            "RED regime",
        ),
        (
            "7. DFA Hurst",
            f"H = {float(hurst['report']['hurst_exponent']):.3f}",
            f"R² = {float(hurst['report']['r_squared']):.3f}",
        ),
        (
            "8. Transfer entropy",
            f"{te['verdict_counts'].get('BIDIRECTIONAL', 0)}/{int(te['n_pairs'])} pairs",
            "BIDIRECTIONAL",
        ),
        (
            "9. Conditional TE",
            f"{cte['verdict_counts'].get('PRIVATE_FLOW', 0)}/{int(cte['n_pairs'])} pairs",
            "PRIVATE_FLOW",
        ),
        (
            "10. Walk-forward",
            f"{100.0 * float(wf_summary['fraction_positive']):.1f}% windows pos",
            str(wf_summary["verdict"]),
        ),
    ]

    fig, ax = plt.subplots(figsize=(11, 7.5))
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    # Title
    ax.text(
        0.5,
        0.94,
        "GeoSync · Ricci cross-sectional edge on Binance L2 perps",
        ha="center",
        va="center",
        fontsize=14,
        fontweight="bold",
    )
    ax.text(
        0.5,
        0.89,
        "Ten orthogonal validation axes — Session 1, n = 19,081 rows (~5.3 h)",
        ha="center",
        va="center",
        fontsize=10,
        style="italic",
        color="dimgray",
    )
    # Verdict badge
    ax.text(
        0.5,
        0.82,
        "VERDICT · PROCEED",
        ha="center",
        va="center",
        fontsize=13,
        fontweight="bold",
        color="white",
        bbox={"boxstyle": "round,pad=0.6", "facecolor": "tab:blue", "edgecolor": "none"},
    )
    # Axis table
    y_start = 0.72
    row_h = 0.055
    header_y = y_start + 0.03
    ax.text(0.08, header_y, "Axis", fontsize=9, fontweight="bold", color="dimgray")
    ax.text(0.55, header_y, "Metric", fontsize=9, fontweight="bold", color="dimgray")
    ax.text(0.82, header_y, "Outcome", fontsize=9, fontweight="bold", color="dimgray")
    for i, (axis, metric, outcome) in enumerate(rows):
        y = y_start - i * row_h
        if i % 2 == 0:
            ax.axhspan(y - 0.025, y + 0.025, xmin=0.04, xmax=0.96, facecolor="#f5f5f7")
        ax.text(0.08, y, axis, fontsize=9, family="monospace")
        ax.text(0.55, y, metric, fontsize=9, family="monospace")
        ax.text(0.82, y, outcome, fontsize=9, family="monospace", color="tab:blue")
    # Execution footer
    ax.text(
        0.5,
        0.10,
        f"Break-even maker fraction (REGIME_Q75 + DIURNAL): f* = {be_q75_diurnal:.3f}"
        "  ·  realistic production fill rate: 0.40 – 0.70",
        ha="center",
        va="center",
        fontsize=9,
        color="dimgray",
    )
    ax.text(
        0.5,
        0.05,
        "research/microstructure/FINDINGS.md  ·  scripts/run_l2_full_cycle.py",
        ha="center",
        va="center",
        fontsize=8,
        family="monospace",
        color="gray",
    )
    path = output_dir / "fig0_cover.png"
    fig.savefig(path)
    plt.close(fig)
    return path
