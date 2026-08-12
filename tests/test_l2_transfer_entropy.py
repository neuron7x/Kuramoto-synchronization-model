"""Tests for Transfer Entropy estimator (binned + surrogate null)."""

from __future__ import annotations

import numpy as np
import pytest

from research.microstructure.transfer_entropy import (
    TransferEntropyReport,
    transfer_entropy,
)

_SEED = 42


def test_te_independent_series_null() -> None:
    """Independent sources → TE not significant in either direction."""
    rng = np.random.default_rng(_SEED)
    x = rng.normal(0.0, 1.0, size=4000).astype(np.float64)
    y = rng.normal(0.0, 1.0, size=4000).astype(np.float64)
    r = transfer_entropy(x, y, n_bins=6, n_surrogates=100, seed=_SEED)
    assert isinstance(r, TransferEntropyReport)
    assert r.verdict in {"NO_FLOW", "INCONCLUSIVE"}
    assert r.p_value_y_to_x > 0.05
    assert r.p_value_x_to_y > 0.05


def test_te_unidirectional_coupling_detected() -> None:
    """y drives x: x_{t+1} = 0.7·x_t + 0.6·y_t + ε → Y_LEADS_X, significant."""
    rng = np.random.default_rng(_SEED)
    n = 6000
    y = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    x = np.zeros(n, dtype=np.float64)
    noise = rng.normal(0.0, 0.2, size=n)
    for t in range(1, n):
        x[t] = 0.7 * x[t - 1] + 0.6 * y[t - 1] + noise[t]
    r = transfer_entropy(x, y, n_bins=6, n_surrogates=100, seed=_SEED)
    assert r.te_y_to_x_nats > 0.0
    assert r.p_value_y_to_x < 0.05
    assert r.asymmetry_nats > 0.0
    assert r.verdict in {"Y_LEADS_X", "BIDIRECTIONAL"}


def test_te_reverse_direction_is_weaker() -> None:
    """With y→x coupling, TE(Y→X) > TE(X→Y) (asymmetry > 0)."""
    rng = np.random.default_rng(_SEED)
    n = 6000
    y = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    x = np.zeros(n, dtype=np.float64)
    noise = rng.normal(0.0, 0.2, size=n)
    for t in range(1, n):
        x[t] = 0.7 * x[t - 1] + 0.6 * y[t - 1] + noise[t]
    r = transfer_entropy(x, y, n_bins=6, n_surrogates=100, seed=_SEED)
    assert r.te_y_to_x_nats > r.te_x_to_y_nats


def test_te_deterministic_under_fixed_seed() -> None:
    rng = np.random.default_rng(_SEED)
    x = rng.normal(0.0, 1.0, size=2000).astype(np.float64)
    y = rng.normal(0.0, 1.0, size=2000).astype(np.float64)
    a = transfer_entropy(x, y, n_bins=6, n_surrogates=50, seed=_SEED)
    b = transfer_entropy(x, y, n_bins=6, n_surrogates=50, seed=_SEED)
    assert a.te_y_to_x_nats == b.te_y_to_x_nats
    assert a.te_x_to_y_nats == b.te_x_to_y_nats
    assert a.p_value_y_to_x == b.p_value_y_to_x


def test_te_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError):
        transfer_entropy(
            np.arange(100, dtype=np.float64),
            np.arange(101, dtype=np.float64),
        )


def test_te_rejects_bad_params() -> None:
    x = np.zeros(500, dtype=np.float64)
    with pytest.raises(ValueError):
        transfer_entropy(x, x, n_bins=1)
    with pytest.raises(ValueError):
        transfer_entropy(x, x, lag_rows=0)
    with pytest.raises(ValueError):
        transfer_entropy(x, x, n_surrogates=2)


def test_te_too_short_returns_inconclusive() -> None:
    x = np.arange(50, dtype=np.float64)
    r = transfer_entropy(x, x, n_bins=4, n_surrogates=20)
    assert r.verdict == "INCONCLUSIVE"
    assert not np.isfinite(r.te_y_to_x_nats)
    assert not np.isfinite(r.te_x_to_y_nats)


def test_te_schema_complete_on_happy_path() -> None:
    rng = np.random.default_rng(_SEED)
    x = rng.normal(0.0, 1.0, size=2000).astype(np.float64)
    y = rng.normal(0.0, 1.0, size=2000).astype(np.float64)
    r = transfer_entropy(x, y, n_bins=6, n_surrogates=50, seed=_SEED)
    assert isinstance(r.te_y_to_x_nats, float)
    assert isinstance(r.te_x_to_y_nats, float)
    assert isinstance(r.asymmetry_nats, float)
    assert 0.0 < r.p_value_y_to_x <= 1.0
    assert 0.0 < r.p_value_x_to_y <= 1.0
    assert r.n_samples == 2000
    assert r.n_surrogates == 50
    assert r.n_bins == 6
    assert r.lag_rows == 1


def test_te_never_negative() -> None:
    """TE is a KL divergence — must be ≥ 0 even on pathological inputs."""
    rng = np.random.default_rng(_SEED)
    x = rng.normal(0.0, 1.0, size=2000).astype(np.float64)
    y = rng.normal(0.0, 1.0, size=2000).astype(np.float64)
    r = transfer_entropy(x, y, n_bins=8, n_surrogates=30, seed=_SEED)
    assert r.te_y_to_x_nats >= 0.0
    assert r.te_x_to_y_nats >= 0.0
