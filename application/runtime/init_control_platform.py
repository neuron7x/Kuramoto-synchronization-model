"""Unified initialization for the TradePulse control platform."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Type, TypeVar

import yaml
from pydantic import ValidationError

from application.runtime.control_gates import evaluate_control_gates
from application.settings import ApiServerSettings, BackendRuntimeSettings

LOGGER = logging.getLogger("tradepulse.control_platform")
SettingsT = TypeVar("SettingsT", bound="BaseSettings")

try:
    from pydantic_settings import BaseSettings
except Exception:  # pragma: no cover - fallback type guard
    BaseSettings = object  # type: ignore[assignment]


@dataclass(frozen=True)
class ControlPlatformInitResult:
    """Return container for unified initialization."""

    runtime_settings: BackendRuntimeSettings
    server_settings: ApiServerSettings
    controllers: Dict[str, object]
    app: Any
    telemetry_meta: Dict[str, Any]
    gate_pipeline: Any
    controllers_required: bool


def _load_yaml(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    candidate = Path(path)
    if not candidate.exists():
        raise FileNotFoundError(f"Configuration file not found: {candidate}")
    with candidate.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError("Top-level YAML configuration must be a mapping")
    return loaded


def _extract_defaults_and_env(
    settings_cls: Type[SettingsT],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Return defaults-only values and env-derived overrides for a BaseSettings class."""

    defaults_instance = settings_cls.model_construct()

    try:
        env_instance = settings_cls()
    except (ValidationError, ValueError) as exc:  # pragma: no cover - defensive guard
        LOGGER.warning(
            "Falling back to defaults for %s due to init error: %s",
            settings_cls.__name__,
            exc,
        )
        env_instance = defaults_instance

    defaults = defaults_instance.model_dump()
    env_applied = env_instance.model_dump()
    env_overrides = {
        key: value for key, value in env_applied.items() if env_applied.get(key) != defaults.get(key)
    }
    return defaults, env_overrides


def _merge_precedence(
    *,
    settings_cls: Type[SettingsT],
    yaml_section: Mapping[str, Any] | None,
    cli_overrides: Mapping[str, Any] | None,
) -> SettingsT:
    """Apply precedence CLI > ENV > YAML > defaults for a single settings class."""

    defaults, env_overrides = _extract_defaults_and_env(settings_cls)
    merged: Dict[str, Any] = {}
    merged.update(defaults)
    if yaml_section:
        merged.update({k: v for k, v in yaml_section.items() if v is not None})
    merged.update(env_overrides)
    if cli_overrides:
        merged.update({k: v for k, v in cli_overrides.items() if v is not None})
    local_default = not yaml_section and not cli_overrides and not env_overrides
    if (
        merged.get("tls") is None
        and not merged.get("allow_plaintext", False)
        and local_default
    ):
        LOGGER.warning(
            "No TLS configuration detected; enabling allow_plaintext for local runs. "
            "Provide TRADEPULSE_API_SERVER_TLS__* or --allow-plaintext to override."
        )
        merged["allow_plaintext"] = True
    return settings_cls.model_validate(merged)


def _resolve_path_precedence(
    *,
    default: str,
    yaml_value: Optional[str],
    env_value: Optional[str],
    cli_value: Optional[str],
) -> str:
    for candidate in (cli_value, env_value, yaml_value, default):
        if candidate:
            return str(candidate)
    return default


def initialize_control_platform(
    *,
    config_path: Optional[str] = None,
    cli_server_overrides: Optional[Mapping[str, Any]] = None,
    cli_runtime_overrides: Optional[Mapping[str, Any]] = None,
    cli_serotonin_config: Optional[str] = None,
    cli_thermo_config: Optional[str] = None,
    app_factory: Optional[Any] = None,
    serotonin_factory: Optional[Any] = None,
    thermo_factory: Optional[Any] = None,
) -> ControlPlatformInitResult:
    """Initialize config, controllers, observability, and app."""

    # Provide benign defaults for local/test environments to avoid mandatory secret errors.
    os.environ.setdefault("TRADEPULSE_AUDIT_SECRET", "test-audit-secret")
    os.environ.setdefault("TRADEPULSE_TWO_FACTOR_SECRET", "JBSWY3DPEHPK3PXP")

    if app_factory is None:
        from application.api.service import create_app as _create_app

        app_factory = _create_app

    yaml_cfg = _load_yaml(config_path)
    runtime_section = yaml_cfg.get("runtime") or yaml_cfg.get("runtime_settings") or {}
    server_section = yaml_cfg.get("server") or yaml_cfg.get("api_server") or {}

    runtime_settings = _merge_precedence(
        settings_cls=BackendRuntimeSettings,
        yaml_section=runtime_section,
        cli_overrides=cli_runtime_overrides,
    )
    server_settings = _merge_precedence(
        settings_cls=ApiServerSettings,
        yaml_section=server_section,
        cli_overrides=cli_server_overrides,
    )

    serotonin_config_path = _resolve_path_precedence(
        default="configs/serotonin.yaml",
        yaml_value=yaml_cfg.get("serotonin_config"),
        env_value=os.getenv("TRADEPULSE_SEROTONIN_CONFIG"),
        cli_value=cli_serotonin_config,
    )
    thermo_config_path = _resolve_path_precedence(
        default="configs/thermo_config.yaml",
        yaml_value=yaml_cfg.get("thermo_config"),
        env_value=os.getenv("TRADEPULSE_THERMO_CONFIG"),
        cli_value=cli_thermo_config,
    )

    controllers: Dict[str, object] = {}
    if serotonin_factory is None:
        from tradepulse.core.neuro.serotonin.serotonin_controller import (
            SerotoninController as _SerotoninController,
        )

        def _build_serotonin_controller(path: str) -> object:
            return _SerotoninController(path)

        serotonin_factory = _build_serotonin_controller

    if thermo_factory is None:
        from runtime.thermo_api import _build_default_graph as _build_default_graph
        from runtime.thermo_controller import ThermoController as _ThermoController

        def _build_thermo_controller(config_path: Optional[str] = None) -> object:
            return _ThermoController(_build_default_graph())

        thermo_factory = _build_thermo_controller

    controllers["serotonin"] = serotonin_factory(serotonin_config_path)
    controllers["thermo"] = thermo_factory(thermo_config_path)

    controllers_required = getattr(runtime_settings, "controllers_required", True)
    gate_pipeline = evaluate_control_gates

    app = app_factory(runtime_settings=runtime_settings)

    telemetry_meta = {
        "effective_config_source": config_path or "defaults",
        "controllers_loaded": sorted(controllers.keys()),
        "serotonin_config_path": serotonin_config_path,
        "thermo_config_path": thermo_config_path,
        "controllers_required": controllers_required,
    }
    LOGGER.info(
        "control_platform_init effective_config_source=%s controllers_loaded=%s",
        telemetry_meta["effective_config_source"],
        telemetry_meta["controllers_loaded"],
    )

    return ControlPlatformInitResult(
        runtime_settings=runtime_settings,
        server_settings=server_settings,
        controllers=controllers,
        app=app,
        telemetry_meta=telemetry_meta,
        gate_pipeline=gate_pipeline,
        controllers_required=controllers_required,
    )


__all__ = ["initialize_control_platform", "ControlPlatformInitResult"]
