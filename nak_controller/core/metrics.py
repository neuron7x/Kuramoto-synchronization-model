"""Normalisation helpers for controller inputs."""
from __future__ import annotations

from .state import clip


def pnl_norm(pnl: float, scale: float = 0.01) -> float:
    """Normalise *pnl* to ``[0, 1]`` given *scale* for positive unit PnL."""

    denom = max(1e-9, scale)
    centred = max(-1.0, min(1.0, pnl / denom))
    return 0.5 * (centred + 1.0)


def dd_norm(drawdown: float, max_dd: float = 0.2) -> float:
    """Normalise drawdown metric to ``[0, 1]``."""

    return clip(drawdown / max(1e-9, max_dd), 0.0, 1.0)


def vol_norm(volatility: float, max_vol: float = 1.0) -> float:
    """Normalise volatility metric to ``[0, 1]``."""

    return clip(volatility / max(1e-9, max_vol), 0.0, 1.0)


def lat_norm(latency_ms: float, p95_ms: float = 50.0) -> float:
    """Normalise latency metric to ``[0, 1]``."""

    return clip(latency_ms / max(1e-9, p95_ms), 0.0, 1.0)


def slippage_norm(slippage: float, threshold: float = 0.001) -> float:
    """Normalise absolute slippage metric to ``[0, 1]``."""

    return clip(abs(slippage) / max(1e-9, threshold), 0.0, 1.0)


__all__ = [
    "pnl_norm",
    "dd_norm",
    "vol_norm",
    "lat_norm",
    "slippage_norm",
]
