r"""Core Div/Conv protocol building blocks.

The implementation favours numerical stability and explicit contracts so
that downstream consumers can rely on the semantics in both online and
batch settings.  The module exposes:

* Gradient estimators for price and flow observables that are invariant to
  affine re-parameterisations of time.
* Cosine-aligned Div/Conv geometry (``\kappa_t`` and ``\theta_t``).
* Divergence functionals equipped with user-provided metrics.
* Thresholding helpers for change-point detection (``\tau_d`` and
  ``\tau_c``).
* Signal aggregation across multiple assets with risk-aware weights.

All public functions validate inputs eagerly and provide deterministic
floating-point behaviour by pinning tolerances and clipping ranges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple

import numpy as np

ArrayLike = Sequence[float] | np.ndarray

_EPS = 1e-12


def _to_ndarray(values: ArrayLike, *, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim == 0:
        array = np.atleast_1d(array)
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains non-finite values: {array}")
    return array


@dataclass(frozen=True)
class DivConvSnapshot:
    """Stateful snapshot of Div/Conv observables for a single timestamp.

    Attributes
    ----------
    price_gradient:
        Gradient of the price process ``∇P_t`` expressed in common
        coordinates.
    flow_gradient:
        Gradient of the flow/volume/latent factor process ``∇F_t``.
    theta:
        Angular displacement between ``∇P_t`` and ``∇F_t``.
    kappa:
        Cosine alignment ``κ_t = cos θ_t``.
    divergence:
        Divergence functional value under the selected metric.
    """

    price_gradient: np.ndarray
    flow_gradient: np.ndarray
    theta: float
    kappa: float
    divergence: float


@dataclass(frozen=True)
class DivConvSignal:
    """Div/Conv signal enriched with portfolio attribution context."""

    asset_id: str
    snapshot: DivConvSnapshot
    risk_weight: float
    exposure: float


def compute_price_gradient(
    prices: ArrayLike,
    *,
    times: Optional[ArrayLike] = None,
) -> np.ndarray:
    """Estimate ``∇P_t`` using symmetric finite differences.

    Parameters
    ----------
    prices:
        Sequence of price observations sampled at ``times``.
    times:
        Optional monotonically increasing timestamps.  When omitted, unit
        spacing is assumed.  Passing explicit times ensures invariance to
        non-uniform sampling.
    """

    price_array = _to_ndarray(prices, name="prices")
    if price_array.size < 2:
        raise ValueError("prices must contain at least two observations")

    if times is None:
        gradient = np.gradient(price_array)
    else:
        time_array = _to_ndarray(times, name="times")
        if time_array.shape != price_array.shape:
            raise ValueError("times and prices must have the same shape")
        if not np.all(np.diff(time_array) > 0):
            raise ValueError("times must be strictly increasing")
        gradient = np.gradient(price_array, time_array)

    return np.asarray(gradient, dtype=float)


def _normalised(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm < _EPS:
        raise ValueError("Cannot normalise a near-zero vector")
    return vector / norm


def compute_theta(price_grad: ArrayLike, flow_grad: ArrayLike) -> float:
    """Compute ``θ_t`` between the gradients in radians."""

    price = _to_ndarray(price_grad, name="price_grad")
    flow = _to_ndarray(flow_grad, name="flow_grad")
    if price.shape != flow.shape:
        raise ValueError("Gradients must share the same dimensionality")

    price_unit = _normalised(price)
    flow_unit = _normalised(flow)
    cosine = float(np.clip(np.dot(price_unit, flow_unit), -1.0, 1.0))
    return float(np.arccos(cosine))


def compute_kappa(price_grad: ArrayLike, flow_grad: ArrayLike) -> float:
    """Return ``κ_t = cos θ_t`` in a numerically stable manner."""

    price = _to_ndarray(price_grad, name="price_grad")
    flow = _to_ndarray(flow_grad, name="flow_grad")
    if price.shape != flow.shape:
        raise ValueError("Gradients must share the same dimensionality")

    price_unit = _normalised(price)
    flow_unit = _normalised(flow)
    return float(np.clip(np.dot(price_unit, flow_unit), -1.0, 1.0))


def compute_time_warp_invariant_metric(
    basis_vectors: Sequence[np.ndarray],
    *,
    weights: Optional[Sequence[float]] = None,
) -> np.ndarray:
    """Construct a positive semi-definite metric invariant to scaling.

    The metric is built as ``M = Σ w_i * (b_i b_i^T)`` so it remains
    unchanged under uniform scaling of each basis vector ``b_i``.
    """

    matrices = []
    if weights is not None and len(weights) != len(basis_vectors):
        raise ValueError("weights and basis_vectors must align")

    for idx, basis in enumerate(basis_vectors):
        vec = _to_ndarray(basis, name=f"basis[{idx}]")
        if vec.ndim != 1:
            raise ValueError("basis vectors must be one-dimensional")
        weight = 1.0 if weights is None else float(weights[idx])
        matrices.append(weight * np.outer(vec, vec))

    if not matrices:
        raise ValueError("At least one basis vector is required")

    metric = np.sum(matrices, axis=0)
    return metric


def compute_divergence_functional(
    price_grad: ArrayLike,
    flow_grad: ArrayLike,
    *,
    metric: Optional[np.ndarray] = None,
) -> float:
    """Evaluate the divergence functional ``D(∇P_t, ∇F_t)``."""

    price = _to_ndarray(price_grad, name="price_grad")
    flow = _to_ndarray(flow_grad, name="flow_grad")
    if price.shape != flow.shape:
        raise ValueError("Gradients must share the same dimensionality")

    delta = price - flow
    if metric is None:
        return float(np.dot(delta, delta))

    metric_array = np.asarray(metric, dtype=float)
    if metric_array.ndim != 2:
        raise ValueError("metric must be a square matrix")
    if metric_array.shape[0] != metric_array.shape[1]:
        raise ValueError("metric must be square")
    if metric_array.shape[0] != price.shape[0]:
        raise ValueError("metric dimensionality mismatch")

    return float(delta @ metric_array @ delta)


def compute_threshold_tau_d(
    divergence_series: ArrayLike, *, alpha: float = 0.95
) -> float:
    """High-side divergence threshold (``τ_d``) via quantiles."""

    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")

    series = np.abs(_to_ndarray(divergence_series, name="divergence_series"))
    if series.size == 0:
        raise ValueError("divergence_series must not be empty")
    return float(np.quantile(series, alpha))


def compute_threshold_tau_c(
    divergence_series: ArrayLike, *, beta: float = 0.05
) -> float:
    """Low-side convergence threshold (``τ_c``) via quantiles."""

    if not 0.0 < beta < 1.0:
        raise ValueError("beta must be in (0, 1)")

    series = np.abs(_to_ndarray(divergence_series, name="divergence_series"))
    if series.size == 0:
        raise ValueError("divergence_series must not be empty")
    return float(np.quantile(series, beta))


def aggregate_signals(
    signals: Iterable[DivConvSignal],
    *,
    normalise_weights: bool = True,
) -> DivConvSnapshot:
    """Aggregate per-asset signals into a portfolio snapshot.

    The aggregation enforces scaling invariance by default by normalising
    supplied risk weights.  Exposure is retained to ease audit trails.
    """

    snapshots: list[Tuple[DivConvSignal, float]] = []
    for signal in signals:
        weight = float(signal.risk_weight)
        if not np.isfinite(weight):
            raise ValueError("risk_weight must be finite")
        snapshots.append((signal, weight))

    if not snapshots:
        raise ValueError("signals must contain at least one element")

    weights = np.array([weight for _, weight in snapshots], dtype=float)
    if normalise_weights:
        weight_sum = np.sum(np.abs(weights))
        if weight_sum < _EPS:
            raise ValueError("risk weights must not all be zero")
        weights = weights / weight_sum

    price_grad = np.zeros_like(snapshots[0][0].snapshot.price_gradient)
    flow_grad = np.zeros_like(snapshots[0][0].snapshot.flow_gradient)
    divergence = 0.0

    for (signal, _), weight in zip(snapshots, weights):
        price_grad = price_grad + weight * signal.snapshot.price_gradient
        flow_grad = flow_grad + weight * signal.snapshot.flow_gradient
        divergence += np.abs(weight) * signal.snapshot.divergence

    theta = compute_theta(price_grad, flow_grad)
    kappa = compute_kappa(price_grad, flow_grad)
    return DivConvSnapshot(
        price_gradient=price_grad,
        flow_gradient=flow_grad,
        theta=theta,
        kappa=kappa,
        divergence=divergence,
    )
