# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Multi-exchange replay data loader with performance metrics collection.

This module provides utilities to load and replay recorded exchange data from
multiple sources, measuring latency, throughput, and slippage for regression testing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

import numpy as np


@dataclass(slots=True, frozen=True)
class ExchangeTick:
    """Single market data tick from exchange recording."""

    exchange_ts: datetime
    ingest_ts: datetime
    symbol: str
    bid: float
    ask: float
    last: float
    volume: float
    exchange: str = "unknown"


@dataclass(slots=True, frozen=True)
class ReplayMetadata:
    """Metadata describing a replay recording."""

    name: str
    exchange: str
    symbol: str
    start_time: datetime
    end_time: datetime
    tick_count: int
    description: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class PerformanceMetrics:
    """Performance measurements collected during replay."""

    latencies_ms: list[float] = field(default_factory=list)
    throughput_tps: float = 0.0
    slippage_bps: list[float] = field(default_factory=list)
    tick_count: int = 0
    duration_s: float = 0.0

    @property
    def latency_median_ms(self) -> float:
        """Median latency in milliseconds."""
        return float(np.median(self.latencies_ms)) if self.latencies_ms else 0.0

    @property
    def latency_p95_ms(self) -> float:
        """95th percentile latency in milliseconds."""
        return float(np.percentile(self.latencies_ms, 95)) if self.latencies_ms else 0.0

    @property
    def latency_p99_ms(self) -> float:
        """99th percentile latency in milliseconds."""
        return float(np.percentile(self.latencies_ms, 99)) if self.latencies_ms else 0.0

    @property
    def latency_max_ms(self) -> float:
        """Maximum latency in milliseconds."""
        return float(max(self.latencies_ms)) if self.latencies_ms else 0.0

    @property
    def slippage_median_bps(self) -> float:
        """Median slippage in basis points."""
        return float(np.median(self.slippage_bps)) if self.slippage_bps else 0.0

    @property
    def slippage_p95_bps(self) -> float:
        """95th percentile slippage in basis points."""
        return float(np.percentile(self.slippage_bps, 95)) if self.slippage_bps else 0.0

    def to_dict(self) -> dict[str, float]:
        """Export metrics as dictionary for serialization."""
        return {
            "tick_count": float(self.tick_count),
            "duration_s": self.duration_s,
            "throughput_tps": self.throughput_tps,
            "latency_median_ms": self.latency_median_ms,
            "latency_p95_ms": self.latency_p95_ms,
            "latency_p99_ms": self.latency_p99_ms,
            "latency_max_ms": self.latency_max_ms,
            "slippage_median_bps": self.slippage_median_bps,
            "slippage_p95_bps": self.slippage_p95_bps,
        }


@dataclass(slots=True, frozen=True)
class PerformanceBudget:
    """Performance budget thresholds for regression detection."""

    latency_median_ms: float = 60.0
    latency_p95_ms: float = 100.0
    latency_max_ms: float = 200.0
    throughput_min_tps: float = 1000.0
    slippage_median_bps: float = 5.0
    slippage_p95_bps: float = 15.0


@dataclass(slots=True, frozen=True)
class RegressionResult:
    """Result of regression check against budget."""

    passed: bool
    violations: tuple[str, ...] = field(default_factory=tuple)
    metrics: PerformanceMetrics | None = None
    budget: PerformanceBudget | None = None


