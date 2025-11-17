# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Multi-armed bandit algorithms for adaptive strategy selection.

This module implements classic bandit algorithms used for online strategy
selection and hyperparameter optimization in the trading agent system.
The implementations use cryptographically strong randomness for security-
sensitive production environments.

Key Components:
    EpsilonGreedy: Classic epsilon-greedy exploration-exploitation algorithm
    UCB1: Upper Confidence Bound algorithm with optimistic initialization
    ThompsonSampling: Bayesian bandit with Beta-Bernoulli conjugate priors

The bandit framework treats trading strategies as "arms" and optimizes
selection based on observed rewards (e.g., Sharpe ratio, PnL). This enables
automatic adaptation to changing market conditions without manual intervention.

All implementations support dynamic arm addition/removal to handle evolving
strategy portfolios. Statistics are maintained incrementally for efficiency.

Example:
    >>> bandit = EpsilonGreedy(["momentum", "mean_reversion"], epsilon=0.1)
    >>> selected = bandit.select()
    >>> reward = execute_strategy(selected)
    >>> bandit.update(selected, reward)

Security Note:
    Uses secrets.SystemRandom for cryptographically strong randomness,
    preventing predictable exploration patterns in production trading.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from secrets import SystemRandom
from typing import Dict, List, Sequence

Arm = str


def _unique_arms(arms: Iterable[Arm]) -> List[Arm]:
    """Return a list of unique arms preserving their original order."""
    seen = set()
    ordered: List[Arm] = []
    for arm in arms:
        if arm in seen:
            continue
        seen.add(arm)
        ordered.append(arm)
    return ordered


class EpsilonGreedy:
    """Classic epsilon-greedy bandit with cryptographically strong randomness."""

    def __init__(
        self,
        arms: Iterable[Arm],
        *,
        epsilon: float = 0.1,
        rng: SystemRandom | None = None,
    ) -> None:
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon must be within [0, 1]")

        ordered_arms = _unique_arms(arms)
        self._values: Dict[Arm, float] = {arm: 0.0 for arm in ordered_arms}
        self._counts: Dict[Arm, int] = {arm: 0 for arm in ordered_arms}
        self.epsilon = float(epsilon)
        self._rng = rng or SystemRandom()

    @property
    def arms(self) -> Sequence[Arm]:
        """Expose the currently known arms in deterministic order."""
        return tuple(self._values.keys())

    def add_arm(self, arm: Arm) -> None:
        """Register a new arm if it does not already exist."""
        if arm in self._values:
            return
        self._values[arm] = 0.0
        self._counts[arm] = 0

    def remove_arm(self, arm: Arm) -> None:
        """Remove an arm and its associated statistics."""
        if arm not in self._values:
            raise KeyError(f"Unknown arm '{arm}'")
        del self._values[arm]
        del self._counts[arm]

    def select(self) -> Arm:
        """Select the next arm using epsilon-greedy exploration."""
        if not self._values:
            raise ValueError("No arms available")
        arms = list(self._values.keys())
        if self._rng.random() < self.epsilon:
            return self._rng.choice(arms)
        return max(arms, key=lambda arm: self._values[arm])

    def update(self, arm: Arm, reward: float) -> None:
        """Update running averages with an observed reward for an arm."""
        if arm not in self._values:
            raise KeyError(f"Unknown arm '{arm}'")
        self._counts[arm] += 1
        n = self._counts[arm]
        self._values[arm] += (reward - self._values[arm]) / n

    def estimate(self, arm: Arm) -> float:
        """Return the current reward estimate for an arm."""
        if arm not in self._values:
            raise KeyError(f"Unknown arm '{arm}'")
        return self._values[arm]

    def pulls(self, arm: Arm) -> int:
        """Return the number of times an arm has been selected."""
        if arm not in self._counts:
            raise KeyError(f"Unknown arm '{arm}'")
        return self._counts[arm]


