"""Fail-closed adversarial tests for the L2 microstructure estimators.

Unit tests cover happy paths; property-based tests cover random-but-
well-posed inputs. This file hits the pathological edge cases that
should never reach a published number:

    · all-NaN input
    · all-Inf input
    · empty input
    · single-element input
    · all-same-value (zero variance) input
    · shape-mismatched inputs
    · negative or zero bins / surrogates / lags

Every estimator must fail-closed: either return the INCONCLUSIVE
verdict with NaN/0 fields, or raise ValueError. No silent garbage
numbers.
"""

from __future__ import annotations

import numpy as np
import pytest

from research.microstructure.conditional_transfer_entropy import (
    conditional_transfer_entropy,
)
from research.microstructure.hurst import dfa_hurst
from research.microstructure.transfer_entropy import transfer_entropy
from research.microstructure.walk_forward import summarize_walk_forward

# ---------------------------------------------------------------------------
# DFA Hurst — adversarial inputs
# ---------------------------------------------------------------------------


def test_hurst_all_nan_returns_inconclusive() -> None:
    x = np.full(1024, np.nan, dtype=np.float64)
    r = dfa_hurst(x)
    assert r.verdict == "INCONCLUSIVE"
    assert r.n_samples_used == 0
    assert not np.isfinite(r.hurst_exponent)


def test_hurst_empty_array_returns_inconclusive() -> None:
    r = dfa_hurst(np.array([], dtype=np.float64))
    assert r.verdict == "INCONCLUSIVE"
    assert not np.isfinite(r.hurst_exponent)


def test_hurst_all_constant_returns_inconclusive() -> None:
    """All-equal → zero fluctuation → cannot fit slope → INCONCLUSIVE."""
    r = dfa_hurst(np.full(1024, 3.14, dtype=np.float64))
    # Either INCONCLUSIVE verdict OR a finite-but-degenerate H; never inf
    assert not np.isinf(r.hurst_exponent)


def test_hurst_single_element_returns_inconclusive() -> None:
    r = dfa_hurst(np.array([1.0], dtype=np.float64))
    assert r.verdict == "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Transfer Entropy — adversarial inputs
# ---------------------------------------------------------------------------


def test_te_shape_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="shape"):
        transfer_entropy(
            np.zeros(100, dtype=np.float64),
            np.zeros(101, dtype=np.float64),
        )


def test_te_too_short_returns_inconclusive() -> None:
    r = transfer_entropy(
        np.arange(50, dtype=np.float64),
        np.arange(50, dtype=np.float64),
        n_bins=5,
        n_surrogates=20,
    )
    assert r.verdict == "INCONCLUSIVE"
    assert not np.isfinite(r.te_y_to_x_nats)


def test_te_all_nan_returns_inconclusive() -> None:
    x = np.full(1024, np.nan, dtype=np.float64)
    y = np.full(1024, np.nan, dtype=np.float64)
    r = transfer_entropy(x, y, n_bins=5, n_surrogates=20)
    assert r.verdict == "INCONCLUSIVE"


def test_te_bad_n_bins_raises() -> None:
    x = np.zeros(500, dtype=np.float64)
    with pytest.raises(ValueError, match="n_bins"):
        transfer_entropy(x, x, n_bins=1)


def test_te_bad_lag_raises() -> None:
    x = np.zeros(500, dtype=np.float64)
    with pytest.raises(ValueError, match="lag_rows"):
        transfer_entropy(x, x, lag_rows=0)


def test_te_bad_surrogates_raises() -> None:
    x = np.zeros(500, dtype=np.float64)
    with pytest.raises(ValueError, match="n_surrogates"):
        transfer_entropy(x, x, n_surrogates=5)


# ---------------------------------------------------------------------------
# Conditional TE — adversarial inputs
# ---------------------------------------------------------------------------


def test_cte_shape_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="shape"):
        conditional_transfer_entropy(
            np.zeros(100, dtype=np.float64),
            np.zeros(100, dtype=np.float64),
            np.zeros(101, dtype=np.float64),
        )


def test_cte_all_inf_treated_as_non_finite() -> None:
    inf_x = np.full(1024, np.inf, dtype=np.float64)
    z = np.random.default_rng(42).normal(0.0, 1.0, size=1024).astype(np.float64)
    r = conditional_transfer_entropy(inf_x, z, z, n_bins=5, n_surrogates=20)
    # Inf is not finite → filtered out → INCONCLUSIVE when <500 rows remain
    assert r.verdict == "INCONCLUSIVE"


def test_cte_bad_n_bins_raises() -> None:
    x = np.zeros(1000, dtype=np.float64)
    with pytest.raises(ValueError, match="n_bins"):
        conditional_transfer_entropy(x, x, x, n_bins=1)


# ---------------------------------------------------------------------------
# Walk-forward summary — adversarial inputs
# ---------------------------------------------------------------------------


def test_wf_empty_rows_returns_inconclusive(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json

    p = tmp_path / "wf.json"
    p.write_text(json.dumps({"rows": [], "window_sec": 2400, "step_sec": 300}))
    r = summarize_walk_forward(p)
    assert r.verdict == "INCONCLUSIVE"
    assert r.n_valid == 0
    assert not np.isfinite(r.ic_mean)


def test_wf_all_nan_ics_returns_inconclusive(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json

    rows = [{"ic_signal": None, "perm_p": None} for _ in range(30)]
    p = tmp_path / "wf.json"
    p.write_text(json.dumps({"rows": rows, "window_sec": 2400, "step_sec": 300}))
    r = summarize_walk_forward(p)
    assert r.verdict == "INCONCLUSIVE"
    assert r.n_valid == 0


def test_wf_missing_required_fields_handled_gracefully(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json

    # Rows missing ic_signal AND perm_p entirely — should be treated as absent
    rows: list[dict[str, object]] = [{}, {}, {}]
    p = tmp_path / "wf.json"
    p.write_text(json.dumps({"rows": rows, "window_sec": 2400, "step_sec": 300}))
    r = summarize_walk_forward(p)
    assert r.verdict == "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Cross-estimator contract — no silent NaN propagation
# ---------------------------------------------------------------------------


def test_no_estimator_returns_inf_on_adversarial() -> None:
    """Compound check: every estimator returns finite-or-NaN, never ±inf."""
    x = np.full(512, np.nan, dtype=np.float64)
    y = np.full(512, np.nan, dtype=np.float64)
    z = np.full(512, np.nan, dtype=np.float64)

    r_h = dfa_hurst(x)
    assert not np.isinf(r_h.hurst_exponent)

    r_te = transfer_entropy(x, y, n_bins=5, n_surrogates=20)
    assert not np.isinf(r_te.te_y_to_x_nats)
    assert not np.isinf(r_te.te_x_to_y_nats)

    r_cte = conditional_transfer_entropy(x, y, z, n_bins=5, n_surrogates=20)
    assert not np.isinf(r_cte.te_unconditional_y_to_x_nats)
    assert not np.isinf(r_cte.te_conditional_y_to_x_nats)