def _parse_timestamp(ts: str) -> datetime:
    """Parse ISO 8601 timestamp with timezone."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_replay_recording(
    path: Path, exchange: str | None = None
) -> tuple[Sequence[ExchangeTick], ReplayMetadata | None]:
    """Load exchange replay recording from JSONL file.

    Args:
        path: Path to JSONL recording file
        exchange: Optional exchange identifier (read from metadata if not provided)

    Returns:
        Tuple of (ticks, metadata)
    """
    if not path.exists():
        raise FileNotFoundError(f"Recording not found: {path}")

    # Try to load metadata from adjacent file
    metadata_path = path.with_suffix(".metadata.json")
    metadata: ReplayMetadata | None = None

    if metadata_path.exists():
        meta_data = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata = ReplayMetadata(
            name=meta_data.get("name", path.stem),
            exchange=meta_data.get("exchange", meta_data.get("venue", exchange or "unknown")),
            symbol=meta_data.get("symbol", ""),
            start_time=_parse_timestamp(meta_data["start_time"]),
            end_time=_parse_timestamp(meta_data["end_time"]),
            tick_count=meta_data.get("tick_count", meta_data.get("record_count", 0)),
            description=meta_data.get("description", ""),
            tags=tuple(meta_data.get("tags", [])),
        )

    # Load ticks from JSONL
    ticks = []
    lines = path.read_text(encoding="utf-8").splitlines()

    for line in lines:
        if not line.strip():
            continue
        record = json.loads(line)
        tick = ExchangeTick(
            exchange_ts=_parse_timestamp(record["exchange_ts"]),
            ingest_ts=_parse_timestamp(record["ingest_ts"]),
            symbol=record.get("symbol", metadata.symbol if metadata else ""),
            bid=float(record["bid"]),
            ask=float(record["ask"]),
            last=float(record["last"]),
            volume=float(record["volume"]),
            exchange=exchange or (metadata.exchange if metadata else "unknown"),
        )
        ticks.append(tick)

    # Create metadata if not loaded from file
    if metadata is None and ticks:
        metadata = ReplayMetadata(
            name=path.stem,
            exchange=exchange or "unknown",
            symbol=ticks[0].symbol,
            start_time=ticks[0].exchange_ts,
            end_time=ticks[-1].exchange_ts,
            tick_count=len(ticks),
        )

    return ticks, metadata


def compute_performance_metrics(ticks: Sequence[ExchangeTick]) -> PerformanceMetrics:
    """Compute performance metrics from replay ticks.

    Args:
        ticks: Sequence of exchange ticks

    Returns:
        Performance metrics including latency, throughput, and slippage
    """
    metrics = PerformanceMetrics()

    if not ticks:
        return metrics

    # Compute latencies
    latencies = [(tick.ingest_ts - tick.exchange_ts).total_seconds() * 1000.0 for tick in ticks]
    metrics.latencies_ms = latencies

    # Compute throughput
    duration = (ticks[-1].exchange_ts - ticks[0].exchange_ts).total_seconds()
    metrics.duration_s = duration
    metrics.tick_count = len(ticks)
    metrics.throughput_tps = len(ticks) / duration if duration > 0 else 0.0

    # Compute slippage (bid-ask spread as proxy)
    slippages = []
    for tick in ticks:
        mid = (tick.bid + tick.ask) / 2.0
        if mid > 0:
            spread_bps = ((tick.ask - tick.bid) / mid) * 10000.0
            slippages.append(spread_bps)
    metrics.slippage_bps = slippages

    return metrics


def check_regression(metrics: PerformanceMetrics, budget: PerformanceBudget) -> RegressionResult:
    """Check if metrics violate performance budget.

    Args:
        metrics: Measured performance metrics
        budget: Performance budget thresholds

    Returns:
        Regression result indicating pass/fail and violations
    """
    violations = []

    if metrics.latency_median_ms > budget.latency_median_ms:
        violations.append(
            f"Latency median {metrics.latency_median_ms:.2f}ms exceeds "
            f"budget {budget.latency_median_ms:.2f}ms"
        )

    if metrics.latency_p95_ms > budget.latency_p95_ms:
        violations.append(
            f"Latency p95 {metrics.latency_p95_ms:.2f}ms exceeds "
            f"budget {budget.latency_p95_ms:.2f}ms"
        )

    if metrics.latency_max_ms > budget.latency_max_ms:
        violations.append(
            f"Latency max {metrics.latency_max_ms:.2f}ms exceeds "
            f"budget {budget.latency_max_ms:.2f}ms"
        )

    if metrics.throughput_tps < budget.throughput_min_tps:
        violations.append(
            f"Throughput {metrics.throughput_tps:.2f} tps below "
            f"budget {budget.throughput_min_tps:.2f} tps"
        )

    if metrics.slippage_median_bps > budget.slippage_median_bps:
        violations.append(
            f"Slippage median {metrics.slippage_median_bps:.2f}bps exceeds "
            f"budget {budget.slippage_median_bps:.2f}bps"
        )

    if metrics.slippage_p95_bps > budget.slippage_p95_bps:
        violations.append(
            f"Slippage p95 {metrics.slippage_p95_bps:.2f}bps exceeds "
            f"budget {budget.slippage_p95_bps:.2f}bps"
        )

    return RegressionResult(
        passed=len(violations) == 0,
        violations=tuple(violations),
        metrics=metrics,
        budget=budget,
    )


def discover_recordings(directory: Path) -> Iterator[Path]:
    """Discover all replay recording files in directory.

    Args:
        directory: Directory to search for recordings

    Yields:
        Paths to JSONL recording files
    """
    if not directory.exists():
        return

    for path in directory.glob("*.jsonl"):
        # Skip metadata files
        if ".metadata" in path.name:
            continue
        yield path


__all__ = [
    "ExchangeTick",
    "ReplayMetadata",
    "PerformanceMetrics",
    "PerformanceBudget",
    "RegressionResult",
    "load_replay_recording",
    "compute_performance_metrics",
    "check_regression",
    "discover_recordings",
]
