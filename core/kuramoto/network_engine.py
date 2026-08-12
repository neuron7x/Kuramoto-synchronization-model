# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""NetworkKuramotoEngine orchestrator.

Wires the six identification stages (phase extraction → natural
frequency → sparse coupling → delays → frustration → metrics) into a
single entry point that turns raw market data into a fully populated
:class:`~core.kuramoto.contracts.NetworkState` plus emergent metrics.

Design
------
* **Stage independence.** Each stage is a separate, fully-typed module
  that can be unit-tested in isolation; the engine only composes
  them. If any stage is swapped out (e.g. SCAD → Lasso, profile
  likelihood → Bayesian MCMC), only this file changes.
* **Frozen state output.** Every object the engine returns is a
  ``frozen=True, slots=True`` dataclass with deeply immutable array
  fields. Downstream consumers (trading feature adapter,
  falsification suite, OOS validator) can cache, share, and swap
  states atomically.
* **Reproducibility.** All randomness flows through explicit
  ``random_state`` seeds on the underlying estimator configs — no
  hidden global state. The orchestrator itself is deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .contracts import (
    CouplingMatrix,
    DelayMatrix,
    EmergentMetrics,
    FrustrationMatrix,
    NetworkState,
    PhaseMatrix,
)
from .coupling_estimator import (
    CouplingEstimationConfig,
    CouplingEstimator,
)
from .delay_estimator import DelayEstimationConfig, DelayEstimator
from .frustration import FrustrationEstimationConfig, FrustrationEstimator
from .metrics import MetricsConfig, compute_metrics
from .natural_frequency import (
    NaturalFrequencyMethod,
    estimate_natural_frequencies,
)
from .phase_extractor import PhaseExtractionConfig, PhaseExtractor

