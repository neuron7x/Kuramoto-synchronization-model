# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T5 — Tsallis entropy as real-time risk gate, MLE-fitted and GoF-gated.

The Tsallis entropic index ``q`` is estimated from the distribution of
portfolio returns over a rolling window. The estimator and the gate are
split into two provenance tiers:

* **The fit is ANCHORED.** ``q`` is obtained by maximum-likelihood — not
  by moment-matching. We exploit the exact algebraic equivalence between
  the q-Gaussian and the Student-t distribution: a q-Gaussian with index
  ``q`` is, up to scale, a Student-t with ``ν = (3 − q) / (q − 1)`` degrees
  of freedom, equivalently ``q = (ν + 3) / (ν + 1)`` (Tsallis 2009,
  Ch. 4; Souza & Tsallis 1997). We MLE-fit ``ν`` by maximising the
  Student-t log-likelihood of the standardised sample (a bounded 1-D
  optimisation) and map it to ``q ∈ [1, 3)``. This is numerically stable
  in the heavy-tail regime ``q ≥ 1.4`` (ν ≤ 5) where the 4th moment — and
  therefore any kurtosis-based estimator — diverges. The legacy
  kurtosis-q closed form is retained ONLY as a reported diagnostic, never
  as the estimator.

* **The regime cutoffs are EXTRAPOLATED.** ``q_normal = 1.35`` and
  ``q_crisis = 1.55`` are operational thresholds sourced from the
  qualitative q-Gaussian finance literature (Borland 2002; Queirós 2005;
  Tsallis 2009). They are NOT fitted constants and carry no per-asset
  calibration proof here. They are operational parameters of the gate,
  documented as such, and are overridable via the constructor.

Goodness-of-fit, fail-closed
----------------------------
A sample that is not a q-Gaussian (bimodal, strongly skewed, regime-mixed)
must NOT be assigned a confident q-derived regime. After fitting we compute
the Kolmogorov-Smirnov statistic of the standardised sample against the
fitted Student-t CDF and its p-value. If ``p < gof_alpha`` the fit is
rejected and ``evaluate`` returns the SAME conservative result used for the
data-scarcity branch (q = 1.5, ELEVATED, multiplier 0.25) with
``gof_passed = False``. We never emit a confident regime from an unfitted
sample.

Small-N MLE escape, fail-closed (one-directional)
--------------------------------------------------
``scipy.stats.t.fit`` ESCAPES to the Gaussian limit on genuine heavy-tailed
samples at small N: the unbounded ν MLE returns ν ≳ 1e11 (clamped to
``_NU_MAX``) ⟹ q ≈ 1.01 ⟹ NORMAL / full position. The KS GoF has too little
power at small N to reject this, so a pre-crisis heavy tail would be sized at
FULL exposure — a fail-OPEN in the dangerous direction. Measured on genuine
t(ν=5) at the default window N=60: 16% of seeds escape to the Gaussian limit.
A sample-size trust floor closes this, DEMOTE-ONLY (it can only make a read
MORE conservative, never less): below ``n_mle_trust`` (default
``_N_MLE_TRUST`` = 300, the smallest N at which the measured escape rate
reaches 0%) a near-Gaussian (low-q) read cannot grant full position and is
demoted to the conservative fallback. The sample size is the operative guard
because the escape flag (``nu_fit > _NU_ESCAPE``) cannot itself distinguish a
genuine Gaussian — which also drives ν→∞ at any N — from a heavy-tail escape;
that distinction is purely a function of N. The escape flag is therefore kept
only as a diagnostic. The guard fires only when the candidate sizing is more
generous than the conservative fallback. A confident CRISIS read (high q,
multiplier < 0.25) is NEVER weakened — cutting exposure on a resolved heavy
tail is the safe direction and is preserved at ANY N.

Position sizing gate (operational, EXTRAPOLATED cutoffs):
    f(q) = max(0, 1 - (q - q_normal) / (q_crisis - q_normal))  # INV-FE2

    q ≤ q_normal → f = 1.0 (full position)
    midway       → f = 0.5
    q ≥ q_crisis → f = 0.0 (no new positions)

