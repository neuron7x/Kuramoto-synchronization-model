"""Utilities for loading and validating TradePulse risk profiles."""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Tuple

import tomllib
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:  # pragma: no cover - for typing only
    from .core import RiskLimits

__all__ = [
    "KillSwitchConfig",
    "LimitsConfig",
    "ModesConfig",
    "PermissionsConfig",
    "RiskProfile",
    "load_risk_profile",
    "resolve_risk_profile_path",
    "clear_risk_profile_cache",
]


DEFAULT_RISK_PROFILE_PATH = Path(__file__).resolve().parents[2] / "risk_profile.toml"


class KillSwitchConfig(BaseModel):
    """Configuration for kill-switch escalation thresholds."""

    model_config = ConfigDict(extra="forbid")

    limit_multiplier: float = Field(ge=1.0)
    violation_threshold: int = Field(ge=1)
    rate_limit_threshold: int = Field(ge=1)


class LimitsConfig(BaseModel):
    """Hard risk limits applied before order execution."""

    model_config = ConfigDict(extra="forbid")

    max_notional: float = Field(gt=0.0)
    max_position: float = Field(gt=0.0)
    max_leverage: float = Field(gt=0.0)
    max_orders_per_interval: int = Field(ge=0)
    interval_seconds: float = Field(ge=0.0)
    kill_switch: KillSwitchConfig


class ModesConfig(BaseModel):
    """Supported operating modes for the trading platform."""

    model_config = ConfigDict(extra="forbid")

    allowed: Tuple[str, ...] = Field(default_factory=lambda: ("paper", "live", "shadow"))
    default: str = "paper"

    @field_validator("allowed")
    @classmethod
    def _normalise_allowed(cls, value: Iterable[str]) -> Tuple[str, ...]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for entry in value:
            normalised = str(entry).strip().lower()
            if not normalised or normalised in seen:
                continue
            seen.add(normalised)
            cleaned.append(normalised)
        if not cleaned:
            msg = "at least one operating mode must be provided"
            raise ValueError(msg)
        return tuple(cleaned)

    @field_validator("default")
    @classmethod
    def _validate_default(cls, value: str, info) -> str:
        normalised = value.strip().lower()
        allowed = info.data.get("allowed", ())
        if allowed and normalised not in allowed:
            msg = f"default mode '{normalised}' must be one of: {', '.join(allowed)}"
            raise ValueError(msg)
        return normalised


class PermissionsConfig(BaseModel):
    """Permissions defined by the active risk profile."""

    model_config = ConfigDict(extra="forbid")

    allowed_instruments: Tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("allowed_instruments")
    @classmethod
    def _normalise_instruments(cls, value: Iterable[str]) -> Tuple[str, ...]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for entry in value:
            normalised = str(entry).strip()
            if not normalised:
                continue
            if normalised in seen:
                continue
            seen.add(normalised)
            cleaned.append(normalised)
        return tuple(cleaned)


class RiskProfile(BaseModel):
    """Complete risk policy describing platform-wide guardrails."""

    model_config = ConfigDict(extra="forbid")

    name: str = "default"
    mode: str | None = None
    modes: ModesConfig = Field(default_factory=ModesConfig)
    limits: LimitsConfig
    permissions: PermissionsConfig = Field(default_factory=PermissionsConfig)

    @model_validator(mode="after")
    def _finalise(self) -> "RiskProfile":
        active_mode = (self.mode or self.modes.default).strip().lower()
        if active_mode not in self.modes.allowed:
            msg = f"mode '{active_mode}' is not permitted; allowed: {', '.join(self.modes.allowed)}"
            raise ValueError(msg)
        object.__setattr__(self, "mode", active_mode)
        return self

    @property
    def allowed_modes(self) -> Tuple[str, ...]:
        """Return all supported operating modes."""

        return self.modes.allowed

    @property
    def active_mode(self) -> str:
        """Return the currently active operating mode."""

        return self.mode or self.modes.default

    @property
    def allowed_instruments(self) -> Tuple[str, ...]:
        """Return the tuple of allowed instrument identifiers."""

        return self.permissions.allowed_instruments

    @property
    def max_leverage(self) -> float:
        """Return the leverage cap enforced by the profile."""

        return float(self.limits.max_leverage)

    def build_risk_limits(self) -> "RiskLimits":
        """Construct a :class:`RiskLimits` instance for this profile."""

        from .core import RiskLimits  # Imported lazily to avoid circular imports.

        return RiskLimits(
            max_notional=float(self.limits.max_notional),
            max_position=float(self.limits.max_position),
            max_orders_per_interval=int(self.limits.max_orders_per_interval),
            interval_seconds=float(self.limits.interval_seconds),
            kill_switch_limit_multiplier=float(self.limits.kill_switch.limit_multiplier),
            kill_switch_violation_threshold=int(self.limits.kill_switch.violation_threshold),
            kill_switch_rate_limit_threshold=int(self.limits.kill_switch.rate_limit_threshold),
        )


def resolve_risk_profile_path(
    path: str | Path | None,
    *,
    base_dir: Path | None = None,
) -> Path:
    """Resolve *path* into an absolute :class:`Path` instance."""

    candidate: Path
    if path is None:
        env_path = os.getenv("TRADEPULSE_RISK_PROFILE")
        if env_path:
            candidate = Path(env_path)
        else:
            candidate = DEFAULT_RISK_PROFILE_PATH
    else:
        candidate = Path(path)

    candidate = candidate.expanduser()
    if not candidate.is_absolute() and base_dir is not None:
        candidate = (base_dir / candidate).resolve()
    elif not candidate.is_absolute():
        candidate = candidate.resolve()
    return candidate


@functools.lru_cache(maxsize=16)
def _load_profile_from_path(resolved_path: str, mode: str | None) -> RiskProfile:
    profile_path = Path(resolved_path)
    if not profile_path.exists():
        raise FileNotFoundError(f"risk profile not found: {profile_path}")
    with profile_path.open("rb") as handle:
        raw_payload = tomllib.load(handle)
    payload = dict(raw_payload)
    if mode is not None:
        payload["mode"] = mode
    return RiskProfile.model_validate(payload)


def load_risk_profile(
    path: str | Path | None = None,
    *,
    mode: str | None = None,
    base_dir: Path | None = None,
    force_reload: bool = False,
) -> RiskProfile:
    """Load and validate the risk profile from *path*."""

    resolved = resolve_risk_profile_path(path, base_dir=base_dir)
    if force_reload:
        _load_profile_from_path.cache_clear()
    return _load_profile_from_path(str(resolved), None if mode is None else mode.lower())


def clear_risk_profile_cache() -> None:
    """Clear cached risk profile instances."""

    _load_profile_from_path.cache_clear()
