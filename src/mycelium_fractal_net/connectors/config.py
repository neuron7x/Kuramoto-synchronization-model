# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
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

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "RestSourceConfig",
    "FileSourceConfig",
    "KafkaSourceConfig",
    "BackendConfig",
    "IngestionConfig",
]


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
    batch_size: int = Field(
        default=100, ge=1, le=10000, description="Max records per poll"
    )
    max_retries: int = Field(default=3, ge=0, le=10, description="Retry attempts")
    timeout: float = Field(
        default=30.0, ge=1.0, le=300.0, description="Request timeout"
    )
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP headers")
    params: dict[str, str] = Field(default_factory=dict, description="Query parameters")
    source_name: str | None = Field(
        default=None, description="Source identifier override"
    )


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
    batch_size: int = Field(
        default=100, ge=1, le=10000, description="Records per batch"
    )
    field_mapping: dict[str, str] = Field(
        default_factory=dict, description="Column to field mapping"
    )
    source_name: str | None = Field(
        default=None, description="Source identifier override"
    )
    timestamp_field: str | None = Field(
        default=None, description="Timestamp field name"
    )

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        """Validate path is not empty."""
        if not value.strip():
            raise ValueError("path cannot be empty")
        return value


class KafkaSourceConfig(BaseModel):
    """Configuration for Kafka message source.

    Attributes:
        bootstrap_servers: Kafka broker addresses
        topic: Topic to consume
        group_id: Consumer group identifier
        auto_offset_reset: Offset reset policy
        batch_size: Messages per batch
        security_protocol: Security protocol
        sasl_mechanism: SASL mechanism
        sasl_username: SASL username
        sasl_password: SASL password
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    bootstrap_servers: str = Field(..., min_length=1, description="Kafka brokers")
    topic: str = Field(..., min_length=1, description="Topic to consume")
    group_id: str = Field(default="mfn-consumer", description="Consumer group")
    auto_offset_reset: Literal["earliest", "latest"] = Field(
        default="latest", description="Offset reset policy"
    )
    batch_size: int = Field(
        default=100, ge=1, le=10000, description="Messages per batch"
    )
    source_name: str | None = Field(
        default=None, description="Source identifier override"
    )
    security_protocol: Literal["PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"] = (
        Field(default="PLAINTEXT", description="Security protocol")
    )
    sasl_mechanism: str | None = Field(default=None, description="SASL mechanism")
    sasl_username: str | None = Field(default=None, description="SASL username")
    sasl_password: str | None = Field(default=None, description="SASL password")


class BackendConfig(BaseModel):
    """Configuration for MFN backend connection.

    Attributes:
        type: Backend type ('local' or 'remote')
        endpoint: Remote endpoint URL (for remote type)
        protocol: Remote protocol ('grpc' or 'rest')
        api_key: Authentication key
        timeout: Request timeout
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    type: Literal["local", "remote"] = Field(
        default="local", description="Backend type"
    )
    endpoint: str | None = Field(default=None, description="Remote endpoint URL")
    protocol: Literal["grpc", "rest"] = Field(
        default="rest", description="Remote protocol"
    )
    api_key: str | None = Field(default=None, description="API key for authentication")
    timeout: float = Field(
        default=30.0, ge=1.0, le=300.0, description="Request timeout"
    )