Empirical regime bands (operational cutoffs, EXTRAPOLATED):
    q < 1.35         →  NORMAL regime
    1.35 ≤ q < 1.55  →  ELEVATED risk
    q ≥ 1.55         →  CRISIS regime

References:
    Tsallis "Introduction to Nonextensive Statistical Mechanics" (2009)
    Souza & Tsallis "Student's t- and r-distributions: Unified
        derivation from an entropic variational principle" Physica A (1997)
    Borland "A theory of non-Gaussian option pricing" Quant. Finance (2002)
    Queirós "On the emergence of a generalised Gamma distribution" EPL (2005)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
from numpy.typing import NDArray
from scipy import stats

# Student-t degrees-of-freedom search bounds for the MLE.
# ν → ∞ is the Gaussian limit (q → 1); ν = 1 is Cauchy (q = 2). We cap
# the lower end at 2.05 so that the variance (and hence the standardising
# step that precedes the fit) stays finite, and the upper end at 200 where
# the t-distribution is Gaussian to ~1e-3 in q. These are search bounds for
# the optimiser, not physics clamps; they bracket q ∈ (1.0, 1.66] from the
# tail-heaviness the data can actually support.
_NU_MIN = 2.05
_NU_MAX = 200.0

# Optimiser-escape detector. scipy.stats.t.fit on a small heavy-tailed
# sample frequently ESCAPES to the Gaussian limit: the unbounded ν MLE
# returns ν ≳ 1e11, which clamps to _NU_MAX and reads as a confident
# q ≈ 1.01 (NORMAL / full position). That is a fail-OPEN: a genuine
# pre-crisis heavy tail would be sized at full exposure. Any fit whose
# UNCLAMPED ν exceeds this escape threshold is treated as "tail not
# resolvable at this sample size", NOT as a confident Gaussian.
# INV-HPC2 / fail-closed: 1e4 sits far above any ν the t-family supports
# as a real heavy/medium tail (ν=1e4 ⟹ q−1 ≈ 2e-4, indistinguishable from
# Gaussian) yet far below the ~1e11 escape values, so it never demotes a
# real fit, only a degenerate escape.
_NU_ESCAPE = 1.0e4

# Minimum sample size for the MLE to be TRUSTED to grant the NORMAL /
# full-position (low-q) verdict. Derived from the escape analysis on
# genuine Student-t(ν=5) samples (the boundary heavy tail q≈1.333):
#   N=60 → 16% escape, N=100 → 7%, N=150 → 4.5%, N=200 → 1.5%,
#   N=250 → 0.5%, N≥300 → 0%  (200 seeds/point, nu_fit > 1e4).
# Below this floor the small-N MLE cannot reliably resolve a heavy tail
# from a Gaussian (the optimiser escapes to the Gaussian limit and reads
# as q≈1 / full position — a fail-OPEN), so a near-Gaussian (low-q) result
# is NOT trustworthy and must NOT grant full position. We pick 300, the
# knee where the measured escape rate reaches 0% — i.e. the smallest N at
# which a "this is a Gaussian / low-q" read is trustworthy enough to size
# at full exposure. This floor is the SOLE operative guard and is
# one-directional: it only DEMOTES an over-confident NORMAL/full read to
# the conservative fallback. A confident CRISIS (high-q) read is preserved
# at ANY N (cutting exposure on a heavy tail is the SAFE direction).
# NOTE on _NU_ESCAPE: a TRUE Gaussian legitimately drives ν→∞ at any N, so
# the escape flag alone cannot distinguish "genuine Gaussian" from "heavy
# tail that escaped"; that distinction is purely a function of N. Hence the
# escape flag is retained only as a diagnostic and the N floor does the
# gating. INV-HPC2 / fail-closed; cf. acceptor tsallis-qmle-gof analysis.
_N_MLE_TRUST = 300


class TsallisRegime(str, Enum):
    """Market regime based on Tsallis q parameter."""

    NORMAL = "normal"  # q < 1.35
    ELEVATED = "elevated"  # 1.35 ≤ q < 1.55
    CRISIS = "crisis"  # q ≥ 1.55


