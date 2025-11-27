"""Lightweight profiling helpers for TradePulse workflows.

This module provides structured instrumentation that can be reused across
command-line tools and notebooks to capture performance characteristics of
project pipelines.  The helpers intentionally avoid hard runtime dependencies
so they work in constrained environments while still reporting useful metrics
such as wall time, CPU time, and peak memory consumption.
"""

from __future__ import annotations

import json
import math
import time
import tracemalloc
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, MutableMapping, Optional


@dataclass(slots=True)
class ProfileSectionResult:
    """Measurement captured for a profiled section."""

    name: str
    wall_time_s: float
    cpu_time_s: float
    peak_memory_mb: float
    metadata: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "wall_time_s": self.wall_time_s,
            "cpu_time_s": self.cpu_time_s,
            "peak_memory_mb": self.peak_memory_mb,
            "metadata": dict(self.metadata),
        }
        if self.error is not None:
            payload["error"] = self.error
        return payload


@dataclass(slots=True)
class ProfileReport:
    """Aggregated profiling data for a complete run."""

    sections: list[ProfileSectionResult]

    @property
    def total_wall_time_s(self) -> float:
        return math.fsum(section.wall_time_s for section in self.sections)

    @property
    def total_cpu_time_s(self) -> float:
        return math.fsum(section.cpu_time_s for section in self.sections)

    @property
    def peak_memory_mb(self) -> float:
        if not self.sections:
            return 0.0
        return max(section.peak_memory_mb for section in self.sections)

    @property
    def section_names(self) -> list[str]:
        return [section.name for section in self.sections]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sections": [section.to_dict() for section in self.sections],
            "total_wall_time_s": self.total_wall_time_s,
            "total_cpu_time_s": self.total_cpu_time_s,
            "peak_memory_mb": self.peak_memory_mb,
        }

    def summary(self) -> str:
        """Return a human readable summary of the profiling report."""

        if not self.sections:
            return "No profiling data collected."
        lines = [
            "Profiling summary:",
            f"  Total wall time: {self.total_wall_time_s:.3f} s",
            f"  Total CPU time:  {self.total_cpu_time_s:.3f} s",
            f"  Peak memory:     {self.peak_memory_mb:.2f} MiB",
            "  Sections:",
        ]
        for section in self.sections:
            extra = ""
            if section.error:
                extra = f" [error: {section.error}]"
            lines.append(
                "    - {name}: {wall:.3f}s wall, {cpu:.3f}s CPU, {mem:.2f} MiB peak{extra}".format(
                    name=section.name,
                    wall=section.wall_time_s,
                    cpu=section.cpu_time_s,
                    mem=section.peak_memory_mb,
                    extra=extra,
                )
            )
        return "\n".join(lines)


class ProfileCollector:
    """Collect structured measurements for multiple profiling sections."""

    def __init__(self) -> None:
        self._sections: list[ProfileSectionResult] = []

    @contextmanager
    def section(
        self, name: str, metadata: Optional[MutableMapping[str, Any]] = None
    ) -> Iterator[MutableMapping[str, Any]]:
        """Profile the enclosed block and record its metrics.

        Parameters
        ----------
        name:
            Identifier for the profiled section.
        metadata:
            Optional mapping that can be populated inside the block with
            additional structured information about the work being profiled.
        """

        meta: MutableMapping[str, Any]
        if metadata is None:
            meta = {}
        else:
            meta = metadata

        start_wall = time.perf_counter()
        start_cpu = time.process_time()
        tracemalloc.start()
        error: str | None = None
        try:
            yield meta
        except Exception as exc:  # pragma: no cover - propagation is tested indirectly
            error = repr(exc)
            meta.setdefault("error", error)
            raise
        finally:
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            elapsed_wall = time.perf_counter() - start_wall
            elapsed_cpu = time.process_time() - start_cpu
            peak_mb = peak / (1024 * 1024)
            self._sections.append(
                ProfileSectionResult(
                    name=name,
                    wall_time_s=elapsed_wall,
                    cpu_time_s=elapsed_cpu,
                    peak_memory_mb=peak_mb,
                    metadata=dict(meta),
                    error=error,
                )
            )

    def build_report(self) -> ProfileReport:
        return ProfileReport(sections=list(self._sections))

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.build_report().to_dict(), indent=indent)


__all__ = ["ProfileCollector", "ProfileReport", "ProfileSectionResult"]
