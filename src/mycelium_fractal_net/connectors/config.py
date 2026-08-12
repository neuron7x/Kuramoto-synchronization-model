# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Configuration models for MFN ingestion connectors.

This module provides Pydantic-based configuration models for all
ingestion components, supporting both environment variables and
config file loading.

Example:
    >>> config = IngestionConfig.from_env()
    >>> # or
    >>> config = IngestionConfig.from_file("config/mfn_ingestion.json")
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "RestSourceConfig",
    "FileSourceConfig",
    "BackendConfig",
    "IngestionConfig",
]


_UNSUPPORTED_GRPC_MESSAGE = (
    "backend.protocol='grpc' is not supported by mycelium_fractal_net.connectors. "
    "Use backend.protocol='rest'."
)


class RestSourceConfig(BaseModel):
    """Configuration for REST HTTP polling source.

    Attributes:
        url: Target endpoint URL
        poll_interval_seconds: Seconds between polls
        batch_size: Maximum records per poll
        max_retries: Retry attempts on failure
        timeout: Request timeout in seconds
        headers: Optional HTTP headers
        params: Optional query parameters
        source_name: Override source identifier
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    url: str = Field(..., min_length=1, description="Target endpoint URL")
    poll_interval_seconds: float = Field(
        default=60.0, ge=1.0, le=3600.0, description="Poll interval"
    )
    batch_size: int = Field(default=100, ge=1, le=10000, description="Max records per poll")
    max_retries: int = Field(default=3, ge=0, le=10, description="Retry attempts")
    timeout: float = Field(default=30.0, ge=1.0, le=300.0, description="Request timeout")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP headers")
    params: dict[str, str] = Field(default_factory=dict, description="Query parameters")
    source_name: str | None = Field(default=None, description="Source identifier override")


class FileSourceConfig(BaseModel):
    """Configuration for file-based data source.

    Attributes:
        path: Path to data file
        format: File format ('jsonl' or 'csv')
        batch_size: Records per batch
        field_mapping: CSV column to field mapping
        source_name: Override source identifier
        timestamp_field: Field containing timestamp
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    path: str = Field(..., min_length=1, description="Path to data file")
    format: Literal["jsonl", "csv"] = Field(default="jsonl", description="File format")
    batch_size: int = Field(default=100, ge=1, le=10000, description="Records per batch")
    field_mapping: dict[str, str] = Field(
        default_factory=dict, description="Column to field mapping"
    )
    source_name: str | None = Field(default=None, description="Source identifier override")
    timestamp_field: str | None = Field(default=None, description="Timestamp field name")

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        """Validate path is not empty."""
        if not value.strip():
            raise ValueError("path cannot be empty")
        return value


