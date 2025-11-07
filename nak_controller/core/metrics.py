"""Normalization helpers for the NaK controller metrics pipeline.

The functions in this module intentionally avoid external dependencies to keep
tests fast and deterministic while providing saturation logic needed by the
controller invariants.

Copyright (c) 2024 TradePulse Technologies. All rights reserved.
Licensed under the TradePulse Proprietary License Agreement (TPLA).
"""

from __future__ import annotations

from .state import clip


def normalize(value: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.0
    x = (value - lo) / (hi - lo)
    return clip(x, 0.0, 1.0)


def pnl_norm(pnl: float, scale: float = 0.01) -> float:
    # squash pnl to [-1,1] then map to [0,1]
    y = max(-1.0, min(1.0, pnl / max(1e-9, scale)))
    return 0.5 * (y + 1.0)


def dd_norm(dd: float, max_dd: float = 0.2) -> float:
    return clip(dd / max(1e-9, max_dd), 0.0, 1.0)


def vol_norm(vol: float, max_vol: float = 1.0) -> float:
    return clip(vol / max(1e-9, max_vol), 0.0, 1.0)


def lat_norm(lat_ms: float, p95_ms: float = 50.0) -> float:
    return clip(lat_ms / max(1e-9, p95_ms), 0.0, 1.0)


def slippage_norm(slip: float, thr: float = 0.001) -> float:
    return clip(abs(slip) / max(1e-9, thr), 0.0, 1.0)
