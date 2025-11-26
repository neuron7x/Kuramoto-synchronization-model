"""Compatibility shims for a minimal subset of scikit-learn.

The original TradePulse analytics stack depends on a handful of utilities from
``scikit-learn`` (logistic regression, isotonic calibration and a couple of
metrics).  The production environment bundles those dependencies, but the kata
testbed deliberately keeps the footprint small and does not install optional
packages.  Importing the true scikit-learn modules would therefore raise a
``ModuleNotFoundError`` and the end-to-end pipeline would fail to even import.

To keep the public API stable – and to avoid rewriting the downstream training
logic – this module provides lightweight, pure NumPy fallbacks that mimic the
parts of the scikit-learn API we rely on.  The implementations prioritise
numerical robustness and readability over raw performance, which is perfectly
adequate for the modest problem sizes exercised in the test-suite.

Only the symbols imported in ``tradepulse_v21`` are implemented here:

``LogisticRegression``
    Solves an L2-regularised logistic regression via iteratively reweighted
    least squares (Newton-Raphson).  The interface mirrors the scikit-learn
    estimator closely enough for our usage (``fit`` and ``decision_function``).

``IsotonicRegression``
    Calibrates probabilities with the Pool Adjacent Violators Algorithm (PAVA)
    and supports ``out_of_bounds='clip'`` which is required by the pipeline.

``TimeSeriesSplit``
    Generates expanding-window train/test splits.

``check_random_state``
    Normalises various random seed representations.

``roc_auc_score`` and ``average_precision_score``
    Metric helpers matching the behaviour needed by the tests.

These shims intentionally stay small and dependency free; if scikit-learn is
available at runtime the real implementations will be used instead.
"""

from __future__ import annotations

from typing import Generator, Iterable, Tuple

import numpy as np

ArrayLike = np.ndarray


class LogisticRegression:
    """Minimal L2-regularised logistic regression estimator.

    The solver uses iteratively reweighted least squares (Newton-Raphson) with
    a ridge penalty controlled by ``C``.  Only the features exercised in the
    pipeline are implemented; attempting to alter the penalty type or solver
    raises ``NotImplementedError`` to fail loudly during development.
    """

    def __init__(
        self,
        *,
        C: float = 1.0,
        penalty: str = "l2",
        class_weight: str | None = None,
        max_iter: int = 200,
        random_state: np.random.RandomState | int | None = None,
        tol: float = 1e-6,
    ) -> None:
        if penalty != "l2":  # pragma: no cover - unsupported in tests
            raise NotImplementedError("Only L2 penalty is implemented in the stub")
        self.C = float(C)
        self.class_weight = class_weight
        self.max_iter = int(max_iter)
        self.tol = float(tol)
        self.random_state = check_random_state(random_state)
        self.coef_: ArrayLike | None = None
        self.intercept_: float | None = None

    def _compute_sample_weight(self, labels: ArrayLike) -> ArrayLike:
        if self.class_weight != "balanced":
            return np.ones_like(labels, dtype=float)

        positives = np.sum(labels == 1)
        negatives = np.sum(labels == 0)
        total = positives + negatives
        if positives == 0 or negatives == 0:
            # Degenerate case – fall back to uniform weights.
            return np.ones_like(labels, dtype=float)

        weight_pos = total / (2.0 * positives)
        weight_neg = total / (2.0 * negatives)
        weights = np.where(labels == 1, weight_pos, weight_neg)
        return weights.astype(float)

    def fit(self, features: ArrayLike, labels: ArrayLike) -> "LogisticRegression":
        x = np.asarray(features, dtype=float)
        y = np.asarray(labels, dtype=float)
        if x.ndim != 2:
            raise ValueError("features must be a 2D array")
        if y.shape[0] != x.shape[0]:
            raise ValueError("labels must align with features")

        n_samples, n_features = x.shape
        weights = self._compute_sample_weight(y)
        coef = self.random_state.normal(scale=0.01, size=n_features)
        intercept = 0.0
        reg_strength = 1.0 / max(self.C, 1e-12)

        for _ in range(self.max_iter):
            logits = x @ coef + intercept
            probs = 1.0 / (1.0 + np.exp(-logits))
            # Clip to avoid numerical issues in log/variance computation.
            probs = np.clip(probs, 1e-8, 1.0 - 1e-8)

            # Weighted residuals and Hessian diagonal for IRLS.
            residual = y - probs
            w = weights * probs * (1.0 - probs)

            # Construct weighted design matrix.
            sqrt_w = np.sqrt(w)
            x_weighted = sqrt_w[:, None] * x
            z = logits + residual / (probs * (1.0 - probs))
            z_weighted = sqrt_w * z

            # Augment matrix with intercept term.
            x_aug = np.column_stack([x_weighted, sqrt_w])
            # Match scikit-learn by excluding the intercept term from regularisation.
            ridge = np.sqrt(reg_strength) * np.diag(
                np.concatenate([np.ones(n_features), np.zeros(1)])
            )
            lhs = x_aug.T @ x_aug + ridge.T @ ridge
            rhs = x_aug.T @ z_weighted

            solution = np.linalg.solve(lhs, rhs)
            new_coef = solution[:-1]
            new_intercept = solution[-1]

            delta = max(np.linalg.norm(new_coef - coef), abs(new_intercept - intercept))
            coef, intercept = new_coef, new_intercept
            if delta < self.tol:
                break

        self.coef_ = coef
        self.intercept_ = float(intercept)
        return self

    def decision_function(self, features: ArrayLike) -> ArrayLike:
        if self.coef_ is None or self.intercept_ is None:
            raise RuntimeError(
                "The model must be fitted before calling decision_function"
            )
        x = np.asarray(features, dtype=float)
        return x @ self.coef_ + self.intercept_


