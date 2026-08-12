# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Variational free energy primitives for digital active inference.

Implements the Friston (2010+) free energy decomposition

    F = D_KL[q(z) || p(z)] − E_q[log p(s | z)]
      = complexity − accuracy

for univariate and diagonal-multivariate Gaussian beliefs. Pure
NumPy; deterministic; no hidden state. Each function is the
algebraically-closed form — no numerical integration, no Monte
Carlo.

Why a separate module
---------------------

The existing :mod:`core.physics.free_energy_trading_gate` operates
on Helmholtz free energy ``F = U − T·S`` over portfolio risk. That
is a *decision gate*. This module operates on **variational** free
energy over a generative model — it is the *belief-update*
primitive that an active-inference agent needs. The two are
related (variational F bounds Helmholtz F under specific
assumptions) but the operational role is different. Mixing them
would confuse callers.

Public surface
--------------

* :class:`GaussianBelief` — frozen 1-D belief (mean, log-variance).
* :class:`DiagonalGaussianBelief` — frozen multivariate diagonal
  belief.
* :func:`kl_divergence` — closed-form KL between two beliefs of
  the same family.
* :func:`expected_log_likelihood` — :math:`E_q[\\log p(s | z)]`
  under a Gaussian observation model.
* :func:`variational_free_energy` — the canonical
  ``complexity − accuracy`` decomposition.
* :func:`surprise` — :math:`-\\log p(s)` under a single Gaussian
  predictive distribution; the per-tick observable that an
  agent's perceptual loop minimises.

Reference
---------

Friston, K. (2010). The free-energy principle: a unified brain
theory? *Nature Reviews Neuroscience*, 11(2), 127–138.

Buckley et al. (2017). The free energy principle for action and
perception: a mathematical review. *Journal of Mathematical
Psychology*, 81, 55–79.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "DiagonalGaussianBelief",
    "GaussianBelief",
    "expected_log_likelihood",
    "kl_divergence",
    "kl_divergence_diagonal",
    "surprise",
    "variational_free_energy",
]


_LOG_2PI: float = math.log(2.0 * math.pi)


@dataclass(frozen=True, slots=True)
class GaussianBelief:
    """Frozen univariate Gaussian belief :math:`q(z) = N(\\mu, e^{\\ell})`.

    Stored in log-variance form for numerical stability — variance
    is always positive by construction; no clipping needed.

    Attributes
    ----------
    mean:
        :math:`\\mu`.
    log_variance:
        :math:`\\ell = \\log \\sigma^2`.
    """

    mean: float
    log_variance: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.mean):
            raise ValueError(f"GaussianBelief.mean must be finite; got {self.mean!r}")
        if not math.isfinite(self.log_variance):
            raise ValueError(
                f"GaussianBelief.log_variance must be finite; got {self.log_variance!r}"
            )

    @property
    def variance(self) -> float:
        return math.exp(self.log_variance)


@dataclass(frozen=True, slots=True)
class DiagonalGaussianBelief:
    """Frozen multivariate diagonal Gaussian belief.

    Variances are stored as ``log_variance`` per dimension; the
    full covariance matrix is implicitly ``diag(exp(log_variance))``.
    """

    mean: NDArray[np.float64]
    log_variance: NDArray[np.float64]

    def __post_init__(self) -> None:
        if self.mean.shape != self.log_variance.shape:
            raise ValueError(
                "DiagonalGaussianBelief: mean and log_variance must have the same shape; "
                f"got mean.shape={self.mean.shape}, log_variance.shape={self.log_variance.shape}."
            )
        if self.mean.ndim != 1:
            raise ValueError(
                f"DiagonalGaussianBelief: expected 1-D arrays; got ndim={self.mean.ndim}."
            )
        if not (np.isfinite(self.mean).all() and np.isfinite(self.log_variance).all()):
            raise ValueError(
                "DiagonalGaussianBelief: mean and log_variance must be all-finite; "
                "INV-HPC2 boundary check."
            )


def kl_divergence(q: GaussianBelief, p: GaussianBelief) -> float:
    r"""Closed-form KL between two univariate Gaussians.

    .. math::
        D_{\mathrm{KL}}[q \,\|\, p] = \frac{1}{2}\left(
            \frac{\sigma_q^2}{\sigma_p^2}
            + \frac{(\mu_p - \mu_q)^2}{\sigma_p^2}
            - 1
            + \log \frac{\sigma_p^2}{\sigma_q^2}
        \right).

    Always non-negative; zero iff :math:`q = p` (in distribution).
    """
    sigma_q_sq = math.exp(q.log_variance)
    sigma_p_sq = math.exp(p.log_variance)
    mean_term = (p.mean - q.mean) ** 2 / sigma_p_sq
    var_term = sigma_q_sq / sigma_p_sq - 1.0 - q.log_variance + p.log_variance
    return 0.5 * (var_term + mean_term)


