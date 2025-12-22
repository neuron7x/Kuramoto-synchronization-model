"""Risk homeostasis module with VaR/ES and Kelly fraction sizing.

This module implements tail risk measurement (VaR/ES) and Kelly criterion
position sizing with regime-aware shrinkage.
"""

from __future__ import annotations

import os
from typing import Literal

import numpy as np

__all__ = ["var_es", "kelly_shrink", "compute_final_size", "RiskConfig"]


class RiskConfig:
    """Risk configuration parameters.

    Parameters
    ----------
    es_limit : float, optional
        Maximum allowed Expected Shortfall, loaded from TP_ES_LIMIT env var
    var_alpha : float, optional
        Confidence level for VaR/ES, loaded from TP_VAR_ALPHA env var
    f_max : float, optional
        Maximum Kelly fraction, loaded from TP_FMAX env var
    """

    def __init__(
        self,
        es_limit: float | None = None,
        var_alpha: float | None = None,
        f_max: float | None = None,
    ):
        self.es_limit = (
            float(os.getenv("TP_ES_LIMIT", "0.03"))
            if es_limit is None
            else float(es_limit)
        )
        self.var_alpha = (
            float(os.getenv("TP_VAR_ALPHA", "0.975"))
            if var_alpha is None
            else float(var_alpha)
        )
        self.f_max = (
            float(os.getenv("TP_FMAX", "1.0")) if f_max is None else float(f_max)
        )


def var_es(returns: np.ndarray, alpha: float = 0.975) -> tuple[float, float]:
    """Compute Value at Risk and Expected Shortfall.

    Parameters
    ----------
    returns : np.ndarray
        Array of returns
    alpha : float, optional
        Confidence level, by default 0.975 (97.5%)

    Returns
    -------
    tuple[float, float]
        (VaR, ES) at the specified confidence level

    Notes
    -----
    We compute VaR/ES on losses (L = -r) so positive values indicate losses.
    """
    returns_array = np.asarray(returns, dtype=float)
    finite_returns = returns_array[np.isfinite(returns_array)]

    if len(finite_returns) == 0:
        return 0.0, 0.0

    # Convert to losses (negative returns)
    losses = -finite_returns

    # VaR is the alpha-quantile of losses
    var = float(np.quantile(losses, alpha))

    # ES is the mean of losses beyond VaR
    tail_losses = losses[losses >= var]
    if len(tail_losses) > 0:
        es = float(np.mean(tail_losses))
    else:
        es = var

    return var, es


def kelly_shrink(
    mu: float,
    sigma2: float,
    ews_level: Literal["KILL", "CAUTION", "EMERGENT"],
    f_max: float = 1.0,
) -> float:
    """Compute Kelly fraction with regime-aware shrinkage.

    Parameters
    ----------
    mu : float
        Expected return
    sigma2 : float
        Variance of returns
    ews_level : Literal["KILL", "CAUTION", "EMERGENT"]
        Early warning system state
    f_max : float, optional
        Maximum allowed fraction, by default 1.0

    Returns
    -------
    float
        Kelly fraction scaled by regime

    Notes
    -----
    Kelly formula: f = μ / σ²
    Regime scaling: λ = {0 for KILL, 0.5 for CAUTION, 1 for EMERGENT}
    Final: f = λ * min(f_max, f_raw)
    """
    if sigma2 <= 0:
        return 0.0

    # Raw Kelly fraction
    f_raw = mu / sigma2

    # Regime-based shrinkage
    lambda_map = {
        "KILL": 0.0,
        "CAUTION": 0.5,
        "EMERGENT": 1.0,
    }
    lambda_factor = lambda_map.get(ews_level, 0.5)

    # Apply shrinkage and cap
    f = lambda_factor * min(f_max, max(0.0, f_raw))

    return float(f)


def compute_final_size(
    size_hint: float,
    kelly_fraction: float,
    f_max: float = 1.0,
) -> float:
    """Compute final position size.

    Parameters
    ----------
    size_hint : float
        Size hint from policy (0-1)
    kelly_fraction : float
        Kelly fraction from risk homeostasis
    f_max : float, optional
        Maximum allowed fraction, by default 1.0

    Returns
    -------
    float
        Final position size = size_hint * kelly_fraction, clipped to [0, f_max]
    """
    size = size_hint * kelly_fraction
    size = max(0.0, min(f_max, size))
    return float(size)


def check_risk_breach(es: float, es_limit: float) -> Literal["OK", "BREACH"]:
    """Check if Expected Shortfall breaches limit.

    Parameters
    ----------
    es : float
        Current Expected Shortfall
    es_limit : float
        Maximum allowed ES

    Returns
    -------
    Literal["OK", "BREACH"]
        Risk state
    """
    if not np.isfinite(es):
        return "BREACH"
    return "BREACH" if es > es_limit else "OK"
