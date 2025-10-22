"""Structured configuration for Kuramoto–Ricci composite workflows."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pydantic
import yaml  # type: ignore[import-untyped]
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError
from pydantic_settings.sources import PydanticBaseSettingsSource

from core.indicators.multiscale_kuramoto import TimeFrame

AliasChoices = getattr(pydantic, "AliasChoices", None)

if (
    AliasChoices is None
):  # pragma: no cover - exercised implicitly via configuration parsing

    class AliasChoices(tuple):
        """Lightweight stand-in for :mod:`pydantic`'s ``AliasChoices`` helper."""

        __slots__ = ()

        def __new__(cls, *choices: str) -> "AliasChoices":
            normalized = tuple(str(choice) for choice in choices if str(choice))
            if not normalized:
                msg = "AliasChoices requires at least one non-empty alias"
                raise ValueError(msg)
            return super().__new__(cls, normalized)  # type: ignore[misc]

        def __repr__(self) -> str:  # pragma: no cover - debug helper
            joined = ", ".join(self)
            return f"AliasChoices({joined})"


DEFAULT_CONFIG_PATH = Path("configs/kuramoto_ricci_composite.yaml")


class ConfigError(ValueError):
    """Raised when a configuration value is invalid."""


def _parse_timeframe(value: Any) -> TimeFrame:
    if isinstance(value, TimeFrame):
        return value
    if isinstance(value, str):
        token = value.strip()
        if token.isdigit():
            value = int(token)
        else:
            try:
                return TimeFrame[token]
            except KeyError as exc:  # pragma: no cover - defensive branch
                raise ValueError(f"unknown timeframe label '{token}'") from exc
    try:
        return TimeFrame(int(value))
    except (ValueError, TypeError) as exc:  # pragma: no cover - defensive branch
        raise ValueError(f"invalid timeframe value: {value!r}") from exc


def _merge_adaptive_window_payload(data: Any) -> Mapping[str, Any]:
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise TypeError("kuramoto configuration must be a mapping")
    payload = dict(data)
    adaptive = payload.pop("adaptive_window", None)
    if isinstance(adaptive, Mapping):
        if "enabled" in adaptive and "use_adaptive_window" not in payload:
            payload["use_adaptive_window"] = adaptive["enabled"]
        if "base_window" in adaptive and "base_window" not in payload:
            payload["base_window"] = adaptive["base_window"]
    return payload


def _coerce_timeframes_payload(value: Any) -> Sequence[Any] | tuple[TimeFrame, ...]:
    if value is None:
        return value
    if isinstance(value, (str, bytes)):
        raise TypeError("kuramoto.timeframes must be a sequence")
    if isinstance(value, Iterable):
        return tuple(_parse_timeframe(item) for item in value)
    raise TypeError("kuramoto.timeframes must be a sequence")


def _ensure_timeframes_non_empty_payload(
    timeframes: Sequence[TimeFrame] | None,
) -> None:
    if not timeframes:
        raise ValueError("kuramoto.timeframes cannot be empty")


def _coerce_int_value(value: Any, field_name: str) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name} cannot be blank")
        try:
            return int(stripped)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be an integer") from exc
    return value


def _coerce_float_value(value: Any, field_name: str) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name} cannot be blank")
        try:
            return float(stripped)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be a number") from exc
    return value


def _coerce_bool_value(value: Any, field_name: str) -> Any:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
        raise ValueError(f"{field_name} must be a boolean value")
    return value