__all__ = [
    "NetworkEngineConfig",
    "NetworkEngineReport",
    "NetworkKuramotoEngine",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NetworkEngineConfig:
    """One container for every sub-estimator's configuration.

    The defaults are production-ready for daily or intraday financial
    data. The individual configs can be overridden field-by-field for
    hyperparameter sweeps or walk-forward validation.
    """

    phase: PhaseExtractionConfig = PhaseExtractionConfig()
    coupling: CouplingEstimationConfig = CouplingEstimationConfig(
        penalty="mcp", lambda_reg=0.1, max_iter=1000, tol=1e-6
    )
    delay: DelayEstimationConfig = DelayEstimationConfig(max_lag=5, method="joint")
    frustration: FrustrationEstimationConfig = FrustrationEstimationConfig()
    metrics: MetricsConfig = MetricsConfig()
    natural_frequency_method: NaturalFrequencyMethod = "median"
    phase_method: str = "hilbert"


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NetworkEngineReport:
    """Full output of :meth:`NetworkKuramotoEngine.identify`.

    Attributes
    ----------
    state
        The identified :class:`NetworkState` — the object consumed
        by the simulation engine (``SE.1``) and cached by the
        trading feature adapter (``M3.4``).
    metrics
        :class:`EmergentMetrics` computed from the identified state.
    """

    state: NetworkState
    metrics: EmergentMetrics


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class NetworkKuramotoEngine:
    """End-to-end identification of the Sakaguchi–Kuramoto network.

    Example
    -------
    >>> engine = NetworkKuramotoEngine()
    >>> report = engine.identify_from_returns(
    ...     returns=log_returns,
    ...     asset_ids=("AAPL", "MSFT", "GOOG", "META", "AMZN"),
    ...     timestamps=ts,
    ... )
    >>> report.state.coupling.K.shape
    (5, 5)
    >>> report.metrics.R_global[-1]
    0.73
    """

    def __init__(self, config: NetworkEngineConfig | None = None) -> None:
        self.config = config or NetworkEngineConfig()
        self._phase = PhaseExtractor(self.config.phase)
        self._coupling = CouplingEstimator(self.config.coupling)
        self._delay = DelayEstimator(self.config.delay)
        self._frustration = FrustrationEstimator(self.config.frustration)

    # ------------------------------------------------------------------
    # Core path: run the full pipeline starting from an already-computed
    # :class:`PhaseMatrix`. Useful when the caller maintains its own
    # phase buffer or wants to cache phases across calls.
    # ------------------------------------------------------------------
    def identify(self, phases: PhaseMatrix) -> NetworkEngineReport:
        """Run the full pipeline on a pre-extracted phase matrix.

        A genuine asset-network Sakaguchi–Kuramoto model requires at least
        two oscillators (``N ≥ 2``); a single series yields a degenerate
        ``1×1`` "network" with no inter-asset coupling to identify. The
        guard is fail-closed: ``N < 2`` raises ``ValueError`` rather than
        returning a meaningless one-node state. For the single-series
        cross-scale phase-coherence descriptor use
        :class:`core.indicators.multiscale_kuramoto.MultiScaleKuramoto`.
        """
        if phases.N < 2:
            raise ValueError(
                f"NetworkKuramotoEngine requires N ≥ 2 oscillators; got N={phases.N}. "
                "A single series has no asset-network coupling to identify; use the "
                "single-series descriptor core.indicators.multiscale_kuramoto instead."
            )
        cfg = self.config
        dt = float(phases.timestamps[1] - phases.timestamps[0])

        coupling: CouplingMatrix = self._coupling.estimate(phases)
        delays: DelayMatrix = self._delay.estimate(phases, coupling)
        frustration: FrustrationMatrix = self._frustration.estimate(phases, coupling, delays)
        omega = estimate_natural_frequencies(phases, method=cfg.natural_frequency_method, dt=dt)

        # Noise std estimate: residual of the coupling model.
        noise_std = self._estimate_noise_std(phases, coupling, delays, frustration, omega, dt)

        state = NetworkState(
            phases=phases,
            coupling=coupling,
            delays=delays,
            frustration=frustration,
            natural_frequencies=omega,
            noise_std=noise_std,
        )
        metrics = compute_metrics(phases, coupling, config=cfg.metrics)
        return NetworkEngineReport(state=state, metrics=metrics)

    # ------------------------------------------------------------------
    # Convenience entry: raw returns → report.
    # ------------------------------------------------------------------
    def identify_from_returns(
        self,
        returns: np.ndarray,
        asset_ids: tuple[str, ...],
        timestamps: np.ndarray,
    ) -> NetworkEngineReport:
        """End-to-end: extract phases from log-returns, then identify.

        ``returns`` must have shape ``(T, N)`` with ``N ≥ 2``. A single
        series (``N < 2``) cannot instantiate an asset-network model and is
        rejected fail-closed before phase extraction; use the single-series
        descriptor :mod:`core.indicators.multiscale_kuramoto` instead. The
        phase extractor is called with the configured method (default:
        Hilbert).
        """
        returns_arr = np.asarray(returns)
        n_assets = int(returns_arr.shape[1]) if returns_arr.ndim == 2 else returns_arr.ndim
        if returns_arr.ndim != 2 or n_assets < 2:
            raise ValueError(
                "NetworkKuramotoEngine.identify_from_returns requires a 2-D returns "
                f"array of shape (T, N) with N ≥ 2; got shape {returns_arr.shape}. "
                "A single series has no asset-network coupling to identify; use the "
                "single-series descriptor core.indicators.multiscale_kuramoto instead."
            )
        phases = self._phase.extract(
            signal=returns,
            asset_ids=asset_ids,
            timestamps=timestamps,
            method=self.config.phase_method,
        )
        return self.identify(phases)

    # ------------------------------------------------------------------
    # Noise standard deviation estimate
    # ------------------------------------------------------------------
    @staticmethod
    def _estimate_noise_std(
        phases: PhaseMatrix,
        coupling: CouplingMatrix,
        delays: DelayMatrix,
        frustration: FrustrationMatrix,
        omega: np.ndarray,
        dt: float,
    ) -> float:
        """Root-mean-square residual of the full identified model.

        For every oscillator ``i`` we reconstruct the predicted
        increment at each step from the full right-hand side of the
        Sakaguchi–Kuramoto equation and return the overall RMS of
        ``y_i(t) − ŷ_i(t)`` (scaled by ``√dt`` to match the
        Euler–Maruyama diffusion coefficient).
        """
        theta = np.asarray(phases.theta, dtype=np.float64)
        K = np.asarray(coupling.K, dtype=np.float64)
        tau = np.asarray(delays.tau, dtype=np.int64)
        alpha = np.asarray(frustration.alpha, dtype=np.float64)
        T, N = theta.shape
        unwrapped = np.unwrap(theta, axis=0)
        diffs = np.diff(unwrapped, axis=0) / dt  # (T-1, N), observed θ̇
        max_lag = int(tau.max()) if tau.size else 0
        if max_lag >= T - 1:
            return 0.0
        residuals: list[float] = []
        for t in range(max_lag, T - 1):
            pred = np.zeros(N)
            for i in range(N):
                acc = float(omega[i])
                for j in range(N):
                    if K[i, j] == 0.0:
                        continue
                    t_d = t - int(tau[i, j])
                    acc += float(K[i, j] * np.sin(theta[t_d, j] - theta[t, i] - alpha[i, j]))
                pred[i] = acc
            residuals.append(float(np.mean((diffs[t] - pred) ** 2)))
        if not residuals:
            return 0.0
        rms = float(np.sqrt(np.mean(residuals)))
        # Convert drift residual to diffusion coefficient: residual
        # variance per unit time is σ². Multiply by √dt to align with
        # Euler–Maruyama noise scaling σ·√dt.
        return rms * float(np.sqrt(dt))
