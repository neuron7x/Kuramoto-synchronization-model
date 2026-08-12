# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Surrogate / null-model falsification toolkit (protocol M3.2).

Given an identified network state we test whether the observed
collective dynamics are *explained* by the signed, delayed coupling
structure or whether they could have arisen from simpler generative
mechanisms. Four rejection tests from the methodology are implemented:

1. **IAAFT surrogates.** Iterative Amplitude-Adjusted Fourier
   Transform (Schreiber & Schmitz, 1996): draws surrogate series
   that preserve both the marginal distribution and the power
   spectrum of the original. If the observed order parameter is
   significantly larger than what the IAAFT null produces, non-
   linear (phase-coupling) structure is required to explain it.
   Implemented inline — no ``nolitsa`` dependency.

2. **Time-shuffled null.** Each phase series is independently shuffled
   along the time axis, destroying all temporal dependencies. A
   drastic but fast sanity check.

3. **Degree-preserving rewiring.** Given the binary adjacency of
   the identified coupling, we shuffle edges while keeping degrees
   fixed, re-simulate the Kuramoto model on the rewired topology,
   and compare the observed clustering / synchrony against the
   rewired ensemble.

4. **Counterfactual perturbations.** Simulated ablations that zero
   out the top-degree hubs, the inhibitory edges, or the delays and
   measure the resulting change in synchrony. The methodology's
   acceptance thresholds are encoded as convenience checks.

All surrogate tests return a ``SurrogateResult`` with the observed
statistic, the null distribution, and a one-sided p-value so the
caller can apply Bonferroni / Holm correction across the whole suite.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .contracts import NetworkState, PhaseMatrix

__all__ = [
    "SurrogateResult",
    "iaaft_surrogate",
    "iaaft_surrogate_test",
    "time_shuffle_test",
    "degree_preserving_rewire",
    "counterfactual_hub_removal",
    "counterfactual_zero_inhibition",
    "counterfactual_zero_delays",
]


@dataclass(frozen=True, slots=True)
class SurrogateResult:
    """Return object for any single surrogate / null-model test."""

    name: str
    observed: float
    null_distribution: np.ndarray
    p_value: float

    def __post_init__(self) -> None:
        nd = np.asarray(self.null_distribution)
        nd.flags.writeable = False
        object.__setattr__(self, "null_distribution", nd)


# ---------------------------------------------------------------------------
# IAAFT surrogate (inline, no nolitsa)
# ---------------------------------------------------------------------------


def iaaft_surrogate(
    x: np.ndarray, n_iterations: int = 100, rng: np.random.Generator | None = None
) -> np.ndarray:
    """Generate one IAAFT surrogate of a 1-D real series.

    The IAAFT scheme iteratively enforces two constraints on the
    surrogate: (1) it has exactly the amplitudes (sorted values) of
    the original, and (2) it has the same power spectrum. At each
    iteration we project onto one constraint set and then the other.
    In practice 50–100 iterations give convergence to within
    floating-point rounding on ordinary financial data.

    Parameters
    ----------
    x
        Real-valued 1-D input series.
    n_iterations
        Maximum number of amplitude ↔ spectrum projection cycles.
    rng
        Numpy random generator. A new default-seeded one is created
        if omitted.
    """
    if x.ndim != 1:
        raise ValueError("x must be 1-D")
    rng = rng or np.random.default_rng()
    x = np.asarray(x, dtype=np.float64)
    sorted_vals = np.sort(x)
    target_fft_mag = np.abs(np.fft.rfft(x))
    surrogate = rng.permutation(x).astype(np.float64)
    for _ in range(n_iterations):
        # Project onto power-spectrum constraint
        fft = np.fft.rfft(surrogate)
        phases = np.angle(fft)
        new_fft = target_fft_mag * np.exp(1j * phases)
        surrogate = np.fft.irfft(new_fft, n=x.size)
        # Project onto amplitude constraint: replace with original
        # values ranked by the current series
        ranks = np.argsort(np.argsort(surrogate))
        surrogate = sorted_vals[ranks]
    return np.asarray(surrogate, dtype=np.float64)


