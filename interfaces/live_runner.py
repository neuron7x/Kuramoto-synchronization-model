# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Orchestration helpers for running the live execution loop."""

from __future__ import annotations

import importlib
import logging
import os
import signal
import threading
from dataclasses import dataclass, fields
from pathlib import Path
from types import FrameType
from typing import Any, Callable, Dict, Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib

from core.utils.metrics import PROMETHEUS_AVAILABLE, start_metrics_server
from execution.connectors import ExecutionConnector
from execution.live_loop import LiveExecutionLoop, LiveLoopConfig
from execution.risk import RiskLimits, RiskManager
from interfaces.execution.common import CredentialError, CredentialProvider
from interfaces.secrets.backends import (
    AWSSecretsManagerBackendConfig,
    HashicorpVaultBackendConfig,
    SecretBackendConfigurationError,
    SecretBackendError,
    build_aws_secrets_manager_resolver,
    build_hashicorp_vault_resolver,
)
from interfaces.secrets.manager import SecretManager, SecretManagerError, VaultResolver
from tacl.risk_gating import RiskGatingConfig, RiskGatingEngine

LOGGER = logging.getLogger(__name__)
DEFAULT_CONFIG_PATH = Path("configs/live/default.toml")


@dataclass(slots=True)
class SecretBackendSettings(BaseModel):
    """Secret backend configuration mapping to a vault/KMS adapter."""

    model_config = ConfigDict(extra="ignore")

    adapter: str = Field(..., min_length=1)
    path: str | None = None
    path_env: str | None = None
    key: str | None = None
    field_mapping: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    def _normalise_aliases(cls, values: Any) -> Any:
        if isinstance(values, Mapping):
            data = dict(values)
            if "backend" in data and "adapter" not in data:
                data["adapter"] = data.pop("backend")
            return data
        return values

    @model_validator(mode="after")
    def _validate_and_normalise(self) -> "SecretBackendSettings":
        if not (self.path or self.path_env):
            raise ValueError("secret backend requires 'path' or 'path_env'")
        object.__setattr__(self, "adapter", str(self.adapter).lower())
        mapping = {str(k).upper(): str(v) for k, v in self.field_mapping.items()}
        object.__setattr__(self, "field_mapping", mapping)
        return self

    def resolve_path(self) -> str | None:
        if self.path:
            return self.path
        if self.path_env:
            value = os.getenv(self.path_env)
            if value:
                return value
        return None


class CredentialSettings(BaseModel):
    """Credential loader configuration for a venue connector."""

    model_config = ConfigDict(extra="ignore")

    env_prefix: str = Field(..., min_length=1)
    required: tuple[str, ...] = Field(default_factory=lambda: ("API_KEY", "API_SECRET"))
    optional: tuple[str, ...] = Field(default_factory=tuple)
    secret_backend: SecretBackendSettings | None = None
    vault_path_env: str | None = None

    @model_validator(mode="before")
    def _coerce_sequence(cls, values: Any) -> Any:
        if isinstance(values, Mapping):
            data = dict(values)
            for key in ("required", "optional"):
                value = data.get(key)
                if isinstance(value, str):
                    data[key] = [value]
            return data
        return values

    @model_validator(mode="after")
    def _normalise(self) -> "CredentialSettings":
        object.__setattr__(self, "env_prefix", str(self.env_prefix).upper())
        object.__setattr__(
            self, "required", tuple(str(key).upper() for key in self.required)
        )
        object.__setattr__(
            self, "optional", tuple(str(key).upper() for key in self.optional)
        )
        if self.secret_backend is None and self.vault_path_env:
            backend = SecretBackendSettings(
                adapter="vault", path_env=self.vault_path_env
            )
            object.__setattr__(self, "secret_backend", backend)
        return self


@dataclass(slots=True)
class VenueSettings:
    """Declarative configuration describing a single venue connector."""

    name: str
    class_path: str
    options: Mapping[str, Any]
    credentials: CredentialSettings | None


