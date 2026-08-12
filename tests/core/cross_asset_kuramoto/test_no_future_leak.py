"""T3: INV-CAK4 — signal on ``data[:t]`` matches signal on ``data[:t+k]``
at all indices ≤ t. Implemented as a property test over random truncation
points on the real panel."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.cross_asset_kuramoto import (
    build_panel,
    compute_log_returns,
    extract_phase,
    kuramoto_order,
)
from core.cross_asset_kuramoto.invariants import assert_cak4_no_future_leak, load_parameter_lock

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCK_PATH = REPO_ROOT / "results" / "cross_asset_kuramoto" / "PARAMETER_LOCK.json"
SPIKE_DATA = Path.home() / "spikes" / "cross_asset_sync_regime" / "data"


@pytest.fixture(scope="module")
def params():
    return load_parameter_lock(LOCK_PATH)


@pytest.fixture(scope="module")
def full_panel(params):
    if not SPIKE_DATA.is_dir():
        pytest.skip("spike data directory not present")
    return build_panel(params.regime_assets, SPIKE_DATA, params.ffill_limit_bdays)


@pytest.fixture(scope="module")
def full_r(params, full_panel):
    log_r = compute_log_returns(full_panel)
    phases = extract_phase(log_r, params.detrend_window_bdays).dropna()
    return kuramoto_order(phases, params.r_window_bdays)


@pytest.mark.xfail(
    reason=(
        "OBS-1 in INTEGRATION_NOTES.md: scipy.signal.hilbert is FFT-based and "
        "non-causal. Spike preserves this behaviour (per protocol §6.MI). "
        "Strict no-future-leak for R(t) therefore fails by design; the "
        "strictly-causal portions of the chain are covered by "
        "`test_signal_uses_only_past_bars_for_kuramoto` below."
    ),
    strict=True,
)
@settings(
    max_examples=4,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(frac=st.floats(min_value=0.40, max_value=0.95))
def test_r_has_no_future_leak(params, full_panel, full_r, frac: float) -> None:
    """Property test kept in xfail state to surface any future strictly-causal rewrite."""
    cutoff_idx = int(len(full_panel) * frac)
    cutoff_ts = full_panel.index[cutoff_idx]

    trunc_panel = full_panel.iloc[: cutoff_idx + 1]
    log_r_trunc = compute_log_returns(trunc_panel)
    if len(log_r_trunc) < params.detrend_window_bdays + 40:
        return
    phases_trunc = extract_phase(log_r_trunc, params.detrend_window_bdays).dropna()
    r_trunc = kuramoto_order(phases_trunc, params.r_window_bdays)

    assert_cak4_no_future_leak(full_r, r_trunc, cutoff_ts)


def test_signal_uses_only_past_bars_for_kuramoto(params) -> None:
    """Unit: kuramoto_order on bars [0..k] cannot depend on bar k+1."""
    rng = np.random.default_rng(0)
    n = 400
    cols = ["A", "B", "C", "D"]
    df = pd.DataFrame(rng.standard_normal((n, len(cols))), columns=cols)
    # Full series
    r_full = kuramoto_order(df, params.r_window_bdays).to_numpy()
    # Truncated at index n - 5
    r_trunc = kuramoto_order(df.iloc[: n - 5], params.r_window_bdays).to_numpy()
    m = min(len(r_full), len(r_trunc))
    a = r_full[:m]
    b = r_trunc[:m]
    mask = np.isfinite(a) & np.isfinite(b)
    assert np.allclose(a[mask], b[mask], rtol=1e-12, atol=1e-12)
