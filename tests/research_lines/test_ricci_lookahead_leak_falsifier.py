# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Look-ahead-leak (lag_sweep_no_future_data) falsifier adequacy.

This is **not** a market claim, alpha, or financial advice. It is a positive +
negative control proving the pre-registered ``lag_sweep_no_future_data`` null
can actually FIRE: it must flag a feature contaminated with future information
and must NOT flag the clean causal feature.

Method (fully synthetic, no real data, no network, no credentials) — reuses the
committed W4 synthetic-null harness so the order book, descriptor, and null are
identical across both falsifier-adequacy tests:

* Negative control — the clean causal Ricci descriptor (past window only). Its
  IC vs the forward return sits inside the permutation-null band → not flagged.
* Positive control — a deliberately look-ahead-contaminated feature: the same
  causal descriptor with a small fraction of the *future* return mixed in
  (a textbook label leak / centered-window bug, injected on purpose). Its IC
  jumps above the null's 95th percentile → flagged.

If the contaminated feature were NOT flagged, the no-lookahead falsifier would be
inadequate (blind to leakage) — a useful failure, not something to mask. The
contamination is an explicit, labeled positive control for the detector; it is
not a property of the Ricci descriptor.

Claim tier is unchanged: INSTRUMENTED / SYNTHETIC. Nothing is promoted.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from tests.research_lines.test_ricci_microstructure_synthetic_falsifier import (
    DATA_SEED,
    N_STEPS,
    _descriptor_series,
    _forward_returns,
    _ic,
    _permutation_null,
    _synthetic_depth5_book,
)

# Injected leak strength (z-scored fraction of the future return mixed into the
# feature). Small enough to be a *subtle* contamination, large enough to clear
# the null band with a robust margin.
LEAK_BETA = 0.03

# Pinned reference statistics for this synthetic realization.
PIN_NULL_P95 = 0.102470
PIN_CAUSAL_IC = 0.059703  # clean feature — inside the null band (not flagged)
PIN_LEAKY_IC = 0.218636  # contaminated feature — above the null (flagged)
PIN_TOLERANCE = 5e-3


def _zscore(x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    return (x - x.mean()) / x.std()


def _leaky_feature(
    causal: npt.NDArray[np.float64], forward: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Causal feature contaminated with a fraction of the FUTURE return.

    This is the deliberate look-ahead leak (positive control). A real pipeline
    must never do this; here we inject it to verify the detector catches it.
    """
    return _zscore(causal) + LEAK_BETA * _zscore(forward)


def _fixture() -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], float]:
    _, _, mid = _synthetic_depth5_book(DATA_SEED, N_STEPS)
    causal = _descriptor_series(mid)
    forward = _forward_returns(mid)
    null_p95 = float(np.percentile(_permutation_null(causal, forward), 95))
    return causal, forward, null_p95


def test_clean_causal_feature_is_not_flagged() -> None:
    """Negative control: the legitimate causal descriptor stays in the null band."""
    causal, forward, null_p95 = _fixture()
    causal_ic = _ic(causal, forward)
    assert causal_ic <= null_p95 + PIN_TOLERANCE, (
        f"FALSE POSITIVE: clean causal feature flagged "
        f"(ic={causal_ic:.6f} > null_p95={null_p95:.6f})"
    )
    assert abs(causal_ic - PIN_CAUSAL_IC) < PIN_TOLERANCE
    assert abs(null_p95 - PIN_NULL_P95) < PIN_TOLERANCE


def test_injected_lookahead_leak_is_flagged() -> None:
    """Positive control: a future-contaminated feature must beat the null."""
    causal, forward, null_p95 = _fixture()
    leaky = _leaky_feature(causal, forward)
    leaky_ic = _ic(leaky, forward)
    assert leaky_ic > null_p95, (
        f"FALSIFIER INADEQUATE: injected look-ahead leak NOT detected "
        f"(leaky_ic={leaky_ic:.6f} <= null_p95={null_p95:.6f}); the "
        f"no-lookahead guard is blind to contamination — do not mask this."
    )
    assert abs(leaky_ic - PIN_LEAKY_IC) < PIN_TOLERANCE


def test_leak_separates_from_clean_feature() -> None:
    """The detector must separate contaminated from clean by a clear margin."""
    causal, forward, _ = _fixture()
    causal_ic = _ic(causal, forward)
    leaky_ic = _ic(_leaky_feature(causal, forward), forward)
    assert leaky_ic > causal_ic + 0.05


def test_leak_detection_is_deterministic() -> None:
    """Same seed ⇒ identical clean and leaky IC (replay precondition)."""
    a_causal, a_fwd, _ = _fixture()
    b_causal, b_fwd, _ = _fixture()
    assert _ic(a_causal, a_fwd) == _ic(b_causal, b_fwd)
    assert _ic(_leaky_feature(a_causal, a_fwd), a_fwd) == _ic(
        _leaky_feature(b_causal, b_fwd), b_fwd
    )
