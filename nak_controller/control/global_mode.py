"""Global mode selection for the NaK controller."""
from __future__ import annotations

from typing import Literal

Mode = Literal["GREEN", "AMBER", "RED"]


def choose_mode(
    global_vol: float,
    portfolio_dd: float,
    vol_amber: float,
    vol_red: float,
    dd_amber: float,
    dd_red: float,
) -> Mode:
    """Select the operating mode based on volatility and drawdown."""

    if portfolio_dd >= dd_red or global_vol >= vol_red:
        return "RED"
    if portfolio_dd >= dd_amber or global_vol >= vol_amber:
        return "AMBER"
    return "GREEN"


def band_expand_for_mode(mode: Mode, band_green: float, band_amber: float, band_red: float) -> float:
    """Return EI band expansion multiplier for *mode*."""

    return {"GREEN": band_green, "AMBER": band_amber, "RED": band_red}[mode]


__all__ = ["Mode", "choose_mode", "band_expand_for_mode"]
