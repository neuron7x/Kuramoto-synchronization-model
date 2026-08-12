# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""MFN-UPSTREAM-CONNECTOR: Unified data ingestion layer for Mycelium Fractal Net.

This module exposes only the supported ingestion surfaces:
- REST API polling
- file feeds

Kafka remains importable only as an explicit fail-closed compatibility error.

Components:
- BaseIngestor: Abstract interface for all data connectors
- RawEvent: Canonical raw event representation
- NormalizedEvent: Validated, normalized event model
- MFNRequest: Adapter to MFN core request structures
- RestIngestor: HTTP polling connector
- FileFeedIngestor: JSONL/CSV file connector
- KafkaIngestor: explicit fail-closed compatibility error (unsupported)
- IngestionRunner: Orchestrator for ingestion pipelines

Example:
    >>> from mycelium_fractal_net.connectors import RestIngestor, IngestionRunner
    >>> ingestor = RestIngestor(url="https://api.example.com/data")
    >>> runner = IngestionRunner(ingestor, backend)
    >>> await runner.run()
"""

from __future__ import annotations

from .base import BaseIngestor, RawEvent
from .config import (
    BackendConfig,
    FileSourceConfig,
    IngestionConfig,
    RestSourceConfig,
)
from .file_feed import FileFeedIngestor
from .kafka_source import KafkaIngestor
from .metrics import IngestionMetrics
from .rest_source import RestIngestor
from .runner import IngestionRunner, LocalBackend, MFNBackend, RemoteBackend
from .transform import (
    MappingError,
    MFNRequest,
    NormalizationError,
    NormalizedEvent,
    Transformer,
)

__all__ = [
    # Base abstractions
    "BaseIngestor",
    "RawEvent",
    # Transform pipeline
    "NormalizedEvent",
    "MFNRequest",
    "Transformer",
    "NormalizationError",
    "MappingError",
    # Connectors
    "RestIngestor",
    "FileFeedIngestor",
    "KafkaIngestor",
    # Runner and backends
    "IngestionRunner",
    "MFNBackend",
    "LocalBackend",
    "RemoteBackend",
    # Configuration
    "IngestionConfig",
    "RestSourceConfig",
    "FileSourceConfig",
    "BackendConfig",
    # Metrics
    "IngestionMetrics",
]
