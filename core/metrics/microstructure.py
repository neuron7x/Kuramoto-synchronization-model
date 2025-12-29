# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Market microstructure metrics for order flow analysis and price formation.

Mathematical Foundation:
    Market microstructure studies the process of price formation in financial markets,
    focusing on the interaction between order flow, liquidity, and price dynamics.

Queue Imbalance:
    Measures the relative supply/demand pressure in the order book:

        QI = (V_bid - V_ask) / (V_bid + V_ask) ∈ [-1, 1]

    where V_bid and V_ask are total volumes at bid and ask sides.

    Interpretation:
        QI = +1: All volume on bid side (strong buying pressure)
        QI =  0: Balanced book
        QI = -1: All volume on ask side (strong selling pressure)

    Empirical properties:
        - |QI| > 0.3: Significant imbalance, potential price movement
        - Sign(QI) often leads short-term price changes
        - Autocorrelation in QI indicates persistent order flow

Kyle's Lambda (Price Impact Coefficient):
    Measures the permanent price impact per unit of signed volume:

        λ = cov(r, q) / var(q)

    where:
        r = price returns (Δp/p)
        q = signed volume (positive for buys, negative for sells)

    Estimated via OLS regression:
        r_t = λ·q_t + ε_t

    Economic Interpretation:
        λ > 0: Positive price impact (informed trading)
        λ ≈ 0: No price impact (noise trading)
        |λ|: Measure of market depth and liquidity
        - High |λ|: Illiquid market, high price impact
        - Low |λ|: Liquid market, low price impact

    Typical values:
        - Large-cap stocks: λ ~ 10⁻⁷ to 10⁻⁵
        - Small-cap stocks: λ ~ 10⁻⁵ to 10⁻³
        - Cryptocurrencies: λ ~ 10⁻⁴ to 10⁻²

Hasbrouck's Information Content:
    Measures the correlation between price innovation and signed order flow:

        ρ = corr(r, sgn(q)·√|q|)

    where the signed square-root transformation reduces impact of outliers.

    Interpretation:
        ρ → +1: High information content (informed trading)
        ρ → 0: Low information content (noise trading)
        ρ < 0: Contrarian/liquidity provision

    Properties:
        - Normalized to [-1, 1] for comparability across assets
        - Robust to extreme volumes due to √ transformation
        - Scale-invariant (independent of price units)

References:
    - Kyle, A. S. (1985). Continuous auctions and insider trading.
      Econometrica, 53(6), 1315-1335.
    - Hasbrouck, J. (1991). Measuring the information content of stock trades.
      The Journal of Finance, 46(1), 179-207.
    - Glosten, L. R., & Milgrom, P. R. (1985). Bid, ask and transaction prices
      in a specialist market with heterogeneously informed traders.
      Journal of Financial Economics, 14(1), 71-100.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np
import pandas as pd


