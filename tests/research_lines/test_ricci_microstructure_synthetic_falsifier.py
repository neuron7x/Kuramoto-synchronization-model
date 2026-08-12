# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Synthetic-null falsifier adequacy for the ricci_microstructure_v1 descriptor.

This is **not** a market claim, alpha, or financial advice. It is a
falsifier-adequacy check: it proves the pre-registered ``permutation_null``
can actually FIRE — i.e. the Ollivier–Ricci microstructure descriptor does
**not** manufacture a signal out of pure noise.

Construction (fully synthetic, no real data, no network, no credentials):

* A structureless depth-5 order book is generated from a seeded RNG. The mid
  price is a martingale (i.i.d. Gaussian log-returns), so the one-step *forward*
  return is independent, by construction, of any descriptor computed from the
  *past* window. A faithful descriptor therefore CANNOT predict it.
* The descriptor is the existing, read-only Ollivier–Ricci pipeline
  ``mean_ricci(build_price_graph(mid_window))`` rolled over sliding windows.
* The information coefficient (IC) is the Spearman rank correlation between the
  descriptor and the forward return.
* The ``permutation_null`` shuffles the forward returns under a fixed seed and
  recomputes the IC many times.

The falsifier FIRES when the descriptor IC does not exceed the null's 95th
percentile and the permutation p-value is not significant. If the descriptor
ever BEAT the null on this noise, that is a useful failure (a look-ahead leak or
a structure-encoding generator) and the assertion must NOT be relaxed.

The claim tier is unchanged: INSTRUMENTED / SYNTHETIC. Nothing is promoted.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from scipy.stats import spearmanr

from core.indicators.ricci import build_price_graph, mean_ricci

# ── Pre-registered, deterministic configuration ────────────────────────────
DATA_SEED = 7
PERM_SEED = 123
N_STEPS = 400
WINDOW = 32
DELTA = 0.005
N_PERMUTATIONS = 500
DEPTH = 5

# Falsifier-fires thresholds.
ALPHA = 0.05  # permutation p-value at/above this ⇒ not significant ⇒ fires
PIN_TOLERANCE = 5e-3  # loose enough for BLAS drift, tight enough to catch a leak

# Pinned reference statistics (this synthetic realization). The headline
# falsifier outcome (ic <= p95, p >= ALPHA) holds with a ~0.043 margin, robust
# to numerical noise; the pins guard against silent regression / a leak.
PIN_DESCRIPTOR_IC = 0.059703
PIN_NULL_P95 = 0.102470
PIN_PERM_PVALUE = 0.2575


