# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Critical-slowing-down (CSD) indicators on a univariate score series.

Conservative, leakage-safe, configurable. Built to make the
candidate signal *fail* unless it really survives — not to look
impressive on a single in-sample run.

Three trailing-window statistics from the early-warning literature
(Scheffer et al. 2009, *Nature* **461**: 53; Dakos et al. 2012,
*PLoS ONE* **7**: e41010):

* **Variance** — sample variance over the trailing window.
* **Lag-1 autocorrelation** — Pearson correlation between the
  window and itself shifted by ``config.lag``. Constant-segment
  policy is explicit: NaN / zero / raise (default NaN).
* **Skewness** — population third standardised moment
  ``m3 / m2**1.5``. Implemented inline (no SciPy dependency).

**No lookahead.** ``indicator[t]`` is computed from
``series[t - window + 1 : t + 1]`` only. A regression test under
``test_critical_slowing_down.py::test_no_lookahead_leakage``
mutates a future segment and asserts the past indicator slice is
bit-identical.

Pure-function API. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "ConstantPolicy",
    "CSDConfig",
    "CSDIndicators",
    "compute_csd_indicators",
]


ConstantPolicy = Literal["nan", "zero", "raise"]


@dataclass(frozen=True, slots=True)
class CSDConfig:
    """Pre-registered CSD hyperparameters.

    Attributes
    ----------
    window
        Trailing-window length (>= 3).
    min_periods
        Minimum number of observations in the window for an
        indicator to be defined (>= 3, <= ``window``).
    ddof
        Delta degrees of freedom for the variance estimator.
        Default 1 (unbiased sample variance).
    lag
        Lag for the autocorrelation. Default 1.
    constant_policy
        Behaviour when the rolling window has zero variance and
        the autocorrelation / skewness is mathematically
        undefined:

        * ``"nan"`` (default) — emit NaN. Recommended for research:
          a NaN propagates honestly and forces the consumer to
          handle the degenerate window.
        * ``"zero"`` — emit ``0.0``. Convenient for downstream code
          that can tolerate a constant null but loses signal of
          degeneracy.
        * ``"raise"`` — fail-closed via :class:`ValueError` at the
          first degenerate window.
    """

    window: int
    min_periods: int
    ddof: int = 1
    lag: int = 1
    constant_policy: ConstantPolicy = "nan"

    def __post_init__(self) -> None:
        if self.window < 3:
            raise ValueError(f"window must be >= 3, got {self.window}")
        if self.min_periods < 3:
            raise ValueError(f"min_periods must be >= 3, got {self.min_periods}")
        if self.min_periods > self.window:
            raise ValueError(f"min_periods ({self.min_periods}) must be <= window ({self.window})")
        if self.lag < 1:
            raise ValueError(f"lag must be >= 1, got {self.lag}")
        if self.lag >= self.min_periods:
            raise ValueError(f"lag ({self.lag}) must be < min_periods ({self.min_periods})")
        if self.ddof < 0:
            raise ValueError(f"ddof must be >= 0, got {self.ddof}")
        if self.ddof >= self.min_periods:
            # bounds: rolling variance / std at the smallest evaluated
            # window must have ≥ 1 degree of freedom; otherwise the
            # estimator is undefined and emits silent NaN/RuntimeWarning.
            raise ValueError(
                f"ddof ({self.ddof}) must be < min_periods "
                f"({self.min_periods}) so the rolling variance is "
                f"defined at the first evaluated window"
            )


@dataclass(frozen=True, slots=True)
class CSDIndicators:
    """Time-resolved CSD indicator series.

    Every output array has length equal to the input series. The
    leading positions where the window is insufficient are NaN; the
    ``valid_count`` array reports the per-time-step number of
    observations actually used.
    """

    variance: NDArray[np.float64]
    lag1_autocorr: NDArray[np.float64]
    skewness: NDArray[np.float64]
    valid_count: NDArray[np.int64]
    config: CSDConfig


def _validate(values: NDArray[np.float64]) -> NDArray[np.float64]:
    v = np.asarray(values, dtype=np.float64)
    if v.ndim != 1:
        raise ValueError(f"series must be 1-D, got shape={v.shape}")
    if v.size == 0:
        raise ValueError("series must be non-empty")
    if not np.isfinite(v).all():
        # Any internal NaN/Inf fails closed; the leakage contract
        # requires the caller to handle missingness explicitly
        # before invoking the indicators.
        raise ValueError("series must be finite (no NaN/Inf)")
    return v


def _apply_constant_policy(config: CSDConfig, where: str) -> float:
    if config.constant_policy == "nan":
        return float("nan")
    if config.constant_policy == "zero":
        return 0.0
    if config.constant_policy == "raise":
        raise ValueError(
            f"degenerate window encountered ({where}); "
            f"constant_policy='raise' is fail-closed by contract"
        )
    raise ValueError(f"unknown constant_policy: {config.constant_policy!r}")


def compute_csd_indicators(
    series: NDArray[np.float64],
    config: CSDConfig,
) -> CSDIndicators:
    """Compute variance / lag-k autocorrelation / skewness on a 1-D series.

    No lookahead by construction: the value at index ``t`` uses
    only ``series[t - window + 1 : t + 1]`` (clipped at the start).
    """
    v = _validate(series)
    n = v.size
    variance = np.full(n, np.nan, dtype=np.float64)
    lag1 = np.full(n, np.nan, dtype=np.float64)
    skew = np.full(n, np.nan, dtype=np.float64)
    valid = np.zeros(n, dtype=np.int64)
    w = config.window
    for t in range(n):
        start = max(0, t - w + 1)
        seg = v[start : t + 1]
        valid[t] = seg.size
        if seg.size < config.min_periods:
            continue
        # Variance.
        # bounds: ddof=config.ddof per CSDConfig contract.
        variance[t] = float(seg.var(ddof=config.ddof))
        # Skewness.
        mean = float(seg.mean())
        centred = seg - mean
        m2 = float((centred**2).mean())
        m3 = float((centred**3).mean())
        if m2 <= 0.0:
            skew[t] = _apply_constant_policy(config, where=f"skewness@t={t}")
        else:
            skew[t] = m3 / (m2**1.5)
        # Lag-k autocorrelation.
        if seg.size <= config.lag:
            continue
        x = seg[: -config.lag]
        y = seg[config.lag :]
        x_std = float(x.std(ddof=config.ddof))
        y_std = float(y.std(ddof=config.ddof))
        if x_std <= 0.0 or y_std <= 0.0:
            lag1[t] = _apply_constant_policy(config, where=f"lag1_autocorr@t={t}")
            continue
        cov = float(((x - x.mean()) * (y - y.mean())).mean())
        # Convert population covariance to sample covariance
        # consistent with x_std / y_std at ddof=config.ddof.
        adj = x.size / max(x.size - config.ddof, 1)
        lag1[t] = (cov / (x_std * y_std)) * adj
    return CSDIndicators(
        variance=variance,
        lag1_autocorr=lag1,
        skewness=skew,
        valid_count=valid,
        config=config,
    )
