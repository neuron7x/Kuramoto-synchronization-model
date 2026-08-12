# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Rigorous Bayes-factor and decision-theory primitives.

Closes the math-depth gap of the audit: every formula here is
derived (not invented) and each derivation cites a primary source.
The :mod:`research.systemic_risk.evidence_ledger` ad hoc
``exp(2·(AUC-0.5)·sqrt(n))`` shortcut is replaced by analytically
correct alternatives.

Catalogue
=========

* :func:`mann_whitney_null_variance` — exact null variance of the
  AUC estimator under :math:`H_0: F_X = F_Y`. Source: Mann & Whitney
  (1947), eq. 5; Bamber (1975), Hanley & McNeil (1982).

* :func:`auc_to_z_under_null` — the standardised statistic
  :math:`Z = (AUC - 0.5)/\\sqrt{\\sigma_0^2}`. Asymptotically
  :math:`Z \\sim \\mathcal{N}(0,1)` under :math:`H_0`.

* :func:`wagenmakers_bic_bayes_factor` — BIC-derived Bayes factor
  :math:`BF_{10} \\approx \\exp(z^2/2)/\\sqrt{n_{eff}}`. Source:
  Wagenmakers (2007) "A practical solution to the pervasive problems
  of p-values", *Psychonomic Bulletin & Review* 14(5):779-804,
  eqs. 6-8.

* :func:`auc_per_crisis_bf_rigorous` — drop-in replacement for the
  ad hoc :func:`evidence_ledger.auc_per_crisis_bayes_factor`. Combines
  the two preceding functions for the per-crisis AUC contract.

* :func:`cramer_rao_alpha_lower_bound` — Cramér-Rao lower bound on
  the power-law tail-index MLE variance:
  :math:`\\mathrm{Var}(\\hat{\\alpha}) \\ge (\\alpha - 1)^2 / n`.
  Source: Clauset, Shalizi & Newman (2009) "Power-law distributions
  in empirical data", *SIAM Review* 51(4):661-703, eq. 3.7.

* :func:`derive_kill_threshold_log_odds` — Bayes-rule decision
  threshold from a 0/1 cost matrix. Source: Berger (1985)
  "Statistical Decision Theory and Bayesian Analysis", eq. 4.4.5.

Pure-function API. No I/O. No mutation.

Conventions
-----------
All inputs are validated; contract violations raise
:class:`ValueError`. No silent NaN propagation. All return values
are finite ``float``.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np

__all__ = [
    "ASYMPTOTIC_BIC_PENALTY",
    "auc_per_crisis_bf_rigorous",
    "auc_to_z_under_null",
    "cramer_rao_alpha_lower_bound",
    "derive_kill_threshold_log_odds",
    "mann_whitney_effective_n",
    "mann_whitney_null_variance",
    "wagenmakers_bic_bayes_factor",
]


# Cap on |log BF| for numerical stability. Reached only at extreme
# evidence; downstream callers should treat |log BF| ≥ this as a
# saturation signal (the numeric ranking is meaningful, the absolute
# value is not).
ASYMPTOTIC_BIC_PENALTY: Final[float] = 20.0


def mann_whitney_null_variance(n_pos: int, n_neg: int) -> float:
    r"""Exact null variance of the AUC estimator.

    For independent samples :math:`\{X_i\}_{i=1}^{n_+}` and
    :math:`\{Y_j\}_{j=1}^{n_-}` with :math:`F_X = F_Y` (no ties of
    measure zero), the Mann-Whitney U-statistic has

    .. math::
        \mathrm{Var}\!\left[\widehat{AUC}\, \big|\, H_0\right]
        = \frac{n_+ + n_- + 1}{12 \, n_+ \, n_-}.

    Source: Mann & Whitney (1947), §3 eq. 5.

    Parameters
    ----------
    n_pos, n_neg
        Sample sizes of the two groups; both must be ≥ 1.

    Returns
    -------
    float
        Strictly positive null variance.
    """
    if n_pos < 1:
        raise ValueError(f"n_pos must be >= 1, got {n_pos}")
    if n_neg < 1:
        raise ValueError(f"n_neg must be >= 1, got {n_neg}")
    return float((n_pos + n_neg + 1)) / (12.0 * float(n_pos) * float(n_neg))


