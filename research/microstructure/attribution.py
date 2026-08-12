"""Attribution & temporal structure of the Ricci cross-sectional edge.

Three empirical questions answered from already-collected substrate, no
new research hypothesis beyond what PR #240 established:

    Q1  Concentration of alpha. What fraction of trades carries what
        fraction of cumulative |gross bp|? Expressed as Gini coefficient
        over absolute per-trade contributions, plus the explicit
        top-K-fraction-that-holds-80%-of-gross.

    Q2  Temporal alignment. Is κ_min leading, coincident, or lagging
        the forward-mid-return it predicts? Measured via pooled
        Spearman IC of signal-shifted-by-k vs fwd return, for k in a
        symmetric band around zero. Peak position = leading-ness.

    Q3  Signal refresh rate. How fast does κ_min forget its past?
        Expressed as 1/e-decay time of the lag-ℓ autocorrelation of
        κ_min itself, integer-interpolated on a 1-second grid.

None of these introduce new numerical content; all operate on the
existing Ricci signal construction in `killtest.py` and existing trade
containers from `pnl.py`. Numerical spine untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.stats import spearmanr

LAGS_DEFAULT_SEC: Final[tuple[int, ...]] = (
    -300,
    -180,
    -120,
    -60,
    -30,
    -10,
    0,
    +10,
    +30,
    +60,
    +120,
    +180,
    +300,
)
AUTOCORR_MAX_LAG_SEC: Final[int] = 1200


@dataclass(frozen=True)
class ConcentrationReport:
    """Q1 — Gini + top-K concentration of |trade bp| contributions."""

    n_trades: int
    total_abs_bp: float
    gini: float
    top_5_pct_frac_of_total: float
    top_10_pct_frac_of_total: float
    top_20_pct_frac_of_total: float
    trades_frac_for_80_pct_of_total: float


@dataclass(frozen=True)
class LagReport:
    """Q2 — signal-lag IC sweep and argmax interpretation."""

    lags_sec: tuple[int, ...]
    ic_per_lag: dict[int, float]
    ic_peak_lag_sec: int
    ic_peak_value: float
    verdict: str  # "LEADING" | "COINCIDENT" | "LAGGING" | "UNRESOLVED"


@dataclass(frozen=True)
class AutocorrReport:
    """Q3 — signal autocorrelation decay time."""

    acf_lag_sec: tuple[int, ...]
    acf: tuple[float, ...]
    tau_decay_sec: float | None  # smallest lag where |ACF| < 1/e ≈ 0.3679


def gini_coefficient(values: NDArray[np.float64]) -> float:
    """Gini of non-negative values; 0 = perfectly uniform, 1 = one element
    holds everything. Safe on empty / all-zero input (returns 0.0)."""
    x = np.abs(np.asarray(values, dtype=np.float64))
    if x.size == 0:
        return 0.0
    total = float(x.sum())
    if total <= 0.0:
        return 0.0
    s = np.sort(x)
    n = x.size
    # Standard formula: G = (2 Σ i·x_i) / (n Σ x_i) − (n+1)/n
    i = np.arange(1, n + 1, dtype=np.float64)
    return float((2.0 * np.sum(i * s) / (n * total)) - (n + 1.0) / n)


def concentration_report(gross_bp: list[float] | NDArray[np.float64]) -> ConcentrationReport:
    """Compute Gini + top-K concentration over |trade bp|."""
    arr = np.abs(np.asarray(gross_bp, dtype=np.float64))
    if arr.size == 0:
        return ConcentrationReport(
            n_trades=0,
            total_abs_bp=0.0,
            gini=0.0,
            top_5_pct_frac_of_total=0.0,
            top_10_pct_frac_of_total=0.0,
            top_20_pct_frac_of_total=0.0,
            trades_frac_for_80_pct_of_total=0.0,
        )
    total = float(arr.sum())
    if total <= 0.0:
        return ConcentrationReport(
            n_trades=int(arr.size),
            total_abs_bp=0.0,
            gini=0.0,
            top_5_pct_frac_of_total=0.0,
            top_10_pct_frac_of_total=0.0,
            top_20_pct_frac_of_total=0.0,
            trades_frac_for_80_pct_of_total=0.0,
        )
    sorted_desc = np.sort(arr)[::-1]
    cumulative_desc = np.cumsum(sorted_desc) / total
    n = arr.size

    def _top_k_share(k_frac: float) -> float:
        k = max(1, int(np.ceil(k_frac * n)))
        return float(cumulative_desc[min(k - 1, n - 1)])

    # smallest trade-fraction holding >= 80 % of total contribution
    idx_80 = int(np.searchsorted(cumulative_desc, 0.80) + 1)
    idx_80 = min(idx_80, n)
    trades_frac_for_80 = float(idx_80 / n)

    return ConcentrationReport(
        n_trades=n,
        total_abs_bp=total,
        gini=gini_coefficient(arr),
        top_5_pct_frac_of_total=_top_k_share(0.05),
        top_10_pct_frac_of_total=_top_k_share(0.10),
        top_20_pct_frac_of_total=_top_k_share(0.20),
        trades_frac_for_80_pct_of_total=trades_frac_for_80,
    )


def _pooled_ic(signal_flat: NDArray[np.float64], target_flat: NDArray[np.float64]) -> float:
    mask = np.isfinite(signal_flat) & np.isfinite(target_flat)
    if int(mask.sum()) < 50:
        return float("nan")
    s = signal_flat[mask]
    t = target_flat[mask]
    if float(np.std(s)) < 1e-14 or float(np.std(t)) < 1e-14:
        return float("nan")
    rho, _ = spearmanr(s, t)
    return float(rho) if np.isfinite(rho) else float("nan")


def lag_ic_sweep(
    signal_1d: NDArray[np.float64],
    target_panel: NDArray[np.float64],
    *,
    lags_sec: tuple[int, ...] = LAGS_DEFAULT_SEC,
    significance_margin: float = 0.02,
) -> LagReport:
    """Compute IC(signal_shift_by_k, target) for k in lags_sec.

    Positive lag k in this implementation means `shifted[t] = signal[t-k]`
    — past signal placed at t. IC(shifted, target) then measures
    cross-correlation at CCF-lag +k: corr(signal[t-k], target[t]).

    In standard CCF terms, peak at +k means X leads Y by k.
    Here X = κ signal, Y = forward return, so peak at +k means the
    *past* κ predicts the target better — signal LEADS and we have
    k seconds of latency budget.

    Peak at −k means future κ predicts current target; this can
    happen when the κ rolling-window overlaps the fwd-return horizon
    (the κ at t+k has already 'seen' part of target[t, t+horizon]).
    That is strictly LAGGING from a causal-use perspective.

    verdict heuristic:
      LEADING     peak lag > +margin_sec          (past signal best)
      COINCIDENT  peak lag within ±margin_sec     (now is optimal)
      LAGGING     peak lag < −margin_sec          (future signal best, overlap artifact)
      UNRESOLVED  max ic_per_lag is NaN
    """
    n = int(signal_1d.shape[0])
    n_sym = int(target_panel.shape[1])
    signal_panel = np.repeat(signal_1d[:, None], n_sym, axis=1)

    ic_per_lag: dict[int, float] = {}
    for k in lags_sec:
        shifted = np.full_like(signal_panel, np.nan)
        if k == 0:
            shifted[:] = signal_panel
        elif k > 0:
            if k < n:
                shifted[k:] = signal_panel[:-k]
        else:
            absk = -k
            if absk < n:
                shifted[:-absk] = signal_panel[absk:]
        ic_per_lag[int(k)] = _pooled_ic(shifted.ravel(), target_panel.ravel())

    finite = [(k, v) for k, v in ic_per_lag.items() if np.isfinite(v)]
    if not finite:
        return LagReport(
            lags_sec=tuple(int(k) for k in lags_sec),
            ic_per_lag=ic_per_lag,
            ic_peak_lag_sec=0,
            ic_peak_value=float("nan"),
            verdict="UNRESOLVED",
        )
    peak_k, peak_v = max(finite, key=lambda kv: kv[1])
    margin_sec = max(10, int(significance_margin * 1000))  # seconds-scale margin
    if peak_k > +margin_sec:
        verdict = "LEADING"  # past-signal IC > coincident → we have latency budget
    elif peak_k < -margin_sec:
        verdict = "LAGGING"  # future-signal IC > coincident → κ hasn't finished integrating
    else:
        verdict = "COINCIDENT"

    return LagReport(
        lags_sec=tuple(int(k) for k in lags_sec),
        ic_per_lag=ic_per_lag,
        ic_peak_lag_sec=int(peak_k),
        ic_peak_value=float(peak_v),
        verdict=verdict,
    )


def autocorrelation_decay(
    signal_1d: NDArray[np.float64],
    *,
    max_lag_sec: int = AUTOCORR_MAX_LAG_SEC,
    lag_step_sec: int = 10,
) -> AutocorrReport:
    """Return lag → ACF(lag) and the 1/e-decay time.

    ACF(ℓ) = corr( x[t], x[t+ℓ] ) on finite pairs. τ_decay is the
    smallest positive ℓ where |ACF(ℓ)| < 1/e ≈ 0.3679; if ACF never
    dips below that within max_lag_sec, τ_decay is None.
    """
    threshold = float(np.exp(-1.0))
    s = np.asarray(signal_1d, dtype=np.float64)
    n = s.shape[0]
    if n < 200:
        return AutocorrReport(
            acf_lag_sec=(0,),
            acf=(1.0,),
            tau_decay_sec=None,
        )

    lag_grid = list(range(0, max_lag_sec + 1, max(1, lag_step_sec)))
    acf_values: list[float] = []
    tau: float | None = None
    for ell in lag_grid:
        if ell == 0:
            acf_values.append(1.0)
            continue
        if ell >= n:
            acf_values.append(float("nan"))
            continue
        a = s[: n - ell]
        b = s[ell:]
        mask = np.isfinite(a) & np.isfinite(b)
        if int(mask.sum()) < 50:
            acf_values.append(float("nan"))
            continue
        aa = a[mask] - np.mean(a[mask])
        bb = b[mask] - np.mean(b[mask])
        denom = float(np.sqrt(np.sum(aa * aa) * np.sum(bb * bb)))
        if denom <= 1e-14:
            acf_values.append(float("nan"))
            continue
        rho = float(np.sum(aa * bb) / denom)
        acf_values.append(rho)
        if tau is None and abs(rho) < threshold and ell > 0:
            # Linear interpolate between previous point and this one
            prev_acf = acf_values[-2]
            prev_lag = lag_grid[len(acf_values) - 2]
            if prev_acf is not None and np.isfinite(prev_acf) and abs(prev_acf) >= threshold:
                # |ACF| crossed threshold between prev_lag and ell
                # Solve |prev_acf + (rho - prev_acf) * t| = threshold
                step = ell - prev_lag
                delta = rho - prev_acf
                if delta != 0.0:
                    t_unit = (threshold - abs(prev_acf)) / (abs(rho) - abs(prev_acf))
                    tau = float(prev_lag + t_unit * step)
                else:
                    tau = float(ell)
            else:
                tau = float(ell)

    return AutocorrReport(
        acf_lag_sec=tuple(int(lag) for lag in lag_grid),
        acf=tuple(acf_values),
        tau_decay_sec=tau,
    )