class IsotonicRegression:
    """Pool Adjacent Violators Algorithm (PAVA) based isotonic regression."""

    def __init__(self, *, out_of_bounds: str = "nan") -> None:
        if out_of_bounds not in {"nan", "clip"}:  # pragma: no cover - parity guard
            raise ValueError("out_of_bounds must be 'nan' or 'clip'")
        self.out_of_bounds = out_of_bounds
        self._x: ArrayLike | None = None
        self._y: ArrayLike | None = None

    def fit(self, x: ArrayLike, y: ArrayLike) -> "IsotonicRegression":
        x_arr = np.asarray(x, dtype=float)
        y_arr = np.asarray(y, dtype=float)
        if x_arr.shape[0] != y_arr.shape[0]:
            raise ValueError("x and y must share the first dimension")

        order = np.argsort(x_arr)
        x_sorted = x_arr[order]
        y_sorted = y_arr[order]
        weights = np.ones_like(y_sorted)

        y_isotonic = _pava(y_sorted, weights)
        self._x = x_sorted
        self._y = y_isotonic
        return self

    def predict(self, x: ArrayLike) -> ArrayLike:
        if self._x is None or self._y is None:
            raise RuntimeError(
                "The isotonic regressor must be fitted before prediction"
            )

        x_arr = np.asarray(x, dtype=float)
        x_sorted = self._x
        y_sorted = self._y

        if self.out_of_bounds == "clip":
            x_clipped = np.clip(x_arr, x_sorted[0], x_sorted[-1])
            return np.interp(x_clipped, x_sorted, y_sorted)
        return np.interp(x_arr, x_sorted, y_sorted, left=np.nan, right=np.nan)


