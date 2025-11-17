# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Market feed recording infrastructure for reproducible tests.

This module provides schemas and utilities for recording real market data feeds
in JSONL format with proper validation, timezone synchronization, and quality control.
Designed for TD(0) RPE, DDM, and Go/No-Go dopamine loop testing with stable,
reproducible samples for regression tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class MarketFeedRecord(BaseModel):
    """Single market feed record with exchange and ingestion timestamps.

    Schema fields:
    - exchange_ts: Timestamp from the exchange (ISO 8601 with timezone)
    - ingest_ts: Timestamp when data was ingested (ISO 8601 with timezone)
    - bid: Best bid price
    - ask: Best ask price
    - last: Last traded price
    - volume: Trade volume
    """

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )

    exchange_ts: datetime = Field(
        ...,
        description="Exchange timestamp in UTC",
    )
    ingest_ts: datetime = Field(
        ...,
        description="Ingestion timestamp in UTC",
    )
    bid: Decimal = Field(
        ...,
        description="Best bid price",
        gt=0,
    )
    ask: Decimal = Field(
        ...,
        description="Best ask price",
        gt=0,
    )
    last: Decimal = Field(
        ...,
        description="Last traded price",
        gt=0,
    )
    volume: Decimal = Field(
        ...,
        description="Trade volume",
        ge=0,
    )

    @field_validator("exchange_ts", "ingest_ts", mode="before")
    @classmethod
    def _validate_timestamp(cls, value: Any) -> datetime:
        """Validate and normalize timestamps to UTC."""
        if isinstance(value, str):
            # Parse ISO 8601 strings
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        elif isinstance(value, datetime):
            dt = value
        elif isinstance(value, (int, float)):
            # Unix timestamp
            dt = datetime.fromtimestamp(value, tz=timezone.utc)
        else:
            raise ValueError(f"Invalid timestamp format: {type(value)}")

        # Ensure UTC timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        return dt

    @field_validator("bid", "ask", "last", "volume", mode="before")
    @classmethod
    def _validate_decimal(cls, value: Any) -> Decimal:
        """Validate and coerce numeric values to Decimal."""
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception as e:
            raise ValueError(f"Invalid numeric value: {value}") from e

    @model_validator(mode="after")
    def _validate_prices(self) -> "MarketFeedRecord":
        """Validate price relationships and constraints."""
        # Bid should be <= Ask
        if self.bid > self.ask:
            raise ValueError(f"Bid {self.bid} must be <= Ask {self.ask}")

        # Last should be within bid-ask spread (with small tolerance for crosses)
        spread_tolerance = self.ask - self.bid
        lower_bound = self.bid - spread_tolerance * Decimal("0.1")
        upper_bound = self.ask + spread_tolerance * Decimal("0.1")

        if not (lower_bound <= self.last <= upper_bound):
            raise ValueError(
                f"Last price {self.last} outside reasonable range "
                f"[{lower_bound}, {upper_bound}] for bid={self.bid}, ask={self.ask}"
            )

        # Ingest timestamp should be >= exchange timestamp (allowing small clock skew)
        latency_ms = (self.ingest_ts - self.exchange_ts).total_seconds() * 1000
        if latency_ms < -100:  # Allow 100ms clock skew
            raise ValueError(
                f"Ingest timestamp {self.ingest_ts} is before exchange timestamp "
                f"{self.exchange_ts} by more than tolerance"
            )

        # Check for reasonable latency (< 10 seconds for sanity)
        if latency_ms > 10_000:
            raise ValueError(
                f"Latency {latency_ms:.1f}ms exceeds maximum threshold of 10s"
            )

        return self

    def to_jsonl(self) -> str:
        """Serialize to JSONL format."""
        data = {
            "exchange_ts": self.exchange_ts.isoformat(),
            "ingest_ts": self.ingest_ts.isoformat(),
            "bid": str(self.bid),
            "ask": str(self.ask),
            "last": str(self.last),
            "volume": str(self.volume),
        }
        return json.dumps(data)

    @classmethod
    def from_jsonl(cls, line: str) -> "MarketFeedRecord":
        """Parse from JSONL format."""
        data = json.loads(line)
        return cls(**data)

    @property
    def latency_ms(self) -> float:
        """Calculate ingestion latency in milliseconds."""
        return (self.ingest_ts - self.exchange_ts).total_seconds() * 1000

    @property
    def spread(self) -> Decimal:
        """Calculate bid-ask spread."""
        return self.ask - self.bid

    @property
    def mid_price(self) -> Decimal:
        """Calculate mid price."""
        return (self.bid + self.ask) / Decimal("2")


@dataclass
class MarketFeedMetadata:
    """Metadata for market feed recordings."""

    symbol: str
    venue: str
    start_time: datetime
    end_time: datetime
    record_count: int
    version: str = "1.0.0"
    description: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "symbol": self.symbol,
            "venue": self.venue,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "record_count": self.record_count,
            "version": self.version,
            "description": self.description,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketFeedMetadata":
        """Create from dictionary."""
        return cls(
            symbol=data["symbol"],
            venue=data["venue"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]),
            record_count=data["record_count"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            tags=data.get("tags", []),
        )


