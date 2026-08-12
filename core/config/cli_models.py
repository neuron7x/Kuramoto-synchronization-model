# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Lightweight Pydantic models for GeoSync CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .postgres import ensure_secure_postgres_uri, is_postgres_uri
from .registry import Environment

__all__ = [
    "CatalogConfig",
    "DataSourceConfig",
    "ExperimentAnalyticsConfig",
    "ExperimentConfig",
    "ExperimentDataConfig",
    "ExperimentArchiveConfig",
    "ExperimentBaselineConfig",
    "ExperimentDeviationAlertConfig",
    "ExperimentReportConfig",
    "ExperimentTrackingConfig",
    "DeploymentConfig",
    "DeploymentManifestsConfig",
    "ExecutionConfig",
    "FeatureFrameSourceConfig",
    "FeatureParityConfig",
    "FeatureParitySpecConfig",
    "IngestConfig",
    "OptimizeConfig",
    "KubectlConfig",
    "PostgresTLSConfig",
    "ReportConfig",
    "StrategyConfig",
    "GeoSyncBaseConfig",
    "VersioningConfig",
]


class VersioningConfig(BaseModel):
    """Configuration describing how artifacts should be versioned."""

    backend: Literal["none", "dvc", "lakefs"] = "none"
    repo_path: Optional[Path] = None
    message: Optional[str] = None

    @model_validator(mode="after")
    def _validate_repo(self) -> "VersioningConfig":
        if self.backend != "none" and self.repo_path is None:
            msg = "repo_path is required when using dvc or lakefs backends"
            raise ValueError(msg)
        return self


class PostgresTLSConfig(BaseModel):
    """TLS material required for PostgreSQL client authentication."""

    ca_file: Path
    cert_file: Path
    key_file: Path


class ExperimentDataConfig(BaseModel):
    """Dataset location for experiment-oriented jobs."""

    price_csv: Path
    price_column: str


class ExperimentAnalyticsConfig(BaseModel):
    """Numeric parameters for experiment analytics windows."""

    window: int
    bins: int
    delta: float

    @field_validator("window")
    @classmethod
    def _validate_window(cls, value: int) -> int:
        if value <= 0:
            msg = "window must be a positive integer"
            raise ValueError(msg)
        return value

    @field_validator("bins")
    @classmethod
    def _validate_bins(cls, value: int) -> int:
        if value <= 0:
            msg = "bins must be a positive integer"
            raise ValueError(msg)
        return value

    @field_validator("delta")
    @classmethod
    def _validate_delta(cls, value: float) -> float:
        if value <= 0:
            msg = "delta must be a positive float"
            raise ValueError(msg)
        return value


class ExperimentReportConfig(BaseModel):
    """Control automatic report and dashboard generation."""

    auto_generate: bool = True
    markdown_filename: str = "experiment_report.md"
    dashboard_filename: str = "experiment_dashboard.html"


class ExperimentArchiveConfig(BaseModel):
    """Configuration for automatic archival of experiment artifacts."""

    enabled: bool = True
    format: Literal["zip", "gztar", "tar", "bztar", "xztar"] = "zip"
    directory: Path | None = None
    keep_original: bool = True


class ExperimentDeviationAlertConfig(BaseModel):
    """Alerting strategy for baseline deviations."""

    enabled: bool = True
    strategy: Literal["relative", "absolute"] = "relative"
    tolerance: float = 0.05
    fail_on_deviation: bool = True


class ExperimentBaselineConfig(BaseModel):
    """Baseline reference metrics used to detect regressions."""

    name: str = "baseline"
    metrics_path: Path
    metric_tolerances: Dict[str, float] = Field(default_factory=dict)


class ExperimentTrackingConfig(BaseModel):
    """Where to persist experiment tracking artifacts."""

    enabled: bool = True
    base_dir: Path
    artifacts_dirname: str = "artifacts"
    reports_dirname: str = "reports"
    hyperparameters_filename: str = "hyperparameters.json"
    reports: ExperimentReportConfig = Field(default_factory=ExperimentReportConfig)
    archive: ExperimentArchiveConfig = Field(default_factory=ExperimentArchiveConfig)
    alerts: ExperimentDeviationAlertConfig = Field(default_factory=ExperimentDeviationAlertConfig)
    baseline: ExperimentBaselineConfig | None = None
    data_versioning: bool = True
    auto_log_config: bool = True
    auto_log_metadata: bool = True
    ci_integration: bool = False
    versioning: VersioningConfig = Field(default_factory=VersioningConfig)


