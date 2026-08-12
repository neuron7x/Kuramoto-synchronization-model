# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Synthetic-null falsifier-adequacy test for ``ricci_microstructure_v1`` (W4).

Closes one physics-evidence gap: proves the production Ricci/geometric descriptor
does NOT hallucinate forward predictive signal on **structureless** synthetic
depth-5 order-book noise.

Status discipline (unchanged by this test):
    INSTRUMENTED / SYNTHETIC / NO EMPIRICAL MARKET PROMOTION.
    This is a falsifier-adequacy test — not a market-signal claim, not alpha,
    not financial advice, and it does not promote measured maturity.

Core law:
    On structureless data the descriptor's |IC| must sit inside the permutation
    null band (``beats_null is False``). A firing falsifier is a real defect
    signal — never silenced by tuning the generator. To prevent a vacuous green,
    a teeth test injects a planted signal and asserts the same machinery FIRES.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest

from tools.research.ricci_synthetic_null import (
    SyntheticNullConfig,
    SyntheticNullResult,
    evaluate_synthetic_null,
    generate_structureless_depth5_book,
    permutation_null_decision,
    ricci_descriptor_series,
)

# A-priori fixed seeds (chosen before observing any result; NOT search-tuned).
HONEST_SEEDS = (20260615, 1, 42, 777, 99999)

# Pinned reference statistics for the default (seed=20260615) realization.
# The headline outcome (|IC| inside the null band, p >= alpha) holds with a wide
# ~0.07 margin; the pins guard against a silent regression or a look-ahead leak.
PIN_OBSERVED_IC = 0.028944
PIN_NULL_BAND = 0.101737
PIN_P_VALUE = 0.570215
PIN_TOLERANCE = 5e-3  # loose enough for BLAS drift, tight enough to catch a leak


@pytest.fixture(scope="module")
def control_result() -> SyntheticNullResult:
    return evaluate_synthetic_null()


# --------------------------------------------------------------------------- #
# Synthetic substrate is genuinely structureless depth-5 noise
# --------------------------------------------------------------------------- #
def test_synthetic_book_is_depth5_and_well_formed() -> None:
    cfg = SyntheticNullConfig()
    book = generate_structureless_depth5_book(cfg)
    assert book.bid.shape == (cfg.n_ticks, 5)
    assert book.ask.shape == (cfg.n_ticks, 5)
    assert book.bid_size.shape == (cfg.n_ticks, 5)
    assert np.all(np.isfinite(book.mid)) and np.all(book.mid > 0.0)
    # Best bid below mid below best ask; levels strictly monotone (valid book).
    assert np.all(book.bid[:, 0] < book.mid) and np.all(book.ask[:, 0] > book.mid)
    assert np.all(np.diff(book.bid, axis=1) < 0.0)
    assert np.all(np.diff(book.ask, axis=1) > 0.0)
    assert np.all(book.bid_size > 0.0) and np.all(book.ask_size > 0.0)


def test_mid_returns_are_serially_unstructured() -> None:
    """Lag-1 autocorrelation of mid log-returns is within sampling noise of 0."""
    cfg = SyntheticNullConfig()
    book = generate_structureless_depth5_book(cfg)
    r = np.diff(np.log(book.mid))
    r0, r1 = r[:-1], r[1:]
    ac1 = float(np.corrcoef(r0, r1)[0, 1])
    # ~2/sqrt(N) two-sigma band for white-noise autocorrelation.
    assert abs(ac1) < 3.0 / np.sqrt(r.size)


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
def test_evaluation_is_deterministic(control_result: SyntheticNullResult) -> None:
    assert evaluate_synthetic_null() == control_result


def test_descriptor_series_is_deterministic() -> None:
    cfg = dataclasses.replace(SyntheticNullConfig(), n_ticks=600)
    mid = generate_structureless_depth5_book(cfg).mid
    a = ricci_descriptor_series(mid, cfg)
    b = ricci_descriptor_series(mid, cfg)
    np.testing.assert_array_equal(np.nan_to_num(a), np.nan_to_num(b))


