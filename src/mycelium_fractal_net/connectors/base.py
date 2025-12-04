# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Base abstractions for MFN data ingestion connectors.

This module defines the core interface that all MFN connectors must implement,
along with the canonical RawEvent data model for ingested data.

Example:
    >>> class MyConnector(BaseIngestor):
    ...     async def connect(self) -> None:
    ...         pass
    ...     async def fetch(self) -> AsyncIterator[RawEvent]:
    ...         yield RawEvent(source="my_source", timestamp=datetime.now(timezone.utc), payload={})
    ...     async def close(self) -> None:
    ...         pass
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = ["BaseIngestor", "RawEvent"]

logger = logging.getLogger(__name__)


class RawEvent(BaseModel):
    """Canonical raw event from an external data source.

    All connectors yield RawEvent instances that are subsequently normalized
    and transformed into MFN requests.

    Attributes:
        source: Identifier of the data source (e.g., "binance_api", "local_csv")
        timestamp: Event timestamp in UTC
        payload: Arbitrary event data as key-value pairs
        meta: Optional metadata (request_id, correlation_id, etc.)
    """

    model_config = ConfigDict(
        frozen=True,
        strict=False,
        str_strip_whitespace=True,
        extra="allow",
    )

    source: str = Field(..., min_length=1, description="Data source identifier")
    timestamp: datetime = Field(..., description="Event timestamp (UTC)")
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Event payload data"
    )
    meta: dict[str, Any] = Field(default_factory=dict, description="Optional metadata")

    @field_validator("timestamp", mode="before")
    @classmethod
    def _coerce_timestamp(cls, value: datetime | float | int | str) -> datetime:
        """Convert various timestamp formats to UTC datetime."""
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        elif isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
        elif isinstance(value, datetime):
            dt = value
        else:
            raise TypeError(f"Cannot convert {type(value).__name__} to datetime")

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt

    @field_validator("source")
    @classmethod
    def _validate_source(cls, value: str) -> str:
        """Ensure source identifier is non-empty."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("source must be non-empty")
        return stripped

    @property
    def ts(self) -> float:
        """Return timestamp as epoch seconds."""
        return self.timestamp.timestamp()


class BaseIngestor(ABC):
    """Abstract base class for all MFN data connectors.

    Connectors must implement:
    - connect(): Initialize connection to data source
    - fetch(): Async iterator yielding RawEvent instances
    - close(): Cleanup resources

    Example:
        >>> class HttpIngestor(BaseIngestor):
        ...     async def connect(self) -> None:
        ...         self.client = httpx.AsyncClient()
        ...     async def fetch(self) -> AsyncIterator[RawEvent]:
        ...         response = await self.client.get(self.url)
        ...         for item in response.json():
        ...             yield RawEvent(source="http", timestamp=..., payload=item)
        ...     async def close(self) -> None:
        ...         await self.client.aclose()
    """

    @abstractmethod
    async def connect(self) -> None:
        """Initialize connection to the data source.

        This method should perform any necessary setup such as:
        - Opening network connections
        - Authenticating with external services
        - Validating configuration

        Raises:
            ConnectionError: If connection cannot be established
        """

    @abstractmethod
    def fetch(self) -> AsyncIterator[RawEvent]:
        """Yield raw events from the data source.

        This is an async generator that continuously yields RawEvent instances.
        For polling sources, it should handle intervals internally.
        For streaming sources, it should yield events as they arrive.

        Yields:
            RawEvent instances representing ingested data

        Raises:
            Exception: If data cannot be fetched
        """

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources and close connections.

        This method should:
        - Close network connections gracefully
        - Release any held resources
        - Ensure proper shutdown
        """

    async def __aenter__(self) -> "BaseIngestor":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(
        self, exc_type: type | None, exc_val: Exception | None, exc_tb: Any
    ) -> None:
        """Async context manager exit."""
        await self.close()