class KuramotoConfig(BaseModel):
    """Configuration payload for :class:`MultiScaleKuramoto`."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    timeframes: tuple[TimeFrame, ...] = Field(
        default=(TimeFrame.M1, TimeFrame.M5, TimeFrame.M15, TimeFrame.H1),
        description="Ordered set of timeframes analysed by the indicator.",
    )
    use_adaptive_window: bool = Field(
        default=True,
        description="Whether to adapt the base window dynamically.",
    )
    base_window: int = Field(
        default=200,
        gt=0,
        description="Base lookback window used by the Kuramoto estimator.",
    )
    min_samples_per_scale: int = Field(
        default=64,
        gt=0,
        description="Minimum number of samples required per analysed scale.",
    )

    @model_validator(mode="before")
    @classmethod
    def _merge_adaptive_window(cls, data: Any) -> Mapping[str, Any]:
        return _merge_adaptive_window_payload(data)

    @field_validator("timeframes", mode="before")
    @classmethod
    def _coerce_timeframes(cls, value: Any) -> Sequence[Any] | tuple[TimeFrame, ...]:
        return _coerce_timeframes_payload(value)

    @field_validator("base_window", "min_samples_per_scale", mode="before")
    @classmethod
    def _coerce_positive_ints(cls, value: Any, info: ValidationInfo) -> Any:
        return _coerce_int_value(value, info.field_name)

    @field_validator("use_adaptive_window", mode="before")
    @classmethod
    def _coerce_use_adaptive(cls, value: Any, info: ValidationInfo) -> Any:
        return _coerce_bool_value(value, info.field_name)

    @model_validator(mode="after")
    def _ensure_timeframes_non_empty(self) -> "KuramotoConfig":
        _ensure_timeframes_non_empty_payload(self.timeframes)
        return self

    def to_engine_kwargs(self) -> dict[str, Any]:
        return {
            "timeframes": self.timeframes,
            "use_adaptive_window": self.use_adaptive_window,
            "base_window": self.base_window,
            "min_samples_per_scale": self.min_samples_per_scale,
        }


class RicciTemporalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    window_size: int = Field(default=100, gt=0)
    n_snapshots: int = Field(default=8, gt=0)
    retain_history: bool = Field(default=True)

    @field_validator("window_size", "n_snapshots", mode="before")
    @classmethod
    def _coerce_temporal_ints(cls, value: Any, info: ValidationInfo) -> Any:
        return _coerce_int_value(value, info.field_name)

    @field_validator("retain_history", mode="before")
    @classmethod
    def _coerce_retain_history(cls, value: Any, info: ValidationInfo) -> Any:
        return _coerce_bool_value(value, info.field_name)


class RicciGraphConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    n_levels: int = Field(default=20, gt=0)
    connection_threshold: float = Field(default=0.1, gt=0, lt=1)

    @field_validator("n_levels", mode="before")
    @classmethod
    def _coerce_level_count(cls, value: Any, info: ValidationInfo) -> Any:
        return _coerce_int_value(value, info.field_name)

    @field_validator("connection_threshold", mode="before")
    @classmethod
    def _coerce_connection_threshold(cls, value: Any, info: ValidationInfo) -> Any:
        return _coerce_float_value(value, info.field_name)


class RicciConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    temporal: RicciTemporalConfig = Field(default_factory=RicciTemporalConfig)
    graph: RicciGraphConfig = Field(default_factory=RicciGraphConfig)

    def to_engine_kwargs(self) -> dict[str, Any]:
        return {
            "window_size": self.temporal.window_size,
            "n_snapshots": self.temporal.n_snapshots,
            "n_levels": self.graph.n_levels,
            "retain_history": self.temporal.retain_history,
            "connection_threshold": self.graph.connection_threshold,
        }


class CompositeThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    R_strong_emergent: float = Field(default=0.8, ge=0, le=1)
    R_proto_emergent: float = Field(default=0.4, ge=0, le=1)
    coherence_min: float = Field(default=0.6, ge=0, le=1)
    ricci_negative: float = Field(default=-0.3)
    temporal_ricci: float = Field(default=-0.2)
    topological_transition: float = Field(default=0.7, ge=0, le=1)

    @field_validator(
        "R_strong_emergent",
        "R_proto_emergent",
        "coherence_min",
        "ricci_negative",
        "temporal_ricci",
        "topological_transition",
        mode="before",
    )
    @classmethod
    def _coerce_threshold_numbers(cls, value: Any, info: ValidationInfo) -> Any:
        return _coerce_float_value(value, info.field_name)

    @model_validator(mode="after")
    def _validate_thresholds(self) -> "CompositeThresholds":
        if self.R_strong_emergent <= self.R_proto_emergent:
            raise ValueError("R_strong_emergent must exceed R_proto_emergent")
        return self


class CompositeSignals(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    min_confidence: float = Field(default=0.5, ge=0, le=1)

    @field_validator("min_confidence", mode="before")
    @classmethod
    def _coerce_min_confidence(cls, value: Any, info: ValidationInfo) -> Any:
        return _coerce_float_value(value, info.field_name)


class CompositeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    thresholds: CompositeThresholds = Field(default_factory=CompositeThresholds)
    signals: CompositeSignals = Field(default_factory=CompositeSignals)

    def to_engine_kwargs(self) -> dict[str, Any]:
        return {
            "R_strong_emergent": self.thresholds.R_strong_emergent,
            "R_proto_emergent": self.thresholds.R_proto_emergent,
            "coherence_threshold": self.thresholds.coherence_min,
            "ricci_negative_threshold": self.thresholds.ricci_negative,
            "temporal_ricci_threshold": self.thresholds.temporal_ricci,
            "transition_threshold": self.thresholds.topological_transition,
            "min_confidence": self.signals.min_confidence,
        }


class KuramotoRicciIntegrationConfig(BaseModel):
    """Composite configuration for the Kuramoto–Ricci integration workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kuramoto: KuramotoConfig = Field(default_factory=KuramotoConfig)
    ricci: RicciConfig = Field(default_factory=RicciConfig)
    composite: CompositeConfig = Field(default_factory=CompositeConfig)

    @classmethod
    def from_mapping(
        cls, data: Mapping[str, Any] | None
    ) -> "KuramotoRicciIntegrationConfig":
        try:
            return cls.model_validate(data or {})
        except ValidationError as exc:  # pragma: no cover - error propagation
            messages = "; ".join(error["msg"] for error in exc.errors())
            raise ConfigError(messages) from exc

    @classmethod
    def from_file(cls, path: str | Path | None) -> "KuramotoRicciIntegrationConfig":
        if path is None:
            return cls()
        payload_path = Path(path)
        if not payload_path.exists():
            raise FileNotFoundError(payload_path)
        with payload_path.open("r", encoding="utf8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if not isinstance(loaded, Mapping):
            raise ConfigError("configuration file must define a mapping")
        return cls.from_mapping(loaded)

    def to_engine_kwargs(self) -> dict[str, dict[str, Any]]:
        return {
            "kuramoto_config": self.kuramoto.to_engine_kwargs(),
            "ricci_config": self.ricci.to_engine_kwargs(),
            "composite_config": self.composite.to_engine_kwargs(),
        }


class YamlSettingsSource(PydanticBaseSettingsSource):
    """Lowest-priority settings source that loads values from YAML files."""

    def __init__(
        self,
        settings_cls: type[BaseSettings] | None,
        init_source: PydanticBaseSettingsSource | None = None,
        env_source: PydanticBaseSettingsSource | None = None,
        dotenv_source: PydanticBaseSettingsSource | None = None,
    ) -> None:
        settings_cls = settings_cls or BaseSettings
        super().__init__(settings_cls)
        self.settings_cls = settings_cls
        self._init_source = init_source
        self._env_source = env_source
        self._dotenv_source = dotenv_source

    def __call__(
        self, settings_cls: type[BaseSettings] | None = None
    ) -> dict[str, Any]:
        if settings_cls is not None:
            self.settings_cls = settings_cls
        config_path = self._resolve_path()
        if config_path is None:
            return {}
        try:
            text = config_path.read_text(encoding="utf8")
        except FileNotFoundError:
            return {}
        try:
            payload = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:  # pragma: no cover - YAML parser errors
            raise SettingsError(
                f"failed to parse YAML configuration at {config_path}: {exc}"
            ) from exc
        if not isinstance(payload, Mapping):
            raise SettingsError(
                f"configuration file {config_path} must define a mapping"
            )
        return dict(payload)

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        return None, field_name, False

    def _resolve_path(self) -> Path | None:
        for source in (self._init_source, self._env_source, self._dotenv_source):
            if source is None:
                continue
            try:
                data = source()
            except SettingsError:  # pragma: no cover - defensive guard
                data = {}
            except Exception:  # pragma: no cover - defensive guard
                data = {}
            candidate = data.get("config_file") or data.get("config")
            if candidate:
                return Path(candidate).expanduser()

        field = self.settings_cls.model_fields.get("config_file")
        default_value = getattr(field, "default", None) if field else None
        default_factory = getattr(field, "default_factory", None) if field else None
        if default_value is None and callable(default_factory):
            default_value = default_factory()
        if default_value:
            return Path(default_value).expanduser()
        return None


class TradePulseSettings(BaseSettings):
    """Application-wide configuration powered by ``pydantic-settings``."""

    model_config = SettingsConfigDict(
        env_prefix="TRADEPULSE_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf8",
        extra="ignore",
        strict=True,
    )

    config_file: Path | None = Field(
        default=DEFAULT_CONFIG_PATH,
        description="Primary YAML configuration file.",
        validation_alias=AliasChoices("config_file", "config"),
    )
    kuramoto: KuramotoConfig = Field(default_factory=KuramotoConfig)
    ricci: RicciConfig = Field(default_factory=RicciConfig)
    composite: CompositeConfig = Field(default_factory=CompositeConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_source = YamlSettingsSource(
            settings_cls, init_settings, env_settings, dotenv_settings
        )
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            yaml_source,
            file_secret_settings,
        )

    def as_kuramoto_ricci_config(self) -> KuramotoRicciIntegrationConfig:
        return KuramotoRicciIntegrationConfig(
            kuramoto=self.kuramoto,
            ricci=self.ricci,
            composite=self.composite,
        )


def export_tradepulse_settings_schema(
    destination: str | Path | None = None,
    *,
    indent: int = 2,
) -> dict[str, Any]:
    """Return the JSON schema for :class:`TradePulseSettings`.

    When ``destination`` is provided the schema is written to the given path on
    disk using UTF-8 encoding. The resulting schema dictionary is always
    returned which allows callers to inspect or further post-process it.
    """

    schema = TradePulseSettings.model_json_schema()
    if destination is not None:
        path = Path(destination)
        payload = json.dumps(schema, indent=indent, sort_keys=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf8")
    return schema


def parse_cli_overrides(pairs: Sequence[str] | None) -> dict[str, Any]:
    """Convert CLI ``key=value`` pairs into nested dictionaries."""

    overrides: dict[str, Any] = {}
    if not pairs:
        return overrides

    for raw in pairs:
        if "=" not in raw:
            raise ConfigError(f"Invalid override '{raw}', expected format key=value")
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigError("Override keys cannot be empty")
        target = overrides
        parts = [segment.strip() for segment in key.split(".") if segment.strip()]
        if not parts:
            raise ConfigError("Override keys cannot be empty")
        for segment in parts[:-1]:
            target = target.setdefault(segment, {})
            if not isinstance(target, dict):
                raise ConfigError(f"Override path '{key}' collides with a scalar value")
        parsed_value: Any
        try:
            parsed_value = yaml.safe_load(value)
        except yaml.YAMLError as exc:  # pragma: no cover - YAML parser errors
            raise ConfigError(f"Unable to parse override '{raw}': {exc}") from exc
        target[parts[-1]] = parsed_value

    return overrides


def load_kuramoto_ricci_config(
    path: str | Path | None,
    *,
    cli_overrides: Mapping[str, Any] | None = None,
) -> KuramotoRicciIntegrationConfig:
    """Load a Kuramoto–Ricci integration config with layered sources."""

    overrides = dict(cli_overrides or {})
    if path is not None:
        overrides.setdefault("config_file", Path(path))
    settings = TradePulseSettings(**overrides)
    return settings.as_kuramoto_ricci_config()


__all__ = [
    "ConfigError",
    "CompositeConfig",
    "CompositeSignals",
    "CompositeThresholds",
    "KuramotoConfig",
    "KuramotoRicciIntegrationConfig",
    "RicciConfig",
    "RicciGraphConfig",
    "RicciTemporalConfig",
    "TradePulseSettings",
    "YamlSettingsSource",
    "export_tradepulse_settings_schema",
    "load_kuramoto_ricci_config",
    "parse_cli_overrides",
]
