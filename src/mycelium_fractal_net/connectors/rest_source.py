# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""REST HTTP polling connector for MFN data ingestion.

This module provides a connector that polls HTTP REST endpoints at configured
intervals and yields RawEvent instances for each record.

Example:
    >>> async with RestIngestor(
    ...     url="https://api.example.com/data",
    ...     poll_interval_seconds=30,
    ...     headers={"Authorization": "Bearer token"}
    ... ) as ingestor:
    ...     async for event in ingestor.fetch():
    ...         print(event.payload)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx

from .base import BaseIngestor, RawEvent

__all__ = ["RestIngestor"]

logger = logging.getLogger(__name__)


class RestIngestor(BaseIngestor):
    """HTTP REST polling connector.

    Periodically polls a REST endpoint and yields records as RawEvent instances.
    Supports authentication headers, query parameters, and configurable retry logic.

    Attributes:
        url: Target HTTP endpoint URL
        poll_interval_seconds: Seconds between poll requests
        batch_size: Maximum records to process per poll
        max_retries: Maximum retry attempts on failure
        timeout: Request timeout in seconds
        headers: Optional HTTP headers (including auth)
        params: Optional query parameters
    """

    def __init__(
        self,
        url: str,
        *,
        poll_interval_seconds: float = 60.0,
        batch_size: int = 100,
        max_retries: int = 3,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        source_name: str | None = None,
    ) -> None:
        """Initialize REST ingestor.

        Args:
            url: Target HTTP endpoint URL
            poll_interval_seconds: Seconds between polls (default: 60)
            batch_size: Max records per poll (default: 100)
            max_retries: Retry attempts on failure (default: 3)
            timeout: Request timeout in seconds (default: 30)
            headers: Optional HTTP headers
            params: Optional query parameters
            source_name: Override for source identifier in events
        """
        self.url = url
        self.poll_interval_seconds = poll_interval_seconds
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.timeout = timeout
        self.headers = headers or {}
        self.params = params or {}
        self.source_name = source_name or self._derive_source_name(url)

        self._client: httpx.AsyncClient | None = None
        self._running = False
        self._poll_count = 0
        self._error_count = 0

    @staticmethod
    def _derive_source_name(url: str) -> str:
        """Derive source name from URL."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            return f"rest_{parsed.netloc.replace('.', '_').replace(':', '_')}"
        except Exception:
            return "rest_source"

    async def connect(self) -> None:
        """Initialize HTTP client connection.

        Creates an httpx.AsyncClient with configured timeout and headers.
        """
        logger.info(f"Connecting REST ingestor to {self.url}")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers=self.headers,
        )
        self._running = True
        logger.info(f"REST ingestor connected: {self.source_name}")

    async def fetch(self) -> AsyncIterator[RawEvent]:
        """Poll endpoint and yield events.

        Continuously polls the configured URL at the specified interval,
        yielding RawEvent instances for each record in the response.

        Yields:
            RawEvent for each record in the response

        Raises:
            RuntimeError: If client not initialized
        """
        if self._client is None:
            raise RuntimeError("Client not initialized. Call connect() first.")

        while self._running:
            try:
                events = await self._fetch_once()
                for event in events:
                    yield event

                self._poll_count += 1
                logger.debug(
                    f"Poll {self._poll_count} completed: {len(events)} events from {self.url}"
                )

            except httpx.HTTPStatusError as e:
                self._error_count += 1
                logger.warning(
                    f"HTTP error polling {self.url}: {e.response.status_code} "
                    f"(attempt {self._error_count})"
                )
            except httpx.RequestError as e:
                self._error_count += 1
                logger.warning(
                    f"Request error polling {self.url}: {e} (attempt {self._error_count})"
                )
            except Exception as e:
                self._error_count += 1
                logger.error(f"Unexpected error polling {self.url}: {e}")

            # Wait before next poll
            await asyncio.sleep(self.poll_interval_seconds)

    async def _fetch_once(self) -> list[RawEvent]:
        """Perform a single fetch operation with retries.

        Returns:
            List of RawEvent instances from the response
        """
        if self._client is None:
            raise RuntimeError("Client not initialized")

        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                response = await self._client.get(self.url, params=self.params)
                response.raise_for_status()

                data = response.json()
                events = self._parse_response(data)

                logger.info(
                    f"Fetched {len(events)} events from {self.url} "
                    f"(status: {response.status_code})"
                )
                return events

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code >= 500:
                    # Retry on server errors
                    logger.warning(
                        f"Server error {e.response.status_code}, "
                        f"retrying ({attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(2**attempt)
                    continue
                raise

            except httpx.RequestError as e:
                last_error = e
                logger.warning(
                    f"Request failed, retrying ({attempt + 1}/{self.max_retries}): {e}"
                )
                await asyncio.sleep(2**attempt)
                continue

        if last_error:
            raise last_error
        return []

    def _parse_response(self, data: Any) -> list[RawEvent]:
        """Parse HTTP response data into RawEvent instances.

        Handles both list and object responses.

        Args:
            data: Parsed JSON response

        Returns:
            List of RawEvent instances
        """
        timestamp = datetime.now(timezone.utc)
        events: list[RawEvent] = []

        if isinstance(data, list):
            # Array response - one event per item
            for i, item in enumerate(data[: self.batch_size]):
                if isinstance(item, dict):
                    # Try to extract timestamp from item
                    item_ts = self._extract_timestamp(item) or timestamp
                    events.append(
                        RawEvent(
                            source=self.source_name,
                            timestamp=item_ts,
                            payload=item,
                            meta={"index": i, "url": self.url},
                        )
                    )
        elif isinstance(data, dict):
            # Object response - check for nested data arrays
            if "data" in data and isinstance(data["data"], list):
                for i, item in enumerate(data["data"][: self.batch_size]):
                    if isinstance(item, dict):
                        item_ts = self._extract_timestamp(item) or timestamp
                        events.append(
                            RawEvent(
                                source=self.source_name,
                                timestamp=item_ts,
                                payload=item,
                                meta={"index": i, "url": self.url},
                            )
                        )
            elif "results" in data and isinstance(data["results"], list):
                for i, item in enumerate(data["results"][: self.batch_size]):
                    if isinstance(item, dict):
                        item_ts = self._extract_timestamp(item) or timestamp
                        events.append(
                            RawEvent(
                                source=self.source_name,
                                timestamp=item_ts,
                                payload=item,
                                meta={"index": i, "url": self.url},
                            )
                        )
            else:
                # Single object response
                item_ts = self._extract_timestamp(data) or timestamp
                events.append(
                    RawEvent(
                        source=self.source_name,
                        timestamp=item_ts,
                        payload=data,
                        meta={"url": self.url},
                    )
                )

        return events

    def _extract_timestamp(self, item: dict[str, Any]) -> datetime | None:
        """Try to extract timestamp from item.

        Looks for common timestamp field names.

        Args:
            item: Dictionary to extract timestamp from

        Returns:
            Extracted datetime or None
        """
        ts_fields = ["timestamp", "time", "ts", "datetime", "created_at", "date"]
        for field in ts_fields:
            if field in item:
                value = item[field]
                try:
                    if isinstance(value, (int, float)):
                        return datetime.fromtimestamp(float(value), tz=timezone.utc)
                    elif isinstance(value, str):
                        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt.astimezone(timezone.utc)
                except Exception:
                    continue
        return None

    async def close(self) -> None:
        """Close HTTP client connection."""
        self._running = False
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info(
                f"REST ingestor closed: {self.source_name} "
                f"(polls: {self._poll_count}, errors: {self._error_count})"
            )

    @property
    def stats(self) -> dict[str, int]:
        """Return ingestion statistics."""
        return {
            "poll_count": self._poll_count,
            "error_count": self._error_count,
        }