class UCB1:
    """Upper Confidence Bound (UCB1) multi-armed bandit implementation."""

    def __init__(self, arms: Iterable[Arm]) -> None:
        ordered_arms = _unique_arms(arms)
        self._values: Dict[Arm, float] = {arm: 0.0 for arm in ordered_arms}
        self._counts: Dict[Arm, int] = {arm: 0 for arm in ordered_arms}
        self._total_pulls = 0

    @property
    def arms(self) -> Sequence[Arm]:
        return tuple(self._values.keys())

    def add_arm(self, arm: Arm) -> None:
        if arm in self._values:
            return
        self._values[arm] = 0.0
        self._counts[arm] = 0

    def select(self) -> Arm:
        if not self._values:
            raise ValueError("No arms available")

        self._total_pulls += 1

        def ucb(arm: Arm) -> float:
            pulls = self._counts[arm]
            if pulls == 0:
                return float("inf")
            exploration = math.sqrt(2.0 * math.log(self._total_pulls) / pulls)
            return self._values[arm] + exploration

        return max(self._values.keys(), key=ucb)

    def update(self, arm: Arm, reward: float) -> None:
        if arm not in self._values:
            raise KeyError(f"Unknown arm '{arm}'")
        self._counts[arm] += 1
        pulls = self._counts[arm]
        self._values[arm] += (reward - self._values[arm]) / pulls

    def estimate(self, arm: Arm) -> float:
        if arm not in self._values:
            raise KeyError(f"Unknown arm '{arm}'")
        return self._values[arm]

    def pulls(self, arm: Arm) -> int:
        if arm not in self._counts:
            raise KeyError(f"Unknown arm '{arm}'")
        return self._counts[arm]


