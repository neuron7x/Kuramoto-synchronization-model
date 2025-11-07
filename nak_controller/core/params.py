"""Immutable controller parameters resolved from configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NaKParams:
    """Resolved NaK controller parameters."""

    L_min: float
    L_max: float
    E_max: float
    EI_low: float
    EI_high: float
    EI_crit: float
    EI_hysteresis: float
    I_max: float
    r_min: float
    r_max: float
    f_min: float
    f_max: float
    delta_r_limit: float
    w_n: float
    w_v: float
    w_d: float
    w_e: float
    w_l: float
    w_s: float
    a_p: float
    a_n: float
    a_v: float
    a_g: float
    a_da: float
    u_e: float
    u_l: float
    u_p: float
    Kp: float
    Ki: float
    beta_DA: float
    eta_ACh: float
    da_gain: float
    na_vol_gain: float
    na_scale: float
    ht_dd_gain: float
    vol_amber: float
    vol_red: float
    dd_amber: float
    dd_red: float
    risk_GREEN: float
    risk_AMBER: float
    risk_RED: float
    act_GREEN: float
    act_AMBER: float
    act_RED: float
    band_GREEN: float
    band_AMBER: float
    band_RED: float
    noise_sigma: float


__all__ = ["NaKParams"]
