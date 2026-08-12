# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fractal–Kuramoto early warning detector.

This module implements the FK-Detector described in the product brief.  It
combines the Kuramoto order parameter with fractal-memory diagnostics to raise
pre-alerts ahead of regime breaks.  The implementation is intentionally
lightweight so that it can run inside streaming micro-batches without external
dependencies beyond :mod:`numpy` and :mod:`pandas`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "FKDetector",
    "FKDetectorConfig",
    "FKDetectorResult",
    "FKDetectorCalibration",
    "estimate_hurst_rs",
]


@dataclass(frozen=True)
class FKDetectorConfig:
    """Configuration for :class:`FKDetector`.

    Attributes
    ----------
    window: int
        Size of the sliding window (in samples) used to compute the metrics.
    kuramoto_lag: int
        Number of samples between the two order-parameter measurements used to
        form ``Δr``.
    alpha_r, alpha_h_mean, alpha_h_dispersion: float
        Weights applied to the standardised features before aggregation.
    trigger_quantile: float
        Quantile of the calibrated distribution used as the pre-alert
        threshold.
    minimum_series_length: int
        Minimum number of samples required to compute the detector.
    epsilon: float
        Numerical guard added to denominators when computing z-scores.
    """

    window: int = 720
    kuramoto_lag: int = 3
    alpha_r: float = 1.0
    alpha_h_mean: float = 1.0
    alpha_h_dispersion: float = 1.0
    trigger_quantile: float = 0.95
    minimum_series_length: int = 128
    epsilon: float = 1e-9


@dataclass(frozen=True)
class FKDetectorCalibration:
    """Calibration statistics used to standardise the detector features."""

    delta_r_mean: float
    delta_r_std: float
    inv_h_mean: float
    inv_h_std: float
    hurst_dispersion_mean: float
    hurst_dispersion_std: float
    trigger_threshold: float


@dataclass(frozen=True)
class FKDetectorResult:
    """Output of :class:`FKDetector.compute`."""

    fk_index: float
    r_value: float
    delta_r: float
    hurst_mean: float
    hurst_dispersion: float
    trigger_threshold: float
    triggered: bool


class FKDetector:
    """Compute the fractal–Kuramoto index and trigger pre-alerts."""

    def __init__(
        self,
        *,
        config: FKDetectorConfig | None = None,
        calibration: FKDetectorCalibration | None = None,
    ) -> None:
        self._config = config or FKDetectorConfig()
        self._calibration = calibration

    @property
    def config(self) -> FKDetectorConfig:
        return self._config

    @property
    def calibration(self) -> FKDetectorCalibration | None:
        return self._calibration

    def compute(
        self,
        prices: Mapping[str, Iterable[float]] | pd.DataFrame | pd.Series,
    ) -> FKDetectorResult:
        """Compute the FK index for the provided price window."""

        price_frame = _ensure_frame(prices)
        if price_frame.shape[0] < self._config.minimum_series_length:
            raise ValueError(
                f"FKDetector requires at least {self._config.minimum_series_length} observations.",
            )

        log_returns = np.log(price_frame).diff().dropna()
        if log_returns.empty:
            raise ValueError("Unable to compute log returns for FKDetector.")

        r_value, delta_r = _kuramoto_metrics(
            log_returns.tail(self._config.window),
            lag=self._config.kuramoto_lag,
        )
        hurst_values = np.array(
            [estimate_hurst_rs(log_returns[column].to_numpy()) for column in log_returns],
            dtype=float,
        )
        hurst_mean, hurst_dispersion = _summarise_hurst(hurst_values)

        calibration = self._calibration or self.calibrate_from_window(log_returns)
        inv_h = 1.0 - hurst_mean

        z_delta_r = _zscore(
            delta_r,
            calibration.delta_r_mean,
            calibration.delta_r_std,
            self._config.epsilon,
        )
        z_inv_h = _zscore(
            inv_h, calibration.inv_h_mean, calibration.inv_h_std, self._config.epsilon
        )
        z_h_dispersion = _zscore(
            hurst_dispersion,
            calibration.hurst_dispersion_mean,
            calibration.hurst_dispersion_std,
            self._config.epsilon,
        )

        fk_index = (
            self._config.alpha_r * z_delta_r
            + self._config.alpha_h_mean * z_inv_h
            + self._config.alpha_h_dispersion * z_h_dispersion
        )

        triggered = fk_index >= calibration.trigger_threshold and delta_r > 0.0

        return FKDetectorResult(
            fk_index=float(fk_index),
            r_value=float(r_value),
            delta_r=float(delta_r),
            hurst_mean=float(hurst_mean),
            hurst_dispersion=float(hurst_dispersion),
            trigger_threshold=float(calibration.trigger_threshold),
            triggered=bool(triggered),
        )

    def calibrate_from_window(self, returns: pd.DataFrame) -> FKDetectorCalibration:
        """Calibrate the detector using the supplied returns window."""

        features = _fk_feature_matrix(returns.tail(self._config.window), self._config.kuramoto_lag)
        if features.size == 0:
            raise ValueError("Not enough data to calibrate FKDetector.")

        delta_r = features[:, 0]
        inv_h = features[:, 1]
        hurst_dispersion = features[:, 2]

        trigger_threshold = float(np.quantile(features[:, 3], self._config.trigger_quantile))

        calibration = FKDetectorCalibration(
            delta_r_mean=float(np.mean(delta_r)),
            delta_r_std=float(np.std(delta_r, ddof=1) + self._config.epsilon),
            inv_h_mean=float(np.mean(inv_h)),
            inv_h_std=float(np.std(inv_h, ddof=1) + self._config.epsilon),
            hurst_dispersion_mean=float(np.mean(hurst_dispersion)),
            hurst_dispersion_std=float(np.std(hurst_dispersion, ddof=1) + self._config.epsilon),
            trigger_threshold=trigger_threshold,
        )
        self._calibration = calibration
        return calibration


