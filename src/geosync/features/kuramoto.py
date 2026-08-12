# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Kuramoto-style synchrony *descriptor* for GeoSync Neuro-Architecture.

Honesty boundary (read before consuming the output)
---------------------------------------------------
This adapter does **not** compute an analytic-signal (Hilbert) instantaneous
phase. It computes a heuristic per-asset proxy angle

    θ_proxy = arctan2(rolling_std(returns), rolling_mean(returns))

over a rolling window, then builds the Kuramoto-form order parameter
``R = |⟨exp(iθ_proxy)⟩|`` and assigns rolling descriptor labels
(``EMERGENT`` / ``CHAOTIC`` / ``TRANSITION`` / ``CAUTION``). The angle is a
std-over-mean *descriptor*, not a physical oscillator phase, so:

* ``R`` here is a **descriptor synchrony of the proxy angles**, NOT a validated
  physical Kuramoto order parameter. The validated analytic-phase path lives in
  ``core/kuramoto/phase_extractor.py`` and is a different code path.
* the regime labels are **descriptor regimes** of that proxy synchrony, NOT
  asserted physical states of a synchronizing oscillator ensemble.

To make this auditable rather than docstring-only, every emitted result carries
machine-readable provenance: ``proxy=True``,
``phase_method="arctan2_std_mean_proxy"``,
``claim_boundary="descriptor_proxy_not_physical_phase"``,
``regime_kind="descriptor_regime"``, and ``information_loss`` recording what the
proxy angle discards relative to a true analytic-signal phase. A consumer can
therefore not silently read ``R`` / the labels as a physical Kuramoto phase.

This descriptor promotes no claim tier, adds no invariant, and asserts no
predictive or financial meaning. Numeric output (``R``, ``delta_R``,
``labels``) is unchanged from the prior implementation; the provenance is
additive and defaulted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from pandas import DataFrame, Series

__all__ = ["KuramotoSynchrony", "KuramotoResult"]

# --- Provenance constants for the proxy descriptor -------------------------
# These are CONSTANTS for this estimator, not tunable outputs. They declare the
# honesty boundary on the emitted result so the proxy synchrony cannot be
# mistaken for the validated analytic-phase Kuramoto path in
# ``core/kuramoto/phase_extractor.py``.
PROXY_PHASE_METHOD = "arctan2_std_mean_proxy"
PROXY_CLAIM_BOUNDARY = "descriptor_proxy_not_physical_phase"
PROXY_REGIME_KIND = "descriptor_regime"
PROXY_INFORMATION_LOSS = (
    "analytic_signal_instantaneous_phase",
    "phase_unwrapping",
    "oscillator_frequency",
)
# Downstream claim status (issue #1107). These travel with the result so a
# consumer cannot read the proxy synchrony as predictive, tradeable, or
# validated. ``validation_status`` is the single token a downstream feature
# pipeline checks before any signal use: it is NEVER "validated" for this proxy.
PROXY_PREDICTIVE_CLAIM = False
PROXY_TRADING_CLAIM = False
PROXY_VALIDATION_STATUS = "descriptor_only"


@dataclass(frozen=True, slots=True)
class KuramotoResult:
    """Result from the Kuramoto-style synchrony *descriptor*.

    The provenance fields make the representation honest and machine-auditable:
    the per-asset angle is the ``arctan2(rolling_std, rolling_mean)`` proxy, so
    ``R`` is a descriptor synchrony (``proxy=True``) and the labels are
    descriptor regimes (``regime_kind="descriptor_regime"``), NOT a physical
    Kuramoto phase. They are constants for this estimator, not tunable outputs.

    Attributes
    ----------
    R : Series
        Descriptor order parameter over time (proxy synchrony of the angles,
        0-1). NOT a validated physical Kuramoto order parameter.
    delta_R : Series
        Change in the descriptor order parameter (ΔR) for regime detection.
    labels : Series
        Descriptor regime labels (CHAOTIC, EMERGENT, TRANSITION, CAUTION) of the
        proxy synchrony — NOT asserted physical oscillator states.
    proxy : bool
        Always ``True``: this is a heuristic proxy, not an analytic-signal phase.
    phase_method : str
        How the per-asset angle is computed (``arctan2_std_mean_proxy``).
    claim_boundary : str
        The honesty boundary token (``descriptor_proxy_not_physical_phase``).
    regime_kind : str
        Kind of the ``labels`` field (``descriptor_regime``).
    information_loss : tuple[str, ...]
        What the proxy angle discards relative to a true analytic-signal phase.
    predictive_claim : bool
        Always ``False``: this descriptor asserts no predictive validity.
    trading_claim : bool
        Always ``False``: this descriptor is not a trading signal.
    validation_status : str
        Always ``"descriptor_only"`` — never "validated"; a downstream consumer
        must treat it as unvalidated provenance, not a signal.
    """

    R: Series
    delta_R: Series
    labels: Series
    proxy: bool = True
    phase_method: str = PROXY_PHASE_METHOD
    claim_boundary: str = PROXY_CLAIM_BOUNDARY
    regime_kind: str = PROXY_REGIME_KIND
    information_loss: tuple[str, ...] = PROXY_INFORMATION_LOSS
    predictive_claim: bool = PROXY_PREDICTIVE_CLAIM
    trading_claim: bool = PROXY_TRADING_CLAIM
    validation_status: str = PROXY_VALIDATION_STATUS


