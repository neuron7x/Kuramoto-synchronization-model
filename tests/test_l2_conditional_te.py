"""Tests for Conditional Transfer Entropy (common-factor conditioning)."""

from __future__ import annotations

import numpy as np
import pytest

from research.microstructure.conditional_transfer_entropy import (
    ConditionalTEReport,
    conditional_transfer_entropy,
)

_SEED = 42


def test_cte_common_factor_artifact_collapses() -> None:
    """H_B synthesis: x, y both driven by z → conditional TE not significant.

    Construction:
        z_t = strong AR(1) common driver
        x_t = α · z_{t-1} + private_x
        y_t = α · z_{t-1} + private_y
        (no y→x coupling beyond shared response to z)

    Expected: conditioning on z removes any apparent y→x flow — the null
    hypothesis that y_past adds no information beyond (x_past, z_past) is
    not rejected.
    """
    rng = np.random.default_rng(_SEED)
    n = 8000
    z = np.zeros(n, dtype=np.float64)
    eps_z = rng.normal(0.0, 1.0, size=n)
    for t in range(1, n):
        z[t] = 0.85 * z[t - 1] + eps_z[t]
    x_private = rng.normal(0.0, 0.25, size=n)
    y_private = rng.normal(0.0, 0.25, size=n)
    x = np.zeros(n, dtype=np.float64)
    y = np.zeros(n, dtype=np.float64)
    for t in range(1, n):
        x[t] = 1.5 * z[t - 1] + x_private[t]
        y[t] = 1.5 * z[t - 1] + y_private[t]

    r = conditional_transfer_entropy(x, y, z, n_bins=4, n_surrogates=60, seed=_SEED)
    assert isinstance(r, ConditionalTEReport)
    assert r.p_value_conditional > 0.05
    assert r.verdict != "PRIVATE_FLOW"


def test_cte_private_flow_survives_conditioning() -> None:
    """y→x direct coupling independent of z → conditional TE remains significant."""
    rng = np.random.default_rng(_SEED)
    n = 4000
    z = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    y = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    x = np.zeros(n, dtype=np.float64)
    noise = rng.normal(0.0, 0.25, size=n)
    for t in range(1, n):
        x[t] = 0.7 * x[t - 1] + 0.8 * y[t - 1] + noise[t]

    r = conditional_transfer_entropy(x, y, z, n_bins=5, n_surrogates=60, seed=_SEED)
    assert r.te_conditional_y_to_x_nats > 0.0
    assert r.p_value_conditional < 0.05
    assert r.verdict in {"PRIVATE_FLOW", "PARTIAL"}


def test_cte_no_coupling_returns_no_flow_or_common() -> None:
    """Independent x, y, z → both TEs near zero."""
    rng = np.random.default_rng(_SEED)
    n = 3000
    x = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    y = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    z = rng.normal(0.0, 1.0, size=n).astype(np.float64)

    r = conditional_transfer_entropy(x, y, z, n_bins=5, n_surrogates=60, seed=_SEED)
    assert r.p_value_conditional > 0.05
    assert r.verdict in {"NO_FLOW", "COMMON_FACTOR"}


def test_cte_deterministic_under_fixed_seed() -> None:
    rng = np.random.default_rng(_SEED)
    x = rng.normal(0.0, 1.0, size=1500).astype(np.float64)
    y = rng.normal(0.0, 1.0, size=1500).astype(np.float64)
    z = rng.normal(0.0, 1.0, size=1500).astype(np.float64)
    a = conditional_transfer_entropy(x, y, z, n_bins=5, n_surrogates=30, seed=_SEED)
    b = conditional_transfer_entropy(x, y, z, n_bins=5, n_surrogates=30, seed=_SEED)
    assert a.te_unconditional_y_to_x_nats == b.te_unconditional_y_to_x_nats
    assert a.te_conditional_y_to_x_nats == b.te_conditional_y_to_x_nats
    assert a.p_value_conditional == b.p_value_conditional


def test_cte_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError):
        conditional_transfer_entropy(
            np.zeros(100, dtype=np.float64),
            np.zeros(100, dtype=np.float64),
            np.zeros(101, dtype=np.float64),
        )


def test_cte_rejects_bad_params() -> None:
    x = np.zeros(1000, dtype=np.float64)
    with pytest.raises(ValueError):
        conditional_transfer_entropy(x, x, x, n_bins=1)
    with pytest.raises(ValueError):
        conditional_transfer_entropy(x, x, x, lag_rows=0)
    with pytest.raises(ValueError):
        conditional_transfer_entropy(x, x, x, n_surrogates=5)


def test_cte_too_short_returns_inconclusive() -> None:
    x = np.arange(100, dtype=np.float64)
    r = conditional_transfer_entropy(x, x, x, n_bins=4, n_surrogates=20)
    assert r.verdict == "INCONCLUSIVE"
    assert not np.isfinite(r.te_conditional_y_to_x_nats)


def test_cte_te_never_negative() -> None:
    """Both CTE and UTE are KL divergences — must be ≥ 0."""
    rng = np.random.default_rng(_SEED)
    n = 2000
    x = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    y = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    z = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    r = conditional_transfer_entropy(x, y, z, n_bins=5, n_surrogates=30, seed=_SEED)
    assert r.te_unconditional_y_to_x_nats >= 0.0
    assert r.te_conditional_y_to_x_nats >= 0.0


def test_cte_schema_complete_on_happy_path() -> None:
    rng = np.random.default_rng(_SEED)
    n = 2000
    x = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    y = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    z = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    r = conditional_transfer_entropy(x, y, z, n_bins=5, n_surrogates=30, seed=_SEED)
    assert isinstance(r.reduction_nats, float)
    assert 0.0 < r.p_value_conditional <= 1.0
    assert r.n_samples == n
    assert r.n_surrogates == 30
    assert r.n_bins == 5
    assert r.lag_rows == 1
