# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""File-based data feed connector for MFN ingestion.

This module provides a connector that reads data from local files
(JSONL, CSV) and yields RawEvent instances for each record.

Supported formats:
- JSON Lines (.jsonl): One JSON object per line
- CSV: Comma-separated values with header row

Example:
    >>> async with FileFeedIngestor(
    ...     path="/data/feed.jsonl",
    ...     format="jsonl"
    ... ) as ingestor:
    ...     async for event in ingestor.fetch():
    ...         print(event.payload)
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from .base import BaseIngestor, RawEvent

__all__ = ["FileFeedIngestor"]

logger = logging.getLogger(__name__)


class FileFeedIngestor(BaseIngestor):
    """Local file feed connector.

    Reads records from local files and yields them as RawEvent instances.
    Supports JSONL and CSV formats with configurable field mappings.

    Attributes:
        path: Path to the data file
        format: File format ('jsonl' or 'csv')
        batch_size: Records to yield per batch
        field_mapping: CSV column to payload field mapping
    """

    def __init__(
        self,
        path: str | Path,
        *,
        format: str = "jsonl",
        batch_size: int = 100,
        field_mapping: dict[str, str] | None = None,
        source_name: str | None = None,
        timestamp_field: str | None = None,
    ) -> None:
        """Initialize file feed ingestor.

        Args:
            path: Path to the data file
            format: File format ('jsonl' or 'csv')
            batch_size: Records per yield batch
            field_mapping: Map CSV columns to payload fields
            source_name: Override for source identifier
            timestamp_field: Field containing timestamp data
        """
        self.path = Path(path)
        self.format = format.lower()
        self.batch_size = batch_size
        self.field_mapping = field_mapping or {}
        self.source_name = source_name or f"file_{self.path.stem}"
        self.timestamp_field = timestamp_field

        if self.format not in ("jsonl", "csv"):
            raise ValueError(f"Unsupported format: {format}. Use 'jsonl' or 'csv'.")

        self._record_count = 0
        self._error_count = 0

    async def connect(self) -> None:
        """Validate file exists and is readable.

        For local files, this is a no-op validation step.
        """
        if not self.path.exists():
            raise FileNotFoundError(f"File not found: {self.path}")
        if not self.path.is_file():
            raise ValueError(f"Path is not a file: {self.path}")

        logger.info(f"File feed ingestor ready: {self.path} (format: {self.format})")

    async def fetch(self) -> AsyncIterator[RawEvent]:
        """Read file and yield events.

        Reads the file line by line (JSONL) or row by row (CSV)
        and yields RawEvent instances.

        Yields:
            RawEvent for each record in the file
        """
        logger.info(f"Starting file ingestion: {self.path}")

        if self.format == "jsonl":
            async for event in self._read_jsonl():
                yield event
        elif self.format == "csv":
            async for event in self._read_csv():
                yield event

        logger.info(
            f"File ingestion complete: {self.path} "
            f"(records: {self._record_count}, errors: {self._error_count})"
        )

    async def _read_jsonl(self) -> AsyncIterator[RawEvent]:
        """Read JSON Lines format file.

        Each line is a complete JSON object.

        Yields:
            RawEvent for each valid JSON line
        """
        with open(self.path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    if not isinstance(data, dict):
                        logger.warning(f"Line {line_num}: Expected dict, got {type(data).__name__}")
                        self._error_count += 1
                        continue

                    timestamp = self._extract_timestamp(data) or datetime.now(timezone.utc)
                    event = RawEvent(
                        source=self.source_name,
                        timestamp=timestamp,
                        payload=data,
                        meta={"line": line_num, "file": str(self.path)},
                    )
                    self._record_count += 1
                    yield event

                except json.JSONDecodeError as e:
                    logger.warning(f"Line {line_num}: JSON parse error: {e}")
                    self._error_count += 1
                    continue

    async def _read_csv(self) -> AsyncIterator[RawEvent]:
        """Read CSV format file.

        First row is treated as headers.

        Yields:
            RawEvent for each row
        """
        with open(self.path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)

            for row_num, row in enumerate(reader, start=1):
                try:
                    # Apply field mapping if specified
                    if self.field_mapping:
                        payload = {}
                        for csv_col, field_name in self.field_mapping.items():
                            if csv_col in row:
                                payload[field_name] = self._coerce_value(row[csv_col])
                        # Include unmapped columns as-is
                        for col, value in row.items():
                            if col not in self.field_mapping:
                                payload[col] = self._coerce_value(value)
                    else:
                        payload = {k: self._coerce_value(v) for k, v in row.items()}

                    timestamp = self._extract_timestamp(payload) or datetime.now(timezone.utc)
                    event = RawEvent(
                        source=self.source_name,
                        timestamp=timestamp,
                        payload=payload,
                        meta={"row": row_num, "file": str(self.path)},
                    )
                    self._record_count += 1
                    yield event

                except Exception as e:
                    logger.warning(f"Row {row_num}: Error processing: {e}")
                    self._error_count += 1
                    continue

    def _coerce_value(self, value: str) -> Any:
        """Attempt to coerce string value to appropriate type.

        Args:
            value: String value from CSV

        Returns:
            Coerced value (int, float, bool, or original string)
        """
        if not value:
            return None

        for caster in (int, float):
            try:
                return caster(value)
            except ValueError:
                continue

        # Check for boolean strings (true/false/yes/no)
        lower_value = value.lower()
        if lower_value in ("true", "yes"):
            return True
        if lower_value in ("false", "no"):
            return False

        return value

    def _extract_timestamp(self, data: dict[str, Any]) -> datetime | None:
        """Extract timestamp from record.

        Args:
            data: Record data

        Returns:
            Extracted datetime or None
        """
        # Use configured timestamp field first
        if self.timestamp_field and self.timestamp_field in data:
            return self._parse_timestamp(data[self.timestamp_field])

        # Try common timestamp fields
        ts_fields = ["timestamp", "time", "ts", "datetime", "created_at", "date"]
        for field in ts_fields:
            if field in data:
                ts = self._parse_timestamp(data[field])
                if ts:
                    return ts

        return None

    def _parse_timestamp(self, value: Any) -> datetime | None:
        """Parse timestamp value.

        Args:
            value: Timestamp value

        Returns:
            Parsed datetime or None
        """
        try:
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    return value.replace(tzinfo=timezone.utc)
                return value.astimezone(timezone.utc)

            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(float(value), tz=timezone.utc)

            if isinstance(value, str):
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)

        except Exception as exc:
            logger.debug("Failed to parse timestamp value %r: %s", value, exc)

        return None

    async def close(self) -> None:
        """Cleanup (no-op for file feed)."""
        logger.info(
            f"File feed closed: {self.source_name} "
            f"(records: {self._record_count}, errors: {self._error_count})"
        )

    @property
    def stats(self) -> dict[str, int]:
        """Return ingestion statistics."""
        return {
            "record_count": self._record_count,
            "error_count": self._error_count,
        }