class BackendConfig(BaseModel):
    """Configuration for MFN backend connection.

    Attributes:
        type: Backend type ('local' or 'remote')
        endpoint: Remote endpoint URL (for remote type)
        protocol: Remote protocol ('rest')
        api_key: Authentication key
        timeout: Request timeout
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    type: Literal["local", "remote"] = Field(default="local", description="Backend type")
    endpoint: str | None = Field(default=None, description="Remote endpoint URL")
    protocol: Literal["rest"] = Field(default="rest", description="Remote protocol")
    api_key: str | None = Field(default=None, description="API key for authentication")
    timeout: float = Field(default=30.0, ge=1.0, le=300.0, description="Request timeout")

    @model_validator(mode="after")
    def _validate_supported_protocol(self) -> "BackendConfig":
        if self.protocol != "rest":
            raise ValueError(_UNSUPPORTED_GRPC_MESSAGE)
        if self.type == "remote" and not self.endpoint:
            raise ValueError("backend.endpoint is required when backend.type='remote'.")
        if self.type == "local" and self.endpoint:
            raise ValueError("backend.endpoint must be omitted when backend.type='local'.")
        if self.type == "local" and self.api_key:
            raise ValueError("backend.api_key must be omitted when backend.type='local'.")
        return self


class IngestionConfig(BaseSettings):
    """Main configuration for MFN ingestion pipeline.

    Supports loading from:
    - Environment variables (MFN_ prefix)
    - JSON configuration file
    - Direct instantiation

    Environment Variables:
        MFN_SOURCE_TYPE: Source type (rest, file)
        MFN_MODE: Processing mode (feature, simulation)
        MFN_BATCH_SIZE: Batch size for processing
        MFN_MAX_QUEUE_SIZE: Maximum queue depth
        MFN_WORKERS: Number of worker tasks
        MFN_REST_URL: REST source URL
        MFN_FILE_PATH: File source path
        MFN_BACKEND_TYPE: Backend type
        MFN_BACKEND_ENDPOINT: Remote backend endpoint
        MFN_BACKEND_API_KEY: Backend API key
    """

    model_config = SettingsConfigDict(
        env_prefix="MFN_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Source configuration
    source_type: Literal["rest", "file"] = Field(default="rest", description="Data source type")
    rest_source: RestSourceConfig | None = Field(default=None, description="REST source config")
    file_source: FileSourceConfig | None = Field(default=None, description="File source config")
    # Backend configuration
    backend: BackendConfig = Field(default_factory=BackendConfig, description="Backend config")

    # Processing configuration
    mode: Literal["feature", "simulation"] = Field(default="feature", description="Processing mode")
    batch_size: int = Field(default=10, ge=1, le=1000, description="Events per batch")
    max_queue_size: int = Field(default=1000, ge=10, le=100000, description="Max queue depth")
    workers: int = Field(default=1, ge=1, le=32, description="Worker task count")

    # Transform configuration
    seed_fields: list[str] = Field(
        default_factory=lambda: ["seeds", "values", "data", "features"],
        description="Fields to extract seeds from",
    )
    grid_field: str = Field(default="grid_size", description="Grid size field")
    param_fields: list[str] = Field(default_factory=list, description="Fields to include in params")

    @classmethod
    def from_env(cls) -> "IngestionConfig":
        """Load configuration from environment variables.

        Returns:
            IngestionConfig populated from MFN_* environment variables
        """

        def _require_choice(env_key: str, allowed: tuple[str, ...], default: str) -> str:
            value = os.environ.get(env_key, default)
            if value not in allowed:
                allowed_str = "', '".join(allowed)
                raise ValueError(f"{env_key} must be one of '{allowed_str}', got '{value}'.")
            return value

        # Build source configs from individual env vars
        rest_url = os.environ.get("MFN_REST_URL")
        file_path = os.environ.get("MFN_FILE_PATH")
        rest_source = None
        file_source = None

        if rest_url:
            rest_source = RestSourceConfig(
                url=rest_url,
                poll_interval_seconds=float(os.environ.get("MFN_REST_POLL_INTERVAL", "60")),
                timeout=float(os.environ.get("MFN_REST_TIMEOUT", "30")),
            )

        if file_path:
            file_format = _require_choice("MFN_FILE_FORMAT", ("jsonl", "csv"), "jsonl")
            file_source = FileSourceConfig(
                path=file_path,
                format=file_format,
            )

        # Build backend config
        backend_type = _require_choice("MFN_BACKEND_TYPE", ("local", "remote"), "local")
        backend_protocol = _require_choice("MFN_BACKEND_PROTOCOL", ("rest",), "rest")
        backend = BackendConfig(
            type=backend_type,
            endpoint=os.environ.get("MFN_BACKEND_ENDPOINT"),
            protocol=backend_protocol,
            api_key=os.environ.get("MFN_BACKEND_API_KEY"),
        )

        source_type_env = _require_choice("MFN_SOURCE_TYPE", ("rest", "file"), "rest")
        mode_env = _require_choice("MFN_MODE", ("feature", "simulation"), "feature")
        return cls(
            source_type=source_type_env,
            rest_source=rest_source,
            file_source=file_source,
            backend=backend,
            mode=mode_env,
            batch_size=int(os.environ.get("MFN_BATCH_SIZE", "10")),
            max_queue_size=int(os.environ.get("MFN_MAX_QUEUE_SIZE", "1000")),
            workers=int(os.environ.get("MFN_WORKERS", "1")),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "IngestionConfig":
        """Load configuration from JSON file.

        Args:
            path: Path to JSON configuration file

        Returns:
            IngestionConfig populated from file

        Raises:
            FileNotFoundError: If config file doesn't exist
            json.JSONDecodeError: If file is not valid JSON
        """
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls.model_validate(data)

    def get_source_config(
        self,
    ) -> RestSourceConfig | FileSourceConfig:
        """Get the active source configuration.

        Returns:
            Source configuration based on source_type

        Raises:
            ValueError: If source config is not set
        """
        if self.source_type == "rest":
            if self.rest_source is None:
                raise ValueError("REST source config not set")
            return self.rest_source
        elif self.source_type == "file":
            if self.file_source is None:
                raise ValueError("File source config not set")
            return self.file_source
        raise ValueError(f"Unknown source type: {self.source_type}")

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary.

        Returns:
            Configuration as dictionary (excludes sensitive fields)
        """
        data = self.model_dump(exclude={"backend": {"api_key"}})
        if "backend" in data and self.backend.api_key:
            data["backend"]["api_key"] = "***"
        return data
