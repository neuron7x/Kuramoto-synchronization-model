"""Markov regime-state transition analysis.

Composes RV-regime mask (high vs low vol) × diurnal direction (+1/0/−1)
into a discrete state per 1-second row. Estimates the transition matrix
P[i,j] = Pr(state_{t+1} = j | state_t = i) and derives:

    * per-state expected dwell time (1 / (1 − P[i,i]))
    * stationary distribution π (left eigenvector of P at λ=1)
    * persistence summary (mean diagonal probability)

Practical implication for execution:
    diagonal ≳ 0.95  → state persists minutes-to-hours; maker-queue
                       placement is viable (state lasts longer than
                       fill time).
    diagonal ≲ 0.80  → state flickers on second-scale; maker queueing
                       risks filling in a different regime than the
                       one that motivated the trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

STATE_LABELS: Final[tuple[str, ...]] = (
    "low_vol_neg",  # rv below q75, diurnal -1
    "low_vol_flat",  # rv below q75, diurnal  0
    "low_vol_pos",  # rv below q75, diurnal +1
    "high_vol_neg",  # rv above q75, diurnal -1
    "high_vol_flat",
    "high_vol_pos",
)


@dataclass(frozen=True)
class RegimeMarkovReport:
    states: tuple[str, ...]
    transition_matrix: tuple[tuple[float, ...], ...]
    diagonal_persistence: tuple[float, ...]
    expected_dwell_sec: tuple[float, ...]
    stationary_distribution: tuple[float, ...]
    state_counts: tuple[int, ...]
    n_transitions: int
    mean_diagonal: float


def classify_states(
    regime_high_mask: NDArray[np.bool_],
    direction_per_row: NDArray[np.int64],
) -> NDArray[np.int64]:
    """Encode (high_vol, direction) into a state index 0..5.

    STATE_LABELS order:
        0 low_vol_neg    regime_high=False, direction=-1
        1 low_vol_flat   regime_high=False, direction= 0
        2 low_vol_pos    regime_high=False, direction=+1
        3 high_vol_neg   regime_high=True,  direction=-1
        4 high_vol_flat  regime_high=True,  direction= 0
        5 high_vol_pos   regime_high=True,  direction=+1
    """
    n = regime_high_mask.shape[0]
    if direction_per_row.shape != (n,):
        raise ValueError(
            f"shape mismatch: regime_mask {regime_high_mask.shape} "
            f"vs direction {direction_per_row.shape}"
        )
    base = np.where(regime_high_mask, 3, 0).astype(np.int64)
    offset = np.clip(direction_per_row.astype(np.int64), -1, 1) + 1
    return base + offset


def transition_matrix(
    states: NDArray[np.int64],
    *,
    n_states: int = len(STATE_LABELS),
) -> NDArray[np.float64]:
    """Empirical transition probability matrix P[i, j] = Pr(j | i).

    Rows that have no outgoing transition (last row, or row followed by
    invalid state) are skipped. Rows are re-normalised per-origin.
    """
    if states.ndim != 1:
        raise ValueError(f"states must be 1D, got shape {states.shape}")
    counts = np.zeros((n_states, n_states), dtype=np.float64)
    for t in range(states.size - 1):
        i = int(states[t])
        j = int(states[t + 1])
        if 0 <= i < n_states and 0 <= j < n_states:
            counts[i, j] += 1.0
    row_sums = counts.sum(axis=1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        probs = np.where(row_sums > 0, counts / np.where(row_sums > 0, row_sums, 1.0), 0.0)
    return probs


def _stationary_distribution(p: NDArray[np.float64]) -> NDArray[np.float64]:
    """Compute stationary π such that πP = π and Σπ = 1.

    Uses eigen-decomposition of P.T; picks the eigenvector with
    eigenvalue closest to 1. Falls back to uniform if numerics fail.
    """
    n = p.shape[0]
    try:
        vals, vecs = np.linalg.eig(p.T)
        idx = int(np.argmin(np.abs(vals - 1.0)))
        vec = np.real(vecs[:, idx])
        s = vec.sum()
        if abs(s) < 1e-12:
            return np.full(n, 1.0 / n, dtype=np.float64)
        pi = vec / s
        pi = np.clip(pi, 0.0, None)
        total = pi.sum()
        if total <= 0.0:
            return np.full(n, 1.0 / n, dtype=np.float64)
        return np.asarray(pi / total, dtype=np.float64)
    except np.linalg.LinAlgError:
        return np.full(n, 1.0 / n, dtype=np.float64)


def regime_markov_report(
    regime_high_mask: NDArray[np.bool_],
    direction_per_row: NDArray[np.int64],
) -> RegimeMarkovReport:
    """End-to-end: classify → transition matrix → dwell times + stationary."""
    states = classify_states(regime_high_mask, direction_per_row)
    p = transition_matrix(states)
    n_states = p.shape[0]

    diag = np.diag(p)
    dwell = np.where(diag < 1.0, 1.0 / np.maximum(1.0 - diag, 1e-12), float("inf"))
    pi = _stationary_distribution(p)

    counts = np.zeros(n_states, dtype=np.int64)
    for i in range(n_states):
        counts[i] = int((states == i).sum())

    return RegimeMarkovReport(
        states=STATE_LABELS,
        transition_matrix=tuple(tuple(float(x) for x in row) for row in p),
        diagonal_persistence=tuple(float(x) for x in diag),
        expected_dwell_sec=tuple(float(x) for x in dwell),
        stationary_distribution=tuple(float(x) for x in pi),
        state_counts=tuple(int(x) for x in counts),
        n_transitions=int(states.size - 1),
        mean_diagonal=float(diag.mean()),
    )