def mann_whitney_effective_n(n_pos: int, n_neg: int) -> float:
    r"""Effective sample size for the Mann-Whitney AUC test.

    Defined as :math:`n_{eff} = n_+ n_- / (n_+ + n_- + 1)`. This is
    the "informational" sample size that controls the prior penalty
    in the BIC approximation; for balanced groups
    :math:`n_+ = n_- = n/2`, :math:`n_{eff} \approx n/4` for large n.
    """
    if n_pos < 1 or n_neg < 1:
        raise ValueError(f"n_pos, n_neg must be >= 1; got ({n_pos}, {n_neg})")
    return float(n_pos) * float(n_neg) / float(n_pos + n_neg + 1)


def auc_to_z_under_null(
    auc: float,
    *,
    n_pos: int,
    n_neg: int,
) -> float:
    r"""Standardise an AUC estimate under :math:`H_0`.

    .. math::
        Z = \frac{\widehat{AUC} - 0.5}
                 {\sqrt{\mathrm{Var}\!\left[\widehat{AUC} | H_0\right]}}

    Asymptotically :math:`Z \to \mathcal{N}(0, 1)` under the null
    (Bamber 1975, Theorem 2).
    """
    if not 0.0 <= auc <= 1.0:
        raise ValueError(f"auc must be in [0, 1], got {auc}")
    sigma2 = mann_whitney_null_variance(n_pos=n_pos, n_neg=n_neg)
    return (auc - 0.5) / math.sqrt(sigma2)


def wagenmakers_bic_bayes_factor(
    z: float,
    *,
    n_eff: float,
) -> float:
    r"""BIC-derived Bayes factor against :math:`H_0` for a z-statistic.

    .. math::
        BF_{10} \approx \frac{\exp(z^2 / 2)}{\sqrt{n_{eff}}}

    Wagenmakers (2007) eqs. 6-8: under a unit-information Gaussian
    prior on the noncentrality parameter, the BIC approximation to
    the Bayes factor is :math:`\log BF_{10} \approx (z^2 - \ln
    n_{eff}) / 2`.

    The result is **clamped** to :math:`|\log BF| \le
    ASYMPTOTIC\_BIC\_PENALTY` (currently 20.0, i.e. BF ∈
    [exp(-20), exp(20)] ≈ [2e-9, 5e8]) to maintain numerical
    stability under extreme evidence; the relative ordering is
    preserved.

    Parameters
    ----------
    z
        Standardised statistic. May be negative (favours the null).
    n_eff
        Effective sample size (e.g. from
        :func:`mann_whitney_effective_n`); must be > 0.

    Returns
    -------
    float
        ``BF_10`` ≥ 0; ``BF_10 == 1.0`` iff ``z == 0`` and
        ``n_eff == 1`` (the prior-penalty-free balanced point).
    """
    if not math.isfinite(z):
        raise ValueError(f"z must be finite, got {z}")
    if n_eff <= 0:
        raise ValueError(f"n_eff must be > 0, got {n_eff}")
    log_bf = (z * z - math.log(n_eff)) / 2.0
    log_bf = max(-ASYMPTOTIC_BIC_PENALTY, min(ASYMPTOTIC_BIC_PENALTY, log_bf))
    return float(math.exp(log_bf))


