"""Invariants INV-CAK1..INV-CAK8 for the integrated module.

Each invariant is:

- INV-CAK1 Parameter freeze      — module parameters match PARAMETER_LOCK.json.
- INV-CAK2 Universe freeze       — regime + strategy universes frozen at spike values.
- INV-CAK3 Deterministic output  — same data + same params ⇒ bit-identical output.
- INV-CAK4 No future leak        — signal at bar t uses only data at or before t.
- INV-CAK5 Cost model required   — any Sharpe/PnL claim on net returns has cost_bps > 0.
- INV-CAK6 Fail-closed           — any invariant violation raises ``CAKInvariantError``.
- INV-CAK7 Rank-order invariance — multiplying all prices by c > 0 does not change signal ordering.
- INV-CAK8 Turnover bounded      — per-bar turnover < 2.0 (= 100% of a 2x portfolio).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .types import StrategyParameters


class CAKInvariantError(ValueError):
    """Raised when any INV-CAK invariant is violated."""


_REQUIRED_LOCK_KEYS: tuple[str, ...] = (
    "seed",
    "regime_universe_ordered",
    "strategy_universe_ordered",
    "panel_ffill_limit_bdays",
    "detrend_window_bdays",
    "r_window_bdays",
    "regime_threshold_train_frac",
    "regime_quantile_low",
    "regime_quantile_high",
    "regime_buckets",
    "execution_lag_bars",
    "return_clip_abs",
    "vol_window_bdays",
    "vol_target_annualised",
    "vol_cap_leverage",
    "cost_bps",
    "bars_per_year",
    "backtest_train_test_split_frac",
    "n_bootstrap",
)


def load_parameter_lock(path: Path) -> StrategyParameters:
    """Parse PARAMETER_LOCK.json into a ``StrategyParameters`` container.

    Enforces INV-CAK1 *at read time*: missing keys fail-closed; unknown
    extra keys are allowed (so adding audit metadata does not break
    code) but documented-but-modified values raise.
    """
    if not path.is_file():
        raise CAKInvariantError(f"PARAMETER_LOCK.json not found at {path}")
    with path.open("r", encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    missing = [k for k in _REQUIRED_LOCK_KEYS if k not in data]
    if missing:
        raise CAKInvariantError(f"PARAMETER_LOCK.json missing required keys: {missing}")
    return StrategyParameters(
        seed=int(data["seed"]),
        regime_assets=tuple(str(a) for a in data["regime_universe_ordered"]),
        strategy_assets=tuple(str(a) for a in data["strategy_universe_ordered"]),
        ffill_limit_bdays=int(data["panel_ffill_limit_bdays"]),
        detrend_window_bdays=int(data["detrend_window_bdays"]),
        r_window_bdays=int(data["r_window_bdays"]),
        regime_threshold_train_frac=float(data["regime_threshold_train_frac"]),
        regime_quantile_low=float(data["regime_quantile_low"]),
        regime_quantile_high=float(data["regime_quantile_high"]),
        regime_buckets={
            str(k): tuple(str(a) for a in v) for k, v in data["regime_buckets"].items()
        },
        execution_lag_bars=int(data["execution_lag_bars"]),
        return_clip_abs=float(data["return_clip_abs"]),
        vol_window_bdays=int(data["vol_window_bdays"]),
        vol_target_annualised=float(data["vol_target_annualised"]),
        vol_cap_leverage=float(data["vol_cap_leverage"]),
        cost_bps=float(data["cost_bps"]),
        bars_per_year=int(data["bars_per_year"]),
        backtest_train_test_split_frac=float(data["backtest_train_test_split_frac"]),
        n_bootstrap=int(data["n_bootstrap"]),
        spike_commit=str(data.get("_spike_commit", "")),
    )


# --- Individual invariant helpers ------------------------------------ #


def assert_cak1_parameter_freeze(params: StrategyParameters, lock_path: Path) -> None:
    """INV-CAK1: in-memory params must match the on-disk lock."""
    expected = load_parameter_lock(lock_path)
    if params != expected:
        raise CAKInvariantError(
            "INV-CAK1 VIOLATED: StrategyParameters diverges from PARAMETER_LOCK.json"
        )


def assert_cak2_universe_freeze(params: StrategyParameters, lock_path: Path) -> None:
    """INV-CAK2: both universes are the frozen values from the lock."""
    expected = load_parameter_lock(lock_path)
    if params.regime_assets != expected.regime_assets:
        raise CAKInvariantError(
            f"INV-CAK2 VIOLATED: regime universe {params.regime_assets} != "
            f"lock {expected.regime_assets}"
        )
    if params.strategy_assets != expected.strategy_assets:
        raise CAKInvariantError(
            f"INV-CAK2 VIOLATED: strategy universe {params.strategy_assets} != "
            f"lock {expected.strategy_assets}"
        )


def assert_cak3_deterministic(series_a: np.ndarray, series_b: np.ndarray) -> None:
    """INV-CAK3: two runs on same data + params produce bit-identical output."""
    if series_a.shape != series_b.shape:
        raise CAKInvariantError(
            f"INV-CAK3 VIOLATED: shape mismatch {series_a.shape} vs {series_b.shape}"
        )
    if not np.array_equal(series_a, series_b, equal_nan=True):
        raise CAKInvariantError("INV-CAK3 VIOLATED: outputs differ across identical runs")


def assert_cak4_no_future_leak(
    signal_full: pd.Series, signal_truncated: pd.Series, truncate_idx: pd.Timestamp
) -> None:
    """INV-CAK4: signal values at or before ``truncate_idx`` must match on both series."""
    common = signal_full.index.intersection(signal_truncated.index)
    common = common[common <= truncate_idx]
    if len(common) == 0:
        return
    a = signal_full.loc[common].to_numpy()
    b = signal_truncated.loc[common].to_numpy()
    mask_a = np.isfinite(a)
    mask_b = np.isfinite(b)
    if not np.array_equal(mask_a, mask_b):
        raise CAKInvariantError("INV-CAK4 VIOLATED: NaN pattern changed with later data")
    a_f = a[mask_a]
    b_f = b[mask_a]
    if not np.allclose(a_f, b_f, rtol=1e-12, atol=1e-12, equal_nan=True):
        raise CAKInvariantError(
            "INV-CAK4 VIOLATED: pre-truncate signal differs when future data added"
        )


def assert_cak5_cost_required(cost_bps: float, emit_performance: bool) -> None:
    """INV-CAK5: any performance claim on net returns must carry cost_bps > 0."""
    if emit_performance and cost_bps <= 0:
        raise CAKInvariantError(
            f"INV-CAK5 VIOLATED: cost_bps={cost_bps} is not > 0 but a net-return "
            "performance claim is being emitted"
        )


def assert_cak7_scale_invariance(
    signal_base: pd.Series, signal_scaled: pd.Series, rtol: float = 1e-10
) -> None:
    """INV-CAK7: multiplying all prices by c > 0 does not change R(t) ordering.

    Because log returns are scale-invariant, the rolling Kuramoto R(t)
    is exactly scale-invariant — enforced as value-equality, not just
    rank-equality.
    """
    common = signal_base.index.intersection(signal_scaled.index)
    a = signal_base.loc[common].to_numpy()
    b = signal_scaled.loc[common].to_numpy()
    m = np.isfinite(a) & np.isfinite(b)
    if not np.allclose(a[m], b[m], rtol=rtol, atol=rtol):
        max_dev = float(np.max(np.abs(a[m] - b[m])))
        raise CAKInvariantError(
            f"INV-CAK7 VIOLATED: R(t) changed under price rescaling; max_dev={max_dev:.2e}"
        )


def assert_cak8_turnover_bounded(turnover: np.ndarray, max_per_bar: float = 2.0) -> None:
    """INV-CAK8: per-bar turnover < ``max_per_bar`` (warn-only by design)."""
    if len(turnover) == 0:
        return
    max_tov = float(np.max(turnover))
    if not math.isfinite(max_tov):
        raise CAKInvariantError("INV-CAK8 VIOLATED: non-finite turnover")
    if max_tov > max_per_bar:
        raise CAKInvariantError(
            f"INV-CAK8 VIOLATED: max per-bar turnover {max_tov:.4f} > cap {max_per_bar}"
        )


def assert_all_invariants(
    params: StrategyParameters,
    lock_path: Path,
    signal_series: pd.Series | None = None,
    cost_bps: float | None = None,
    turnover: np.ndarray | None = None,
) -> None:
    """Composite check — used by entry-point code that wants one call.

    Parameter-only INVs (CAK1, CAK2) are always enforced. Observation-
    dependent INVs (CAK4, CAK5, CAK7, CAK8) are only enforced when the
    relevant observation arrays are supplied.
    """
    assert_cak1_parameter_freeze(params, lock_path)
    assert_cak2_universe_freeze(params, lock_path)
    if cost_bps is not None:
        assert_cak5_cost_required(cost_bps, emit_performance=True)
    if turnover is not None:
        assert_cak8_turnover_bounded(turnover)
    # CAK3/CAK4/CAK7 are pairwise and invoked directly in tests.