@dataclass(frozen=True, slots=True)
class TsallisGateResult:
    """Result of Tsallis gate evaluation.

    Attributes
    ----------
    q : float
        MLE-fitted Tsallis index (Student-t equivalence). q ≥ 1.
    regime : TsallisRegime
        Operational regime from the EXTRAPOLATED q cutoffs. When the fit
        is rejected (``gof_passed is False``) this is the conservative
        ELEVATED fallback, NOT a q-derived classification.
    position_multiplier : float
        Position-size multiplier in [0, 1].
    kurtosis : float
        Reported DIAGNOSTIC only (excess kurtosis). NOT the estimator.
        Diverges in the heavy-tail regime — do not consume as a q proxy.
    nu : float
        Fitted Student-t degrees of freedom (the MLE primitive).
    gof_stat : float
        Kolmogorov-Smirnov statistic of the standardised sample vs the
        fitted t CDF. Lower is a better fit.
    gof_pvalue : float
        KS p-value. ``gof_passed`` is ``gof_pvalue >= gof_alpha``.
    gof_passed : bool
        Whether the q-Gaussian/t fit is accepted. When False the q,
        regime, and multiplier are the conservative fallback, not a
        confident q-derived decision.
    window_returns : int
        Number of observations used.
    """

    q: float
    regime: TsallisRegime
    position_multiplier: float
    kurtosis: float
    nu: float
    gof_stat: float
    gof_pvalue: float
    gof_passed: bool
    window_returns: int


def _q_from_nu(nu: float) -> float:
    """Map Student-t degrees of freedom to Tsallis index.

    q = (ν + 3) / (ν + 1). For ν → ∞ → q → 1 (Gaussian); ν = 1 → q = 2
    (Cauchy). Souza & Tsallis (1997), Tsallis (2009) Ch. 4.
    """
    return (nu + 3.0) / (nu + 1.0)


def _diagnostic_kurtosis(standardized: NDArray[np.float64]) -> float:
    """Excess kurtosis of an already-standardised sample (diagnostic only)."""
    return float(np.mean(standardized**4) - 3.0)


@dataclass(frozen=True, slots=True)
class _QFit:
    """Internal: result of the MLE + GoF on a standardised sample."""

    q: float
    nu: float
    kurtosis: float
    gof_stat: float
    gof_pvalue: float
    degenerate: bool  # True ⟹ no real fit (insufficient/zero-variance data)
    escaped: bool  # True ⟹ optimiser escaped to Gaussian limit (nu_fit > _NU_ESCAPE)


