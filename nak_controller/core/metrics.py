"""Normalization utilities for controller metrics."""

from __future__ import annotations

from .state import clip


def pnl_norm(pnl: float, scale: float = 0.01) -> float:
    """Return a normalized profit-and-loss signal in the range [0, 1]."""
    if scale <= 0.0:
        raise ValueError("scale must be positive")
    y = max(-1.0, min(1.0, pnl / scale))
    return 0.5 * (y + 1.0)


def dd_norm(drawdown: float, max_dd: float = 0.2) -> float:
    """Normalize drawdown magnitude into [0, 1]."""
    if max_dd <= 0.0:
        raise ValueError("max_dd must be positive")
    return clip(drawdown / max_dd, 0.0, 1.0)


def vol_norm(volatility: float, max_vol: float = 1.0) -> float:
    """Normalize realized volatility into [0, 1]."""
    if max_vol <= 0.0:
        raise ValueError("max_vol must be positive")
    return clip(volatility / max_vol, 0.0, 1.0)


def lat_norm(latency_ms: float, p95_ms: float = 50.0) -> float:
    """Normalize latency to [0, 1] based on a P95 target."""
    if p95_ms <= 0.0:
        raise ValueError("p95_ms must be positive")
    return clip(latency_ms / p95_ms, 0.0, 1.0)


def slippage_norm(slippage: float, threshold: float = 0.001) -> float:
    """Normalize slippage magnitude to [0, 1]."""
    if threshold <= 0.0:
        raise ValueError("threshold must be positive")
    return clip(abs(slippage) / threshold, 0.0, 1.0)


__all__ = [
    "pnl_norm",
    "dd_norm",
    "vol_norm",
    "lat_norm",
    "slippage_norm",
]
