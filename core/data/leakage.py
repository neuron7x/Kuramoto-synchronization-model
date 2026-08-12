# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed temporal-leakage guards at the data-contract layer.

GeoSync handles leakage only in narrow contexts today: Combinatorial Purged CV
(``research/robustness/cpcv.py``) purges/embargoes for cross-validation, and
``assert_cak4_no_future_leak`` (``core/cross_asset_kuramoto/invariants.py``)
checks truncation-invariance for one estimator. There is no general, reusable,
context-free data-contract primitive that fail-closes on train/test overlap or
future-label leakage *before* data reaches the feature/graph layer.

This module provides exactly that. Both guards operate on a monotonic numeric
time coordinate (bar index or epoch seconds) and raise :class:`LeakageError`
with no silent numeric repair:

* :func:`assert_no_train_test_leakage` rejects a split whose training window
  reaches into (or too close to) the test window — the classic look-ahead that
  inflates backtests.
* :func:`assert_no_future_label_leakage` rejects a label that does not strictly
  post-date the decision it supervises — a label cannot be observed at or before
  the moment the decision is made.

Nothing here is a market claim. These are arithmetic facts about time
coordinates: a contract layer, not a predictor.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray


class LeakageError(ValueError):
    """Raised when a temporal-leakage guard rejects its input.

    Subclasses :class:`ValueError` so existing fail-closed ``except ValueError``
    handlers in the data layer catch it, while callers that care specifically
    about leakage can target :class:`LeakageError`.
    """


def _as_finite_1d(name: str, values: ArrayLike) -> NDArray[np.float64]:
    """Coerce ``values`` to a finite, non-empty 1-D float array or fail closed.

    Empty input, more (or fewer) than one dimension, and any NaN/Inf entry are
    all rejected with :class:`LeakageError`. No silent repair (no dropna, no
    reshape, no clipping) — a malformed time coordinate is a contract violation,
    not something to quietly fix.
    """
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1:
        raise LeakageError(
            f"LEAKAGE-GUARD VIOLATED: {name} must be 1-D, got ndim={array.ndim} "
            f"shape={array.shape}; a time coordinate is a flat sequence, not a "
            f"matrix — fail-closed, no silent reshape"
        )
    if array.size == 0:
        raise LeakageError(
            f"LEAKAGE-GUARD VIOLATED: {name} is empty; an empty time coordinate "
            f"cannot be proven leakage-free — fail-closed, no vacuous pass"
        )
    if not np.all(np.isfinite(array)):
        n_bad = int(np.count_nonzero(~np.isfinite(array)))
        raise LeakageError(
            f"LEAKAGE-GUARD VIOLATED: {name} has {n_bad} non-finite entr"
            f"{'y' if n_bad == 1 else 'ies'} (NaN/Inf) of size={array.size}; "
            f"non-finite time coordinates are undefined order — fail-closed, no "
            f"silent dropna"
        )
    return array


def assert_no_train_test_leakage(
    train_times: ArrayLike,
    test_times: ArrayLike,
    *,
    embargo: float = 0.0,
) -> None:
    """Fail closed unless the training window ends before the test window opens.

    The split is leakage-free iff ``max(train_times) < min(test_times) -
    embargo``. Equality (adjacency) and any overlap both leak: the last training
    observation must sit strictly more than ``embargo`` ahead of the first test
    observation, so no information from the test interval (nor its embargoed
    neighbourhood) is visible at training time.

    Args:
        train_times: 1-D monotonic-free numeric time coordinate of the training
            set (bar index or epoch seconds). Order is not required; only the
            extremes matter.
        test_times: 1-D numeric time coordinate of the test set.
        embargo: Non-negative gap (same units as the time coordinate) that must
            separate the training maximum from the test minimum. ``0.0`` forbids
            only overlap and adjacency; a positive value widens the dead zone.

    Raises:
        LeakageError: if either array is empty/non-1-D/non-finite, if ``embargo``
            is negative or non-finite, or if ``max(train) >= min(test) -
            embargo`` (overlap or insufficient embargo).
    """
    train = _as_finite_1d("train_times", train_times)
    test = _as_finite_1d("test_times", test_times)

    embargo_value = float(embargo)
    if not np.isfinite(embargo_value):
        raise LeakageError(
            f"LEAKAGE-GUARD VIOLATED: embargo must be finite, got {embargo!r}; fail-closed"
        )
    if embargo_value < 0.0:
        raise LeakageError(
            f"LEAKAGE-GUARD VIOLATED: embargo must be >= 0, got {embargo_value}; "
            f"a negative embargo would license overlap — fail-closed"
        )

    train_max = float(train.max())
    test_min = float(test.min())
    boundary = test_min - embargo_value
    if train_max >= boundary:
        raise LeakageError(
            f"LEAKAGE-GUARD VIOLATED: train/test leakage — max(train)={train_max} "
            f">= min(test)-embargo={boundary} (min(test)={test_min}, "
            f"embargo={embargo_value}); training reaches into the embargoed test "
            f"window. Required: max(train) < min(test) - embargo. Fail-closed."
        )


def assert_no_future_label_leakage(
    decision_times: ArrayLike,
    label_times: ArrayLike,
) -> None:
    """Fail closed unless every label strictly post-dates its decision.

    Element-wise contract: ``label_times[i] > decision_times[i]`` for all ``i``.
    A label observed at (``==``) or before (``<``) the decision it supervises
    cannot have informed nothing — it is future information leaking into the
    decision moment. The two arrays are paired positionally and must share a
    length.

    Args:
        decision_times: 1-D numeric time coordinate of each decision.
        label_times: 1-D numeric time coordinate of the label realised for the
            decision at the same position.

    Raises:
        LeakageError: if either array is empty/non-1-D/non-finite, if the two
            lengths differ, or if any ``label_times[i] <= decision_times[i]``.
    """
    decisions = _as_finite_1d("decision_times", decision_times)
    labels = _as_finite_1d("label_times", label_times)

    if decisions.shape != labels.shape:
        raise LeakageError(
            f"LEAKAGE-GUARD VIOLATED: shape mismatch — decision_times "
            f"shape={decisions.shape} vs label_times shape={labels.shape}; labels "
            f"are paired to decisions positionally and must align — fail-closed"
        )

    not_future = labels <= decisions
    if bool(np.any(not_future)):
        offending = int(np.argmax(not_future))
        n_bad = int(np.count_nonzero(not_future))
        raise LeakageError(
            f"LEAKAGE-GUARD VIOLATED: future-label leakage — {n_bad} of "
            f"{labels.size} label(s) do not strictly post-date their decision; "
            f"first at index {offending}: label={float(labels[offending])} <= "
            f"decision={float(decisions[offending])}. Required: label > decision "
            f"element-wise. Fail-closed."
        )