class ExperimentConfig(BaseModel):
    """Hydra experiment configuration with strict database validation."""

    name: str
    db_uri: str
    db_tls: PostgresTLSConfig | None = None
    debug: bool = False
    log_level: str = "INFO"
    random_seed: int = 0
    data: ExperimentDataConfig
    analytics: ExperimentAnalyticsConfig
    tracking: ExperimentTrackingConfig

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        valid_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        if normalized not in valid_levels:
            msg = "log_level must be one of CRITICAL, ERROR, WARNING, INFO, DEBUG, or NOTSET"
            raise ValueError(msg)
        return normalized

    @field_validator("random_seed")
    @classmethod
    def _validate_random_seed(cls, value: int) -> int:
        if value < 0:
            msg = "random_seed must be greater than or equal to zero"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _validate_database_security(self) -> "ExperimentConfig":
        ensure_secure_postgres_uri(self.db_uri)
        if is_postgres_uri(self.db_uri) and self.db_tls is None:
            msg = "db_tls must be provided when using a PostgreSQL database"
            raise ValueError(msg)
        return self


class CatalogConfig(BaseModel):
    """Simple file-backed catalog configuration."""

    path: Path = Field(default=Path("data/feature_catalog.json"))


class DataSourceConfig(BaseModel):
    """Location of input data for CLI jobs."""

    kind: Literal["csv", "parquet"] = "csv"
    path: Path
    timestamp_field: str = "timestamp"
    value_field: str = "price"


class StrategyConfig(BaseModel):
    """Describes a callable that returns trading signals."""

    entrypoint: str
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_entrypoint(self) -> "StrategyConfig":
        if ":" not in self.entrypoint:
            raise ValueError("entrypoint must be of the form 'module:function'")
        return self


class GeoSyncBaseConfig(BaseModel):
    """Common metadata shared by CLI configurations."""

    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IngestConfig(GeoSyncBaseConfig):
    """Configuration driving the ingest command."""

    source: DataSourceConfig
    destination: Path
    catalog: CatalogConfig = Field(default_factory=CatalogConfig)
    versioning: VersioningConfig = Field(default_factory=VersioningConfig)


class ExecutionConfig(BaseModel):
    """Execution parameters for the backtest command."""

    starting_cash: float = 100_000.0
    fee_bps: float = 0.0


class BacktestConfig(GeoSyncBaseConfig):
    """Configuration for running a simple vectorized backtest."""

    data: DataSourceConfig
    strategy: StrategyConfig
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    results_path: Path = Field(default=Path("reports/backtest.json"))
    catalog: CatalogConfig = Field(default_factory=CatalogConfig)
    versioning: VersioningConfig = Field(default_factory=VersioningConfig)


class OptimizeConfig(GeoSyncBaseConfig):
    """Configuration for parameter search via grid search."""

    objective: str
    search_space: Dict[str, Iterable[Any]]
    results_path: Path = Field(default=Path("reports/optimize.json"))
    versioning: VersioningConfig = Field(default_factory=VersioningConfig)

    @model_validator(mode="after")
    def _validate_objective(self) -> "OptimizeConfig":
        if ":" not in self.objective:
            raise ValueError("objective must be of the form 'module:function'")
        return self


class ExecConfig(GeoSyncBaseConfig):
    """Configuration for running a real-time signal evaluation."""

    data: DataSourceConfig
    strategy: StrategyConfig
    results_path: Path = Field(default=Path("reports/exec.json"))
    catalog: CatalogConfig = Field(default_factory=CatalogConfig)
    versioning: VersioningConfig = Field(default_factory=VersioningConfig)


class ReportConfig(GeoSyncBaseConfig):
    """Configuration for aggregating CLI outputs into a report."""

    inputs: List[Path]
    output_path: Path
    html_output_path: Path | None = None
    pdf_output_path: Path | None = None
    template: Optional[Path] = None
    versioning: VersioningConfig = Field(default_factory=VersioningConfig)


class FeatureFrameSourceConfig(BaseModel):
    """Location of offline feature snapshots used for parity checks."""

    path: Path
    format: Literal["auto", "csv", "parquet"] = "auto"


