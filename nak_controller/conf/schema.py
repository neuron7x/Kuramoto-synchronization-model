"""Validation schema for ``nak_controller/conf/nak.yaml``.

The schema leverages Pydantic to validate bounds and enforce strict
configuration semantics before the controller consumes the values.

Copyright (c) 2024 TradePulse Technologies. All rights reserved.
Licensed under the TradePulse Proprietary License Agreement (TPLA).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ..core.params import NaKParams

LOGGER = logging.getLogger(__name__)


class ModeMultipliers(BaseModel):
    """Container for per-mode multipliers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    GREEN: float
    AMBER: float
    RED: float


class NaKConfigModel(BaseModel):
    """Typed representation of the validated NaK configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # bounds
    L_min: float
    L_max: float
    E_max: float
    EI_low: float
    EI_high: float
    EI_crit: float
    EI_hysteresis: float = Field(..., gt=0.0)
    I_max: float
    r_min: float
    r_max: float
    f_min: float
    f_max: float
    delta_r_limit: float = Field(..., gt=0.0)

    # load weights
    w_n: float
    w_v: float
    w_d: float
    w_e: float
    w_l: float
    w_s: float

    # energy coeffs
    a_p: float
    a_n: float
    a_v: float
    a_g: float
    a_da: float

    # EI composition
    u_e: float
    u_l: float
    u_p: float

    # PI controller
    Kp: float
    Ki: float

    # neuromods
    beta_DA: float
    eta_ACh: float
    da_gain: float
    na_vol_gain: float
    na_scale: float
    ht_dd_gain: float

    # modes
    vol_amber: float
    vol_red: float
    dd_amber: float
    dd_red: float

    risk_mult: ModeMultipliers
    activity_mult: ModeMultipliers
    band_expand: ModeMultipliers

    noise_sigma: float = Field(..., ge=0.0)

    @field_validator(
        "EI_low",
        "EI_high",
        "EI_crit",
        "u_e",
        "u_l",
        "u_p",
        "na_scale",
    )
    @classmethod
    def _unit_interval(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("value must be within [0, 1]")
        return value

    @field_validator("r_min", "r_max", "f_min", "f_max", "I_max")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0.0:
            raise ValueError("value must be non-negative")
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> "NaKConfigModel":
        if self.L_min >= self.L_max:
            raise ValueError("L_min must be < L_max")
        if self.E_max <= 0.0:
            raise ValueError("E_max must be positive")
        if not 0.0 <= self.f_min <= self.f_max:
            raise ValueError("f_min must be <= f_max and non-negative")
        if not (self.r_min <= 1.0 <= self.r_max):
            raise ValueError("risk bounds must bracket 1.0")
        if not self.EI_low < self.EI_high:
            raise ValueError("EI_low must be < EI_high")
        if not self.EI_crit < self.EI_low:
            raise ValueError("EI_crit must be < EI_low")
        if self.delta_r_limit > (self.r_max - self.r_min):
            raise ValueError("delta_r_limit cannot exceed risk span")
        if self.vol_amber > self.vol_red:
            raise ValueError("vol_amber must be <= vol_red")
        if self.dd_amber > self.dd_red:
            raise ValueError("dd_amber must be <= dd_red")

        load_weight_sum = self.w_n + self.w_v + self.w_d + self.w_e + self.w_l + self.w_s
        if load_weight_sum > 1.0 + 1e-9:
            raise ValueError("load weights must sum to <= 1.0")
        if abs(load_weight_sum - 1.0) > 1e-6:
            LOGGER.warning("load weights sum to %.4f", load_weight_sum)

        ei_weight_sum = self.u_e + self.u_l + self.u_p
        if abs(ei_weight_sum - 1.0) > 1e-6:
            raise ValueError("EI composition weights must sum to 1.0")

        for name, mult, allow_zero in (
            ("risk_mult", self.risk_mult, True),
            ("activity_mult", self.activity_mult, False),
            ("band_expand", self.band_expand, False),
        ):
            values = mult.model_dump().values()
            if allow_zero:
                if any(value < 0.0 for value in values):
                    raise ValueError(f"{name} values must be non-negative")
            else:
                if any(value <= 0.0 for value in values):
                    raise ValueError(f"{name} values must be positive")

        if self.band_expand.RED < self.band_expand.AMBER:
            raise ValueError("band_expand.RED must be >= band_expand.AMBER")

        return self

    def to_params(self) -> NaKParams:
        data: Dict[str, Any] = self.model_dump()
        data.update({
            "risk_GREEN": self.risk_mult.GREEN,
            "risk_AMBER": self.risk_mult.AMBER,
            "risk_RED": self.risk_mult.RED,
            "act_GREEN": self.activity_mult.GREEN,
            "act_AMBER": self.activity_mult.AMBER,
            "act_RED": self.activity_mult.RED,
            "band_GREEN": self.band_expand.GREEN,
            "band_AMBER": self.band_expand.AMBER,
            "band_RED": self.band_expand.RED,
        })
        for key in ("risk_mult", "activity_mult", "band_expand"):
            data.pop(key, None)
        return NaKParams(**data)


def load_nak_params(path: str | Path) -> NaKParams:
    """Load and validate the NaK configuration file located at *path*."""

    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "nak" not in raw:
        raise ValueError("configuration must contain top-level 'nak' mapping")

    nak_section = raw["nak"]
    if not isinstance(nak_section, dict):
        raise ValueError("'nak' section must be a mapping")

    try:
        model = NaKConfigModel.model_validate(nak_section)
    except ValidationError as exc:  # pragma: no cover - message path is covered indirectly
        raise ValueError(str(exc)) from exc

    return model.to_params()


__all__ = ["ModeMultipliers", "NaKConfigModel", "load_nak_params"]
