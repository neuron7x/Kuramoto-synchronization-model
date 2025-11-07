"""Global mode selection logic."""

from __future__ import annotations

from typing import Literal

Mode = Literal["GREEN", "AMBER", "RED"]


def choose_mode(
    global_vol: float,
    portfolio_dd: float,
    *,
    vol_amber: float,
    vol_red: float,
    dd_amber: float,
    dd_red: float,
) -> Mode:
    """Select the global operating mode based on risk indicators."""
    if portfolio_dd >= dd_red or global_vol >= vol_red:
        return "RED"
    if portfolio_dd >= dd_amber or global_vol >= vol_amber:
        return "AMBER"
    return "GREEN"


def band_expand_for_mode(
    mode: Mode, *, band_GREEN: float, band_AMBER: float, band_RED: float
) -> float:
    """Return the band expansion factor for the requested mode."""
    if mode == "GREEN":
        return band_GREEN
    if mode == "AMBER":
        return band_AMBER
    return band_RED


__all__ = ["Mode", "choose_mode", "band_expand_for_mode"]