def _synthetic_depth5_book(
    seed: int, n: int
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Return (bid_px[n,5], ask_px[n,5], mid[n]) for a structureless book.

    The mid is a martingale; the book is symmetric depth-5 quotes around it.
    No predictable structure is encoded, so it is a valid null.
    """
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(0.0, 1e-3, size=n)
    mid = 100.0 * np.exp(np.cumsum(log_returns))
    # Half-spread and per-level offsets/sizes drawn from the same RNG; structure-free.
    half_spread = 0.01 + 0.002 * rng.random(n)
    level_offsets = np.arange(1, DEPTH + 1, dtype=np.float64) * 0.01
    bid_px = mid[:, None] - half_spread[:, None] - level_offsets[None, :]
    ask_px = mid[:, None] + half_spread[:, None] + level_offsets[None, :]
    # Mid reconstructed from L1 equals the martingale mid (symmetric quotes).
    recon_mid = (bid_px[:, 0] + ask_px[:, 0]) / 2.0
    return bid_px, ask_px, recon_mid


def _descriptor_series(mid: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Rolling mean Ollivier–Ricci curvature over past mid-price windows."""
    values = [
        mean_ricci(build_price_graph(mid[t - WINDOW : t], delta=DELTA))
        for t in range(WINDOW, len(mid) - 1)
    ]
    return np.asarray(values, dtype=np.float64)


def _forward_returns(mid: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """One-step forward return aligned to each descriptor sample (no look-ahead)."""
    return np.asarray(
        [(mid[t + 1] - mid[t]) / mid[t] for t in range(WINDOW, len(mid) - 1)],
        dtype=np.float64,
    )


def _ic(a: npt.NDArray[np.float64], b: npt.NDArray[np.float64]) -> float:
    return abs(float(spearmanr(a, b).correlation))


def _permutation_null(
    descriptor: npt.NDArray[np.float64], forward: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    rng = np.random.default_rng(PERM_SEED)
    return np.asarray(
        [_ic(descriptor, rng.permutation(forward)) for _ in range(N_PERMUTATIONS)],
        dtype=np.float64,
    )


def test_descriptor_is_deterministic() -> None:
    """Same seed ⇒ bit-identical book and descriptor (replay precondition)."""
    _, _, mid_a = _synthetic_depth5_book(DATA_SEED, N_STEPS)
    _, _, mid_b = _synthetic_depth5_book(DATA_SEED, N_STEPS)
    assert np.array_equal(mid_a, mid_b)
    assert np.array_equal(_descriptor_series(mid_a), _descriptor_series(mid_b))


def test_book_is_synthetic_depth5_and_credential_free() -> None:
    """The input is a structureless depth-5 book — no real/credentialed data."""
    bid_px, ask_px, mid = _synthetic_depth5_book(DATA_SEED, N_STEPS)
    assert bid_px.shape == (N_STEPS, DEPTH)
    assert ask_px.shape == (N_STEPS, DEPTH)
    # Well-formed book: best ask strictly above best bid, levels monotone.
    assert np.all(ask_px[:, 0] > bid_px[:, 0])
    assert np.all(np.diff(ask_px, axis=1) > 0)
    assert np.all(np.diff(bid_px, axis=1) < 0)


def test_permutation_null_fires_on_synthetic_noise() -> None:
    """Core falsifier-adequacy assertion: the descriptor does NOT beat the null.

    On a martingale mid the forward return is independent of the past-window
    descriptor, so a faithful Ricci descriptor must produce an IC inside the
    permutation-null band. If it exceeds the null, STOP — that is a look-ahead
    leak or a structure-encoding generator, not a signal. Do not relax this.
    """
    _, _, mid = _synthetic_depth5_book(DATA_SEED, N_STEPS)
    descriptor = _descriptor_series(mid)
    forward = _forward_returns(mid)
    assert descriptor.shape == forward.shape
    assert not np.isnan(descriptor).any()

    descriptor_ic = _ic(descriptor, forward)
    null = _permutation_null(descriptor, forward)
    null_p95 = float(np.percentile(null, 95))
    # One-sided permutation p-value (with +1 smoothing).
    pvalue = float((np.sum(null >= descriptor_ic) + 1) / (N_PERMUTATIONS + 1))

    # Falsifier FIRES: descriptor IC does not exceed the 95th-percentile null,
    # and the permutation test is not significant.
    assert descriptor_ic <= null_p95 + PIN_TOLERANCE, (
        f"FALSIFIER DID NOT FIRE: descriptor_ic={descriptor_ic:.6f} beat "
        f"null_p95={null_p95:.6f} on synthetic noise — investigate look-ahead "
        f"leak or structured generator; do NOT relax this assertion."
    )
    assert pvalue >= ALPHA, (
        f"descriptor IC significant vs permutation null (p={pvalue:.4f} < {ALPHA}) "
        f"on noise — falsifier failed to fire; investigate, do not mask."
    )

    # Regression pins (loose tolerance for BLAS drift).
    assert abs(descriptor_ic - PIN_DESCRIPTOR_IC) < PIN_TOLERANCE
    assert abs(null_p95 - PIN_NULL_P95) < PIN_TOLERANCE
    assert abs(pvalue - PIN_PERM_PVALUE) < 5e-2
