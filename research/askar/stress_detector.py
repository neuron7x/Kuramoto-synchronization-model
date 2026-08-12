"""Residualised ΔUnity stress detector — early-warning for SPX drawdowns.

Adapted from the Codex reformulation-branch diff (2026-04-10). The key
methodological upgrade vs PR #193 Unity is orthogonalisation *before*
measuring predictive edge:

  stress_signal(t) = residual( ΔUnity(t) ∼ vol_10, mom_20 )

Unity = λ₁(corr) / N is the top-eigenvalue absorption ratio; its
first difference marks structural integration shocks. Residualising
against realised volatility and 20-bar momentum removes the two
factors that dominate naive Unity regressions, leaving the genuinely
orthogonal part.

Expanding-quantile persistence alerts fire when the residual is in
the top 10 % of its own history for ``persistence`` consecutive bars.
``lead_capture_rate`` measures the fraction of future drawdown events
(cumulative [t+10, t+30] return ≤ threshold) that the alerts flagged
in the preceding 10–30 bar lead window.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


@dataclass(frozen=True, slots=True)
class StressDetectorReport:
    ic_stress_vs_future_drawdown: float
    corr_stress_vol: float
    corr_stress_momentum: float
    lead_capture_rate: float
    alert_rate: float
    contradictions: tuple[str, ...]
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_corr(a: pd.Series, b: pd.Series) -> float:
    frame = pd.concat([a, b], axis=1).dropna()
    if len(frame) < 30:
        return 0.0
    rho, _ = spearmanr(frame.iloc[:, 0], frame.iloc[:, 1])
    return float(rho) if np.isfinite(rho) else 0.0


def _residualize(y: pd.Series, controls: pd.DataFrame) -> pd.Series:
    frame = pd.concat([y, controls], axis=1).dropna()
    out = pd.Series(np.nan, index=y.index, dtype=float)
    if len(frame) < 40:
        return out
    yv = frame.iloc[:, 0].to_numpy(dtype=float)
    x = frame.iloc[:, 1:].to_numpy(dtype=float)
    x = np.column_stack([np.ones(len(x)), x])
    beta, *_ = np.linalg.lstsq(x, yv, rcond=None)
    resid = yv - x @ beta
    out.loc[frame.index] = resid
    return out


def _future_min_return(ret: pd.Series, h_lo: int = 10, h_hi: int = 30) -> pd.Series:
    vals = ret.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    for i in range(len(vals)):
        lo = i + h_lo
        hi = min(len(vals), i + h_hi + 1)
        if lo >= hi:
            continue
        out[i] = float(np.min(np.cumsum(vals[lo:hi])))
    return pd.Series(out, index=ret.index)


def _expanding_alerts(
    signal: pd.Series,
    q: float = 0.9,
    min_obs: int = 120,
    persistence: int = 3,
) -> pd.Series:
    alerts = pd.Series(False, index=signal.index, dtype=bool)
    above = pd.Series(False, index=signal.index, dtype=bool)
    for i in range(1, len(signal)):
        hist = signal.iloc[:i].dropna()
        if len(hist) < min_obs:
            continue
        th = float(hist.quantile(q))
        value = signal.iloc[i]
        above.iloc[i] = bool(np.isfinite(value) and value >= th)
        if i >= persistence - 1:
            window_any = bool(above.iloc[i - persistence + 1 : i + 1].all())
            alerts.iloc[i] = window_any
    return alerts


def _lead_capture(alerts: pd.Series, drawdowns: pd.Series, threshold: float = -0.05) -> float:
    events = drawdowns[drawdowns <= threshold]
    if len(events) == 0:
        return 0.0
    captured = 0
    for ts in events.index:
        loc = alerts.index.get_loc(ts)
        if not isinstance(loc, int):
            continue
        lo = max(0, int(loc) - 30)
        hi = max(0, int(loc) - 10)
        if hi > lo and bool(alerts.iloc[lo:hi].any()):
            captured += 1
    return float(captured / len(events))


def _rolling_unity(returns: pd.DataFrame, window: int) -> pd.Series:
    """Rolling top-eigenvalue absorption ratio λ₁/N on the correlation matrix."""
    arr = returns.to_numpy(dtype=float)
    n, k = arr.shape
    out = pd.Series(np.nan, index=returns.index, dtype=float)
    if k < 2 or window < 10:
        return out
    for i in range(window, n):
        w = arr[i - window : i]
        corr = np.corrcoef(w.T)
        corr = np.nan_to_num(corr, nan=0.0)
        eigs = np.linalg.eigvalsh(corr)
        lam1 = float(eigs[-1]) if eigs.size else 0.0
        out.iloc[i] = lam1 / float(k)
    return out


def run_stress_detector(
    prices: pd.DataFrame,
    *,
    target_asset: str = "USA_500_Index",
    unity_window: int = 60,
) -> tuple[pd.Series, pd.Series, StressDetectorReport]:
    """Early stress detector orthogonal to vol and momentum.

    Returns:
        (stress_signal, alerts, report)

    Mechanism:
      1. ΔUnity = diff(λ₁ / N)                       (structural integration shock)
      2. residualise ΔUnity against {vol_10, mom_20} (remove factor leakage)
      3. expanding 90-percentile + 3-bar persistence (precursor alerts)
      4. validate lead-time vs cumulative [t+10, t+30] SPX drawdown ≤ -5 %
    """
    if target_asset not in prices.columns:
        raise KeyError(f"target_asset {target_asset!r} missing from prices")

    prices = prices.sort_index()
    ratio = prices / prices.shift(1)
    log_arr = np.log(ratio.to_numpy())
    returns = (
        pd.DataFrame(log_arr, index=ratio.index, columns=ratio.columns)
        .replace([np.inf, -np.inf], np.nan)
        .dropna(how="all")
    )

    usable = returns.dropna(axis=1, how="all")
    unity = _rolling_unity(usable, window=unity_window)
    d_unity = unity.diff()

    vol10 = returns[target_asset].rolling(10).std()
    mom20 = prices[target_asset].pct_change(20).reindex(returns.index)
    controls = pd.DataFrame({"vol10": vol10, "mom20": mom20})
    stress_signal = _residualize(d_unity, controls)

    alerts = _expanding_alerts(stress_signal, q=0.9, min_obs=120, persistence=3)
    future_dd = _future_min_return(returns[target_asset], 10, 30)

    ic = _safe_corr(stress_signal, -future_dd)
    corr_v = _safe_corr(stress_signal, vol10)
    corr_m = _safe_corr(stress_signal, mom20)
    capture = _lead_capture(alerts, future_dd, threshold=-0.05)

    contradictions: list[str] = []
    if abs(corr_v) > 0.15:
        contradictions.append("stress_signal_leaks_volatility")
    if abs(corr_m) > 0.15:
        contradictions.append("stress_signal_leaks_momentum")
    if float(alerts.mean()) > 0.30:
        contradictions.append("alert_rate_too_high_for_early_warning")

    passed = bool(abs(corr_v) <= 0.15 and abs(corr_m) <= 0.15 and ic >= 0.05)
    report = StressDetectorReport(
        ic_stress_vs_future_drawdown=float(ic),
        corr_stress_vol=float(corr_v),
        corr_stress_momentum=float(corr_m),
        lead_capture_rate=float(capture),
        alert_rate=float(alerts.mean()),
        contradictions=tuple(contradictions),
        passed=passed,
    )
    return stress_signal, alerts, report


__all__ = ["StressDetectorReport", "run_stress_detector"]
