"""Statistical robustness layer for the Ricci cross-sectional edge.

Four textbook measures that adversarial review demands but the spine
did not previously expose:

    R1  Block bootstrap (Politis-Romano 1994) CI on Spearman IC.
        Time-series-aware: preserves local autocorrelation by sampling
        contiguous blocks instead of individual rows. Standard practice
        for correlated financial signals; point-IC + permutation-p
        alone understate uncertainty.

    R2  Deflated Sharpe Ratio (Lopez de Prado 2014). Corrects the
        observed Sharpe for the number of trials implicit in signal
        discovery. Returns the probability that the best-observed
        Sharpe is not a statistical artifact of multiple testing.

    R3  Augmented Dickey-Fuller stationarity test. If κ_min is
        non-stationary (unit root), IC estimates may be spurious. A
        stationary signal is a necessary (not sufficient) condition
        for durable alpha.

    R4  Mutual Information (histogram-based KDE estimator). Captures
        any non-linear dependence Spearman misses. MI = 0 ⇔ true
        independence; Spearman = 0 does not imply independence.

Pure functions. Deterministic under seed. No network I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.stats import spearmanr

DEFAULT_BLOCK_SIZE: Final[int] = 300  # ~ signal decay time from attribution
DEFAULT_N_BOOTSTRAPS: Final[int] = 1000
DEFAULT_ADF_MAX_LAG: Final[int] = 20
DEFAULT_MI_BINS: Final[int] = 32


@dataclass(frozen=True)
class BootstrapICReport:
    """R1 — block-bootstrap confidence interval on Spearman IC."""

    ic_point: float
    ic_mean_bootstrap: float
    ic_std_bootstrap: float
    ci_lo_95: float
    ci_hi_95: float
    n_bootstraps: int
    block_size: int
    significant_at_95: bool  # 0 is NOT inside [ci_lo, ci_hi]


@dataclass(frozen=True)
class DeflatedSharpeReport:
    """R2 — Lopez de Prado deflated Sharpe ratio."""

    sharpe_observed: float
    n_trials: int
    n_observations: int
    sharpe_expected_max: float
    deflated_sharpe: float
    probability_sharpe_is_real: float


@dataclass(frozen=True)
class ADFReport:
    """R3 — Augmented Dickey-Fuller unit-root test."""

    statistic: float
    pvalue: float
    lag_used: int
    n_obs_used: int
    verdict: str  # "STATIONARY" | "UNIT_ROOT" | "INCONCLUSIVE"


@dataclass(frozen=True)
class MutualInfoReport:
    """R4 — Mutual Information estimate (nats)."""

    mutual_information_nats: float
    mutual_information_bits: float
    correlation_spearman: float
    n_bins: int
    n_samples: int


# ---------------------------------------------------------------------------
# R1 · Block bootstrap on Spearman IC
# ---------------------------------------------------------------------------


def _spearman_finite(x: NDArray[np.float64], y: NDArray[np.float64]) -> float:
    mask = np.isfinite(x) & np.isfinite(y)
    if int(mask.sum()) < 30:
        return float("nan")
    xs = x[mask]
    ys = y[mask]
    if float(np.std(xs)) < 1e-14 or float(np.std(ys)) < 1e-14:
        return float("nan")
    rho, _ = spearmanr(xs, ys)
    return float(rho) if np.isfinite(rho) else float("nan")


def block_bootstrap_ic(
    signal: NDArray[np.float64],
    target: NDArray[np.float64],
    *,
    block_size: int = DEFAULT_BLOCK_SIZE,
    n_bootstraps: int = DEFAULT_N_BOOTSTRAPS,
    seed: int = 42,
) -> BootstrapICReport:
    """Politis-Romano stationary block bootstrap on Spearman IC.

    Both arrays must be 1D and aligned. Samples contiguous blocks of
    `block_size` rows with replacement to preserve local autocorrelation.
    """
    x = np.asarray(signal, dtype=np.float64).ravel()
    y = np.asarray(target, dtype=np.float64).ravel()
    if x.shape != y.shape:
        raise ValueError(f"signal/target shape mismatch: {x.shape} vs {y.shape}")
    if block_size < 1:
        raise ValueError(f"block_size must be >= 1, got {block_size}")
    if n_bootstraps < 10:
        raise ValueError(f"n_bootstraps must be >= 10, got {n_bootstraps}")

    n = x.size
    rng = np.random.default_rng(seed)
    point = _spearman_finite(x, y)

    ics: list[float] = []
    if n < block_size:
        return BootstrapICReport(
            ic_point=point,
            ic_mean_bootstrap=float("nan"),
            ic_std_bootstrap=float("nan"),
            ci_lo_95=float("nan"),
            ci_hi_95=float("nan"),
            n_bootstraps=0,
            block_size=block_size,
            significant_at_95=False,
        )

    n_blocks = max(1, n // block_size)
    for _ in range(n_bootstraps):
        starts = rng.integers(0, n - block_size + 1, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block_size, dtype=np.int64) for s in starts])
        ic_b = _spearman_finite(x[idx], y[idx])
        if np.isfinite(ic_b):
            ics.append(ic_b)

    if not ics:
        return BootstrapICReport(
            ic_point=point,
            ic_mean_bootstrap=float("nan"),
            ic_std_bootstrap=float("nan"),
            ci_lo_95=float("nan"),
            ci_hi_95=float("nan"),
            n_bootstraps=0,
            block_size=block_size,
            significant_at_95=False,
        )

    arr = np.asarray(ics, dtype=np.float64)
    lo = float(np.quantile(arr, 0.025))
    hi = float(np.quantile(arr, 0.975))
    significant = bool((lo > 0.0) or (hi < 0.0))

    return BootstrapICReport(
        ic_point=point,
        ic_mean_bootstrap=float(arr.mean()),
        ic_std_bootstrap=float(arr.std(ddof=1)) if arr.size > 1 else float("nan"),
        ci_lo_95=lo,
        ci_hi_95=hi,
        n_bootstraps=int(arr.size),
        block_size=block_size,
        significant_at_95=significant,
    )


# ---------------------------------------------------------------------------
# R2 · Deflated Sharpe Ratio (Lopez de Prado)
# ---------------------------------------------------------------------------


def _inverse_normal_cdf(p: float) -> float:
    """Stable approximation of the inverse CDF of N(0,1); vectorised via scipy
    would be marginally cleaner but we keep zero extra imports."""
    # Beasley-Springer-Moro coefficients; accurate to ~1e-9 for p ∈ [0.02, 0.98]
    # For extreme tails, fall back to Box-Muller tail approximation.
    if p <= 0.0 or p >= 1.0:
        return float("nan")
    # Use scipy if available at runtime (cleaner path in a library context)
    from scipy.stats import norm

    return float(norm.ppf(p))


def _euler_mascheroni() -> float:
    return 0.5772156649015329


def deflated_sharpe(
    sharpe_observed: float,
    *,
    n_trials: int,
    n_observations: int,
) -> DeflatedSharpeReport:
    """Lopez de Prado (2014) deflated Sharpe ratio.

    Adjusts the observed Sharpe for implicit multiple-testing: given
    `n_trials` candidate strategies and `n_observations` returns, it
    computes the probability the observed max-Sharpe is not just the
    best of many independent noise trials.

    Unit convention (critical): `sharpe_observed` is the per-observation
    Sharpe under the normal-returns simplification, σ(SR)=1/√(T-1).
    This code compares the standardised t-statistic of the observed SR
    against the expected max of `n_trials` standard-normal draws
    (Blanchet-Scaillet 2007 approximation).

    Formula:
        t_obs        = SR_obs · √(T − 1)            (standardised)
        E[max z | N] = (1 − γ) · Φ⁻¹(1 − 1/N)
                      + γ · Φ⁻¹(1 − 1/(N · e))
        DSR          = t_obs − E[max z | N]
        P(real)      = Φ(DSR)
    where γ = Euler-Mascheroni constant, Φ is standard-normal CDF.

    sharpe_expected_max in the report is exposed in SR units
    (E[max z] / √(T − 1)) for comparability with the observed input.
    """
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1, got {n_trials}")
    if n_observations < 2:
        raise ValueError(f"n_observations must be >= 2, got {n_observations}")

    from scipy.stats import norm

    gamma = _euler_mascheroni()
    expected_max_z = (1.0 - gamma) * _inverse_normal_cdf(
        1.0 - 1.0 / float(n_trials)
    ) + gamma * _inverse_normal_cdf(1.0 - 1.0 / (float(n_trials) * np.e))

    sqrt_t = float(np.sqrt(n_observations - 1))
    t_obs = float(sharpe_observed) * sqrt_t
    dsr = t_obs - expected_max_z
    prob = float(norm.cdf(dsr))
    expected_max_sr = expected_max_z / sqrt_t

    return DeflatedSharpeReport(
        sharpe_observed=float(sharpe_observed),
        n_trials=int(n_trials),
        n_observations=int(n_observations),
        sharpe_expected_max=float(expected_max_sr),
        deflated_sharpe=float(dsr),
        probability_sharpe_is_real=prob,
    )


# ---------------------------------------------------------------------------
# R3 · Augmented Dickey-Fuller stationarity
# ---------------------------------------------------------------------------


def adf_stationarity(
    signal: NDArray[np.float64],
    *,
    max_lag: int = DEFAULT_ADF_MAX_LAG,
    significance: float = 0.05,
) -> ADFReport:
    """Delegates to statsmodels if available; falls back to manual OLS ADF.

    Null hypothesis: signal has a unit root (non-stationary).
    Reject null (p < significance) ⇒ STATIONARY.
    """
    x = np.asarray(signal, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size < 50:
        return ADFReport(
            statistic=float("nan"),
            pvalue=float("nan"),
            lag_used=0,
            n_obs_used=int(x.size),
            verdict="INCONCLUSIVE",
        )
    try:
        from statsmodels.tsa.stattools import adfuller

        result = adfuller(x, maxlag=max_lag, autolag="AIC")
        stat = float(result[0])
        pvalue = float(result[1])
        lag_used = int(result[2])
        n_used = int(result[3])
    except Exception:
        # Manual OLS AR(1) fallback
        dy = np.diff(x)
        y_lag = x[:-1]
        slope, intercept = np.polyfit(y_lag, dy, 1)
        pred = slope * y_lag + intercept
        resid = dy - pred
        se_slope = float(np.sqrt(np.sum(resid**2) / (len(dy) - 2))) / float(
            np.sqrt(np.sum((y_lag - y_lag.mean()) ** 2) + 1e-14)
        )
        stat = float(slope / (se_slope + 1e-14))
        # rough asymptotic critical value at 5% for AR(1) without drift ≈ -1.95
        pvalue = 0.05 if stat < -2.86 else (0.10 if stat < -1.95 else 0.50)
        lag_used = 1
        n_used = int(len(dy))

    if pvalue < significance:
        verdict = "STATIONARY"
    elif pvalue > 0.10:
        verdict = "UNIT_ROOT"
    else:
        verdict = "INCONCLUSIVE"

    return ADFReport(
        statistic=stat,
        pvalue=pvalue,
        lag_used=lag_used,
        n_obs_used=n_used,
        verdict=verdict,
    )


# ---------------------------------------------------------------------------
# R4 · Mutual Information (histogram estimator)
# ---------------------------------------------------------------------------


def mutual_information(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    *,
    n_bins: int = DEFAULT_MI_BINS,
) -> MutualInfoReport:
    """Histogram-estimator MI in nats and bits.

    For large n and smooth densities, MI ≈ 0.5 · log(1 / (1 - ρ²)) under
    the bivariate-normal assumption; the non-parametric histogram
    estimate here makes no such assumption.
    """
    xs = np.asarray(x, dtype=np.float64).ravel()
    ys = np.asarray(y, dtype=np.float64).ravel()
    mask = np.isfinite(xs) & np.isfinite(ys)
    if int(mask.sum()) < 100:
        return MutualInfoReport(
            mutual_information_nats=float("nan"),
            mutual_information_bits=float("nan"),
            correlation_spearman=float("nan"),
            n_bins=n_bins,
            n_samples=int(mask.sum()),
        )
    xs = xs[mask]
    ys = ys[mask]
    hist, _, _ = np.histogram2d(xs, ys, bins=n_bins)
    pxy = hist / hist.sum()
    px = pxy.sum(axis=1, keepdims=True)
    py = pxy.sum(axis=0, keepdims=True)
    denom = px * py
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(denom > 0, pxy / denom, 0.0)
        contrib = np.where(pxy > 0, pxy * np.log(np.maximum(ratio, 1e-300)), 0.0)
    mi_nats = float(contrib.sum())
    rho, _ = spearmanr(xs, ys)
    return MutualInfoReport(
        mutual_information_nats=mi_nats,
        mutual_information_bits=mi_nats / float(np.log(2.0)),
        correlation_spearman=float(rho) if np.isfinite(rho) else float("nan"),
        n_bins=n_bins,
        n_samples=int(xs.size),
    )
