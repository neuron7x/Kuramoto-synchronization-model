"""Memory-efficient telemetry manager for thermodynamics system.

This module provides memory-optimized storage and management of telemetry data,
with automatic compression, archival, and efficient querying capabilities.
"""

from __future__ import annotations

import gzip
import json
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

import numpy as np


@dataclass
class TelemetryWindow:
    """Fixed-size window of telemetry data with compression."""

    max_size: int = 1000
    data: Deque[Dict[str, Any]] = field(default_factory=deque)
    compressed_archives: List[bytes] = field(default_factory=list)

    def append(self, record: Dict[str, Any]) -> None:
        """Add a record to the window."""
        self.data.append(record)

        # Auto-compress when window is full
        if len(self.data) >= self.max_size:
            self._compress_and_archive()

    def _compress_and_archive(self) -> None:
        """Compress older data and move to archives."""
        if len(self.data) < self.max_size // 2:
            return

        # Take half the data to compress
        to_compress = []
        for _ in range(self.max_size // 2):
            if self.data:
                to_compress.append(self.data.popleft())

        if to_compress:
            # Compress using gzip
            json_data = json.dumps(to_compress)
            compressed = gzip.compress(json_data.encode("utf-8"))
            self.compressed_archives.append(compressed)

    def get_recent(self, n: int = 100) -> List[Dict[str, Any]]:
        """Get the n most recent records."""
        return list(self.data)[-n:]

    def get_all_uncompressed(self) -> List[Dict[str, Any]]:
        """Get all uncompressed records."""
        return list(self.data)

    def get_all_records(self) -> List[Dict[str, Any]]:
        """Return both uncompressed and archived telemetry in chronological order."""

        records: List[Dict[str, Any]] = []
        for archive in self.compressed_archives:
            try:
                json_data = gzip.decompress(archive).decode("utf-8")
                records.extend(json.loads(json_data))
            except (OSError, EOFError, json.JSONDecodeError):
                # Skip corrupted archives instead of failing the entire read
                continue

        records.extend(self.get_all_uncompressed())
        return records

    def decompress_archive(self, index: int) -> List[Dict[str, Any]]:
        """Decompress a specific archive."""
        if 0 <= index < len(self.compressed_archives):
            compressed = self.compressed_archives[index]
            json_data = gzip.decompress(compressed).decode("utf-8")
            return json.loads(json_data)
        return []

    def get_memory_usage(self) -> Dict[str, int]:
        """Get memory usage statistics in bytes."""
        uncompressed_size = sum(
            len(json.dumps(record).encode("utf-8")) for record in self.data
        )
        compressed_size = sum(len(archive) for archive in self.compressed_archives)

        return {
            "uncompressed_bytes": uncompressed_size,
            "compressed_bytes": compressed_size,
            "uncompressed_records": len(self.data),
            "compressed_archives": len(self.compressed_archives),
            "compression_ratio": (
                uncompressed_size / compressed_size if compressed_size > 0 else 0.0
            ),
        }

    def clear(self) -> None:
        """Clear all data."""
        self.data.clear()
        self.compressed_archives.clear()


class OptimizedTelemetryManager:
    """Memory-optimized telemetry manager with efficient storage and querying.

    Features:
    - Automatic compression of old data
    - Efficient memory usage with deque
    - Fast queries for recent data
    - Aggregated statistics computation
    - Export to compressed files
    """

    def __init__(
        self,
        *,
        window_size: int = 1000,
        max_archives: int = 10,
        export_dir: Optional[Path] = None,
    ) -> None:
        """Initialize the telemetry manager.

        Args:
            window_size: Maximum number of uncompressed records
            max_archives: Maximum number of compressed archives to keep
            export_dir: Directory for exporting telemetry data
        """
        self.window = TelemetryWindow(max_size=window_size)
        self.max_archives = max_archives
        self.export_dir = export_dir or Path(".ci_artifacts")

        # Statistics cache
        self._stats_cache: Optional[Dict[str, Any]] = None
        self._stats_cache_time: float = 0.0
        self._stats_cache_ttl: float = 1.0  # 1 second TTL

    def record(self, telemetry: Dict[str, Any]) -> None:
        """Record a telemetry event."""
        # Ensure timestamp
        if "timestamp" not in telemetry:
            telemetry["timestamp"] = time.time()

        self.window.append(telemetry)

        # Invalidate stats cache
        self._stats_cache = None

        # Limit number of archives
        if len(self.window.compressed_archives) > self.max_archives:
            # Export oldest archives to disk
            self._export_old_archives()

    def _export_old_archives(self) -> None:
        """Export old archives to disk to free memory."""
        if len(self.window.compressed_archives) <= self.max_archives:
            return

        try:
            self.export_dir.mkdir(parents=True, exist_ok=True)

            while len(self.window.compressed_archives) > self.max_archives:
                archive = self.window.compressed_archives.pop(0)
                timestamp = int(time.time() * 1000)
                filename = self.export_dir / f"thermo_telemetry_{timestamp}.json.gz"

                with filename.open("wb") as f:
                    f.write(archive)
        except (OSError, IOError):
            # If export fails, just keep in memory
            pass

    def get_recent(self, n: int = 100) -> List[Dict[str, Any]]:
        """Get the n most recent telemetry records."""
        return self.window.get_recent(n)

    def get_time_range(
        self,
        start_time: float,
        end_time: float,
    ) -> List[Dict[str, Any]]:
        """Get telemetry records within a time range."""
        records = []

        for record in self.window.get_all_records():
            ts = record.get("timestamp", 0.0)
            if start_time <= ts <= end_time:
                records.append(record)

        return records

    def compute_statistics(self, force: bool = False) -> Dict[str, Any]:
        """Compute aggregated statistics over telemetry data.

        Args:
            force: Force recomputation even if cache is valid

        Returns:
            Dictionary of statistics
        """
        # Check cache
        if not force and self._stats_cache is not None:
            if time.time() - self._stats_cache_time < self._stats_cache_ttl:
                return self._stats_cache

        records = self.window.get_all_records()

        if not records:
            return {
                "count": 0,
                "avg_F": 0.0,
                "max_F": 0.0,
                "min_F": 0.0,
                "avg_dF_dt": 0.0,
                "circuit_breaker_activations": 0,
                "topology_changes": 0,
            }

        # Extract metrics
        F_values = [r.get("F", 0.0) for r in records]
        dF_dt_values = [r.get("dF_dt", 0.0) for r in records]
        circuit_breaker_states = [
            r.get("circuit_breaker_active", False) for r in records
        ]
        topology_changes = sum(len(r.get("topology_changes", [])) for r in records)

        # Compute statistics using NumPy for efficiency
        F_array = np.array(F_values)
        dF_dt_array = np.array(dF_dt_values)

        stats = {
            "count": len(records),
            "avg_F": float(np.mean(F_array)),
            "std_F": float(np.std(F_array)),
            "max_F": float(np.max(F_array)),
            "min_F": float(np.min(F_array)),
            "median_F": float(np.median(F_array)),
            "avg_dF_dt": float(np.mean(dF_dt_array)),
            "std_dF_dt": float(np.std(dF_dt_array)),
            "circuit_breaker_activations": sum(
                1 for active in circuit_breaker_states if active
            ),
            "topology_changes": topology_changes,
            "time_span": (
                records[-1].get("timestamp", 0.0) - records[0].get("timestamp", 0.0)
                if len(records) > 1
                else 0.0
            ),
        }

        # Cache the result
        self._stats_cache = stats
        self._stats_cache_time = time.time()

        return stats

    def get_crisis_periods(self, threshold: float = 0.1) -> List[Dict[str, Any]]:
        """Identify periods where the system was in crisis mode.

        Args:
            threshold: F deviation threshold for crisis detection

        Returns:
            List of crisis periods with start/end times and severity
        """
        records = self.window.get_all_uncompressed()
        if not records:
            return []

        crisis_periods = []
        in_crisis = False
        crisis_start = None
        max_F_in_crisis = 0.0

        for record in records:
            crisis_mode = record.get("crisis_mode", "NORMAL")
            F_value = record.get("F", 0.0)
            timestamp = record.get("timestamp", 0.0)

            is_crisis = crisis_mode not in ["NORMAL", "normal"]

            if is_crisis and not in_crisis:
                # Start of crisis
                in_crisis = True
                crisis_start = timestamp
                max_F_in_crisis = F_value
            elif is_crisis and in_crisis:
                # Continue crisis
                max_F_in_crisis = max(max_F_in_crisis, F_value)
            elif not is_crisis and in_crisis:
                # End of crisis
                crisis_periods.append(
                    {
                        "start_time": crisis_start,
                        "end_time": timestamp,
                        "duration": timestamp - crisis_start if crisis_start else 0.0,
                        "max_F": max_F_in_crisis,
                        "severity": "critical" if max_F_in_crisis > 1.3 else "elevated",
                    }
                )
                in_crisis = False
                crisis_start = None
                max_F_in_crisis = 0.0

        # Handle ongoing crisis
        if in_crisis and crisis_start is not None:
            crisis_periods.append(
                {
                    "start_time": crisis_start,
                    "end_time": records[-1].get("timestamp", 0.0),
                    "duration": records[-1].get("timestamp", 0.0) - crisis_start,
                    "max_F": max_F_in_crisis,
                    "severity": "critical" if max_F_in_crisis > 1.3 else "elevated",
                    "ongoing": True,
                }
            )

        return crisis_periods

    def export_to_json(self, filepath: Optional[Path] = None) -> Path:
        """Export telemetry to a JSON file.

        Args:
            filepath: Output file path (default: auto-generated)

        Returns:
            Path to the exported file
        """
        if filepath is None:
            self.export_dir.mkdir(parents=True, exist_ok=True)
            timestamp = int(time.time() * 1000)
            filepath = self.export_dir / f"thermo_telemetry_{timestamp}.json"

        records = self.window.get_all_uncompressed()

        with filepath.open("w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

        return filepath

    def export_to_compressed_json(self, filepath: Optional[Path] = None) -> Path:
        """Export telemetry to a compressed JSON file.

        Args:
            filepath: Output file path (default: auto-generated)

        Returns:
            Path to the exported file
        """
        if filepath is None:
            self.export_dir.mkdir(parents=True, exist_ok=True)
            timestamp = int(time.time() * 1000)
            filepath = self.export_dir / f"thermo_telemetry_{timestamp}.json.gz"

        records = self.window.get_all_uncompressed()
        json_data = json.dumps(records, indent=2)
        compressed = gzip.compress(json_data.encode("utf-8"))

        with filepath.open("wb") as f:
            f.write(compressed)

        return filepath

    def get_memory_usage(self) -> Dict[str, Any]:
        """Get memory usage statistics."""
        return self.window.get_memory_usage()

    def clear(self) -> None:
        """Clear all telemetry data."""
        self.window.clear()
        self._stats_cache = None
