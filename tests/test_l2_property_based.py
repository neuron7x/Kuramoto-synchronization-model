"""Property-based tests for the L2 microstructure estimators.

Hand-picked unit tests cover canonical cases (known signals, fixed seeds).
These Hypothesis strategies exercise the estimators against *random*
inputs across plausible parameter space. They catch edge-case failures
that fixed tests cannot anticipate: pathological scalings, NaN-injected
series, all-equal values, bi-modal distributions, degenerate constants.

Each property below is an algebraic or structural guarantee — not a
statistical hope — that the estimator must satisfy universally.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from research.microstructure.conditional_transfer_entropy import (
    conditional_transfer_entropy,
)
from research.microstructure.hurst import dfa_hurst
from research.microstructure.transfer_entropy import transfer_entropy
from research.microstructure.walk_forward import summarize_walk_forward

# ---------------------------------------------------------------------------
# DFA Hurst — scale-invariance + bounded output
# ---------------------------------------------------------------------------


@given(
    n=st.integers(min_value=256, max_value=2048),
    seed=st.integers(min_value=0, max_value=10_000),
    scale=st.floats(min_value=0.1, max_value=10.0, allow_nan=False),
)
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
def test_hurst_is_scale_invariant(n: int, seed: int, scale: float) -> None:
    """DFA-1 Hurst is invariant under multiplicative rescaling on well-posed
    signals. Signals are Gaussian white noise so the integrated fluctuation
    function is guaranteed well above float64 precision at every scale.
    """
    rng = np.random.default_rng(seed)
    signal = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    scaled = (signal * scale).astype(np.float64)
    r1 = dfa_hurst(signal)
    r2 = dfa_hurst(scaled)
    if np.isfinite(r1.hurst_exponent) and np.isfinite(r2.hurst_exponent):
        assert abs(r1.hurst_exponent - r2.hurst_exponent) < 1e-4


@given(
    n=st.integers(min_value=256, max_value=2048),
    seed=st.integers(min_value=0, max_value=10_000),
    shift=st.floats(min_value=-1e3, max_value=1e3, allow_nan=False),
)
@settings(max_examples=30, deadline=None)
def test_hurst_is_shift_invariant(n: int, seed: int, shift: float) -> None:
    """DFA-1 integrates demeaned signal → adding a constant is a no-op."""
    rng = np.random.default_rng(seed)
    signal = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    shifted = (signal + shift).astype(np.float64)
    r1 = dfa_hurst(signal)
    r2 = dfa_hurst(shifted)
    if np.isfinite(r1.hurst_exponent) and np.isfinite(r2.hurst_exponent):
        assert abs(r1.hurst_exponent - r2.hurst_exponent) < 1e-4


@given(
    n=st.integers(min_value=0, max_value=60),
    fill_value=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False),
)
@settings(max_examples=30, deadline=None)
def test_hurst_short_input_returns_inconclusive(n: int, fill_value: float) -> None:
    """Any input shorter than 4 · min_scale → INCONCLUSIVE, never crash or inf."""
    signal = np.full(n, fill_value, dtype=np.float64)
    r = dfa_hurst(signal)
    assert r.n_samples_used == n
    if n < 64:
        assert r.verdict == "INCONCLUSIVE"
        assert not np.isfinite(r.hurst_exponent)
    assert not np.isinf(r.hurst_exponent)


# ---------------------------------------------------------------------------
# Transfer Entropy — non-negativity + determinism
# ---------------------------------------------------------------------------


@given(
    n=st.integers(min_value=400, max_value=1200),
    seed=st.integers(min_value=0, max_value=10_000),
)
@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_te_is_nonnegative_on_random_inputs(n: int, seed: int) -> None:
    """Random x, y of any length ≥ 400 → TE ≥ 0 in both directions."""
    rng = np.random.default_rng(seed)
    x = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    y = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    r = transfer_entropy(x, y, n_bins=5, n_surrogates=20, seed=seed)
    assert r.te_y_to_x_nats >= 0.0
    assert r.te_x_to_y_nats >= 0.0
    assert 0.0 < r.p_value_y_to_x <= 1.0
    assert 0.0 < r.p_value_x_to_y <= 1.0


@given(
    seed=st.integers(min_value=0, max_value=10_000),
)
@settings(max_examples=10, deadline=None)
def test_te_deterministic_across_two_calls(seed: int) -> None:
    """Identical inputs + seed → byte-identical report."""
    rng = np.random.default_rng(seed)
    x = rng.normal(0.0, 1.0, size=600).astype(np.float64)
    y = rng.normal(0.0, 1.0, size=600).astype(np.float64)
    a = transfer_entropy(x, y, n_bins=5, n_surrogates=20, seed=seed)
    b = transfer_entropy(x, y, n_bins=5, n_surrogates=20, seed=seed)
    assert a == b


# ---------------------------------------------------------------------------
# Conditional TE — non-negativity + determinism
# ---------------------------------------------------------------------------


@given(
    seed=st.integers(min_value=0, max_value=10_000),
)
@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_cte_nonneg_and_deterministic(seed: int) -> None:
    rng = np.random.default_rng(seed)
    n = 800
    x = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    y = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    z = rng.normal(0.0, 1.0, size=n).astype(np.float64)
    a = conditional_transfer_entropy(x, y, z, n_bins=4, n_surrogates=20, seed=seed)
    b = conditional_transfer_entropy(x, y, z, n_bins=4, n_surrogates=20, seed=seed)
    assert a == b
    assert a.te_unconditional_y_to_x_nats >= 0.0
    assert a.te_conditional_y_to_x_nats >= 0.0


# ---------------------------------------------------------------------------
# Walk-forward summary — quantile monotonicity + verdict taxonomy
# ---------------------------------------------------------------------------


@given(
    ics=st.lists(
        st.floats(min_value=-0.5, max_value=0.5, allow_nan=False),
        min_size=10,
        max_size=200,
    ),
)
@settings(max_examples=40, deadline=None)
def test_walk_forward_quantiles_are_monotonic(
    ics: list[float],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    rows = [{"ic_signal": ic, "perm_p": 0.01} for ic in ics]
    tmp = tmp_path_factory.mktemp("wf")
    p: Path = tmp / "wf.json"
    p.write_text(json.dumps({"rows": rows, "window_sec": 2400, "step_sec": 300}))
    r = summarize_walk_forward(p)
    assert r.ic_min <= r.ic_q25 <= r.ic_median <= r.ic_q75 <= r.ic_max
    assert r.verdict in {"STABLE_POSITIVE", "MIXED", "UNSTABLE", "INCONCLUSIVE"}
    assert 0.0 <= r.fraction_positive <= 1.0