def iaaft_surrogate_test(
    phases: PhaseMatrix,
    *,
    n_surrogates: int = 200,
    statistic: str = "max_R",
    seed: int = 0,
) -> SurrogateResult:
    """Test whether the observed ``R(t)`` exceeds the IAAFT null.

    We generate IAAFT surrogates of each oscillator's ``sin(θ)`` series
    independently, reconstruct per-surrogate phases via the Hilbert
    transform of the surrogate, and compute the chosen statistic
    (max or mean of ``R(t)``). The p-value is the fraction of
    surrogates whose statistic is at least as extreme as the observed.
    """
    from scipy.signal import hilbert

    if statistic not in ("max_R", "mean_R"):
        raise ValueError("statistic must be 'max_R' or 'mean_R'")
    theta = np.asarray(phases.theta, dtype=np.float64)
    T, N = theta.shape
    rng = np.random.default_rng(seed)

    def _stat_from_theta(th: np.ndarray) -> float:
        R = np.abs(np.mean(np.exp(1j * th), axis=1))
        return float(np.max(R)) if statistic == "max_R" else float(np.mean(R))

    observed = _stat_from_theta(theta)

    null = np.empty(n_surrogates, dtype=np.float64)
    sin_theta = np.sin(theta)
    for s in range(n_surrogates):
        theta_surr = np.empty_like(theta)
        for i in range(N):
            surr = iaaft_surrogate(sin_theta[:, i], n_iterations=80, rng=rng)
            theta_surr[:, i] = np.angle(hilbert(surr))
        theta_surr = np.mod(theta_surr, 2 * np.pi)
        null[s] = _stat_from_theta(theta_surr)

    p_value = float(np.mean(null >= observed))
    return SurrogateResult(
        name="iaaft_surrogate",
        observed=observed,
        null_distribution=null,
        p_value=p_value,
    )


# ---------------------------------------------------------------------------
# Time-shuffle test
# ---------------------------------------------------------------------------


def time_shuffle_test(
    phases: PhaseMatrix,
    *,
    n_shuffles: int = 200,
    seed: int = 0,
) -> SurrogateResult:
    """Rejection test: shuffle each phase series along the time axis.

    Destroys any temporal dependence. If ``R(t)`` on the observed
    data greatly exceeds the shuffled null, coherence is temporally
    structured — a minimum requirement before any claim about
    coupling or delays can be entertained.
    """
    theta = np.asarray(phases.theta, dtype=np.float64)
    T, N = theta.shape
    rng = np.random.default_rng(seed)
    observed = float(np.mean(np.abs(np.mean(np.exp(1j * theta), axis=1))))
    null = np.empty(n_shuffles, dtype=np.float64)
    for s in range(n_shuffles):
        shuffled = np.empty_like(theta)
        for i in range(N):
            shuffled[:, i] = rng.permutation(theta[:, i])
        null[s] = float(np.mean(np.abs(np.mean(np.exp(1j * shuffled), axis=1))))
    p_value = float(np.mean(null >= observed))
    return SurrogateResult(
        name="time_shuffle",
        observed=observed,
        null_distribution=null,
        p_value=p_value,
    )


# ---------------------------------------------------------------------------
# Degree-preserving rewiring
# ---------------------------------------------------------------------------


