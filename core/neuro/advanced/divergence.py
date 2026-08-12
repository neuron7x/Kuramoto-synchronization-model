# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
r"""Hybrid divergence computation for neuroeconomic trading agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .causal import GrangerResult, granger_causality
from .quantum import (
    QuantumBeliefUpdate,
    quantum_active_update,
    quantum_relative_entropy,
    to_density_matrix,
)


@dataclass(frozen=True, slots=True)
class DivergenceConfig:
    """Configuration for :func:`compute_divergence_convergence_phi`."""

    learning_rate: float = 0.1
    divergence_threshold: float = 0.7
    divergence_mode: Literal["classical", "quantum"] = "classical"
    entropy_weight: float = 0.5
    causal_window: int = 32
    causal_max_lag: int = 3
    causal_p_threshold: float | None = 0.05
    causal_feature: str | None = None
    normalisation: Literal["none", "zscore", "robust"] = "robust"


@dataclass(frozen=True, slots=True)
class DivergenceOutput:
    """Container returning all computed series for convenience."""

    frame: pd.DataFrame
    config: DivergenceConfig

    @property
    def divergence(self) -> pd.Series:
        return self.frame["divergence"]

    @property
    def convergence(self) -> pd.Series:
        return self.frame["convergence"]

    @property
    def phi(self) -> pd.Series:
        return self.frame["phi"]


def _cosine_similarity(u: np.ndarray, v: np.ndarray) -> float:
    numerator = float(np.dot(u, v))
    denominator = float(np.linalg.norm(u) * np.linalg.norm(v))
    if denominator < 1e-12:
        return 1.0
    value = numerator / denominator
    return float(np.clip(value, -1.0, 1.0))


def _ensure_frame(
    price: pd.Series,
    features: pd.DataFrame,
) -> pd.DataFrame:
    frame = pd.concat([price.rename("price"), features], axis=1)
    frame = frame.dropna()
    if frame.empty:
        raise ValueError("input series contain no overlapping non-null values")
    return frame


def _select_causal_series(frame: pd.DataFrame, config: DivergenceConfig) -> pd.Series:
    if config.causal_feature is not None:
        if config.causal_feature not in frame.columns:
            msg = f"causal_feature '{config.causal_feature}' is not present in features"
            raise KeyError(msg)
        return frame[config.causal_feature]
    non_price_columns = [column for column in frame.columns if column != "price"]
    if not non_price_columns:
        raise ValueError("features must contain at least one non-price column")
    return frame[non_price_columns[0]]


def _normalise_deltas(
    deltas: pd.DataFrame, mode: Literal["none", "zscore", "robust"], eps: float = 1e-12
) -> pd.DataFrame:
    if mode == "none" or deltas.empty:
        return deltas.copy()

    normalised = pd.DataFrame(index=deltas.index, columns=deltas.columns, dtype=float)
    for column in deltas.columns:
        series = deltas[column].astype(float)
        if mode == "zscore":
            centre = float(series.mean())
            scale = float(series.std(ddof=0))
        else:
            centre = float(series.median())
            scale = float(np.median(np.abs(series - centre)))

        if not np.isfinite(scale) or scale < eps:
            scale = float(series.abs().median())
        if not np.isfinite(scale) or scale < eps:
            scale = 1.0

        normalised[column] = (series - centre) / scale

    return normalised


def _compute_divergence(
    price_delta: float,
    feature_delta: np.ndarray,
    config: DivergenceConfig,
) -> tuple[float, float]:
    if config.divergence_mode == "quantum":
        embedding = np.zeros_like(feature_delta, dtype=float)
        embedding[0] = price_delta
        rho_p = to_density_matrix(embedding)
        rho_f = to_density_matrix(feature_delta)
        divergence = max(0.0, quantum_relative_entropy(rho_p, rho_f))
        if divergence < config.divergence_threshold:
            convergence = max(0.0, 1.0 - divergence / (config.divergence_threshold + 1.0))
        else:
            convergence = max(0.0, 1.0 - divergence / (divergence + 1.0))
        return divergence, convergence

    vector = np.zeros_like(feature_delta, dtype=float)
    vector[0] = price_delta
    similarity = _cosine_similarity(vector, feature_delta)
    divergence = max(0.0, 1.0 - similarity)
    if divergence < config.divergence_threshold:
        divergence = 0.0
    convergence = max(0.0, similarity)
    return divergence, convergence


def compute_divergence_convergence_phi(
    price: pd.Series,
    features: pd.DataFrame,
    *,
    config: DivergenceConfig | None = None,
) -> DivergenceOutput:
    r"""Compute divergence, convergence and quantum-active belief updates.

    Parameters
    ----------
    price:
        Price series :math:`P_t` used to generate directional deltas.
    features:
        Feature matrix :math:`F_t` (e.g., oscillators, volume metrics) aligned
        with ``price``.
    config:
        Optional :class:`DivergenceConfig`. When omitted, the default
        configuration emphasises classical cosine divergence with causal
        validation enabled.

    Returns
    -------
    DivergenceOutput
        Contains the resulting DataFrame with columns ``divergence``,
        ``convergence``, ``phi``, ``causal_p_value`` and ``causal_pass``.
    """

    if config is None:
        config = DivergenceConfig()

    frame = _ensure_frame(price, features)
    deltas = frame.diff().dropna()
    if deltas.empty:
        raise ValueError("unable to compute differences for divergence analysis")

    normalised_deltas = _normalise_deltas(deltas, config.normalisation)

    causal_series = _select_causal_series(frame, config)

    divergence_values: list[float] = []
    convergence_values: list[float] = []
    phi_values: list[float] = []
    entropy_values: list[float] = []
    p_values: list[float] = []
    causal_flags: list[bool] = []

    phi = 0.0
    for idx, (timestamp, row) in enumerate(normalised_deltas.iterrows()):
        price_delta = float(row["price"])
        feature_delta = row.drop(labels="price").to_numpy(dtype=float)

        divergence, convergence = _compute_divergence(price_delta, feature_delta, config)

        causal_result: GrangerResult | None = None
        if config.causal_p_threshold is not None:
            start = max(0, idx + 1 - config.causal_window)
            window = frame.iloc[start : idx + 2]
            try:
                causal_result = granger_causality(
                    window["price"],
                    window[causal_series.name],
                    max_lag=config.causal_max_lag,
                    p_threshold=config.causal_p_threshold,
                )
            except ValueError:
                causal_result = None

        if causal_result is not None and not causal_result.causes:
            divergence_values.append(float("nan"))
            convergence_values.append(0.0)
            phi_values.append(phi)
            entropy_values.append(0.0)
            p_values.append(causal_result.p_value)
            causal_flags.append(False)
            continue

        belief_update: QuantumBeliefUpdate
        belief_update = quantum_active_update(
            phi,
            convergence,
            divergence,
            learning_rate=config.learning_rate,
            entropy_weight=config.entropy_weight,
            state_vector=(phi, convergence, divergence, *feature_delta.tolist()),
        )
        phi = belief_update.phi

        divergence_values.append(divergence)
        convergence_values.append(convergence)
        phi_values.append(phi)
        entropy_values.append(belief_update.entropy)
        if causal_result is None:
            p_values.append(float("nan"))
            causal_flags.append(True)
        else:
            p_values.append(causal_result.p_value)
            causal_flags.append(causal_result.causes)

    result = pd.DataFrame(
        {
            "divergence": divergence_values,
            "convergence": convergence_values,
            "phi": phi_values,
            "entropy": entropy_values,
            "causal_p_value": p_values,
            "causal_pass": causal_flags,
        },
        index=deltas.index,
    )

    return DivergenceOutput(frame=result, config=config)


__all__ = [
    "DivergenceConfig",
    "DivergenceOutput",
    "compute_divergence_convergence_phi",
]