def _fit_q_mle(returns: NDArray[np.float64]) -> _QFit:
    """MLE-fit the Student-t df on standardised returns and run a KS GoF.

    Returns a ``_QFit``. The ``degenerate`` flag is set for the
    insufficient-data and zero-variance branches; those map to the
    Gaussian limit (q = 1, ν = ∞-proxy) and a vacuous GoF.
    """
    returns = np.asarray(returns, dtype=np.float64)
    if returns.size < 4:
        # Insufficient data → assume Gaussian limit. Degenerate fit.
        return _QFit(
            q=1.0,
            nu=_NU_MAX,
            kurtosis=0.0,
            gof_stat=0.0,
            gof_pvalue=1.0,
            degenerate=True,
            escaped=False,
        )

    mean = float(np.mean(returns))
    std = float(np.std(returns, ddof=1))
    if std < 1e-12:
        # No variance → Gaussian limit, no distribution to fit. Degenerate.
        return _QFit(
            q=1.0,
            nu=_NU_MAX,
            kurtosis=0.0,
            gof_stat=0.0,
            gof_pvalue=1.0,
            degenerate=True,
            escaped=False,
        )

    standardized = (returns - mean) / std
    kurtosis = _diagnostic_kurtosis(standardized)

    # Full 3-parameter MLE of the Student-t (df, loc, scale) on the RAW
    # sample. scipy.stats.t.fit maximises the joint likelihood; fitting
    # loc/scale jointly (rather than pre-standardising and assuming unit
    # scale) is essential — the standardisation by the *sample* std biases
    # the shape estimate for heavy tails. This is the heavy-tail-stable
    # estimator: it uses the full likelihood, not the 4th moment, so it
    # stays well-defined for ν ≤ 4 (q ≥ 1.4) where kurtosis is ∞.
    nu_fit, loc_fit, scale_fit = stats.t.fit(returns)

    # The unbounded MLE ν is used for the goodness-of-fit (must match the
    # actual fitted distribution). For the q mapping we clamp ν into the
    # supported search bracket: a Gaussian sample drives ν → very large
    # (q → 1) and the Cauchy floor caps tail heaviness.
    # INV-HPC2: clamp keeps ν finite ⟹ q finite; map then floors q ≥ 1.
    nu_for_q = float(np.clip(nu_fit, _NU_MIN, _NU_MAX))
    # Escape detection BEFORE the clamp hides it: a genuine heavy tail at
    # small N can drive the unbounded MLE ν to ~1e11 (Gaussian-limit
    # escape), which clamps to _NU_MAX and masquerades as a confident
    # q ≈ 1.01. Flag it so evaluate() can refuse to grant full position.
    # INV-HPC2 / fail-closed; see _NU_ESCAPE.
    escaped = bool(nu_fit > _NU_ESCAPE)
    q = _q_from_nu(nu_for_q)
    # INV-HPC2: q ∈ (1, 1.66] for ν ∈ [2.05, 200]; the floor keeps q ≥ 1
    # exactly at the Gaussian limit and guards float drift at ν = _NU_MAX.
    q = max(q, 1.0)

    # Goodness-of-fit: KS of the RAW sample against the fully-fitted t CDF
    # (df, loc, scale all from the MLE). p < alpha ⟹ not a q-Gaussian.
    ks = stats.kstest(returns, "t", args=(nu_fit, loc_fit, scale_fit))
    gof_stat = float(ks.statistic)
    gof_pvalue = float(ks.pvalue)

    return _QFit(
        q=q,
        nu=nu_for_q,
        kurtosis=kurtosis,
        gof_stat=gof_stat,
        gof_pvalue=gof_pvalue,
        degenerate=False,
        escaped=escaped,
    )