def kl_divergence_diagonal(q: DiagonalGaussianBelief, p: DiagonalGaussianBelief) -> float:
    r"""Closed-form KL between two diagonal multivariate Gaussians.

    Sums the per-dimension univariate KLs (independence under
    diagonal covariance).
    """
    if q.mean.shape != p.mean.shape:
        raise ValueError(
            "kl_divergence_diagonal: q and p must share shape; "
            f"got q.shape={q.mean.shape}, p.shape={p.mean.shape}."
        )
    sigma_q_sq = np.exp(q.log_variance)
    sigma_p_sq = np.exp(p.log_variance)
    mean_term = (p.mean - q.mean) ** 2 / sigma_p_sq
    var_term = sigma_q_sq / sigma_p_sq - 1.0 - q.log_variance + p.log_variance
    return float(0.5 * np.sum(var_term + mean_term))


def expected_log_likelihood(
    q: GaussianBelief,
    observation: float,
    observation_log_variance: float,
    observation_map_slope: float = 1.0,
    observation_map_intercept: float = 0.0,
) -> float:
    r"""Compute :math:`E_q[\log p(s | z)]` for a linear-Gaussian likelihood.

    Likelihood model: ``s = a · z + b + ε``, with
    :math:`\varepsilon \sim N(0, \sigma_s^2)`. Closed-form expectation
    under :math:`q(z) = N(\mu_q, \sigma_q^2)`:

    .. math::
        E_q[\log p(s | z)] = -\frac{1}{2}\Big(
            \log(2\pi\sigma_s^2)
            + \frac{(s - a\mu_q - b)^2 + a^2 \sigma_q^2}{\sigma_s^2}
        \Big).

    A *higher* value (less negative) means a better fit between
    the belief and the observation.

    Parameters
    ----------
    q:
        Belief over the latent ``z``.
    observation:
        Observed value ``s``.
    observation_log_variance:
        :math:`\log \sigma_s^2`.
    observation_map_slope, observation_map_intercept:
        Linear map ``s = a·z + b``. Defaults to identity (``a=1, b=0``).
    """
    if not (math.isfinite(observation) and math.isfinite(observation_log_variance)):
        raise ValueError(
            "expected_log_likelihood: observation and observation_log_variance "
            "must be finite (INV-HPC2)."
        )
    sigma_s_sq = math.exp(observation_log_variance)
    sigma_q_sq = math.exp(q.log_variance)
    residual = observation - observation_map_slope * q.mean - observation_map_intercept
    quadratic = (residual**2 + (observation_map_slope**2) * sigma_q_sq) / sigma_s_sq
    return -0.5 * (_LOG_2PI + observation_log_variance + quadratic)


def variational_free_energy(
    q: GaussianBelief,
    p: GaussianBelief,
    observation: float,
    observation_log_variance: float,
    observation_map_slope: float = 1.0,
    observation_map_intercept: float = 0.0,
) -> float:
    r"""Variational free energy ``F = complexity − accuracy``.

    .. math::
        F = D_{\mathrm{KL}}[q(z) \,\|\, p(z)] - E_q[\log p(s | z)].

    Minimising :math:`F` over :math:`q` is the *perceptual* mode
    of active inference: tighten the posterior so it matches the
    prior under the observed likelihood. Minimising over actions
    (changing the observation distribution) is the *active* mode.

    The function returns the bare scalar; callers decide which mode
    of descent to apply.
    """
    complexity = kl_divergence(q, p)
    accuracy = expected_log_likelihood(
        q,
        observation=observation,
        observation_log_variance=observation_log_variance,
        observation_map_slope=observation_map_slope,
        observation_map_intercept=observation_map_intercept,
    )
    return complexity - accuracy


def surprise(observation: float, predicted_mean: float, predicted_log_variance: float) -> float:
    r"""Surprise = :math:`-\log p(s)` under a single Gaussian predictive.

    .. math::
        -\log p(s) = \frac{1}{2}\Big(
            \log(2\pi\sigma^2) + \frac{(s - \mu)^2}{\sigma^2}
        \Big).

    Always non-negative; minimised when the observation lands at
    the predicted mean. The per-tick observable an agent's
    perceptual loop minimises by updating beliefs (perceptual
    inference) or acting (active inference).
    """
    if not (
        math.isfinite(observation)
        and math.isfinite(predicted_mean)
        and math.isfinite(predicted_log_variance)
    ):
        raise ValueError(
            "surprise: observation, predicted_mean, predicted_log_variance must be finite."
        )
    sigma_sq = math.exp(predicted_log_variance)
    quadratic = (observation - predicted_mean) ** 2 / sigma_sq
    return 0.5 * (_LOG_2PI + predicted_log_variance + quadratic)
