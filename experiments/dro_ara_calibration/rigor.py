# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Statistical rigor layer for DRO-ARA calibration (v3).

Builds on top of ``research/microstructure/robustness.py`` to attach
calibration-specific statistical claims to every (H, rs) grid cell:

* **Bootstrap Sharpe CI** — block bootstrap (Politis–Romano) on fold-level
  OOS returns → 95 % confidence interval for the mean Sharpe.
* **Surrogate null p-value** — stationary block bootstrap on independently
  shuffled gate × return pairs → empirical P(|Sharpe*| ≥ |Sharpe_obs| | H₀).
* **Deflated Sharpe** — Lopez de Prado (2014). Given N grid trials and
  n_obs fold samples, returns P(edge is real | multiple-testing).
* **Min detectable Sharpe (power)** — given observed σ and n_obs, the
  Sharpe level that would be rejected at 80 % power, 5 % significance.
* **Baselines** — ``buy_hold`` and ``random_gate`` counterfactuals so the
  filter's information content can be measured as lift, not absolute level.

No invariants are relaxed; this module computes statistics only. Zero
mutation of engine constants.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy import stats

from research.microstructure.robustness import deflated_sharpe as _deflated_sharpe

DEFAULT_N_BOOTSTRAPS: Final[int] = 1000
DEFAULT_N_SURROGATES: Final[int] = 1000
DEFAULT_BLOCK_SIZE: Final[int] = 8  # ~quarterly blocks on monthly folds
DEFAULT_POWER: Final[float] = 0.80
DEFAULT_ALPHA: Final[float] = 0.05


@dataclass(frozen=True)
class SharpeBootstrap:
    """Block bootstrap CI on annualised Sharpe across folds."""

    sharpe_point: float
    sharpe_mean: float
    sharpe_std: float
    ci_lo_95: float
    ci_hi_95: float
    n_bootstraps: int
    block_size: int
    significant_at_95: bool  # 0 ∉ [ci_lo, ci_hi]


@dataclass(frozen=True)
class NullTest:
    """Surrogate null test on Sharpe via gate-randomisation."""

    sharpe_observed: float
    sharpe_null_mean: float
    sharpe_null_std: float
    p_value_two_sided: float
    n_surrogates: int


@dataclass(frozen=True)
class DeflatedResult:
    """Lopez de Prado Deflated Sharpe summary."""

    sharpe_observed: float
    expected_max_sharpe_under_null: float
    deflated_sharpe_stat: float
    probability_edge_is_real: float
    n_trials: int
    n_observations: int


@dataclass(frozen=True)
class PowerAnalysis:
    """Minimum detectable Sharpe given observed volatility."""

    n_observations: int
    sigma_per_obs: float
    alpha: float
    power: float
    min_detectable_sharpe_annualised: float
    empirical_sharpe: float
    is_adequately_powered: bool


def _sharpe_annualised(returns: NDArray[np.float64], *, periods_per_year: int = 252) -> float:
    """Annualised Sharpe on a 1-D return series. NaN-safe (returns 0 on degeneracy)."""
    r = np.asarray(returns, dtype=np.float64).ravel()
    r = r[np.isfinite(r)]
    if r.size < 2:
        return 0.0
    mean = float(np.mean(r))
    std = float(np.std(r, ddof=1))
    if std < 1e-14:
        return 0.0
    return float(mean / std * np.sqrt(periods_per_year))


def bootstrap_sharpe_ci(
    fold_sharpes: NDArray[np.float64],
    *,
    n_bootstraps: int = DEFAULT_N_BOOTSTRAPS,
    block_size: int = DEFAULT_BLOCK_SIZE,
    seed: int = 42,
) -> SharpeBootstrap:
    """Politis–Romano stationary block bootstrap on per-fold Sharpes.

    Resamples fold-level Sharpe ratios in contiguous blocks to preserve
    any serial dependence across rolling windows. Returns 95 % CI on the
    mean Sharpe across folds.
    """
    arr = np.asarray(fold_sharpes, dtype=np.float64).ravel()
    arr = arr[np.isfinite(arr)]
    n = arr.size
    if n < 3:
        return SharpeBootstrap(
            sharpe_point=float(np.mean(arr)) if n else 0.0,
            sharpe_mean=float("nan"),
            sharpe_std=float("nan"),
            ci_lo_95=float("nan"),
            ci_hi_95=float("nan"),
            n_bootstraps=0,
            block_size=block_size,
            significant_at_95=False,
        )

    point = float(np.mean(arr))
    rng = np.random.default_rng(seed)
    effective_block = max(1, min(block_size, n))
    n_blocks = max(1, n // effective_block)

    means: list[float] = []
    for _ in range(n_bootstraps):
        starts = rng.integers(0, n - effective_block + 1, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + effective_block, dtype=np.int64) for s in starts])
        idx = idx[:n]
        means.append(float(np.mean(arr[idx])))

    boots = np.asarray(means, dtype=np.float64)
    lo = float(np.quantile(boots, 0.025))
    hi = float(np.quantile(boots, 0.975))
    return SharpeBootstrap(
        sharpe_point=point,
        sharpe_mean=float(boots.mean()),
        sharpe_std=float(boots.std(ddof=1)),
        ci_lo_95=lo,
        ci_hi_95=hi,
        n_bootstraps=int(boots.size),
        block_size=effective_block,
        significant_at_95=bool(lo > 0.0 or hi < 0.0),
    )


