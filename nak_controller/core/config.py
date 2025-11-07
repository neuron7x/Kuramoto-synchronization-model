"""Validation helpers for the NaK YAML configuration."""
from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator


class RiskMult(BaseModel):
    """Risk multipliers per global mode."""

    GREEN: float
    AMBER: float
    RED: float


class ActivityMult(BaseModel):
    """Activity multipliers per global mode."""

    GREEN: float
    AMBER: float
    RED: float


class BandExpand(BaseModel):
    """EI band expansion per global mode."""

    GREEN: float
    AMBER: float
    RED: float


class NakConfig(BaseModel):
    """Schema for the NaK configuration block."""

    model_config = ConfigDict(extra="forbid")

    L_min: float = 0.0
    L_max: float = 1.0
    E_max: float = 1.0
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
    risk_mult: RiskMult
    activity_mult: ActivityMult
    band_expand: BandExpand
    noise_sigma: float

    @field_validator("EI_high")
    @classmethod
    def validate_ei_band(cls, value: float, info: ValidationInfo) -> float:
        low = info.data.get("EI_low", 0.0)
        if value <= low:
            raise ValueError("EI_high must be greater than EI_low")
        return value

    @field_validator("r_min", "r_max")
    @classmethod
    def validate_risk_bounds(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("risk bounds must be positive")
        return value

    @field_validator("delta_r_limit")
    @classmethod
    def validate_delta_limit(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError("delta_r_limit must be in (0, 1]")
        return value


def load_validated(config_dict: Dict[str, Any]) -> NakConfig:
    """Load and validate *config_dict* into :class:`NakConfig`."""

    return NakConfig(**config_dict)


__all__ = ["NakConfig", "load_validated"]
