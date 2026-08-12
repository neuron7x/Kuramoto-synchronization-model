# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Occam penalty — AIC / BIC / MDL adjusters for the Adversarial Ladder.

Closes audit task 11. The Adversarial Baseline Ladder evaluates a
candidate's verdict-bearing metric (typically AUC, log-likelihood
or Sharpe ratio) against a roster of prosecutor models. A naïve
comparison rewards complex candidates that overfit; this module
ships three classic complexity penalties so a candidate must beat
its prosecutors *after* paying for its degrees of freedom.

Penalties
---------
* **AIC** — Akaike (1974). ``AIC = 2k - 2 log L``. Asymptotically
  optimal for prediction.
* **BIC** — Schwarz (1978). ``BIC = k log n - 2 log L``. Stronger
  penalty; asymptotically optimal for *model identification*.
* **MDL** — Minimum Description Length (Rissanen 1978). Equivalent
  to BIC up to ``O(1)``; ships an explicit two-part code form for
  the candidate / prosecutor pair.

API convention: each function takes ``log_likelihood`` (already
log-space, no ``log(0)`` corner cases) plus ``k`` (parameter count)
and ``n`` (effective sample size where applicable). All return the
**penalized log-likelihood** so larger = better and the comparison
``penalized_lhood(A) > penalized_lhood(B)`` means A wins.

Pure-function API.
"""

from __future__ import annotations

import math

__all__ = [
    "aic_penalized_log_likelihood",
    "bic_penalized_log_likelihood",
    "mdl_penalized_log_likelihood",
    "occam_winner",
]


def aic_penalized_log_likelihood(log_likelihood: float, *, k: int) -> float:
    """Penalized log-likelihood under AIC.

    Higher is better. Equivalent to ``log_likelihood - k`` since
    AIC = -2 (log L - k).
    """
    if k < 0:
        raise ValueError(f"k must be >= 0, got {k}")
    if not math.isfinite(log_likelihood):
        raise ValueError(f"log_likelihood must be finite, got {log_likelihood}")
    return float(log_likelihood) - float(k)


def bic_penalized_log_likelihood(log_likelihood: float, *, k: int, n: int) -> float:
    """Penalized log-likelihood under BIC.

    Higher is better. Equivalent to ``log_likelihood - 0.5 k log n``
    since BIC = -2 (log L - 0.5 k log n).
    """
    if k < 0:
        raise ValueError(f"k must be >= 0, got {k}")
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    if not math.isfinite(log_likelihood):
        raise ValueError(f"log_likelihood must be finite, got {log_likelihood}")
    return float(log_likelihood) - 0.5 * float(k) * math.log(float(n))


def mdl_penalized_log_likelihood(
    log_likelihood: float, *, k: int, n: int, c0: float = 0.0
) -> float:
    """Penalized log-likelihood under the MDL two-part code.

    Equivalent to BIC up to a model-class constant ``c0``:

        L_MDL = log_likelihood - 0.5 k log n - c0.

    The constant ``c0`` accounts for the cost of describing the
    *family* of models (e.g. linear-vs-nonlinear). Defaults to 0.
    """
    if not math.isfinite(c0):
        raise ValueError(f"c0 must be finite, got {c0}")
    return bic_penalized_log_likelihood(log_likelihood, k=k, n=n) - float(c0)


def occam_winner(
    *,
    candidate_log_lhood: float,
    candidate_k: int,
    prosecutor_log_lhood: float,
    prosecutor_k: int,
    n: int,
    method: str = "BIC",
) -> tuple[bool, float]:
    """Compare two models under an Occam penalty.

    Parameters
    ----------
    candidate_log_lhood, candidate_k
        Candidate's log-likelihood and parameter count.
    prosecutor_log_lhood, prosecutor_k
        Prosecutor's log-likelihood and parameter count.
    n
        Effective sample size for BIC / MDL. Ignored for AIC.
    method
        One of ``"AIC"``, ``"BIC"``, ``"MDL"``.

    Returns
    -------
    tuple[bool, float]
        ``(candidate_wins, margin)`` where ``margin`` is
        ``L_candidate - L_prosecutor`` after penalty. Positive
        margin → candidate wins.
    """
    method_upper = method.upper()
    if method_upper == "AIC":
        c = aic_penalized_log_likelihood(candidate_log_lhood, k=candidate_k)
        p = aic_penalized_log_likelihood(prosecutor_log_lhood, k=prosecutor_k)
    elif method_upper == "BIC":
        c = bic_penalized_log_likelihood(candidate_log_lhood, k=candidate_k, n=n)
        p = bic_penalized_log_likelihood(prosecutor_log_lhood, k=prosecutor_k, n=n)
    elif method_upper == "MDL":
        c = mdl_penalized_log_likelihood(candidate_log_lhood, k=candidate_k, n=n)
        p = mdl_penalized_log_likelihood(prosecutor_log_lhood, k=prosecutor_k, n=n)
    else:
        raise ValueError(f"unknown method {method!r}; expected one of AIC, BIC, MDL")
    margin = c - p
    return (margin > 0.0, float(margin))