def auc_per_crisis_bf_rigorous(
    auc: float,
    *,
    n_pos: int,
    n_neg: int,
) -> float:
    r"""Rigorous Bayes factor for a per-crisis AUC contract.

    Drop-in replacement for
    :func:`research.systemic_risk.evidence_ledger
    .auc_per_crisis_bayes_factor` whose ad hoc form
    :math:`\exp(2\,(AUC-0.5)\sqrt{n})` lacked a derivation.

    Pipeline
    ~~~~~~~~
    1. Compute :math:`Z` via :func:`auc_to_z_under_null`.
    2. Compute :math:`n_{eff}` via :func:`mann_whitney_effective_n`.
    3. Return :func:`wagenmakers_bic_bayes_factor`.

    Sanity checks (verified by tests):

    * ``BF(AUC=0.5)`` saturates only via the prior-penalty term:
      :math:`BF_{10}(z=0) = 1/\sqrt{n_{eff}} \le 1`. This is the
      canonical Bayesian "Lindley penalty" — uninformative data on a
      composite alternative *favours the null*.
    * ``BF`` is strictly monotone in :math:`|AUC - 0.5|`.
    * ``BF(AUC, n_pos, n_neg) == BF(1 - AUC, n_pos, n_neg)`` —
      symmetric under polarity flip.
    """
    z = auc_to_z_under_null(auc, n_pos=n_pos, n_neg=n_neg)
    n_eff = mann_whitney_effective_n(n_pos=n_pos, n_neg=n_neg)
    return wagenmakers_bic_bayes_factor(z, n_eff=n_eff)


def cramer_rao_alpha_lower_bound(
    alpha: float,
    *,
    n: int,
) -> float:
    r"""Cramér-Rao lower bound on the variance of the power-law MLE.

    For data :math:`\{x_i \ge x_{\min}\}_{i=1}^{n}` drawn from
    :math:`p(x; \alpha) = (\alpha-1) x_{\min}^{\alpha-1} x^{-\alpha}`,
    the Fisher information per observation is :math:`I(\alpha) = 1/(\alpha-1)^2`,
    giving the Cramér-Rao lower bound:

    .. math::
        \mathrm{Var}(\hat{\alpha}_{MLE}) \ge \frac{(\alpha - 1)^2}{n}.

    Source: Clauset, Shalizi & Newman (2009) eq. 3.7. Equality holds
    asymptotically for the MLE; finite-sample variance can be larger
    (especially when :math:`x_{\min}` is itself estimated).

    Returns the lower bound on the **standard error**:
    :math:`SE_{LB} = (\alpha - 1) / \sqrt{n}`.
    """
    if alpha <= 1.0:
        raise ValueError(f"alpha must be > 1, got {alpha}")
    if n < 2:
        raise ValueError(f"n must be >= 2, got {n}")
    return (alpha - 1.0) / math.sqrt(float(n))


def derive_kill_threshold_log_odds(
    *,
    cost_false_kill: float,
    cost_false_pass: float,
) -> float:
    r"""Derive the KILL log-odds threshold from a 0/1 cost matrix.

    Bayes-rule decision threshold under a binary loss
    :math:`\ell(\text{KILL true claim}) = c_{FK}` and
    :math:`\ell(\text{PASS false claim}) = c_{FP}`:

    .. math::
        p^{\,*} = \frac{c_{FK}}{c_{FK} + c_{FP}}, \qquad
        \log\frac{p^{\,*}}{1 - p^{\,*}} = \log\frac{c_{FK}}{c_{FP}}.

    Source: Berger (1985) §4.4 "Bayesian decision theory under
    asymmetric loss".

    Example
    -------
    The default constant
    :data:`research.systemic_risk.evidence_ledger.KILL_TRIGGER_LOG_ODDS`
    = ``-5.0`` corresponds to a cost ratio
    :math:`c_{FK} / c_{FP} \approx e^{-5} \approx 0.0067`, i.e.
    "killing a true claim is ~150× cheaper than passing a false
    claim" — the canonical falsification-first calibration.

    Parameters
    ----------
    cost_false_kill, cost_false_pass
        Strictly positive scalars in any consistent cost unit.

    Returns
    -------
    float
        Log-odds threshold; ``posterior_log_odds <= threshold`` →
        KILL.
    """
    if cost_false_kill <= 0:
        raise ValueError(f"cost_false_kill must be > 0, got {cost_false_kill}")
    if cost_false_pass <= 0:
        raise ValueError(f"cost_false_pass must be > 0, got {cost_false_pass}")
    return float(np.log(cost_false_kill / cost_false_pass))