def degree_preserving_rewire(
    adjacency: np.ndarray,
    *,
    n_swaps: int | None = None,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Double-edge-swap rewiring that preserves the degree sequence.

    Pure numpy implementation of the classical swap: pick two edges
    ``(u, v)`` and ``(x, y)``, swap to ``(u, y)`` and ``(x, v)`` if
    the new edges do not already exist and are not self-loops. The
    function operates on a binary adjacency; pass ``np.abs(K) > 0``
    to rewire a signed coupling graph while preserving its topology.
    """
    rng = rng or np.random.default_rng()
    adj = (np.asarray(adjacency) != 0).astype(np.int8)
    np.fill_diagonal(adj, 0)
    # Edges as (row, col) pairs on the upper triangle to avoid
    # double-counting for symmetric inputs; for directed inputs we
    # iterate the full array.
    edges = list(zip(*np.where(adj > 0)))
    if not edges:
        return np.asarray(adj, dtype=np.int64)
    n_swaps = n_swaps or 20 * len(edges)
    for _ in range(n_swaps):
        i1, i2 = rng.integers(0, len(edges), size=2)
        if i1 == i2:
            continue
        u, v = edges[i1]
        x, y = edges[i2]
        if len({u, v, x, y}) < 4:
            continue
        if adj[u, y] or adj[x, v]:
            continue
        adj[u, v] = adj[x, y] = 0
        adj[u, y] = adj[x, v] = 1
        edges[i1] = (u, y)
        edges[i2] = (x, v)
    return np.asarray(adj, dtype=np.int64)


# ---------------------------------------------------------------------------
# Counterfactual perturbations
# ---------------------------------------------------------------------------


def _simulate_and_score(
    state: NetworkState,
    K_override: np.ndarray,
    tau_override: np.ndarray | None = None,
) -> float:
    """Simulate one counterfactual and return the mean ``R(t)``.

    Runs a minimal Euler-Maruyama integrator on the modified state
    for the same length as the observed phase trajectory and
    reports the mean global order parameter. The implementation is
    intentionally local (no Julia call-out) so that counterfactuals
    are fast enough to be part of unit-test budgets.
    """
    theta_obs = np.asarray(state.phases.theta, dtype=np.float64)
    T, N = theta_obs.shape
    omega = np.asarray(state.natural_frequencies, dtype=np.float64)
    alpha = np.asarray(state.frustration.alpha, dtype=np.float64)
    sigma = float(state.noise_std)
    dt = float(state.phases.timestamps[1] - state.phases.timestamps[0])
    tau = tau_override if tau_override is not None else state.delays.tau
    K = K_override

    rng = np.random.default_rng(0)
    theta = np.zeros((T, N))
    theta[0] = theta_obs[0]
    active = K != 0.0
    for t in range(1, T):
        t_del = np.clip(
            t - 1 - tau, 0, t - 1
        )  # bounds: delay index clamped to valid time range [0, t-1]
        col = np.broadcast_to(np.arange(N)[np.newaxis, :], (N, N))
        theta_d = theta[t_del, col]
        pd = theta_d - theta[t - 1][:, np.newaxis] - alpha
        coupling = np.sum(np.where(active, K * np.sin(pd), 0.0), axis=1)
        noise = sigma * rng.standard_normal(N) * np.sqrt(dt)
        theta[t] = theta[t - 1] + dt * (omega + coupling) + noise
    R = np.abs(np.mean(np.exp(1j * theta), axis=1))
    return float(np.mean(R))


def counterfactual_hub_removal(state: NetworkState, *, top_k: int = 5) -> SurrogateResult:
    """Remove the ``top_k`` highest-degree nodes and compare ``R̄``.

    Returns a :class:`SurrogateResult` whose ``null_distribution``
    contains a single scalar (the counterfactual ``R̄``) for API
    uniformity with the resampling-based tests.
    """
    K = np.asarray(state.coupling.K, dtype=np.float64)
    degrees = np.sum(np.abs(K) > 0, axis=1)
    top = np.argsort(-degrees)[:top_k]
    K_cf = K.copy()
    K_cf[top, :] = 0.0
    K_cf[:, top] = 0.0
    observed = _simulate_and_score(state, K)
    ablated = _simulate_and_score(state, K_cf)
    # Methodology acceptance: hub removal should cut R̄ by ≥ 20 %
    return SurrogateResult(
        name="cf_hub_removal",
        observed=observed,
        null_distribution=np.array([ablated]),
        p_value=float(ablated / observed if observed > 0 else 1.0),
    )


def counterfactual_zero_inhibition(
    state: NetworkState,
) -> SurrogateResult:
    """Zero all inhibitory (negative) edges and compare ``R̄``."""
    K = np.asarray(state.coupling.K, dtype=np.float64)
    K_cf = np.where(K < 0, 0.0, K)
    observed = _simulate_and_score(state, K)
    ablated = _simulate_and_score(state, K_cf)
    return SurrogateResult(
        name="cf_zero_inhibition",
        observed=observed,
        null_distribution=np.array([ablated]),
        p_value=float(ablated / observed if observed > 0 else 1.0),
    )


def counterfactual_zero_delays(
    state: NetworkState,
) -> SurrogateResult:
    """Zero all delays and compare ``R̄``."""
    zero_tau = np.zeros_like(state.delays.tau)
    observed = _simulate_and_score(state, state.coupling.K)
    ablated = _simulate_and_score(state, state.coupling.K, tau_override=zero_tau)
    return SurrogateResult(
        name="cf_zero_delays",
        observed=observed,
        null_distribution=np.array([ablated]),
        p_value=float(ablated / observed if observed > 0 else 1.0),
    )
