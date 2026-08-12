# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""NetworkKuramotoFeature — trading-pipeline adapter (protocol M3.4).

Two-tier latency model
----------------------
* **Tier 1 (online).** Fast per-bar inference path: phase refresh
  on a rolling window, order-parameter update, cached cluster order
  lookups, incremental CSD statistics, feature dict assembly. Target
  latency < 10 ms for ``N = 50``. No estimator re-fits.
* **Tier 2 (batch).** Heavy periodic recalibration:
  :class:`~core.kuramoto.network_engine.NetworkKuramotoEngine.identify`
  runs end-to-end, writes a new :class:`NetworkState` into the
  feature, and the online path atomically picks it up on the next
  bar. Frequency is caller-controlled (daily / weekly / monthly).

The online path reads the cached state through a read-only reference;
because :class:`NetworkState` is a frozen, deeply immutable dataclass,
there is no locking required — writers swap the reference in one
atomic assignment.

Feature vocabulary
------------------
The feature dict is flat and stable so downstream signal-generator
code can bind to well-known keys:

- ``kuramoto_R_global`` — latest global order parameter.
- ``kuramoto_R_derivative`` — bar-over-bar change in ``R``.
- ``kuramoto_metastability`` — rolling variance of ``R``.
- ``kuramoto_n_clusters`` — number of detected communities.
- ``kuramoto_chimera_index`` — latest chimera index.
- ``kuramoto_max_cluster_R`` — max cluster coherence.
- ``kuramoto_csd_variance`` / ``kuramoto_csd_autocorr`` —
  critical-slowing-down indicators at the latest bar.
- ``kuramoto_coupling_density`` — fraction of non-zero edges.
- ``kuramoto_inhibition_ratio`` — fraction of inhibitory edges.
- ``kuramoto_R_cluster_{c}`` — per-cluster order parameter.
- ``kuramoto_calibration_age_bars`` — number of bars since the last
  batch recalibration (0 on the bar calibration was applied).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque

import numpy as np

from .contracts import NetworkState
from .network_engine import NetworkEngineConfig, NetworkKuramotoEngine
from .phase_extractor import PhaseExtractionConfig

