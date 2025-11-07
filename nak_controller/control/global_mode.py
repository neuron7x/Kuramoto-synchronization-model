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
    if portfolio_dd >= dd_red or global_vol >= vol_red:
        return "RED"
    if portfolio_dd >= dd_amber or global_vol >= vol_amber:
        return "AMBER"
    return "GREEN"


def band_expand_for_mode(mode: Mode, b_green: float, b_amber: float, b_red: float) -> float:
    return dict(GREEN=b_green, AMBER=b_amber, RED=b_red)[mode]