class TimeSeriesSplit:
    """Expanding window time-series split generator."""

    def __init__(self, *, n_splits: int = 5, test_size: int | None = None) -> None:
        if n_splits < 1:
            raise ValueError("n_splits must be at least 1")
        self.n_splits = int(n_splits)
        self.test_size = test_size

    def split(
        self, X: ArrayLike | Iterable[object]
    ) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        n_samples = len(X) if isinstance(X, np.ndarray) else len(list(X))
        indices = np.arange(n_samples)
        if self.n_splits >= n_samples:
            raise ValueError("Not enough samples for the requested number of splits")

        test_size = self.test_size
        if test_size is None:
            test_size = max(1, n_samples // (self.n_splits + 1))

        for split_idx in range(self.n_splits):
            test_start = (split_idx + 1) * test_size
            test_end = test_start + test_size
            if test_start >= n_samples:
                break
            if test_end > n_samples:
                test_end = n_samples
            yield indices[:test_start], indices[test_start:test_end]


def check_random_state(
    seed: np.random.RandomState | int | None,
) -> np.random.RandomState:
    if seed is None or seed is np.random:
        return np.random.mtrand._rand
    if isinstance(seed, (int, np.integer)):
        return np.random.RandomState(seed)
    if isinstance(seed, np.random.RandomState):
        return seed
    raise ValueError(f"Invalid random_state: {seed!r}")


def roc_auc_score(labels: ArrayLike, scores: ArrayLike) -> float:
    labels_arr = np.asarray(labels, dtype=float)
    scores_arr = np.asarray(scores, dtype=float)
    if labels_arr.shape[0] != scores_arr.shape[0]:
        raise ValueError("labels and scores must share the first dimension")

    order = np.argsort(scores_arr)
    labels_sorted = labels_arr[order]
    positives = np.sum(labels_sorted == 1)
    negatives = np.sum(labels_sorted == 0)
    if positives == 0 or negatives == 0:
        return float("nan")

    ranks = np.arange(1, len(scores_arr) + 1)
    rank_sum = np.sum(ranks[labels_sorted == 1])
    auc = (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)
    return float(auc)


def average_precision_score(labels: ArrayLike, scores: ArrayLike) -> float:
    labels_arr = np.asarray(labels, dtype=float)
    scores_arr = np.asarray(scores, dtype=float)
    order = np.argsort(-scores_arr)
    labels_sorted = labels_arr[order]
    tp = 0.0
    total = 0.0
    precision_sum = 0.0
    positives = np.sum(labels_sorted == 1)
    if positives == 0:
        return 0.0

    for idx, label in enumerate(labels_sorted, start=1):
        total += 1
        if label == 1:
            tp += 1
            precision_sum += tp / total
    return float(precision_sum / positives)


def _pava(y: ArrayLike, weights: ArrayLike) -> ArrayLike:
    """Pool Adjacent Violators Algorithm."""

    y = np.asarray(y, dtype=float)
    w = np.asarray(weights, dtype=float)
    if y.ndim != 1:
        raise ValueError("y must be one-dimensional")
    if y.shape[0] != w.shape[0]:
        raise ValueError("weights must match y")

    values = y.copy()
    weights = w.copy()
    starts = np.arange(len(values))
    ends = np.arange(len(values))

    idx = 0
    while idx < len(values) - 1:
        if values[idx] <= values[idx + 1] + 1e-12:
            idx += 1
            continue

        total_weight = weights[idx] + weights[idx + 1]
        total_value = (
            weights[idx] * values[idx] + weights[idx + 1] * values[idx + 1]
        ) / total_weight

        values[idx] = total_value
        weights[idx] = total_weight
        ends[idx] = ends[idx + 1]

        values = np.delete(values, idx + 1)
        weights = np.delete(weights, idx + 1)
        starts = np.delete(starts, idx + 1)
        ends = np.delete(ends, idx + 1)

        if idx > 0:
            idx -= 1

    result = np.empty_like(y, dtype=float)
    for value, start, end in zip(values, starts, ends):
        result[start : end + 1] = value
    return result


__all__ = [
    "LogisticRegression",
    "IsotonicRegression",
    "TimeSeriesSplit",
    "check_random_state",
    "roc_auc_score",
    "average_precision_score",
]