def _load_toml(path: Path) -> Mapping[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _import_string(path: str) -> type[ExecutionConnector]:
    module_path, _, attribute = path.rpartition(".")
    if not module_path or not attribute:
        raise ImportError(f"Invalid import path '{path}'")
    module = importlib.import_module(module_path)
    try:
        obj = getattr(module, attribute)
    except AttributeError as exc:  # pragma: no cover - defensive
        raise ImportError(
            f"Module '{module_path}' does not define '{attribute}'"
        ) from exc
    if not isinstance(obj, type) or not issubclass(obj, ExecutionConnector):
        raise TypeError(f"{path} is not an ExecutionConnector class")
    return obj


def _dataclass_kwargs(schema, values: Mapping[str, Any]) -> Dict[str, Any]:
    allowed = {field.name for field in fields(schema)}
    return {key: values[key] for key in allowed & values.keys()}


class LiveTradingRunner:
    """High level runner coordinating :class:`LiveExecutionLoop`."""

    def __init__(
        self,
        config_path: Path | None = None,
        *,
        venues: Sequence[str] | None = None,
        state_dir_override: Path | None = None,
        metrics_port: int | None = None,
        secret_manager: SecretManager | None = None,
        secret_backends: Mapping[str, VaultResolver] | None = None,
    ) -> None:
        self._config_path = (config_path or DEFAULT_CONFIG_PATH).expanduser()
        if not self._config_path.exists():
            raise FileNotFoundError(
                f"Live trading config not found: {self._config_path}"
            )
        raw_config = _load_toml(self._config_path)
        self._config_dir = self._config_path.parent
        self._raw_loop = dict(raw_config.get("loop", {}))
        self._raw_risk = dict(raw_config.get("risk", {}))
        self._raw_metrics = dict(raw_config.get("metrics", {}))
        self._raw_risk_gating = dict(raw_config.get("risk_gating", {}))

        requested = {v.lower() for v in venues} if venues else None
        raw_venues = raw_config.get("venues", [])
        self._venue_settings: list[VenueSettings] = []
        for entry in raw_venues:
            name = str(entry.get("name"))
            class_path = str(entry.get("class"))
            if not name or not class_path:
                raise ValueError("Each venue must provide 'name' and 'class'")
            if requested and name.lower() not in requested:
                continue
            options = {
                k: v
                for k, v in entry.items()
                if k not in {"name", "class", "credentials"}
            }
            credentials_cfg = entry.get("credentials")
            credentials: CredentialSettings | None = None
            if credentials_cfg:
                try:
                    credentials = CredentialSettings.model_validate(credentials_cfg)
                except ValidationError as exc:
                    raise ValueError(
                        f"Invalid credential configuration for venue '{name}': {exc}"
                    ) from exc
            self._venue_settings.append(
                VenueSettings(
                    name=name,
                    class_path=class_path,
                    options=options,
                    credentials=credentials,
                )
            )

        if requested and not self._venue_settings:
            raise ValueError("No venues matched the requested --venue filters")
        if not self._venue_settings:
            raise ValueError("Configuration does not define any venues")

        self._state_dir_override = state_dir_override
        self._metrics_port = metrics_port or self._raw_metrics.get("port")

        self._loop: LiveExecutionLoop | None = None
        self._loop_config: LiveLoopConfig | None = None
        self._risk_manager: RiskManager | None = None
        self._pre_action_filter: object | None = None
        self._connectors: Dict[str, ExecutionConnector] = {}
        self._credentials: Dict[str, Mapping[str, str]] = {}
        self._secret_manager = secret_manager
        self._inline_secret_backends: Dict[str, VaultResolver] = {}
        self._register_default_backends()
        for name, resolver in (secret_backends or {}).items():
            self._inline_secret_backends[str(name).lower()] = resolver
        if self._secret_manager is not None:
            for adapter, resolver in self._inline_secret_backends.items():
                self._secret_manager.register(adapter, resolver)
        self._stop_event = threading.Event()
        self._signal_handlers: Dict[int, Callable[[int, FrameType | None], None]] = {}
        self._kill_reason: str | None = None

        self._build_connectors()
        self._build_credentials()
        self._build_risk_manager()
        self._build_loop_config()
        self._build_pre_action_filter()

    # ------------------------------------------------------------------
    # Public API
    @property
    def loop(self) -> LiveExecutionLoop:
        if self._loop is None:
            raise RuntimeError("Live loop has not been started")
        return self._loop

    @property
    def connectors(self) -> Mapping[str, ExecutionConnector]:
        return self._connectors

    @property
    def risk_manager(self) -> RiskManager:
        if self._risk_manager is None:
            raise RuntimeError("Risk manager is not initialised")
        return self._risk_manager

    @property
    def config_path(self) -> Path:
        return self._config_path

    @property
    def kill_switch_reason(self) -> str | None:
        return self._kill_reason

    def start(self, *, cold_start: bool) -> None:
        if self._loop is not None:
            raise RuntimeError("Live loop already running")
        self._stop_event.clear()
        self._kill_reason = None
        if self._loop_config is None:
            raise RuntimeError("Live loop configuration not initialised")
        loop = LiveExecutionLoop(
            self._connectors,
            self.risk_manager,
            config=self._loop_config,
            pre_action_filter=self._pre_action_filter,
        )
        loop.on_kill_switch.connect(self._handle_kill_switch)
        loop.on_reconnect.connect(self._handle_reconnect)
        loop.on_position_snapshot.connect(self._handle_position_snapshot)
        self._loop = loop

        self._start_metrics_server()

        LOGGER.info(
            "Starting live trading runner",
            extra={
                "event": "live_runner.start",
                "cold_start": cold_start,
                "venues": list(self._connectors),
            },
        )
        loop.start(cold_start=cold_start)

    def request_stop(self, reason: str | None = None) -> None:
        if reason:
            LOGGER.info(
                "Stop requested",
                extra={"event": "live_runner.stop_requested", "reason": reason},
            )
        self._stop_event.set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._stop_event.wait(timeout)

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._loop is None:
            return
        LOGGER.info(
            "Shutting down live trading runner", extra={"event": "live_runner.shutdown"}
        )
        try:
            self._loop.shutdown()
        finally:
            self._loop = None

    def run(self, *, cold_start: bool) -> None:
        self.register_signal_handlers()
        try:
            self.start(cold_start=cold_start)
            while not self.wait(timeout=1.0):
                continue
        except KeyboardInterrupt:  # pragma: no cover - interactive guard
            LOGGER.info("Keyboard interrupt received – stopping live runner")
        finally:
            self.shutdown()
            self.restore_signal_handlers()

    # ------------------------------------------------------------------
    # Internal helpers
    def register_signal_handlers(self) -> None:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous = signal.getsignal(signum)
            self._signal_handlers[signum] = previous  # type: ignore[assignment]

            def handler(sig: int, frame: FrameType | None) -> None:
                LOGGER.info(
                    "Signal received",
                    extra={"event": "live_runner.signal", "signal": sig},
                )
                self.request_stop(reason=f"signal:{sig}")

            signal.signal(signum, handler)

    def restore_signal_handlers(self) -> None:
        for signum, handler in self._signal_handlers.items():
            signal.signal(signum, handler)
        self._signal_handlers.clear()

    def _build_connectors(self) -> None:
        for settings in self._venue_settings:
            connector_cls = _import_string(settings.class_path)
            connector = connector_cls(**settings.options)
            self._connectors[settings.name] = connector

    def _get_backend_resolver(self, adapter: str) -> VaultResolver:
        adapter_key = str(adapter).lower()
        if self._secret_manager is not None:
            try:
                return self._secret_manager.get_resolver(adapter_key)
            except SecretManagerError:
                pass
        resolver = self._inline_secret_backends.get(adapter_key)
        if resolver is None:
            raise RuntimeError(f"No secret backend registered for adapter '{adapter}'")
        return resolver

    def _register_default_backends(self) -> None:
        backends: dict[str, VaultResolver] = {}

        try:
            vault_config = HashicorpVaultBackendConfig.from_environment()
        except SecretBackendConfigurationError as exc:
            LOGGER.warning(
                "HashiCorp Vault backend is misconfigured",
                extra={
                    "event": "live_runner.secret_backend",
                    "backend": "vault",
                    "error": str(exc),
                },
            )
        else:
            if vault_config is not None:
                try:
                    backends["vault"] = build_hashicorp_vault_resolver(vault_config)
                except SecretBackendError as exc:
                    LOGGER.error(
                        "Failed to initialise HashiCorp Vault backend",
                        extra={
                            "event": "live_runner.secret_backend",
                            "backend": "vault",
                            "error": str(exc),
                        },
                    )

        try:
            aws_config = AWSSecretsManagerBackendConfig.from_environment()
        except SecretBackendConfigurationError as exc:
            LOGGER.warning(
                "AWS Secrets Manager backend is misconfigured",
                extra={
                    "event": "live_runner.secret_backend",
                    "backend": "aws-secrets-manager",
                    "error": str(exc),
                },
            )
        else:
            if aws_config is not None:
                try:
                    resolver = build_aws_secrets_manager_resolver(aws_config)
                except SecretBackendError as exc:
                    LOGGER.error(
                        "Failed to initialise AWS Secrets Manager backend",
                        extra={
                            "event": "live_runner.secret_backend",
                            "backend": "aws-secrets-manager",
                            "error": str(exc),
                        },
                    )
                else:
                    backends["aws-secrets-manager"] = resolver
                    backends.setdefault("secretsmanager", resolver)

        for name, resolver in backends.items():
            self._inline_secret_backends.setdefault(name, resolver)

    def _wrap_backend_resolver(
        self, venue: str, backend: SecretBackendSettings
    ) -> VaultResolver:
        base_resolver = self._get_backend_resolver(backend.adapter)
        field_mapping = dict(backend.field_mapping)

        def _resolver(path: str) -> Mapping[str, str]:
            payload = base_resolver(path)
            if backend.key:
                nested = payload.get(backend.key)
                if not isinstance(nested, Mapping):
                    raise RuntimeError(
                        f"Secret backend '{backend.adapter}' for venue '{venue}' did not return a mapping "
                        f"for key '{backend.key}'"
                    )
                payload = nested
            data = {str(k): v for k, v in payload.items()}
            normalised = {key.upper(): str(value) for key, value in data.items()}
            for dest, source in field_mapping.items():
                if source in data:
                    normalised[dest] = str(data[source])
            return normalised

        return _resolver

    def _build_credentials(self) -> None:
        for settings in self._venue_settings:
            credentials_cfg = settings.credentials
            if credentials_cfg is None:
                continue
            provider_kwargs: Dict[str, Any] = {
                "required_keys": credentials_cfg.required,
                "optional_keys": credentials_cfg.optional,
            }
            backend_cfg = credentials_cfg.secret_backend
            if backend_cfg is not None:
                resolver = self._wrap_backend_resolver(settings.name, backend_cfg)
                resolved_path = backend_cfg.resolve_path()
                if resolved_path is None:
                    env_hint = (
                        f" from environment variable '{backend_cfg.path_env}'"
                        if backend_cfg.path_env
                        else ""
                    )
                    raise RuntimeError(
                        f"Secret backend '{backend_cfg.adapter}' for venue '{settings.name}' did not resolve a path"
                        f"{env_hint}."
                    )
                provider_kwargs["vault_resolver"] = resolver
                provider_kwargs["vault_path"] = resolved_path
                provider_kwargs["vault_path_env"] = backend_cfg.path_env
            provider = CredentialProvider(
                credentials_cfg.env_prefix,
                **provider_kwargs,
            )
            try:
                credentials = provider.load()
            except CredentialError as exc:
                raise RuntimeError(
                    f"Failed to load credentials for {settings.name}: {exc}"
                ) from exc
            connector = self._connectors.get(settings.name)
            if connector is not None and hasattr(connector, "set_credential_provider"):
                try:
                    connector.set_credential_provider(provider)
                except Exception as exc:  # pragma: no cover - defensive guard
                    LOGGER.debug(
                        "Connector did not accept injected credential provider",
                        extra={
                            "event": "live_runner.credentials",
                            "venue": settings.name,
                            "error": str(exc),
                        },
                    )
            self._credentials[settings.name] = credentials

    def _build_risk_manager(self) -> None:
        if self._risk_manager is not None:
            return
        risk_kwargs = _dataclass_kwargs(RiskLimits, self._raw_risk)
        limits = RiskLimits(**risk_kwargs)
        self._risk_manager = RiskManager(limits)

    def _build_loop_config(self) -> None:
        if self._loop_config is not None:
            return
        loop_values = dict(self._raw_loop)
        state_dir_value = self._state_dir_override or loop_values.get("state_dir")
        if state_dir_value is None:
            state_dir_value = Path("var/live_state")
        state_dir = Path(state_dir_value)
        if not state_dir.is_absolute():
            state_dir = (self._config_dir / state_dir).resolve()
        loop_values["state_dir"] = state_dir
        loop_kwargs = _dataclass_kwargs(LiveLoopConfig, loop_values)
        loop_kwargs.setdefault("credentials", self._credentials)
        self._loop_config = LiveLoopConfig(**loop_kwargs)
        # Ensure credentials map is available even if dataclass filtered it out
        self._loop_config.credentials = self._credentials

    def _build_pre_action_filter(self) -> None:
        if self._pre_action_filter is not None:
            return
        payload = dict(self._raw_risk_gating)
        enabled = payload.pop("enabled", True)
        if not enabled:
            return
        config_kwargs = _dataclass_kwargs(RiskGatingConfig, payload)
        config = RiskGatingConfig(**config_kwargs)
        self._pre_action_filter = RiskGatingEngine(config)

    def _start_metrics_server(self) -> None:
        if self._metrics_port is None:
            return
        if not PROMETHEUS_AVAILABLE:
            LOGGER.warning(
                "prometheus_client not installed – metrics server disabled",
                extra={"event": "live_runner.metrics_disabled"},
            )
            return
        try:
            start_metrics_server(int(self._metrics_port))
        except Exception as exc:  # pragma: no cover - defensive guard
            LOGGER.warning(
                "Failed to start metrics server",
                extra={"event": "live_runner.metrics_error", "error": str(exc)},
            )
        else:
            LOGGER.info(
                "Metrics server listening",
                extra={"event": "live_runner.metrics", "port": int(self._metrics_port)},
            )

    def _handle_kill_switch(self, reason: str) -> None:
        self._kill_reason = reason
        LOGGER.critical(
            "Kill-switch engaged – stopping runner",
            extra={"event": "live_runner.kill_switch", "reason": reason},
        )
        self.request_stop(reason="kill_switch")

    def _handle_reconnect(
        self, venue: str, attempt: int, delay: float, exc: Exception | None
    ) -> None:
        payload: Dict[str, Any] = {
            "event": "live_runner.reconnect",
            "venue": venue,
            "attempt": attempt,
            "backoff_seconds": delay,
        }
        if exc is not None:
            payload["error"] = str(exc)
        LOGGER.warning("Connector reconnect triggered", extra=payload)

    def _handle_position_snapshot(
        self, venue: str, positions: Iterable[Mapping[str, Any]]
    ) -> None:
        count = sum(1 for _ in positions)
        LOGGER.debug(
            "Position snapshot received",
            extra={
                "event": "live_runner.positions",
                "venue": venue,
                "positions": count,
            },
        )


__all__ = ["LiveTradingRunner", "DEFAULT_CONFIG_PATH"]
