"""High level ingestion adapters with fault tolerance support."""

from .alpaca import AlpacaIngestionAdapter
from .base import (
    FaultTolerancePolicy,
    IngestionAdapter,
    RateLimitConfig,
    RetryConfig,
    TimeoutConfig,
)
from .ccxt import CCXTIngestionAdapter
from .csv import CSVIngestionAdapter
from .parquet import ParquetIngestionAdapter
from .polygon import PolygonIngestionAdapter

__all__ = [
    "AlpacaIngestionAdapter",
    "CCXTIngestionAdapter",
    "CSVIngestionAdapter",
    "ParquetIngestionAdapter",
    "PolygonIngestionAdapter",
    "FaultTolerancePolicy",
    "IngestionAdapter",
    "RateLimitConfig",
    "RetryConfig",
    "TimeoutConfig",
]
