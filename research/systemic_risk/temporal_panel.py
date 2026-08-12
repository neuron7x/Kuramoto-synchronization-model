# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Temporal-exposure-panel boundary validator.

The end-to-end falsification path (deferred — see
``falsification.run_end_to_end_falsification``) consumes a panel of
exposure snapshots indexed by date. This module ships the *boundary
contract* for that input today so the eventual ingest pipeline cannot
silently drift away from the documented schema.

The validator is fail-closed: any contract violation raises an
:class:`InvalidTemporalPanelError`. There is no "best-effort
repair" branch — the goal is to make the empirical pipeline
trustworthy from its first input.

Pure-function API. No I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import numpy as np
from numpy.typing import NDArray

from .errors import (
    InvalidExposureMatrixError,
    InvalidNodeLabelsError,
    InvalidTemporalPanelError,
)

__all__ = [
    "validate_temporal_exposure_panel",
]


def validate_temporal_exposure_panel(
    panels: Mapping[date, NDArray[np.float64]],
    node_labels: tuple[str, ...],
) -> None:
    """Validate a temporal panel of exposure snapshots.

    Contract (every condition is fail-closed):

    1. ``panels`` is non-empty.
    2. Every key is a :class:`datetime.date`; iteration in sorted
       order is strictly increasing (no duplicate dates).
    3. Every value is a square ``(N, N)`` ``np.ndarray`` with the
       same ``N`` as ``len(node_labels)``.
    4. Every value is finite (no NaN, no Inf) and non-negative.
    5. ``node_labels`` itself satisfies the same uniqueness /
       non-empty / non-whitespace contract enforced by
       :func:`from_exposure_matrix` (delegated to that path's
       label invariants via direct re-validation here).

    Raises
    ------
    InvalidTemporalPanelError
        Empty panel, non-monotonic dates, or shape inconsistencies
        across snapshots.
    InvalidExposureMatrixError
        A snapshot violates the per-matrix invariants (NaN/Inf,
        negative entry, non-square shape).
    InvalidNodeLabelsError
        ``node_labels`` is empty / has duplicates / has empty or
        whitespace-only entries / contains None or non-str.
    """
    if not panels:
        raise InvalidTemporalPanelError("panels must be non-empty; got 0 snapshots")
    # Label-side contract — mirrors topology.from_exposure_matrix.
    if any(lbl is None for lbl in node_labels):
        raise InvalidNodeLabelsError("node_labels must not contain None")
    if any(not isinstance(lbl, str) for lbl in node_labels):
        raise InvalidNodeLabelsError("node_labels must contain only str values")
    if any(lbl.strip() == "" for lbl in node_labels):
        raise InvalidNodeLabelsError(
            "node_labels must not contain empty or whitespace-only strings"
        )
    if len(set(node_labels)) != len(node_labels):
        raise InvalidNodeLabelsError("node_labels must be unique")
    n = len(node_labels)
    if n == 0:
        raise InvalidNodeLabelsError("node_labels must be non-empty")
    sorted_keys = sorted(panels.keys())
    prev: date | None = None
    for k in sorted_keys:
        if not isinstance(k, date):
            raise InvalidTemporalPanelError(
                f"panel keys must be datetime.date, got {type(k).__name__}"
            )
        if prev is not None and k <= prev:
            raise InvalidTemporalPanelError(
                f"panel dates must be strictly increasing; prev={prev} >= current={k}"
            )
        prev = k
    for k in sorted_keys:
        snapshot = np.asarray(panels[k], dtype=np.float64)
        if snapshot.ndim != 2 or snapshot.shape[0] != snapshot.shape[1]:
            raise InvalidExposureMatrixError(
                f"snapshot {k} must be square 2-D, got shape={snapshot.shape}"
            )
        if snapshot.shape[0] != n:
            raise InvalidTemporalPanelError(
                f"snapshot {k} has shape {snapshot.shape} but "
                f"node_labels length is {n}; node universe must be "
                f"stable across the panel (entry/exit policy must be "
                f"explicit, not silent)"
            )
        if not np.isfinite(snapshot).all():
            raise InvalidExposureMatrixError(f"snapshot {k} contains non-finite entries (NaN/Inf)")
        if np.any(snapshot < 0):
            raise InvalidExposureMatrixError(f"snapshot {k} contains negative exposures")