class KuramotoSynchrony:
    """Kuramoto-style synchrony *descriptor* over a std/mean proxy angle.

    This adapter computes a heuristic proxy angle
    ``arctan2(rolling_std, rolling_mean)`` per asset and forms the Kuramoto
    order parameter over those angles. It is a descriptor, NOT the validated
    analytic-signal phase path (see ``core/kuramoto/phase_extractor.py``). Every
    emitted result declares this boundary via provenance fields
    (``proxy=True`` / ``claim_boundary="descriptor_proxy_not_physical_phase"``).

    Parameters
    ----------
    window : int, optional
        Rolling window size for computing the proxy angle, by default 30
    lag : int, optional
        Lag for computing ΔR (change in descriptor synchrony), by default 3
    R_threshold_high : float, optional
        Threshold for the EMERGENT descriptor regime, by default 0.7
    R_threshold_low : float, optional
        Threshold below which is the CHAOTIC descriptor regime, by default 0.4
    """

    def __init__(
        self,
        window: int = 30,
        lag: int = 3,
        R_threshold_high: float = 0.7,
        R_threshold_low: float = 0.4,
    ):
        self.window = window
        self.lag = lag
        self.R_high = R_threshold_high
        self.R_low = R_threshold_low

    def fit_transform(self, prices: DataFrame) -> dict[str, object]:
        """Compute the Kuramoto-style synchrony descriptor from price data.

        Parameters
        ----------
        prices : DataFrame
            Price data with shape (T, N) where T is time steps and N is assets.
            Index should be DatetimeIndex.

        Returns
        -------
        dict
            Dictionary with keys:
            - 'R': Series of descriptor order parameter values
            - 'delta_R': Series of ΔR values
            - 'labels': Series of descriptor regime labels
            - 'proxy': True (heuristic proxy, not analytic-signal phase)
            - 'phase_method': 'arctan2_std_mean_proxy'
            - 'claim_boundary': 'descriptor_proxy_not_physical_phase'
            - 'regime_kind': 'descriptor_regime'
            - 'information_loss': tuple of discarded analytic-phase information

        The ``R`` / ``delta_R`` / ``labels`` values are numerically unchanged
        from the prior implementation; the provenance keys are additive so a
        consumer cannot read ``R`` / the labels as a physical Kuramoto phase.
        """
        if not isinstance(prices.index, pd.DatetimeIndex):
            raise ValueError("prices must have DatetimeIndex")

        if len(prices) < self.window:
            raise ValueError(
                f"Insufficient data: need at least {self.window} points, got {len(prices)}"
            )

        # Compute returns
        returns = prices.pct_change().fillna(0.0)

        # Compute proxy angles for each asset (NOT analytic-signal phases)
        phases = self._compute_phases(returns)

        # Compute Kuramoto-form descriptor order parameter R(t)
        R = self._compute_order_parameter(phases)

        # Compute ΔR
        delta_R = R.diff(self.lag).fillna(0.0)

        # Assign descriptor regime labels based on adaptive thresholds
        labels = self._assign_labels(R, delta_R)

        return {
            "R": R,
            "delta_R": delta_R,
            "labels": labels,
            "proxy": True,
            "phase_method": PROXY_PHASE_METHOD,
            "claim_boundary": PROXY_CLAIM_BOUNDARY,
            "regime_kind": PROXY_REGIME_KIND,
            "information_loss": PROXY_INFORMATION_LOSS,
            "predictive_claim": PROXY_PREDICTIVE_CLAIM,
            "trading_claim": PROXY_TRADING_CLAIM,
            "validation_status": PROXY_VALIDATION_STATUS,
        }

    def result(self, prices: DataFrame) -> KuramotoResult:
        """Compute the descriptor and return it as a provenance-bearing result.

        Identical numeric computation to :meth:`fit_transform`, wrapped in a
        :class:`KuramotoResult` so the proxy / claim-boundary provenance travels
        with ``R`` / ``delta_R`` / ``labels`` as a single typed object.
        """
        out = self.fit_transform(prices)
        R = out["R"]
        delta_R = out["delta_R"]
        labels = out["labels"]
        assert isinstance(R, pd.Series)
        assert isinstance(delta_R, pd.Series)
        assert isinstance(labels, pd.Series)
        return KuramotoResult(R=R, delta_R=delta_R, labels=labels)

    def _compute_phases(self, returns: DataFrame) -> DataFrame:
        """Compute the per-asset proxy angle (NOT an analytic-signal phase).

        ``θ_proxy = arctan2(rolling_std(returns), rolling_mean(returns))``. This
        is a std-over-mean descriptor of the rolling return distribution, not a
        Hilbert instantaneous phase; the validated analytic-phase extractor is
        ``core/kuramoto/phase_extractor.py``.
        """
        phases = np.arctan2(
            returns.rolling(self.window, min_periods=self.window // 2).std(),
            returns.rolling(self.window, min_periods=self.window // 2).mean(),
        )
        return phases.fillna(0.0)

    def _compute_order_parameter(self, phases: DataFrame) -> Series:
        """Compute the Kuramoto-form order parameter over the proxy angles.

        R = |⟨exp(iθ_proxy)⟩| where ⟨⟩ is the mean over assets. Because θ_proxy
        is a descriptor angle (see :meth:`_compute_phases`), this ``R`` is a
        descriptor synchrony, not a validated physical Kuramoto order parameter.
        """
        # Complex representation of the proxy angles
        complex_phases = np.exp(1j * phases.values)

        # Mean over assets (axis=1)
        mean_complex = complex_phases.mean(axis=1)

        # Magnitude is the descriptor order parameter
        R = np.abs(mean_complex)

        return pd.Series(R, index=phases.index, name="R")

    def _assign_labels(self, R: Series, delta_R: Series) -> Series:
        """Assign descriptor regime labels based on R and ΔR.

        Uses adaptive thresholds based on rolling median and IQR. The labels
        (EMERGENT / CHAOTIC / TRANSITION / CAUTION) are descriptor regimes of
        the proxy synchrony, NOT asserted physical oscillator states.
        """
        labels = pd.Series("CAUTION", index=R.index, dtype=str)

        # Adaptive thresholds using rolling statistics
        R_median = R.rolling(self.window * 3, min_periods=self.window).median()
        R_iqr = R.rolling(self.window * 3, min_periods=self.window).quantile(0.75) - R.rolling(
            self.window * 3, min_periods=self.window
        ).quantile(0.25)

        # Use fixed thresholds initially, then adaptive
        R_high_adaptive = R_median + R_iqr
        R_low_adaptive = R_median - R_iqr

        # Fill NaN in adaptive thresholds with fixed thresholds
        R_high_adaptive = R_high_adaptive.fillna(self.R_high)
        R_low_adaptive = R_low_adaptive.fillna(self.R_low)

        # Assign descriptor regime labels
        labels.loc[R > R_high_adaptive] = "EMERGENT"
        labels.loc[R < R_low_adaptive] = "CHAOTIC"

        # Add transition labels based on ΔR
        delta_R_threshold = delta_R.rolling(self.window * 2, min_periods=self.window).std()
        delta_R_threshold = delta_R_threshold.fillna(0.1)

        labels.loc[delta_R.abs() > 2 * delta_R_threshold] = "TRANSITION"

        return labels