class TsallisRiskGate:
    """Real-time position sizing gate based on a MLE-fitted Tsallis q.

    The fit (``estimate_q`` / ``fit_q``) is anchored: q is obtained by
    maximum-likelihood on the Student-t equivalence and gated by a
    Kolmogorov-Smirnov goodness-of-fit test. The regime cutoffs
    (``q_normal``, ``q_crisis``) are operational, literature-sourced
    EXTRAPOLATED parameters, not fitted constants.

    Parameters
    ----------
    window : int
        Rolling window for q estimation (default 60).
    q_normal : float
        Upper bound for NORMAL regime (default 1.35). Operational cutoff,
        EXTRAPOLATED.
    q_crisis : float
        Lower bound for CRISIS regime (default 1.55). Operational cutoff,
        EXTRAPOLATED.
    min_observations : int
        Minimum observations for a reliable q estimate (default 20).
    gof_alpha : float
        KS significance level (default 0.05). A fit with p-value below
        this is rejected and the gate fails closed to the conservative
        fallback. Operational parameter.
    n_mle_trust : int
        Minimum sample size for the MLE to be trusted to grant the
        NORMAL / full-position (low-q) verdict (default ``_N_MLE_TRUST`` =
        250). Below this, a near-Gaussian (low-q) read is demoted to the
        conservative fallback because the small-N Student-t MLE escapes to
        the Gaussian limit on genuine heavy tails (fail-OPEN). One-
        directional: it never weakens a confident CRISIS (high-q) read.
        Operational parameter; basis documented at ``_N_MLE_TRUST``.
    """

    # Position multiplier of the conservative fail-closed fallback. The
    # small-N guard only demotes reads MORE generous than this; CRISIS
    # reads (mult < this, e.g. 0.0) are preserved. Mirrors
    # _conservative_result.
    _conservative_multiplier: float = 0.25

    def __init__(
        self,
        window: int = 60,
        q_normal: float = 1.35,
        q_crisis: float = 1.55,
        min_observations: int = 20,
        gof_alpha: float = 0.05,
        n_mle_trust: int = _N_MLE_TRUST,
    ) -> None:
        if window < 2:
            raise ValueError(f"window must be ≥ 2, got {window}")
        if q_normal >= q_crisis:
            raise ValueError(f"q_normal must be < q_crisis: {q_normal} vs {q_crisis}")
        if min_observations < 2:
            raise ValueError(f"min_observations must be ≥ 2, got {min_observations}")
        if not 0.0 < gof_alpha < 1.0:
            raise ValueError(f"gof_alpha must be in (0, 1), got {gof_alpha}")
        if n_mle_trust < 2:
            raise ValueError(f"n_mle_trust must be ≥ 2, got {n_mle_trust}")
        self._window = window
        self._q_normal = q_normal
        self._q_crisis = q_crisis
        self._min_obs = min_observations
        self._gof_alpha = gof_alpha
        self._N_MLE_TRUST = n_mle_trust
        self._history: list[TsallisGateResult] = []

    @property
    def window(self) -> int:
        return self._window

    @property
    def gof_alpha(self) -> float:
        return self._gof_alpha

    @property
    def history(self) -> list[TsallisGateResult]:
        return list(self._history)

    @staticmethod
    def estimate_q(returns: NDArray[np.float64]) -> float:
        """Estimate Tsallis q by MLE on the Student-t equivalence.

        Fits the Student-t degrees of freedom ν by maximum likelihood on
        the standardised sample and maps to q = (ν + 3) / (ν + 1).

        For a Gaussian sample ν → large, q → 1. For heavy tails ν is small
        and q is larger (Cauchy ν = 1 → q = 2). Insufficient data
        (< 4 points) or zero variance returns the Gaussian limit q = 1.0.

        This replaces the legacy kurtosis closed form q = (5 + 3κ)/(3 + κ),
        which is unstable exactly in the heavy-tail regime the gate targets
        (the 4th moment diverges for ν ≤ 4 ⟺ q ≥ 1.4). Kurtosis is now a
        reported diagnostic only.
        """
        return _fit_q_mle(returns).q

    @staticmethod
    def fit_q(returns: NDArray[np.float64]) -> _QFit:
        """Full MLE + GoF fit (q, ν, diagnostic kurtosis, KS stat/pvalue)."""
        return _fit_q_mle(returns)

    def classify_regime(self, q: float) -> TsallisRegime:
        """Classify market regime from q value (operational cutoffs)."""
        if q < self._q_normal:
            return TsallisRegime.NORMAL
        elif q < self._q_crisis:
            return TsallisRegime.ELEVATED
        else:
            return TsallisRegime.CRISIS

    def position_multiplier(self, q: float) -> float:
        """Compute position size multiplier from q.

        f(q) = max(0, 1 - (q - q_normal) / (q_crisis - q_normal))  # INV-FE2

        Linear ramp from 1.0 at q_normal to 0.0 at q_crisis.
        """
        if q <= self._q_normal:
            return 1.0
        if q >= self._q_crisis:
            return 0.0
        return 1.0 - (q - self._q_normal) / (self._q_crisis - self._q_normal)

    def _conservative_result(
        self,
        n_obs: int,
        *,
        gof_stat: float,
        gof_pvalue: float,
        nu: float,
        kurtosis: float,
    ) -> TsallisGateResult:
        """Conservative fail-closed result (data scarcity OR GoF rejection).

        Mirrors the historical data-scarcity convention: q = 1.5 (ELEVATED),
        position_multiplier = 0.25. Used both when n_obs < min_observations
        and when the q-Gaussian fit is rejected — in neither case do we
        emit a confident q-derived regime.
        """
        return TsallisGateResult(
            q=1.5,
            regime=TsallisRegime.ELEVATED,
            position_multiplier=0.25,
            kurtosis=kurtosis,
            nu=nu,
            gof_stat=gof_stat,
            gof_pvalue=gof_pvalue,
            gof_passed=False,
            window_returns=n_obs,
        )

    def evaluate(self, returns: NDArray[np.float64]) -> TsallisGateResult:
        """Evaluate gate on return series.

        Parameters
        ----------
        returns : (T,) or (T, N) return series.
            If 2-D, uses flattened cross-sectional returns.

        Returns
        -------
        TsallisGateResult with MLE q, GoF stat/pvalue, regime, multiplier.

        Fail-closed behaviour
        ---------------------
        * ``n_obs < min_observations`` → conservative fallback
          (q = 1.5, ELEVATED, multiplier 0.25, gof_passed = False).
        * fit rejected (``gof_pvalue < gof_alpha``) → SAME conservative
          fallback; the sample is not a q-Gaussian and no confident
          q-derived regime is emitted.
        """
        returns = np.asarray(returns, dtype=np.float64)
        if returns.ndim == 2:
            # Use cross-sectional returns for portfolio-level q
            returns = returns.ravel()

        tail = returns[-self._window :]
        n_obs = tail.size

        if n_obs < self._min_obs:
            # Insufficient data → conservative, fail-closed.
            result = self._conservative_result(
                n_obs, gof_stat=1.0, gof_pvalue=0.0, nu=float("nan"), kurtosis=0.0
            )
            self._history.append(result)
            return result

        fit = _fit_q_mle(tail)

        # GoF gate. A degenerate (zero-variance / sub-4) sample that
        # survived the n_obs check is a true Gaussian limit (q = 1) and is
        # NOT failed closed: it is a well-fit, low-risk sample. Only a
        # genuine fit with a rejected KS p-value fails closed.
        gof_passed = fit.degenerate or fit.gof_pvalue >= self._gof_alpha

        if not gof_passed:
            result = self._conservative_result(
                n_obs,
                gof_stat=fit.gof_stat,
                gof_pvalue=fit.gof_pvalue,
                nu=fit.nu,
                kurtosis=fit.kurtosis,
            )
            self._history.append(result)
            return result

        q = fit.q
        regime = self.classify_regime(q)
        mult = self.position_multiplier(q)

        # SMALL-N FAIL-CLOSED GUARD (one-directional, demote-only).
        # At small N the Student-t MLE ESCAPES to the Gaussian limit on a
        # genuine heavy-tailed sample and the KS GoF lacks the power to reject
        # it; the result is a confident NORMAL/full-position read on a
        # pre-crisis tail — the dangerous fail-OPEN direction. The escape rate
        # only reaches 0% at N≥_N_MLE_TRUST (see its derivation), and the
        # escape flag cannot itself distinguish a genuine Gaussian (which also
        # drives ν→∞ at any N) from a heavy-tail escape — so the SAMPLE SIZE is
        # the operative guard. We refuse to grant a LESS-conservative position
        # than the conservative fallback whenever n_obs < _N_MLE_TRUST. This
        # only fires when the candidate sizing is MORE generous than the
        # fallback (mult > 0.25): a genuine CRISIS read (high q, mult < 0.25,
        # e.g. 0.0) is NEVER weakened — cutting exposure on a resolved heavy
        # tail is the SAFE direction and is preserved at ANY N. INV-FE2 /
        # INV-HPC2; see _N_MLE_TRUST for the escape-rate basis.
        not_trustworthy = n_obs < self._N_MLE_TRUST
        if not_trustworthy and mult > self._conservative_multiplier:
            result = self._conservative_result(
                n_obs,
                gof_stat=fit.gof_stat,
                gof_pvalue=fit.gof_pvalue,
                nu=fit.nu,
                kurtosis=fit.kurtosis,
            )
            self._history.append(result)
            return result

        result = TsallisGateResult(
            q=q,
            regime=regime,
            position_multiplier=mult,
            kurtosis=fit.kurtosis,
            nu=fit.nu,
            gof_stat=fit.gof_stat,
            gof_pvalue=fit.gof_pvalue,
            gof_passed=True,
            window_returns=n_obs,
        )
        self._history.append(result)
        return result

    def evaluate_prices(self, prices: NDArray[np.float64]) -> TsallisGateResult:
        """Convenience: compute returns from prices, then evaluate."""
        prices = np.asarray(prices, dtype=np.float64)
        if prices.ndim == 1:
            if prices.size < 2:
                raise ValueError("Need ≥ 2 prices")
            returns = np.diff(np.log(np.maximum(prices, 1e-12)))
        else:
            if prices.shape[0] < 2:
                raise ValueError("Need ≥ 2 time steps")
            returns = np.diff(np.log(np.maximum(prices, 1e-12)), axis=0)
        return self.evaluate(returns)


__all__ = ["TsallisRiskGate", "TsallisGateResult", "TsallisRegime"]