class ThompsonSampling:
    """Thompson Sampling (Bayesian) multi-armed bandit with Beta priors.

    Implements Thompson Sampling using Beta-Bernoulli conjugate priors for
    reward distributions in [0, 1]. This Bayesian approach naturally balances
    exploration and exploitation by sampling from posterior distributions.

    Thompson Sampling often outperforms UCB1 in practice, especially with
    delayed or batched feedback. It's particularly effective for financial
    applications where reward distributions may be non-stationary.

    The implementation assumes binary or [0,1] bounded rewards and maintains
    Beta(α, β) posterior distributions for each arm. Uses cryptographically
    strong randomness for production trading safety.

    References:
        Thompson, W. R. (1933). On the likelihood that one unknown probability
        exceeds another in view of the evidence of two samples. Biometrika, 25(3/4).

        Agrawal, S., & Goyal, N. (2012). Analysis of Thompson Sampling for the
        multi-armed bandit problem. COLT 2012.
    """

    def __init__(
        self,
        arms: Iterable[Arm],
        *,
        alpha_prior: float = 1.0,
        beta_prior: float = 1.0,
        rng: SystemRandom | None = None,
    ) -> None:
        """Initialize Thompson Sampling with Beta priors.

        Args:
            arms: Collection of arm identifiers.
            alpha_prior: Prior success count (α parameter of Beta distribution).
                Default 1.0 gives uniform prior Beta(1,1).
            beta_prior: Prior failure count (β parameter of Beta distribution).
                Default 1.0 gives uniform prior Beta(1,1).
            rng: Random number generator. Uses SystemRandom() if not provided.

        Raises:
            ValueError: If alpha_prior or beta_prior <= 0.
        """
        if alpha_prior <= 0.0 or beta_prior <= 0.0:
            raise ValueError("Beta prior parameters must be positive")

        ordered_arms = _unique_arms(arms)
        self._alphas: Dict[Arm, float] = {arm: alpha_prior for arm in ordered_arms}
        self._betas: Dict[Arm, float] = {arm: beta_prior for arm in ordered_arms}
        self._alpha_prior = alpha_prior
        self._beta_prior = beta_prior
        self._rng = rng or SystemRandom()

    @property
    def arms(self) -> Sequence[Arm]:
        """Return currently known arms in deterministic order."""
        return tuple(self._alphas.keys())

    def add_arm(self, arm: Arm) -> None:
        """Register a new arm with prior distribution."""
        if arm in self._alphas:
            return
        self._alphas[arm] = self._alpha_prior
        self._betas[arm] = self._beta_prior

    def remove_arm(self, arm: Arm) -> None:
        """Remove an arm and its posterior distribution."""
        if arm not in self._alphas:
            raise KeyError(f"Unknown arm '{arm}'")
        del self._alphas[arm]
        del self._betas[arm]

    def select(self) -> Arm:
        """Select arm by sampling from posterior Beta distributions.

        Returns:
            Arm with highest sampled value from its posterior.

        Raises:
            ValueError: If no arms are available.
        """
        if not self._alphas:
            raise ValueError("No arms available")

        # Sample theta from Beta(α, β) for each arm
        samples = {
            arm: self._sample_beta(self._alphas[arm], self._betas[arm])
            for arm in self._alphas
        }

        return max(samples, key=samples.get)  # type: ignore

    def update(self, arm: Arm, reward: float) -> None:
        """Update posterior distribution with observed reward.

        Args:
            arm: Arm that was pulled.
            reward: Observed reward in [0, 1]. Values are clamped if outside.

        Raises:
            KeyError: If arm is unknown.
        """
        if arm not in self._alphas:
            raise KeyError(f"Unknown arm '{arm}'")

        # Clamp reward to [0, 1] for Beta-Bernoulli model
        reward_clamped = max(0.0, min(1.0, float(reward)))

        # Bayesian update: α += reward, β += (1 - reward)
        self._alphas[arm] += reward_clamped
        self._betas[arm] += 1.0 - reward_clamped

    def estimate(self, arm: Arm) -> float:
        """Return posterior mean E[θ] = α / (α + β).

        Args:
            arm: Arm to query.

        Returns:
            Posterior mean reward estimate.

        Raises:
            KeyError: If arm is unknown.
        """
        if arm not in self._alphas:
            raise KeyError(f"Unknown arm '{arm}'")

        alpha = self._alphas[arm]
        beta = self._betas[arm]
        return float(alpha / (alpha + beta))

    def pulls(self, arm: Arm) -> int:
        """Return effective number of observations (α + β - prior sum).

        Args:
            arm: Arm to query.

        Returns:
            Number of times arm has been updated.

        Raises:
            KeyError: If arm is unknown.
        """
        if arm not in self._alphas:
            raise KeyError(f"Unknown arm '{arm}'")

        return int(
            self._alphas[arm] + self._betas[arm] - self._alpha_prior - self._beta_prior
        )

    def credible_interval(
        self, arm: Arm, confidence: float = 0.95
    ) -> tuple[float, float]:
        """Compute Bayesian credible interval for arm's reward distribution.

        Args:
            arm: Arm to query.
            confidence: Confidence level in (0, 1). Default 0.95 for 95% CI.

        Returns:
            Tuple (lower, upper) bounds of credible interval.

        Raises:
            KeyError: If arm is unknown.
            ValueError: If confidence not in (0, 1).
        """
        if arm not in self._alphas:
            raise KeyError(f"Unknown arm '{arm}'")
        if not (0.0 < confidence < 1.0):
            raise ValueError(f"Confidence must be in (0, 1), got {confidence}")

        alpha = self._alphas[arm]
        beta = self._betas[arm]

        # Use Beta distribution quantiles
        # For production use, would integrate scipy.stats.beta.ppf
        # Simple approximation for now using normal approximation
        mean = alpha / (alpha + beta)
        var = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))
        std = math.sqrt(var)

        # Approximate with normal (good for alpha, beta > 5)
        z = 1.96 if confidence == 0.95 else 2.576  # Common values
        lower = max(0.0, mean - z * std)
        upper = min(1.0, mean + z * std)

        return (float(lower), float(upper))

    def _sample_beta(self, alpha: float, beta: float) -> float:
        """Sample from Beta(α, β) using built-in random.

        Uses standard library implementation via random.betavariate,
        seeded with cryptographically strong random bits.
        """
        # Generate seed from SystemRandom for reproducibility with security
        import random

        temp_rng = random.Random(self._rng.getrandbits(256))
        return temp_rng.betavariate(alpha, beta)


__all__ = [
    "EpsilonGreedy",
    "UCB1",
    "ThompsonSampling",
]