class MarketFeedRecording:
    """Container for market feed recordings with validation and quality control."""

    def __init__(
        self,
        records: List[MarketFeedRecord],
        metadata: Optional[MarketFeedMetadata] = None,
    ):
        self.records = records
        self.metadata = metadata
        self._validate_monotonicity()

    def _validate_monotonicity(self) -> None:
        """Validate that timestamps are monotonically increasing."""
        if len(self.records) < 2:
            return

        for i in range(1, len(self.records)):
            prev = self.records[i - 1]
            curr = self.records[i]

            if curr.exchange_ts < prev.exchange_ts:
                raise ValueError(
                    f"Exchange timestamps not monotonic at index {i}: "
                    f"{prev.exchange_ts} -> {curr.exchange_ts}"
                )

    def write_jsonl(self, path: Path) -> None:
        """Write recording to JSONL file."""
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            for record in self.records:
                f.write(record.to_jsonl() + "\n")

    @classmethod
    def read_jsonl(cls, path: Path) -> "MarketFeedRecording":
        """Read recording from JSONL file."""
        records = []
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(MarketFeedRecord.from_jsonl(line))
        return cls(records)

    def write_with_metadata(
        self,
        jsonl_path: Path,
        metadata_path: Optional[Path] = None,
    ) -> None:
        """Write recording with metadata file."""
        self.write_jsonl(jsonl_path)

        if metadata_path and self.metadata:
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            with open(metadata_path, "w") as f:
                json.dump(self.metadata.to_dict(), f, indent=2)

    @classmethod
    def read_with_metadata(
        cls,
        jsonl_path: Path,
        metadata_path: Optional[Path] = None,
    ) -> "MarketFeedRecording":
        """Read recording with metadata file."""
        recording = cls.read_jsonl(jsonl_path)

        if metadata_path and metadata_path.exists():
            with open(metadata_path, "r") as f:
                metadata_dict = json.load(f)
                recording.metadata = MarketFeedMetadata.from_dict(metadata_dict)

        return recording

    def iter_records(self) -> Iterator[MarketFeedRecord]:
        """Iterate over records."""
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> MarketFeedRecord:
        return self.records[index]


def validate_recording(recording: MarketFeedRecording) -> Dict[str, Any]:
    """Validate recording quality and return metrics.

    Returns:
        Dictionary with validation metrics and any warnings.
    """
    if len(recording) == 0:
        return {
            "valid": False,
            "error": "Empty recording",
        }

    # Calculate latency statistics
    latencies = [r.latency_ms for r in recording.records]
    latency_median = sorted(latencies)[len(latencies) // 2]
    latency_p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    latency_max = max(latencies)

    # Calculate spread statistics
    spreads = [float(r.spread) for r in recording.records]
    spread_median = sorted(spreads)[len(spreads) // 2]
    spread_min = min(spreads)
    spread_max = max(spreads)

    # Calculate volume statistics
    volumes = [float(r.volume) for r in recording.records]
    volume_mean = sum(volumes) / len(volumes)
    volume_zero_count = sum(1 for v in volumes if v == 0)

    # Check time gaps
    time_gaps = []
    for i in range(1, len(recording)):
        gap_ms = (
            recording[i].exchange_ts - recording[i - 1].exchange_ts
        ).total_seconds() * 1000
        time_gaps.append(gap_ms)

    max_gap_ms = max(time_gaps) if time_gaps else 0
    median_gap_ms = sorted(time_gaps)[len(time_gaps) // 2] if time_gaps else 0

    warnings = []

    # Check for quality issues
    if latency_p95 > 100:
        warnings.append(f"High P95 latency: {latency_p95:.1f}ms")

    if max_gap_ms > 5000:
        warnings.append(f"Large time gap detected: {max_gap_ms:.1f}ms")

    if volume_zero_count > len(recording) * 0.5:
        warnings.append(
            f"High proportion of zero volume: {volume_zero_count}/{len(recording)}"
        )

    if spread_min <= 0:
        warnings.append(f"Non-positive spread detected: {spread_min}")

    return {
        "valid": True,
        "record_count": len(recording),
        "duration_seconds": (
            recording[-1].exchange_ts - recording[0].exchange_ts
        ).total_seconds(),
        "latency_ms": {
            "median": latency_median,
            "p95": latency_p95,
            "max": latency_max,
        },
        "spread": {
            "median": spread_median,
            "min": spread_min,
            "max": spread_max,
        },
        "volume": {
            "mean": volume_mean,
            "zero_count": volume_zero_count,
        },
        "time_gaps_ms": {
            "median": median_gap_ms,
            "max": max_gap_ms,
        },
        "warnings": warnings,
    }