def test_descriptor_respects_ricci_bound_inv_rc3() -> None:
    """INV-RC3: build_price_graph curvature stays in [-1, 1] — even on noise.

    The descriptor must honour its physics contract regardless of input; a value
    outside the bound would signal a graph-construction or curvature regression,
    independent of any predictive claim.
    """
    cfg = dataclasses.replace(SyntheticNullConfig(), n_ticks=900)
    mid = generate_structureless_depth5_book(cfg).mid
    series = ricci_descriptor_series(mid, cfg)
    finite = series[np.isfinite(series)]
    assert finite.size > 0
    lo, hi = float(finite.min()), float(finite.max())
    assert np.all(finite >= -1.0) and np.all(finite <= 1.0), (
        f"INV-RC3 VIOLATED: descriptor curvature [{lo:.4f}, {hi:.4f}] left [-1, 1] "
        f"on structureless depth-5 noise; expected every windowed curvature inside "
        f"the build_price_graph bound (consecutive integer nodes). "
        f"delta={cfg.delta}, window={cfg.window}, n_ticks={cfg.n_ticks}, seed={cfg.seed}"
    )


# --------------------------------------------------------------------------- #
# CORE LAW — descriptor must NOT beat the null on structureless noise
# --------------------------------------------------------------------------- #
def test_ricci_does_not_beat_null_on_structureless_noise(
    control_result: SyntheticNullResult,
) -> None:
    r = control_result
    assert r.n_samples >= 8
    # The falsifier must not fire: descriptor manufactures no signal.
    assert r.beats_null is False, (
        f"FALSIFIER FIRED: Ricci |IC|={r.observed_ic:.4f} beat the permutation "
        f"null band={r.null_abs_ic_band:.4f} (p={r.p_value:.4f}) on structureless "
        "depth-5 noise. Do NOT tune the generator to suppress this — it is a real "
        "defect signal that the descriptor hallucinates signal."
    )
    assert r.observed_ic <= r.null_abs_ic_band
    assert r.p_value >= SyntheticNullConfig().alpha
    # Regression pins against the fixed realization (catch silent leak/drift).
    assert abs(r.observed_ic - PIN_OBSERVED_IC) < PIN_TOLERANCE
    assert abs(r.null_abs_ic_band - PIN_NULL_BAND) < PIN_TOLERANCE
    assert abs(r.p_value - PIN_P_VALUE) < 5e-2


@pytest.mark.parametrize("seed", HONEST_SEEDS)
def test_negative_control_holds_across_fixed_seeds(seed: int) -> None:
    cfg = dataclasses.replace(SyntheticNullConfig(), seed=seed, n_permutations=600)
    r = evaluate_synthetic_null(cfg)
    assert r.beats_null is False, (
        f"FALSIFIER FIRED at seed={seed}: |IC|={r.observed_ic:.4f} > "
        f"band={r.null_abs_ic_band:.4f}. Report, do not hide."
    )


# --------------------------------------------------------------------------- #
# Adequacy ("teeth") — the same machinery MUST fire on a planted signal
# --------------------------------------------------------------------------- #
def test_falsifier_fires_on_planted_signal() -> None:
    """Guards against a vacuous green: an injected monotone signal must beat the null."""
    cfg = dataclasses.replace(SyntheticNullConfig(), n_permutations=600)
    rng = np.random.default_rng(0)
    sig = rng.normal(size=300)
    fwd = 3.0 * sig + rng.normal(0.0, 0.1, size=300)  # strong rank dependence
    r = permutation_null_decision(sig, fwd, cfg)
    assert r.beats_null is True
    assert r.observed_ic > r.null_abs_ic_band
    assert r.p_value < cfg.alpha


def test_cli_emits_artifact_and_zero_exit(tmp_path: Path) -> None:
    from tools.research.ricci_synthetic_null import main

    out = tmp_path / "synthetic_null_falsifier.json"
    rc = main([str(out)])
    assert rc == 0  # control passes → falsifier does not fire
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["line_id"] == "ricci_microstructure_v1"
    assert payload["status"] == "INSTRUMENTED"
    assert payload["result"]["beats_null"] is False


def test_decision_rejects_undersized_or_misaligned_samples() -> None:
    cfg = SyntheticNullConfig()
    with pytest.raises(ValueError, match="aligned samples"):
        permutation_null_decision(np.zeros(4), np.zeros(4), cfg)
    with pytest.raises(ValueError, match="aligned samples"):
        permutation_null_decision(np.zeros(20), np.zeros(19), cfg)
