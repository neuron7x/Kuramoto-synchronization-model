"""Heterogeneous Auto-Regressive (HAR) model utilities."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, Tuple

import numpy as np


@dataclass
class HARState:
    coeffs: np.ndarray
    intercept: float
    lags: Tuple[int, ...]
    history: Deque[float]
    alpha: float


def _design_matrix(rv: np.ndarray, lags: Tuple[int, ...]) -> np.ndarray:
    rows = len(rv) - max(lags)
    X = np.ones((rows, len(lags) + 1))
    for i, lag in enumerate(lags, start=1):
        X[:, i] = rv[max(lags) - lag : len(rv) - lag]
    return X


def fit_har(rv: np.ndarray, lags: Tuple[int, ...] = (1, 5, 22)) -> Dict[str, object]:
    """Fit a simple HAR model via least squares."""

    if len(rv) <= max(lags):
        raise ValueError("Insufficient data for HAR fit")
    X = _design_matrix(rv, lags)
    y = rv[max(lags) :]
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    intercept = float(beta[0])
    coeffs = beta[1:]
    history: Deque[float] = deque(rv.tolist(), maxlen=max(lags) + 10)
    return {
        "state": HARState(coeffs=coeffs, intercept=intercept, lags=lags, history=history, alpha=0.05),
    }


def predict_har(state: Dict[str, object], k: int = 1) -> float:
    har_state: HARState = state["state"]
    hist = np.array(list(har_state.history))
    if len(hist) < max(har_state.lags) + 1:
        return float(hist.mean() if len(hist) else 0.0)
    features = [1.0]
    for lag in har_state.lags:
        features.append(hist[-lag])
    return float(np.dot(np.array(features), np.concatenate(([har_state.intercept], har_state.coeffs))))


def update_har(state: Dict[str, object], new_rv: float, alpha: float = 0.05) -> None:
    har_state: HARState = state["state"]
    har_state.history.append(new_rv)
    har_state.alpha = alpha
    hist = np.array(list(har_state.history))
    if len(hist) <= max(har_state.lags):
        return
    X = _design_matrix(hist, har_state.lags)
    y = hist[max(har_state.lags) :]
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    har_state.intercept = float(beta[0])
    har_state.coeffs = beta[1:]
