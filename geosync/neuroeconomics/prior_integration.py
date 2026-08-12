# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Bayesian prior-likelihood-posterior integration.

Constructs (Summerfield & de Lange 2014):
  C17: prior                  — P(s) over state space from regime history
  C18: likelihood             — P(e|s) from signal model
  C19: posterior_update       — P(s|e) ∝ L(e|s) × P(s)
  C20: expectation_suppression — reduced response to predicted signals
  C21: attention_vs_expectation — independent gates (NOT conflated)
  C22: drift_rate_bias        — prior biases evidence accumulation rate
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class PriorState:
    prior: tuple[float, ...]  # P(s) over states
    posterior: tuple[float, ...]  # P(s|e) after update
    suppression_weight: float  # 1 - P(e|prior): surprise amplification
    drift_bias: float  # prior contribution to accumulation rate
    attention_gate: float  # independent salience (NOT from prior)
    prior_entropy: float  # H(prior) — for control_value


class PriorIntegrator:
    """Bayesian belief update with expectation suppression.

    Parameters
    ----------
    n_states
        Number of discrete states (default 5: regimes).
    beta_prior
        Strength of prior → drift_bias coupling.
    salience_decay
        Decay rate for attention gate.
    """

    def __init__(
        self,
        *,
        n_states: int = 5,
        beta_prior: float = 0.3,
        salience_decay: float = 0.9,
    ) -> None:
        self.n_states = n_states
        self.beta_prior = beta_prior
        self.salience_decay = salience_decay
        # Uniform prior
        self._prior = np.ones(n_states, dtype=np.float64) / n_states
        self._attention = 0.5
        # Pre-allocated work buffers (avoid allocation per tick)
        self._unnorm = np.empty(n_states, dtype=np.float64)
        self._lik_buf = np.empty(n_states, dtype=np.float64)

    def update(
        self,
        *,
        likelihood: np.ndarray | list[float],
        salience: float = 0.5,
    ) -> PriorState:
        """Bayesian update: posterior ∝ likelihood × prior.

        Parameters
        ----------
        likelihood
            P(evidence | state) for each state. Must be non-negative.
        salience
            Independent attention signal ∈ [0, 1] (C21: NOT from prior).
        """
        # Copy into pre-allocated buffer (zero-alloc hot path)
        if isinstance(likelihood, np.ndarray) and likelihood.shape == (self.n_states,):
            np.copyto(self._lik_buf, likelihood)
        else:
            lik_arr = np.asarray(likelihood, dtype=np.float64)
            if lik_arr.shape != (self.n_states,):
                raise ValueError(f"likelihood must have {self.n_states} elements")
            np.copyto(self._lik_buf, lik_arr)

        np.clip(self._lik_buf, 0.0, None, out=self._lik_buf)

        # C19: Posterior = likelihood × prior, normalized (in-place)
        np.multiply(self._lik_buf, self._prior, out=self._unnorm)
        z = float(self._unnorm.sum())
        if z < 1e-10:
            posterior = self._prior.copy()
        else:
            posterior = self._unnorm / z

        # C20: Expectation suppression = 1 - P(evidence | prior)
        # High when evidence is surprising (low prior probability)
        expected_prob = float(np.sum(self._lik_buf * self._prior))
        suppression = 1.0 - min(1.0, expected_prob)

        # C22: Drift bias = beta × max prior probability
        drift_bias = self.beta_prior * float(self._prior.max())

        # C21: Attention gate — independent of expectation
        self._attention = self.salience_decay * self._attention + (1.0 - self.salience_decay) * max(
            0.0, min(1.0, salience)
        )

        # Prior entropy for control_value
        prior_entropy = _entropy(self._prior)

        # Update prior for next step
        self._prior = posterior.copy()

        return PriorState(
            prior=tuple(float(p) for p in self._prior),
            posterior=tuple(float(p) for p in posterior),
            suppression_weight=suppression,
            drift_bias=drift_bias,
            attention_gate=self._attention,
            prior_entropy=prior_entropy,
        )

    def seed_prior(self, distribution: np.ndarray | list[float]) -> None:
        """Seed prior from regime classifier (context_memory → prior_integration)."""
        d = np.asarray(distribution, dtype=np.float64)
        if d.shape != (self.n_states,):
            raise ValueError(f"distribution must have {self.n_states} elements")
        total = float(d.sum())
        if total > 0:
            self._prior = d / total
        else:
            self._prior = np.ones(self.n_states, dtype=np.float64) / self.n_states


def _entropy(p: np.ndarray) -> float:
    """Shannon entropy in bits."""
    safe = p[p > 0]
    return float(-np.sum(safe * np.log2(safe)))