__all__ = [
    "FeatureConfig",
    "NetworkKuramotoFeature",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FeatureConfig:
    """Runtime configuration for the streaming feature adapter.

    Attributes
    ----------
    window : int
        Length of the rolling bar buffer used for online phase
        extraction. The full buffer is re-Hilbert-ed on every bar
        (cheap for ``window ≤ 500`` and ``N ≤ 50``).
    csd_buffer : int
        Depth of the rolling ``R(t)`` buffer used for the online CSD
        estimates.
    phase_config : PhaseExtractionConfig
        Configuration handed to the online phase extractor.
    engine_config : NetworkEngineConfig
        Configuration used by the batch recalibration engine.
    """

    window: int = 200
    csd_buffer: int = 100
    phase_config: PhaseExtractionConfig = PhaseExtractionConfig(
        fs=1.0, f_low=0.05, f_high=0.4, detrend_window=None
    )
    engine_config: NetworkEngineConfig = NetworkEngineConfig()

    def __post_init__(self) -> None:
        if self.window < 32:
            raise ValueError("window must be ≥ 32 for the Butterworth filter")
        if self.csd_buffer < 2:
            raise ValueError("csd_buffer must be ≥ 2")


# ---------------------------------------------------------------------------
# Feature adapter
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class NetworkKuramotoFeature:
    """Two-tier feature generator for the trading pipeline.

    Usage
    -----
    >>> feat = NetworkKuramotoFeature(asset_ids=("AAPL", "MSFT", "GOOG"))
    >>> # Prime the rolling buffer with historical bars first
    >>> feat.warmup(hist_returns)
    >>> # Periodically run batch recalibration (e.g. end-of-day)
    >>> feat.recalibrate(batch_returns, batch_timestamps)
    >>> # Per-bar online inference (hot path)
    >>> features = feat.update(latest_returns_row, latest_timestamp)
    """

    asset_ids: tuple[str, ...]
    config: FeatureConfig = field(default_factory=FeatureConfig)
    _buffer: Deque[np.ndarray] = field(init=False, repr=False)
    _timestamps: Deque[float] = field(init=False, repr=False)
    _state: NetworkState | None = field(default=None, init=False, repr=False)
    _R_history: Deque[float] = field(init=False, repr=False)
    _last_calibration_bar: int = field(default=-1, init=False, repr=False)
    _bar_count: int = field(default=0, init=False, repr=False)
    _engine: NetworkKuramotoEngine = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._buffer = deque(maxlen=self.config.window)
        self._timestamps = deque(maxlen=self.config.window)
        self._R_history = deque(maxlen=self.config.csd_buffer)
        self._engine = NetworkKuramotoEngine(self.config.engine_config)

    # ------------------------------------------------------------------
    # Warmup
    # ------------------------------------------------------------------
    def warmup(self, returns: np.ndarray) -> None:
        """Preload the rolling buffer with historical bars.

        ``returns`` must have shape ``(T, N)`` with ``N == len(asset_ids)``.
        Only the trailing ``window`` rows are kept.
        """
        if returns.ndim != 2 or returns.shape[1] != len(self.asset_ids):
            raise ValueError(
                f"returns must be shape (T, {len(self.asset_ids)}); got {returns.shape}"
            )
        for row in returns[-self.config.window :]:
            self._buffer.append(np.asarray(row, dtype=np.float64))
            self._timestamps.append(float(len(self._buffer)))
            self._bar_count += 1

    # ------------------------------------------------------------------
    # Tier 2 — batch recalibration (cold path)
    # ------------------------------------------------------------------
    def recalibrate(
        self,
        returns: np.ndarray,
        timestamps: np.ndarray,
    ) -> None:
        """Run the full engine on ``returns`` and swap in the new state.

        ``returns`` should span enough history to give the estimators
        statistical power — typically 5–10× the rolling buffer size
        used by the online path.
        """
        report = self._engine.identify_from_returns(
            returns=returns, asset_ids=self.asset_ids, timestamps=timestamps
        )
        # Atomic swap (frozen state — single reference assignment)
        self._state = report.state
        self._last_calibration_bar = self._bar_count

    # ------------------------------------------------------------------
    # Tier 1 — per-bar online update (hot path)
    # ------------------------------------------------------------------
    def update(self, returns_row: np.ndarray, timestamp: float) -> dict[str, float]:
        """Append one bar and return the feature dictionary.

        The hot path does:
        1. push the new row into the rolling buffer;
        2. Hilbert-transform the buffered return series to recover
           phases;
        3. compute ``R_global``, per-cluster ``R`` (using cached
           cluster labels), chimera index, CSD indicators;
        4. assemble and return the feature dict.
        """
        if returns_row.shape != (len(self.asset_ids),):
            raise ValueError(
                f"returns_row must have shape ({len(self.asset_ids)},); got {returns_row.shape}"
            )
        self._buffer.append(np.asarray(returns_row, dtype=np.float64))
        self._timestamps.append(float(timestamp))
        self._bar_count += 1

        if self._state is None:
            # Without a calibrated state we can only report the raw
            # order parameter; cluster-level features are not yet
            # defined. This lets the pipeline survive the cold start.
            theta_now = self._phases_from_buffer()
            if theta_now is None:
                return {}
            R_global = float(np.abs(np.mean(np.exp(1j * theta_now[-1]))))
            self._R_history.append(R_global)
            return {
                "kuramoto_R_global": R_global,
                "kuramoto_calibration_age_bars": float("nan"),
            }

        theta_now = self._phases_from_buffer()
        if theta_now is None:
            return {}
        latest_theta = theta_now[-1]
        R_global = float(np.abs(np.mean(np.exp(1j * latest_theta))))
        self._R_history.append(R_global)

        cluster_assignments = self._current_cluster_assignments()
        R_clusters: dict[int, float] = {}
        if cluster_assignments is not None:
            for c in np.unique(cluster_assignments):
                mask = cluster_assignments == c
                if mask.any():
                    R_clusters[int(c)] = float(np.abs(np.mean(np.exp(1j * latest_theta[mask]))))

        # Chimera: variance of cluster-level R at this bar
        chimera = float(np.var(list(R_clusters.values()))) if len(R_clusters) >= 2 else 0.0

        # CSD from rolling R history
        R_hist = np.array(self._R_history, dtype=np.float64)
        if R_hist.size >= 3:
            csd_var = float(np.var(R_hist, ddof=0))
            # lag-1 autocorr
            a = R_hist[:-1] - R_hist[:-1].mean()
            b = R_hist[1:] - R_hist[1:].mean()
            denom = float(np.sqrt(np.dot(a, a) * np.dot(b, b)))
            csd_ac = float(np.dot(a, b) / denom) if denom > 0 else 0.0
        else:
            csd_var = 0.0
            csd_ac = 0.0

        R_deriv = R_global - float(self._R_history[-2]) if len(self._R_history) >= 2 else 0.0

        out: dict[str, float] = {
            "kuramoto_R_global": R_global,
            "kuramoto_R_derivative": R_deriv,
            "kuramoto_metastability": csd_var,
            "kuramoto_n_clusters": float(len(R_clusters)),
            "kuramoto_chimera_index": chimera,
            "kuramoto_max_cluster_R": max(R_clusters.values()) if R_clusters else 0.0,
            "kuramoto_csd_variance": csd_var,
            "kuramoto_csd_autocorr": csd_ac,
            "kuramoto_coupling_density": 1.0 - float(self._state.coupling.sparsity),
            "kuramoto_inhibition_ratio": float(np.mean(self._state.coupling.K < 0.0)),
            "kuramoto_calibration_age_bars": float(self._bar_count - self._last_calibration_bar),
        }
        for c, r in R_clusters.items():
            out[f"kuramoto_R_cluster_{c}"] = r
        return out

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _phases_from_buffer(self) -> np.ndarray | None:
        """Hilbert-transform the buffered returns into wrapped phases."""
        if len(self._buffer) < self.config.window:
            return None
        buf = np.stack(list(self._buffer), axis=0)
        # Bandpass via FFT then Hilbert — cheap in this size regime
        from .phase_extractor import extract_phases_hilbert

        theta, _ = extract_phases_hilbert(buf, self.config.phase_config)
        return theta

    def _current_cluster_assignments(self) -> np.ndarray | None:
        """Derive cluster labels from the currently cached state.

        We re-run the lightweight signed-community detector on the
        cached ``K`` matrix (cheap — O(N³) with small constant for
        N ≤ 50) so the feature dict exposes stable cluster indices
        even if the downstream metric pipeline is not invoked.
        """
        if self._state is None:
            return None
        from .metrics import signed_communities

        return signed_communities(self._state.coupling.K)