class IngestionConfig(BaseSettings):
    """Main configuration for MFN ingestion pipeline.

    Supports loading from:
    - Environment variables (MFN_ prefix)
    - JSON configuration file
    - Direct instantiation

    Environment Variables:
        MFN_SOURCE_TYPE: Source type (rest, file, kafka)
        MFN_MODE: Processing mode (feature, simulation)
        MFN_BATCH_SIZE: Batch size for processing
        MFN_MAX_QUEUE_SIZE: Maximum queue depth
        MFN_WORKERS: Number of worker tasks
        MFN_REST_URL: REST source URL
        MFN_FILE_PATH: File source path
        MFN_KAFKA_SERVERS: Kafka bootstrap servers
        MFN_KAFKA_TOPIC: Kafka topic
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
    source_type: Literal["rest", "file", "kafka"] = Field(
        default="rest", description="Data source type"
    )
    rest_source: RestSourceConfig | None = Field(
        default=None, description="REST source config"
    )
    file_source: FileSourceConfig | None = Field(
        default=None, description="File source config"
    )
    kafka_source: KafkaSourceConfig | None = Field(
        default=None, description="Kafka source config"
    )

    # Backend configuration
    backend: BackendConfig = Field(
        default_factory=BackendConfig, description="Backend config"
    )

    # Processing configuration
    mode: Literal["feature", "simulation"] = Field(
        default="feature", description="Processing mode"
    )
    batch_size: int = Field(default=10, ge=1, le=1000, description="Events per batch")
    max_queue_size: int = Field(
        default=1000, ge=10, le=100000, description="Max queue depth"
    )
    workers: int = Field(default=1, ge=1, le=32, description="Worker task count")

    # Transform configuration
    seed_fields: list[str] = Field(
        default_factory=lambda: ["seeds", "values", "data", "features"],
        description="Fields to extract seeds from",
    )
    grid_field: str = Field(default="grid_size", description="Grid size field")
    param_fields: list[str] = Field(
        default_factory=list, description="Fields to include in params"
    )

    @classmethod
    def from_env(cls) -> "IngestionConfig":
        """Load configuration from environment variables.

        Returns:
            IngestionConfig populated from MFN_* environment variables
        """
        # Build source configs from individual env vars
        rest_url = os.environ.get("MFN_REST_URL")
        file_path = os.environ.get("MFN_FILE_PATH")
        kafka_servers = os.environ.get("MFN_KAFKA_SERVERS")
        kafka_topic = os.environ.get("MFN_KAFKA_TOPIC")

        rest_source = None
        file_source = None
        kafka_source = None

        if rest_url:
            rest_source = RestSourceConfig(
                url=rest_url,
                poll_interval_seconds=float(
                    os.environ.get("MFN_REST_POLL_INTERVAL", "60")
                ),
                timeout=float(os.environ.get("MFN_REST_TIMEOUT", "30")),
            )

        if file_path:
            file_format = os.environ.get("MFN_FILE_FORMAT", "jsonl")
            if file_format in ("jsonl", "csv"):
                file_source = FileSourceConfig(
                    path=file_path,
                    format=file_format,
                )

        if kafka_servers and kafka_topic:
            kafka_source = KafkaSourceConfig(
                bootstrap_servers=kafka_servers,
                topic=kafka_topic,
                group_id=os.environ.get("MFN_KAFKA_GROUP", "mfn-consumer"),
            )

        # Build backend config
        backend_type = os.environ.get("MFN_BACKEND_TYPE", "local")
        backend_protocol = os.environ.get("MFN_BACKEND_PROTOCOL", "rest")
        backend = BackendConfig(
            type=backend_type if backend_type in ("local", "remote") else "local",
            endpoint=os.environ.get("MFN_BACKEND_ENDPOINT"),
            protocol=(
                backend_protocol if backend_protocol in ("grpc", "rest") else "rest"
            ),
            api_key=os.environ.get("MFN_BACKEND_API_KEY"),
        )

        source_type_env = os.environ.get("MFN_SOURCE_TYPE", "rest")
        mode_env = os.environ.get("MFN_MODE", "feature")
        return cls(
            source_type=(
                source_type_env
                if source_type_env in ("rest", "file", "kafka")
                else "rest"
            ),
            rest_source=rest_source,
            file_source=file_source,
            kafka_source=kafka_source,
            backend=backend,
            mode=mode_env if mode_env in ("feature", "simulation") else "feature",
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
    ) -> RestSourceConfig | FileSourceConfig | KafkaSourceConfig:
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
        elif self.source_type == "kafka":
            if self.kafka_source is None:
                raise ValueError("Kafka source config not set")
            return self.kafka_source
        else:
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
