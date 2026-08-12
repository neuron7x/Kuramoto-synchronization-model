# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Configuration model for the NaK controller."""

from __future__ import annotations

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationInfo,
    field_validator,
    model_validator,
)


class _BaseTriplet(BaseModel):
    """Base model for structured triplets used in configuration."""

    GREEN: float
    AMBER: float
    RED: float

    model_config = ConfigDict(extra="forbid")

    @field_validator("GREEN", "AMBER", "RED")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0.0:
            raise ValueError("multipliers must be non-negative")
        return value


class RiskMult(_BaseTriplet):
    """Risk multipliers per global mode."""


class ActivityMult(_BaseTriplet):
    """Activity multipliers per global mode."""


class BandExpand(_BaseTriplet):
    """Band expansion factors per global mode."""


class NakConfig(BaseModel):
    """Validated configuration for :class:`NaKController`."""

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

    @field_validator("L_max")
    @classmethod
    def _validate_load_bounds(cls, value: float, info: ValidationInfo) -> float:
        if value <= info.data.get("L_min", 0.0):
            raise ValueError("L_max must be greater than L_min")
        return value

    @field_validator("E_max")
    @classmethod
    def _validate_energy(cls, value: float) -> float:
        if value <= 0.0:
            raise ValueError("E_max must be positive")
        return value

    @field_validator("EI_high")
    @classmethod
    def _validate_ei_band(cls, value: float, info: ValidationInfo) -> float:
        ei_low = info.data.get("EI_low", 0.0)
        if value <= ei_low:
            raise ValueError("EI_high must be greater than EI_low")
        return value

    @field_validator("EI_hysteresis")
    @classmethod
    def _validate_hysteresis(cls, value: float) -> float:
        if value < 0.0:
            raise ValueError("EI_hysteresis must be non-negative")
        return value

    @field_validator("r_min", "r_max", "f_min", "f_max", "I_max")
    @classmethod
    def _positive_bounds(cls, value: float) -> float:
        if value <= 0.0:
            raise ValueError("controller bounds must be strictly positive")
        return value

    @field_validator("delta_r_limit")
    @classmethod
    def _validate_rate_limit(cls, value: float) -> float:
        if not 0.0 < value <= 1.0:
            raise ValueError("delta_r_limit must be in the interval (0, 1]")
        return value

    @field_validator("vol_red")
    @classmethod
    def _validate_vol_thresholds(cls, value: float, info: ValidationInfo) -> float:
        vol_amber = info.data.get("vol_amber")
        if vol_amber is not None and value < vol_amber:
            raise ValueError("vol_red must be greater than or equal to vol_amber")
        return value

    @field_validator("dd_red")
    @classmethod
    def _validate_dd_thresholds(cls, value: float, info: ValidationInfo) -> float:
        dd_amber = info.data.get("dd_amber")
        if dd_amber is not None and value < dd_amber:
            raise ValueError("dd_red must be greater than or equal to dd_amber")
        return value

    @field_validator("noise_sigma")
    @classmethod
    def _validate_noise(cls, value: float) -> float:
        if value < 0.0:
            raise ValueError("noise_sigma must be non-negative")
        return value

    @model_validator(mode="after")
    def _validate_composites(self) -> "NakConfig":
        weight_sum = self.w_n + self.w_v + self.w_d + self.w_e + self.w_l + self.w_s
        if weight_sum > 1.0 + 1e-6:
            raise ValueError("sum of load weights must not exceed 1.0")
        recovery_reserve = self.u_e + self.u_l + self.u_p
        if recovery_reserve <= 0.0:
            raise ValueError("u_e + u_l + u_p must be positive to retain recovery reserve")
        if self.r_min >= self.r_max:
            raise ValueError("r_min must be less than r_max")
        if self.f_min >= self.f_max:
            raise ValueError("f_min must be less than f_max")
        if not (self.r_min <= 1.0 <= self.r_max):
            raise ValueError("risk range must include 1.0")
        return self


__all__ = ["NakConfig", "RiskMult", "ActivityMult", "BandExpand"]