def _ensure_frame(
    data: Mapping[str, Iterable[float]] | pd.DataFrame | pd.Series,
) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data
    if isinstance(data, pd.Series):
        return data.to_frame()
    return pd.DataFrame(data)


def _kuramoto_metrics(returns: pd.DataFrame, *, lag: int) -> tuple[float, float]:
    phases = np.unwrap(np.angle(np.exp(1j * returns.cumsum().to_numpy())), axis=0)
    order_parameter = np.abs(np.mean(np.exp(1j * phases), axis=1))
    r_value = float(order_parameter[-1])
    lag = max(1, min(lag, len(order_parameter) - 1))
    delta_r = float(order_parameter[-1] - order_parameter[-1 - lag])
    return r_value, delta_r


def _fk_feature_matrix(returns: pd.DataFrame, lag: int) -> np.ndarray:
    if len(returns) < lag + 2:
        return np.empty((0, 4))

    r_values, delta_rs, inv_hs, dispersions, fk_indices = [], [], [], [], []
    for end in range(lag + 2, len(returns) + 1):
        window = returns.iloc[:end]
        r_value, delta_r = _kuramoto_metrics(window, lag=lag)
        hurst_values = np.array(
            [estimate_hurst_rs(window[column].to_numpy()) for column in window],
        )
        hurst_mean, hurst_dispersion = _summarise_hurst(hurst_values)
        inv_h = 1.0 - hurst_mean
        r_values.append(r_value)
        delta_rs.append(delta_r)
        inv_hs.append(inv_h)
        dispersions.append(hurst_dispersion)
        fk_indices.append(delta_r + inv_h + hurst_dispersion)

    features = np.column_stack([delta_rs, inv_hs, dispersions, fk_indices])
    mask = np.all(np.isfinite(features), axis=1)
    return features[mask]


def _summarise_hurst(values: np.ndarray) -> tuple[float, float]:
    finite = np.isfinite(values)
    if not np.any(finite):
        return 0.5, 0.0
    data = values[finite]
    mean = float(np.mean(data))
    if data.size < 2:
        return mean, 0.0
    dispersion = float(np.std(data, ddof=1))
    return mean, dispersion


def _zscore(value: float, mean: float, std: float, epsilon: float) -> float:
    return (value - mean) / (std if std > epsilon else epsilon)


def estimate_hurst_rs(
    series: Sequence[float], *, min_window: int = 8, max_window: int | None = None
) -> float:
    """Estimate the Hurst exponent using the rescaled range method."""

    values = np.asarray(series, dtype=float)
    if values.size < min_window:
        return float("nan")

    if max_window is None:
        max_window = values.size // 2
    max_window = max(min_window, min(max_window, values.size // 2))
    if max_window <= min_window:
        return float("nan")

    window_sizes = np.unique(np.linspace(min_window, max_window, num=8, dtype=int))
    rs_values = []
    for window in window_sizes:
        if window <= 1:
            continue
        segments = values[: len(values) - len(values) % window]
        if segments.size == 0:
            continue
        reshaped = segments.reshape(-1, window)
        means = reshaped.mean(axis=1, keepdims=True)
        demeaned = reshaped - means
        cumulative = np.cumsum(demeaned, axis=1)
        ranges = cumulative.max(axis=1) - cumulative.min(axis=1)
        std = reshaped.std(axis=1, ddof=1)
        valid = std > 0
        if not np.any(valid):
            continue
        rs = np.mean(ranges[valid] / std[valid])
        if rs > 0:
            rs_values.append((np.log(window), np.log(rs)))

    if len(rs_values) < 2:
        return float("nan")

    x, y = np.transpose(rs_values)
    slope, _ = np.polyfit(x, y, 1)
    return float(np.clip(slope, 0.0, 1.5))