class FeatureParitySpecConfig(BaseModel):
    """Declarative parity expectations for a feature view."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    feature_view: str
    entity_columns: Tuple[str, ...] = ("entity_id",)
    timestamp_column: str = "ts"
    timestamp_granularity: pd.Timedelta | str | None = None
    numeric_tolerance: float | None = 0.0
    max_clock_skew: pd.Timedelta | str | None = "0s"
    allow_schema_evolution: bool = False
    value_columns: Tuple[str, ...] | None = None

    @field_validator("timestamp_granularity", "max_clock_skew", mode="before")
    def _parse_timedelta(cls, value: object) -> pd.Timedelta | None:
        if value is None or isinstance(value, pd.Timedelta):
            return value
        if isinstance(value, str) and value.strip().lower() in {"", "none"}:
            return None
        try:
            return pd.Timedelta(value)
        except (ValueError, TypeError) as exc:  # pragma: no cover - defensive
            raise ValueError("timedelta fields must be pandas-compatible strings") from exc

    @model_validator(mode="after")
    def _validate_columns(self) -> "FeatureParitySpecConfig":
        if not self.entity_columns:
            raise ValueError("entity_columns must define at least one column")
        return self


class FeatureParityConfig(GeoSyncBaseConfig):
    """Top-level configuration driving the feature parity CLI command."""

    offline: FeatureFrameSourceConfig
    online_store: Path = Field(default=Path("data/online_features"))
    mode: Literal["append", "overwrite"] = "append"
    spec: FeatureParitySpecConfig

    @model_validator(mode="after")
    def _validate_mode(self) -> "FeatureParityConfig":
        if self.mode not in {"append", "overwrite"}:
            raise ValueError("mode must be either 'append' or 'overwrite'")
        return self


class DeploymentManifestsConfig(BaseModel):
    """Describe how Kubernetes manifests should be located for deployment."""

    model_config = ConfigDict(extra="forbid")

    root: Path = Field(default=Path("deploy/kustomize/overlays"))
    name: str | None = None
    path: Path | None = None

    @model_validator(mode="after")
    def _validate_choice(self) -> "DeploymentManifestsConfig":
        if self.path is not None and self.name is not None:
            msg = "manifests.path and manifests.name are mutually exclusive"
            raise ValueError(msg)
        return self


class KubectlConfig(BaseModel):
    """Parameters controlling kubectl invocation for deployments."""

    model_config = ConfigDict(extra="forbid")

    binary: Path = Field(default=Path("kubectl"))
    context: str | None = None
    namespace: str | None = None
    extra_args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    dry_run: Literal["none", "client", "server"] = "client"


class DeploymentConfig(GeoSyncBaseConfig):
    """Configuration driving the GeoSync deployment CLI command."""

    model_config = ConfigDict(extra="forbid")

    environment: Environment
    strategy: str
    artifact: str
    manifests: DeploymentManifestsConfig = Field(default_factory=DeploymentManifestsConfig)
    deployment_name: str = "geosync-api"
    wait_for_rollout: bool = True
    rollout_timeout_seconds: float = 600.0
    kubectl: KubectlConfig = Field(default_factory=KubectlConfig)
    annotations: Dict[str, str] = Field(default_factory=dict)
    summary_path: Path = Field(default=Path("reports/live/deployments/latest.json"))

    @field_validator("strategy", "artifact")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("strategy and artifact must be non-empty strings")
        return value.strip()

    @field_validator("rollout_timeout_seconds")
    @classmethod
    def _validate_timeout(cls, value: float) -> float:
        if value <= 0.0:
            raise ValueError("rollout_timeout_seconds must be greater than zero")
        return float(value)

    @field_validator("annotations")
    @classmethod
    def _normalize_annotations(cls, value: Dict[str, str]) -> Dict[str, str]:
        normalized: Dict[str, str] = {}
        for key, val in value.items():
            normalized[str(key)] = str(val)
        return normalized

    @model_validator(mode="after")
    def _validate_rollout(self) -> "DeploymentConfig":
        if not self.wait_for_rollout:
            return self
        if self.rollout_timeout_seconds <= 0.0:
            raise ValueError("wait_for_rollout requires a positive rollout_timeout_seconds")
        return self
