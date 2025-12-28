"""Statistical resampling utilities for backtest performance metrics."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Iterable, Sequence

import numpy as np
from numpy.typing import NDArray

from backtest.performance import PerformanceReport, compute_performance_metrics

_DEFAULT_BOOTSTRAP_SAMPLES = 1000
_DEFAULT_CONFIDENCE_LEVEL = 0.95
_DEFAULT_MCMC_SAMPLES = 2000
_DEFAULT_PRIOR_MU = 0.0
_DEFAULT_PRIOR_KAPPA = 1e-3
_DEFAULT_PRIOR_ALPHA = 1.0
_DEFAULT_PRIOR_BETA = 1.0

_METRIC_NAMES = tuple(field.name for field in fields(PerformanceReport))


def _as_array(
    values: Iterable[float] | NDArray[np.float64] | None,
) -> NDArray[np.float64]:
    if values is None:
        return np.array([], dtype=float)
    if isinstance(values, np.ndarray):
        return values.astype(float)
    return np.asarray(list(values), dtype=float)


def _validate_confidence_level(confidence_level: float) -> float:
    if not 0.0 < confidence_level < 1.0:
        msg = "confidence_level must lie in the open interval (0, 1)"
        raise ValueError(msg)
    return float(confidence_level)


def _validate_metric_names(metrics: Sequence[str] | None) -> tuple[str, ...]:
    if metrics is None:
        return _METRIC_NAMES

    invalid = sorted(set(metrics) - set(_METRIC_NAMES))
    if invalid:
        invalid_names = ", ".join(invalid)
        msg = f"Unknown metrics requested: {invalid_names}"
        raise ValueError(msg)

    return tuple(dict.fromkeys(metrics))


def _compute_returns(
    equity_curve: NDArray[np.float64], initial_capital: float
) -> NDArray[np.float64]:
    if equity_curve.size == 0:
        return np.array([], dtype=float)

    previous = np.concatenate(([float(initial_capital)], equity_curve[:-1]))
    with np.errstate(divide="ignore", invalid="ignore"):
        returns = (equity_curve - previous) / previous
    returns = returns[np.isfinite(returns)]
    return returns.astype(float)


def _equity_from_returns(
    returns: NDArray[np.float64], initial_capital: float
) -> NDArray[np.float64]:
    cumulative = np.cumprod(1.0 + returns, axis=-1)
    return float(initial_capital) * cumulative


def _confidence_interval(
    samples: NDArray[np.float64], confidence_level: float
) -> tuple[float | None, float | None]:
    valid = samples[np.isfinite(samples)]
    if valid.size == 0:
        return (None, None)

    alpha = 1.0 - confidence_level
    lower = float(np.quantile(valid, alpha / 2.0))
    upper = float(np.quantile(valid, 1.0 - alpha / 2.0))
    return (lower, upper)


@dataclass(slots=True)
class ResampledMetric:
    """Distribution of a single performance metric."""

    name: str
    point_estimate: float | None
    samples: NDArray[np.float64]
    ci_lower: float | None
    ci_upper: float | None


@dataclass(slots=True)
class ResamplingResult:
    """Container for the outcome of a resampling experiment."""

    method: str
    confidence_level: float
    metrics: dict[str, ResampledMetric]

    def summary(self) -> dict[str, dict[str, float | None]]:
        """Return a serialisable summary of the resampled metrics."""

        return {
            name: {
                "point_estimate": metric.point_estimate,
                "ci_lower": metric.ci_lower,
                "ci_upper": metric.ci_upper,
            }
            for name, metric in self.metrics.items()
        }


def bootstrap_performance_metrics(
    *,
    equity_curve: Iterable[float] | NDArray[np.float64],
    initial_capital: float,
    pnl: Iterable[float] | NDArray[np.float64] | None = None,
    position_changes: Iterable[float] | NDArray[np.float64] | None = None,
    confidence_level: float = _DEFAULT_CONFIDENCE_LEVEL,
    num_resamples: int = _DEFAULT_BOOTSTRAP_SAMPLES,
    random_state: int | None = None,
    metrics: Sequence[str] | None = None,
) -> ResamplingResult:
    """Estimate confidence intervals via bootstrap resampling.

    The bootstrap assumes that period-to-period returns are independent and
    identically distributed. For each resample the returns are drawn with
    replacement and propagated into a synthetic equity curve before computing a
    fresh :class:`PerformanceReport`.
    """

    if num_resamples <= 0:
        msg = "num_resamples must be a positive integer"
        raise ValueError(msg)

    confidence_level = _validate_confidence_level(confidence_level)
    selected_metrics = _validate_metric_names(metrics)

    equity_array = _as_array(equity_curve)
    if equity_array.size == 0:
        msg = "equity_curve must contain at least one observation"
        raise ValueError(msg)

    pnl_array = _as_array(pnl)
    position_array = _as_array(position_changes)

    returns = _compute_returns(equity_array, initial_capital)
    if returns.size == 0:
        msg = "Unable to infer returns from the supplied equity curve"
        raise ValueError(msg)

    rng = np.random.default_rng(random_state)

    baseline = compute_performance_metrics(
        equity_curve=equity_array,
        pnl=pnl_array if pnl_array.size else None,
        position_changes=position_array if position_array.size else None,
        initial_capital=float(initial_capital),
    )
    baseline_dict = baseline.as_dict()

    samples_by_metric = {
        name: np.full(num_resamples, np.nan, dtype=float) for name in selected_metrics
    }

    for index in range(num_resamples):
        chosen = rng.integers(0, returns.size, size=returns.size)
        sample_returns = returns[chosen]
        synthetic_equity = _equity_from_returns(sample_returns, initial_capital)

        synthetic_pnl = None
        if pnl_array.size:
            synthetic_pnl = pnl_array[chosen]

        synthetic_positions = None
        if position_array.size:
            synthetic_positions = position_array[chosen]

        report = compute_performance_metrics(
            equity_curve=synthetic_equity,
            pnl=synthetic_pnl,
            position_changes=synthetic_positions,
            initial_capital=float(initial_capital),
        )
        values = report.as_dict()

        for name in selected_metrics:
            value = values[name]
            samples_by_metric[name][index] = (
                float(value) if value is not None else np.nan
            )

    metrics_result: dict[str, ResampledMetric] = {}
    for name in selected_metrics:
        samples = samples_by_metric[name]
        ci_lower, ci_upper = _confidence_interval(samples, confidence_level)
        metrics_result[name] = ResampledMetric(
            name=name,
            point_estimate=baseline_dict.get(name),
            samples=samples,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
        )

    return ResamplingResult(
        method="bootstrap",
        confidence_level=confidence_level,
        metrics=metrics_result,
    )


def bayesian_mcmc_performance_metrics(
    *,
    equity_curve: Iterable[float] | NDArray[np.float64],
    initial_capital: float,
    pnl: Iterable[float] | NDArray[np.float64] | None = None,
    position_changes: Iterable[float] | NDArray[np.float64] | None = None,
    confidence_level: float = _DEFAULT_CONFIDENCE_LEVEL,
    num_samples: int = _DEFAULT_MCMC_SAMPLES,
    random_state: int | None = None,
    metrics: Sequence[str] | None = None,
    mu_prior: float = _DEFAULT_PRIOR_MU,
    kappa_prior: float = _DEFAULT_PRIOR_KAPPA,
    alpha_prior: float = _DEFAULT_PRIOR_ALPHA,
    beta_prior: float = _DEFAULT_PRIOR_BETA,
) -> ResamplingResult:
    """Approximate posterior distributions using a conjugate MCMC model.

    The implementation assumes that returns follow a Gaussian distribution with
    unknown mean and variance. Conjugate Normal-Inverse-Gamma priors are used to
    draw posterior samples which are then converted into synthetic equity
    trajectories for performance evaluation.
    """

    if num_samples <= 0:
        msg = "num_samples must be a positive integer"
        raise ValueError(msg)

    if kappa_prior <= 0.0:
        msg = "kappa_prior must be positive"
        raise ValueError(msg)
    if alpha_prior <= 0.0 or beta_prior <= 0.0:
        msg = "alpha_prior and beta_prior must be positive"
        raise ValueError(msg)

    confidence_level = _validate_confidence_level(confidence_level)
    selected_metrics = _validate_metric_names(metrics)

    equity_array = _as_array(equity_curve)
    if equity_array.size == 0:
        msg = "equity_curve must contain at least one observation"
        raise ValueError(msg)

    pnl_array = _as_array(pnl)
    position_array = _as_array(position_changes)

    returns = _compute_returns(equity_array, initial_capital)
    if returns.size == 0:
        msg = "Unable to infer returns from the supplied equity curve"
        raise ValueError(msg)

    rng = np.random.default_rng(random_state)

    baseline = compute_performance_metrics(
        equity_curve=equity_array,
        pnl=pnl_array if pnl_array.size else None,
        position_changes=position_array if position_array.size else None,
        initial_capital=float(initial_capital),
    )
    baseline_dict = baseline.as_dict()

    n_obs = returns.size
    sample_mean = float(np.mean(returns))
    squared_diff = float(np.sum((returns - sample_mean) ** 2))

    kappa_post = kappa_prior + n_obs
    mu_post = (kappa_prior * mu_prior + n_obs * sample_mean) / kappa_post
    alpha_post = alpha_prior + n_obs / 2.0
    beta_post = (
        beta_prior
        + 0.5 * squared_diff
        + (kappa_prior * n_obs * (sample_mean - mu_prior) ** 2) / (2.0 * kappa_post)
    )

    sigma_squared = 1.0 / rng.gamma(
        shape=alpha_post, scale=1.0 / beta_post, size=num_samples
    )
    sigma = np.sqrt(sigma_squared)
    mu_samples = rng.normal(loc=mu_post, scale=np.sqrt(sigma_squared / kappa_post))

    samples_by_metric = {
        name: np.full(num_samples, np.nan, dtype=float) for name in selected_metrics
    }

    for index in range(num_samples):
        simulated_returns = rng.normal(mu_samples[index], sigma[index], size=n_obs)
        synthetic_equity = _equity_from_returns(simulated_returns, initial_capital)

        report = compute_performance_metrics(
            equity_curve=synthetic_equity,
            pnl=pnl_array if pnl_array.size else None,
            position_changes=position_array if position_array.size else None,
            initial_capital=float(initial_capital),
        )
        values = report.as_dict()

        for name in selected_metrics:
            value = values[name]
            samples_by_metric[name][index] = (
                float(value) if value is not None else np.nan
            )

    metrics_result: dict[str, ResampledMetric] = {}
    for name in selected_metrics:
        samples = samples_by_metric[name]
        ci_lower, ci_upper = _confidence_interval(samples, confidence_level)
        metrics_result[name] = ResampledMetric(
            name=name,
            point_estimate=baseline_dict.get(name),
            samples=samples,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
        )

    return ResamplingResult(
        method="bayesian-mcmc",
        confidence_level=confidence_level,
        metrics=metrics_result,
    )


__all__ = [
    "ResampledMetric",
    "ResamplingResult",
    "bootstrap_performance_metrics",
    "bayesian_mcmc_performance_metrics",
]
