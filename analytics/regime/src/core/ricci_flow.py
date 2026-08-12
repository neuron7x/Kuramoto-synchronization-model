# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Ricci-flow inspired portfolio rebalancer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

__all__ = [
    "RicciFlowConfig",
    "RicciFlowResult",
    "RicciFlowRebalancer",
]


@dataclass(frozen=True)
class RicciFlowConfig:
    """Configuration for :class:`RicciFlowRebalancer`."""

    curvature_beta: float = 3.0
    risk_aversion: float = 5.0
    turnover_penalty: float = 0.5
    step_size: float = 0.05
    minimum_weight: float = 0.0


@dataclass(frozen=True)
class RicciFlowResult:
    """Result returned by :class:`RicciFlowRebalancer.rebalance`."""

    weights: pd.Series
    ricci_mean: float
    curvature_distribution: pd.Series
    objective_value: float


class RicciFlowRebalancer:
    """Project weights along a curvature-aware gradient flow."""

    def __init__(self, config: RicciFlowConfig | None = None) -> None:
        self._config = config or RicciFlowConfig()

    @property
    def config(self) -> RicciFlowConfig:
        return self._config

    def rebalance(
        self,
        covariance: Mapping[str, Mapping[str, float]] | pd.DataFrame,
        *,
        correlation: Mapping[str, Mapping[str, float]] | pd.DataFrame | None = None,
        previous_weights: Mapping[str, float] | pd.Series | None = None,
    ) -> RicciFlowResult:
        cov = _to_frame(covariance)
        corr = _to_frame(correlation) if correlation is not None else _safe_corr(cov)
        if cov.shape[0] != cov.shape[1]:
            raise ValueError("Covariance matrix must be square.")

        if previous_weights is None:
            prev = np.repeat(1.0 / cov.shape[0], cov.shape[0])
        else:
            prev_series = pd.Series(previous_weights, index=cov.index, dtype=float)
            prev = prev_series.reindex(cov.index).fillna(0.0).to_numpy()
            prev = _project_simplex(prev, lower_bound=self._config.minimum_weight)

        curvature = _forman_ricci(corr.to_numpy(), beta=self._config.curvature_beta)
        ricci_mean = float(curvature.mean())

        grad_curvature = curvature - curvature.mean()
        grad_risk = 2.0 * cov.to_numpy() @ prev
        gradient = grad_curvature - self._config.risk_aversion * grad_risk

        candidate = prev + self._config.step_size * gradient
        candidate = _project_simplex(candidate, lower_bound=self._config.minimum_weight)
        weights = (
            1.0 - self._config.turnover_penalty
        ) * candidate + self._config.turnover_penalty * prev
        weights = _project_simplex(weights, lower_bound=self._config.minimum_weight)

        objective = (
            -ricci_mean
            + self._config.risk_aversion * float(weights @ (cov.to_numpy() @ weights))
            + self._config.turnover_penalty * float(np.linalg.norm(weights - prev, ord=1))
        )

        weight_series = pd.Series(weights, index=cov.index, name="weight")
        curvature_series = pd.Series(curvature, index=cov.index, name="curvature")

        return RicciFlowResult(
            weights=weight_series,
            ricci_mean=ricci_mean,
            curvature_distribution=curvature_series,
            objective_value=float(objective),
        )


def _to_frame(
    matrix: Mapping[str, Mapping[str, float]] | pd.DataFrame | None,
) -> pd.DataFrame:
    if matrix is None:
        raise ValueError("Matrix is required.")
    if isinstance(matrix, pd.DataFrame):
        return matrix
    return pd.DataFrame(matrix)


def _safe_corr(covariance: pd.DataFrame) -> pd.DataFrame:
    std = np.sqrt(np.diag(covariance.to_numpy()))
    denom = np.outer(std, std)
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = covariance.to_numpy() / denom
    corr = np.clip(corr, -1.0, 1.0)
    np.fill_diagonal(corr, 1.0)
    return pd.DataFrame(corr, index=covariance.index, columns=covariance.columns)


def _forman_ricci(correlation: np.ndarray, *, beta: float) -> np.ndarray:
    weights = np.exp(-beta * (1.0 - np.clip(correlation, -1.0, 1.0)))
    np.fill_diagonal(weights, 0.0)
    degrees = weights.sum(axis=1)
    curvature = np.empty(weights.shape[0], dtype=float)
    for i in range(weights.shape[0]):
        neighbor_weights = weights[i]
        total = 0.0
        for j, w_ij in enumerate(neighbor_weights):
            if i == j or w_ij == 0.0:
                continue
            term = 2.0
            term -= degrees[i] - w_ij
            term -= degrees[j] - weights[j, i]
            total += w_ij * term
        curvature[i] = total
    return curvature


def _project_simplex(vector: Iterable[float], *, lower_bound: float = 0.0) -> np.ndarray:
    x = np.asarray(vector, dtype=float)
    if lower_bound < 0:
        raise ValueError("lower_bound must be non-negative")

    n = x.size
    shift = float(lower_bound)
    target = 1.0 - n * shift

    if target < 0:
        raise ValueError("lower_bound is infeasible for the simplex")
    if target == 0:
        return np.full(n, shift, dtype=float)

    shifted = np.maximum(x - shift, 0.0)

    u = np.sort(shifted)[::-1]
    cssv = np.cumsum(u)
    rho = np.nonzero(u * np.arange(1, n + 1) > (cssv - target))[0][-1]
    theta = (cssv[rho] - target) / (rho + 1)
    projected = np.maximum(shifted - theta, 0.0)
    projected += shift
    # numerical guard in case of small floating-point drift
    projected /= projected.sum()
    return projected