def surrogate_null_sharpe(
    fold_sharpes: NDArray[np.float64],
    *,
    n_surrogates: int = DEFAULT_N_SURROGATES,
    seed: int = 42,
) -> NullTest:
    """Empirical p-value for mean Sharpe under a sign-flip null.

    Under H₀ (no edge): each fold's Sharpe is equally likely to have
    the opposite sign. This is the permutation-test analogue for
    paired-with-zero comparison on fold-level Sharpes.

    Equivalent to a one-sample sign-flip test on the mean; valid without
    distributional assumptions on fold-Sharpe.
    """
    arr = np.asarray(fold_sharpes, dtype=np.float64).ravel()
    arr = arr[np.isfinite(arr)]
    n = arr.size
    if n < 3:
        return NullTest(
            sharpe_observed=float(np.mean(arr)) if n else 0.0,
            sharpe_null_mean=float("nan"),
            sharpe_null_std=float("nan"),
            p_value_two_sided=float("nan"),
            n_surrogates=0,
        )
    observed = float(np.mean(arr))
    rng = np.random.default_rng(seed)
    null_means = np.empty(n_surrogates, dtype=np.float64)
    for i in range(n_surrogates):
        signs = rng.choice([-1.0, 1.0], size=n)
        null_means[i] = float(np.mean(arr * signs))
    p_two = float(np.mean(np.abs(null_means) >= abs(observed)))
    return NullTest(
        sharpe_observed=observed,
        sharpe_null_mean=float(null_means.mean()),
        sharpe_null_std=float(null_means.std(ddof=1)),
        p_value_two_sided=p_two,
        n_surrogates=int(n_surrogates),
    )


def deflated_sharpe_wrapper(
    sharpe_observed: float, *, n_trials: int, n_observations: int
) -> DeflatedResult:
    """Thin adapter around research.microstructure.robustness.deflated_sharpe."""
    rep = _deflated_sharpe(sharpe_observed, n_trials=n_trials, n_observations=n_observations)
    return DeflatedResult(
        sharpe_observed=rep.sharpe_observed,
        expected_max_sharpe_under_null=rep.sharpe_expected_max,
        deflated_sharpe_stat=rep.deflated_sharpe,
        probability_edge_is_real=rep.probability_sharpe_is_real,
        n_trials=rep.n_trials,
        n_observations=rep.n_observations,
    )


def min_detectable_sharpe(
    empirical_sharpe: float,
    *,
    n_observations: int,
    sigma_per_obs: float,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
    periods_per_year: int = 252,
) -> PowerAnalysis:
    """Min Sharpe detectable at (α, 1−β) power; compares to empirical level.

    Using the one-sample t-test approximation. For H₀: μ = 0 vs. H₁: μ > 0,
    effect size δ = μ / σ per-observation. n_obs and σ are pre-scaled; we
    return the annualised Sharpe equivalent.
    """
    if n_observations < 3 or sigma_per_obs <= 0.0:
        return PowerAnalysis(
            n_observations=int(n_observations),
            sigma_per_obs=float(sigma_per_obs),
            alpha=float(alpha),
            power=float(power),
            min_detectable_sharpe_annualised=float("inf"),
            empirical_sharpe=float(empirical_sharpe),
            is_adequately_powered=False,
        )
    z_alpha = float(stats.norm.ppf(1.0 - alpha))
    z_beta = float(stats.norm.ppf(power))
    per_obs_effect = (z_alpha + z_beta) / float(np.sqrt(n_observations))
    annualised = per_obs_effect * float(np.sqrt(periods_per_year))
    detectable = bool(abs(empirical_sharpe) >= annualised)
    return PowerAnalysis(
        n_observations=int(n_observations),
        sigma_per_obs=float(sigma_per_obs),
        alpha=float(alpha),
        power=float(power),
        min_detectable_sharpe_annualised=annualised,
        empirical_sharpe=float(empirical_sharpe),
        is_adequately_powered=detectable,
    )


# ---------------------------------------------------------------------------
# Baselines (counterfactuals for lift measurement)
# ---------------------------------------------------------------------------


def baseline_buy_hold_sharpe(
    test_prices: NDArray[np.float64], *, periods_per_year: int = 252
) -> float:
    """Trivial passive baseline: hold position +1 for the full test window."""
    p = np.asarray(test_prices, dtype=np.float64)
    if p.size < 2:
        return 0.0
    rets = np.diff(p) / np.maximum(p[:-1], 1e-12)
    return _sharpe_annualised(rets, periods_per_year=periods_per_year)


def baseline_random_gate_sharpe(
    combo_signal: NDArray[np.float64],
    test_prices: NDArray[np.float64],
    *,
    gate_rate: float,
    seed: int = 42,
    n_draws: int = 100,
    fee_per_trade: float = 5e-4,
) -> float:
    """Expected Sharpe if the gate mask were drawn i.i.d. Bernoulli(gate_rate).

    Averages over ``n_draws`` random masks to reduce Monte Carlo noise.
    Matches the fold-level signal shape used by ``vectorized_backtest``.
    """
    from backtest.event_driven import vectorized_backtest

    p = np.asarray(test_prices, dtype=np.float64)
    sig = np.asarray(combo_signal, dtype=np.float64)
    if sig.shape != p.shape:
        raise ValueError(f"signal/price shape mismatch: {sig.shape} vs {p.shape}")
    if not 0.0 <= gate_rate <= 1.0:
        raise ValueError(f"gate_rate must be in [0, 1], got {gate_rate}")
    if n_draws < 1:
        raise ValueError(f"n_draws must be >= 1, got {n_draws}")

    rng = np.random.default_rng(seed)
    sharpes = np.empty(n_draws, dtype=np.float64)
    for i in range(n_draws):
        mask = (rng.random(p.size) < gate_rate).astype(np.float64)
        gated = sig * mask
        bt = vectorized_backtest(p, gated, fee_per_trade=fee_per_trade)
        sharpes[i] = float(bt["sharpe"])
    return float(np.mean(sharpes))
