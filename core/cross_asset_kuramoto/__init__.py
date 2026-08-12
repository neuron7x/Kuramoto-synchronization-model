"""Cross-asset Kuramoto regime strategy — integrated module.

Source spike: ``~/spikes/cross_asset_sync_regime/`` (composite SHA-256
``9e76e3b511d31245239961e386901214ea3a4ccc549c87009e29b814f6576fe3``).
Every numeric parameter is frozen at its spike value; see
``results/cross_asset_kuramoto/PARAMETER_LOCK.json``. Any behaviour-
affecting divergence requires a separate PR with full re-verification.

Public API is intentionally narrow: callers import the top-level
helpers listed in ``__all__`` and the strong-typed result containers
from ``.types``. Lower-level functions remain addressable for tests.
"""

from __future__ import annotations

from .engine import BacktestResult, compute_metrics, simulate_rp_strategy
from .invariants import CAKInvariantError, assert_all_invariants, load_parameter_lock
from .signal import (
    build_panel,
    build_returns_panel,
    classify_regimes,
    compute_log_returns,
    extract_phase,
    kuramoto_order,
    load_asset_close,
)
from .types import PanelSpec, Regime, RegimeThresholds, StrategyParameters

__all__ = [
    "BacktestResult",
    "CAKInvariantError",
    "PanelSpec",
    "Regime",
    "RegimeThresholds",
    "StrategyParameters",
    "assert_all_invariants",
    "build_panel",
    "build_returns_panel",
    "classify_regimes",
    "compute_log_returns",
    "compute_metrics",
    "extract_phase",
    "kuramoto_order",
    "load_asset_close",
    "load_parameter_lock",
    "simulate_rp_strategy",
]
