"""Typed containers for cross-asset Kuramoto integration.

All dataclasses are frozen; the module is a value-holder layer with
zero mutation after construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Regime(str, Enum):
    """Three-state Kuramoto regime classification (spike §sync_regime)."""

    LOW_SYNC = "low_sync"
    MID_SYNC = "mid_sync"
    HIGH_SYNC = "high_sync"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PanelSpec:
    """Substrate specification for the regime universe and strategy universe."""

    data_dir: Path
    regime_assets: tuple[str, ...]
    strategy_assets: tuple[str, ...]
    cache_map: dict[str, str]
    calendar_freq: str
    timezone: str
    ffill_limit_bdays: int


@dataclass(frozen=True)
class RegimeThresholds:
    """Quantile thresholds derived from the first ``train_frac`` of the R(t) series."""

    q33: float
    q66: float
    train_frac: float


@dataclass(frozen=True)
class StrategyParameters:
    """Every parameter that affects strategy output.

    Mirrors ``PARAMETER_LOCK.json``. ``StrategyParameters.from_lock_file``
    is the canonical constructor; direct construction is allowed for
    test fixtures but invariants check the values match the on-disk lock.
    """

    seed: int
    regime_assets: tuple[str, ...]
    strategy_assets: tuple[str, ...]
    ffill_limit_bdays: int
    detrend_window_bdays: int
    r_window_bdays: int
    regime_threshold_train_frac: float
    regime_quantile_low: float
    regime_quantile_high: float
    regime_buckets: dict[str, tuple[str, ...]]
    execution_lag_bars: int
    return_clip_abs: float
    vol_window_bdays: int
    vol_target_annualised: float
    vol_cap_leverage: float
    cost_bps: float
    bars_per_year: int
    backtest_train_test_split_frac: float
    n_bootstrap: int
    spike_commit: str = field(default="")


@dataclass(frozen=True)
class BacktestResult:
    """Return-series outputs of ``simulate_rp_strategy``.

    Attributes are kept compatible with the spike DataFrame columns so
    reproduction is exact: ``gross_ret``, ``net_ret``, ``turnover``,
    ``leverage``, ``regime``.
    """

    gross_ret: tuple[float, ...]
    net_ret: tuple[float, ...]
    turnover: tuple[float, ...]
    leverage: tuple[float, ...]
    regime: tuple[str, ...]
    index_iso: tuple[str, ...]