def queue_imbalance(bid_sizes: Sequence[float], ask_sizes: Sequence[float]) -> float:
    """Compute the queue imbalance metric for order book analysis.

    Mathematical Definition:
        The queue imbalance quantifies the relative supply/demand pressure:

            QI = (V_bid - V_ask) / (V_bid + V_ask)

        where:
            V_bid = ∑ᵢ bid_sizes[i]  (total bid-side volume)
            V_ask = ∑ᵢ ask_sizes[i]  (total ask-side volume)

    Interpretation:
        QI ∈ [-1, 1]:
            QI = +1: All volume on bid side (maximum buying pressure)
            QI > +0.3: Strong buying pressure, upward price pressure
            QI ∈ [-0.3, +0.3]: Balanced order book
            QI < -0.3: Strong selling pressure, downward price pressure
            QI = -1: All volume on ask side (maximum selling pressure)

    Applications:
        - Short-term price direction prediction
        - Liquidity assessment
        - Market making strategies
        - Trade execution timing

    Parameters
    ----------
    bid_sizes, ask_sizes:
        Sequences of resting volume at the bid and ask. The function accepts
        either level aggregates or individual order sizes. Negative values are
        clipped to zero before computation.

    Returns
    -------
    float: Queue imbalance QI ∈ [-1, 1]. Returns 0.0 if total volume is zero.

    Complexity:
        Time: O(N + M) where N, M are lengths of bid_sizes, ask_sizes
        Space: O(1)

    Examples:
        >>> # Balanced book
        >>> qi = queue_imbalance([100, 50, 30], [100, 50, 30])
        >>> assert abs(qi) < 0.01

        >>> # Buy-side pressure
        >>> qi = queue_imbalance([200, 100], [50, 30])
        >>> assert qi > 0.5  # Strong buy pressure

        >>> # Sell-side pressure
        >>> qi = queue_imbalance([30, 20], [150, 100])
        >>> assert qi < -0.5  # Strong sell pressure

    References:
        - Cont, R., et al. (2014). The price impact of order book events.
          Journal of Financial Econometrics, 12(1), 47-88.
        - Cartea, Á., et al. (2015). Algorithmic and High-Frequency Trading. Cambridge.
    """

    bid_total = float(np.sum(np.clip(bid_sizes, a_min=0.0, a_max=None)))
    ask_total = float(np.sum(np.clip(ask_sizes, a_min=0.0, a_max=None)))
    denom = bid_total + ask_total
    if denom <= 0.0:
        return 0.0
    return (bid_total - ask_total) / denom


def kyles_lambda(returns: Sequence[float], signed_volume: Sequence[float]) -> float:
    """Estimate Kyle's lambda (price impact coefficient) using least squares regression.

    Mathematical Foundation:
        Kyle's lambda measures the permanent price impact per unit of signed order flow.
        From Kyle's (1985) market microstructure model:

            r_t = λ·q_t + ε_t

        where:
            r_t = price return at time t
            q_t = signed volume (buy volume - sell volume)
            λ = Kyle's lambda (price impact coefficient)
            ε_t = noise term

        The OLS estimator for λ is:

            λ̂ = cov(r, q) / var(q) = E[(r - r̄)(q - q̄)] / E[(q - q̄)²]

    Economic Interpretation:
        λ represents the cost of trading per unit volume:
        - λ > 0: Informed trading → buys push price up, sells push down
        - λ ≈ 0: Uninformed/noise trading → no systematic price impact
        - |λ|: Inverse measure of market depth/liquidity
          * High |λ|: Shallow market, high price impact
          * Low |λ|: Deep market, low price impact

    Market Regimes by λ:
        - Ultra-liquid (Large-cap): λ ~ 10⁻⁷ to 10⁻⁵
        - Liquid (Mid-cap): λ ~ 10⁻⁵ to 10⁻⁴
        - Moderate liquidity: λ ~ 10⁻⁴ to 10⁻³
        - Illiquid (Small-cap): λ ~ 10⁻³ to 10⁻²
        - Very illiquid: λ > 10⁻²

    Parameters
    ----------
    returns : Sequence[float]
        Time series of price returns (typically log returns or percentage changes).
    signed_volume : Sequence[float]
        Signed volume series where positive indicates buying and negative indicates selling.

    Returns
    -------
    float: Estimated Kyle's lambda λ̂. Returns 0.0 if:
        - Insufficient data
        - Volume variance is zero (no trading activity)
        - Non-finite values encountered

    Numerical Stability:
        - Mean-centering prevents numerical issues with large absolute values
        - NaN/Inf filtering ensures robustness
        - Division-by-zero check on denominator

    Complexity:
        Time: O(N) where N = len(returns)
        Space: O(N) for filtered arrays

    Examples:
        >>> # Informed trading (positive impact)
        >>> returns = [0.01, -0.02, 0.015, -0.01, 0.005]
        >>> volume = [1000, -1500, 1200, -800, 500]
        >>> lam = kyles_lambda(returns, volume)
        >>> assert lam > 0  # Positive price impact

        >>> # No impact (noise trading)
        >>> returns = np.random.randn(1000) * 0.001
        >>> volume = np.random.randn(1000) * 1000
        >>> lam = kyles_lambda(returns, volume)
        >>> assert abs(lam) < 1e-6  # Near-zero impact

    References:
        - Kyle, A. S. (1985). Continuous auctions and insider trading.
          Econometrica, 53(6), 1315-1335.
        - Hasbrouck, J. (2007). Empirical Market Microstructure. Oxford.
        - Glosten, L. R., & Harris, L. E. (1988). Estimating the components of
          the bid-ask spread. Journal of Financial Economics, 21(1), 123-142.
    """

    r = np.asarray(list(returns), dtype=float)
    q = np.asarray(list(signed_volume), dtype=float)
    mask = np.isfinite(r) & np.isfinite(q)
    r = r[mask]
    q = q[mask]
    if r.size == 0 or q.size == 0:
        return 0.0
    if np.allclose(q, 0.0):
        return 0.0
    q = q - np.mean(q)
    r = r - np.mean(r)
    denom = np.dot(q, q)
    if denom <= 0.0:
        return 0.0
    return float(np.dot(q, r) / denom)


