from __future__ import annotations

from ..core.state import clip


def dopamine(unexp_reward: float, beta_DA: float) -> float:
    return clip(0.5 + beta_DA * unexp_reward, 0.0, 1.0)


def noradrenaline(global_vol: float, na_vol_gain: float) -> float:
    return clip(na_vol_gain * global_vol, 0.0, 1.0)


def serotonin(portfolio_dd: float, ht_dd_gain: float) -> float:
    return clip(ht_dd_gain * portfolio_dd, 0.0, 1.0)


def acetylcholine(exposure: float, eta_ACh: float) -> float:
    return clip(0.5 + eta_ACh * exposure, 0.0, 1.0)


def modulate_risk_da(r_tilde: float, DA: float, da_gain: float, r_min: float, r_max: float) -> float:
    delta = da_gain * (DA - 0.5)
    return max(r_min, min(r_max, r_tilde + delta))


def modulate_activity_ach(activity_mult: float, ACh: float) -> float:
    return clip(activity_mult * (0.5 + ACh), 0.25, 1.5)
