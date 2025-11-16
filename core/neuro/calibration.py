"""Automated calibration system for Adaptive Market Mind (AMM) parameters.

This module provides random search-based hyperparameter optimization for the AMM
system. The calibration process evaluates candidate configurations based on a
composite score that balances precision magnitude with pulse-error correlation.

The calibrator explores key AMM parameters including:
- EMA span for forecasting
- Volatility decay rate
- Precision scaling (alpha)
- Entropy penalty (beta)
- Kuramoto and Ricci modulation gains
- Target burst rate (rho)

Key Components:
    CalibConfig: Search space bounds and iteration count
    CalibResult: Complete calibration outcome with best config and diagnostics
    calibrate_amm: Main calibration function using random search

The scoring function prioritizes configurations that achieve high precision
while maintaining strong correlation between prediction errors and the output
pulse signal. This ensures the AMM responds appropriately to forecast quality.

Example:
    >>> calib_cfg = CalibConfig(iters=100)
    >>> result = calibrate_amm(returns, R_series, kappa_series, calib_cfg)
    >>> print(f"Best score: {result.score:.3f}")
    >>> amm = AdaptiveMarketMind(result.config)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from .amm import AdaptiveMarketMind, AMMConfig

Float = np.float32


@dataclass
class CalibConfig:
    """Configuration controlling random calibration search bounds."""

    iters: int = 200
    seed: int = 7
    ema_span: tuple[int, int] = (8, 96)
    vol_lambda: tuple[float, float] = (0.86, 0.98)
    alpha: tuple[float, float] = (0.2, 5.0)
    beta: tuple[float, float] = (0.1, 2.0)
    lambda_sync: tuple[float, float] = (0.2, 1.2)
    eta_ricci: tuple[float, float] = (0.1, 1.0)
    rho: tuple[float, float] = (0.01, 0.12)


@dataclass
class CalibResult:
    """Structured outcome of the calibration routine."""

    config: AMMConfig
    score: float
    metrics: Mapping[str, float]


def _rand(
    rng: np.random.Generator, lo_hi: tuple[float, float], *, is_int: bool = False
) -> float | int:
    lo, hi = lo_hi
    if is_int:
        return int(rng.integers(lo, hi + 1))
    return float(rng.uniform(lo, hi))


def _evaluate_trace(
    S: np.ndarray, P: np.ndarray, PE: np.ndarray
) -> tuple[float, Mapping[str, float]] | None:
    """Compute the calibration score and diagnostics for a trace."""

    if len(S) < 2:
        return None

    precision = np.clip(P, 0.01, 100.0)
    mean_precision = float(np.mean(precision))
    if not np.isfinite(mean_precision) or mean_precision <= 0.0:
        return None

    pulse_std = float(np.std(S))
    pe_std = float(np.std(PE))
    if pulse_std <= 0.0 or pe_std <= 0.0:
        corr = 0.0
    else:
        cov = float(np.cov(PE, S, ddof=0)[0, 1])
        corr = cov / (pe_std * pulse_std)

    if not np.isfinite(corr):
        return None

    precision_std = float(np.std(precision))
    score = corr * mean_precision
    metrics: dict[str, float] = {
        "corr": float(corr),
        "mean_precision": mean_precision,
        "precision_std": precision_std,
        "pulse_std": pulse_std,
        "pe_std": pe_std,
        "score": float(score),
    }
    return float(score), metrics


def calibrate_random(
    x: np.ndarray,
    R: np.ndarray,
    kappa: np.ndarray,
    cfg: CalibConfig,
    *,
    return_details: bool = False,
) -> AMMConfig | CalibResult:
    """Random search over :class:`AMMConfig` parameter space.

    Parameters
    ----------
    x, R, kappa:
        Historical traces that drive the AMM simulation.
    cfg:
        Configuration describing the search bounds.
    return_details:
        If ``True`` the structured :class:`CalibResult` is returned instead of the
        bare configuration.
    """

    rng = np.random.default_rng(cfg.seed)
    best_result: CalibResult | None = None
    best_config: AMMConfig | None = None
    for _ in range(cfg.iters):
        c = AMMConfig(
            ema_span=_rand(rng, cfg.ema_span, is_int=True),
            vol_lambda=_rand(rng, cfg.vol_lambda),
            alpha=_rand(rng, cfg.alpha),
            beta=_rand(rng, cfg.beta),
            lambda_sync=_rand(rng, cfg.lambda_sync),
            eta_ricci=_rand(rng, cfg.eta_ricci),
            rho=_rand(rng, cfg.rho),
        )
        amm = AdaptiveMarketMind(c)
        S, P, PE = [], [], []
        for i in range(len(x)):
            o = amm.update(float(x[i]), float(R[i]), float(kappa[i]), None)
            S.append(o["amm_pulse"])
            P.append(o["amm_precision"])
            PE.append(abs(o["pe"]))
        S = np.asarray(S, dtype=Float)
        P = np.asarray(P, dtype=Float)
        PE = np.asarray(PE, dtype=Float)
        evaluated = _evaluate_trace(S, P, PE)
        if evaluated is None:
            continue
        score, metrics = evaluated
        if best_result is None or score > best_result.score:
            best_result = CalibResult(config=c, score=score, metrics=metrics)
            best_config = c

    if return_details:
        if best_result is None:
            return CalibResult(config=AMMConfig(), score=float("nan"), metrics={})
        return best_result

    return best_config if best_config is not None else AMMConfig()