def hasbrouck_information_impulse(
    returns: Sequence[float], signed_volume: Sequence[float]
) -> float:
    """Estimate Hasbrouck's information content using signed square-root volume.

    The statistic is effectively the correlation between centered returns and the
    signed square-root of volume.  Normalizing by the Euclidean norms of both
    series makes the measure invariant to affine transformations (shifts and
    rescaling) of the input data, which is desirable for downstream property
    tests that compare relative information content rather than absolute
    magnitudes.
    """

    r = np.asarray(list(returns), dtype=float)
    q = np.asarray(list(signed_volume), dtype=float)
    mask = np.isfinite(r) & np.isfinite(q)
    r = r[mask]
    q = q[mask]
    if r.size == 0 or q.size == 0:
        return 0.0
    q = q - np.mean(q)
    transformed = np.sign(q) * np.sqrt(np.abs(q))
    transformed = transformed - np.mean(transformed)
    r = r - np.mean(r)
    norm_transformed = float(np.linalg.norm(transformed))
    norm_returns = float(np.linalg.norm(r))
    if norm_transformed == 0.0 or norm_returns == 0.0:
        return 0.0
    return float(np.dot(transformed, r) / (norm_transformed * norm_returns))


@dataclass(slots=True)
class MicrostructureReport:
    """Container for per-symbol microstructure metrics."""

    symbol: str
    samples: int
    avg_queue_imbalance: float
    kyles_lambda: float
    hasbrouck_impulse: float


def build_symbol_microstructure_report(
    frame: pd.DataFrame,
    *,
    symbol_col: str = "symbol",
    bid_col: str = "bid_volume",
    ask_col: str = "ask_volume",
    returns_col: str = "returns",
    signed_volume_col: str = "signed_volume",
) -> pd.DataFrame:
    """Generate a per-symbol report of the microstructure metrics."""

    required = {symbol_col, bid_col, ask_col, returns_col, signed_volume_col}
    missing = required - set(frame.columns)
    if missing:
        raise KeyError(f"Missing columns for microstructure report: {sorted(missing)}")

    grouped = frame.groupby(symbol_col, sort=True)
    rows = []
    for symbol, group in grouped:
        qi = queue_imbalance(group[bid_col].to_numpy(), group[ask_col].to_numpy())
        k_lambda = kyles_lambda(
            group[returns_col].to_numpy(), group[signed_volume_col].to_numpy()
        )
        impulse = hasbrouck_information_impulse(
            group[returns_col].to_numpy(), group[signed_volume_col].to_numpy()
        )
        rows.append(
            MicrostructureReport(
                symbol=str(symbol),
                samples=int(len(group)),
                avg_queue_imbalance=float(qi),
                kyles_lambda=float(k_lambda),
                hasbrouck_impulse=float(impulse),
            )
        )

    return pd.DataFrame([asdict(row) for row in rows])


__all__ = [
    "MicrostructureReport",
    "build_symbol_microstructure_report",
    "hasbrouck_information_impulse",
    "kyles_lambda",
    "queue_imbalance",
]
