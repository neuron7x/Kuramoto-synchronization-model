# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Synthetic benchmark harness for time-series backends."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from time import perf_counter
from typing import Callable, Iterable, Mapping, Sequence

from .config import BenchmarkWorkload, TimeSeriesSchema

__all__ = ["BenchmarkRunner"]


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * percentile / 100.0
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    weight = index - lower
    return values[lower] * (1 - weight) + values[upper] * weight


@dataclass
class BenchmarkMetrics:
    ingest_p50_ms: float
    ingest_p99_ms: float
    query_p50_ms: float
    query_p95_ms: float
    rows_ingested: int
    ingest_throughput_rows_s: float
    query_throughput_qps: float


class BenchmarkRunner:
    """Runs deterministic ingestion/query workloads for regression testing."""

    def __init__(
        self, schema: TimeSeriesSchema, *, clock: Callable[[], float] | None = None
    ) -> None:
        self._schema = schema
        self._clock = clock or perf_counter

    def run(
        self,
        *,
        workload: BenchmarkWorkload,
        ingestion_callable: Callable[[Sequence[Mapping[str, object]]], None],
        query_callable: Callable[[Mapping[str, object]], None],
    ) -> BenchmarkMetrics:
        ingest_latencies: list[float] = []
        query_latencies: list[float] = []
        total_rows = 0

        for batch_size in workload.ingest_batches:
            batch = list(self._generate_batch(batch_size, offset=total_rows))
            start = self._clock()
            ingestion_callable(batch)
            elapsed_ms = (self._clock() - start) * 1_000
            ingest_latencies.append(elapsed_ms)
            total_rows += batch_size

        for _ in range(workload.warmup_iterations):
            query_callable(self._query_parameters(total_rows))

        for _ in range(workload.query_iterations):
            params = self._query_parameters(total_rows)
            start = self._clock()
            query_callable(params)
            elapsed_ms = (self._clock() - start) * 1_000
            query_latencies.append(elapsed_ms)

        ingest_sorted = sorted(ingest_latencies)
        query_sorted = sorted(query_latencies)
        total_ingest_ms = sum(ingest_sorted)
        total_query_ms = sum(query_sorted)
        ingest_throughput = (total_rows / total_ingest_ms) * 1_000 if total_ingest_ms > 0 else 0.0
        query_throughput = (
            (workload.query_iterations / total_query_ms if workload.query_iterations > 0 else 0.0)
            * 1_000
            if total_query_ms > 0
            else 0.0
        )
        return BenchmarkMetrics(
            ingest_p50_ms=median(ingest_sorted),
            ingest_p99_ms=_percentile(ingest_sorted, 99.0),
            query_p50_ms=median(query_sorted),
            query_p95_ms=_percentile(query_sorted, 95.0),
            rows_ingested=total_rows,
            ingest_throughput_rows_s=ingest_throughput,
            query_throughput_qps=query_throughput,
        )

    def _generate_batch(self, batch_size: int, *, offset: int) -> Iterable[Mapping[str, object]]:
        timestamp_column = self._schema.timestamp_column
        dimensions = [dimension.name for dimension in self._schema.dimensions]
        measures = [measure.name for measure in self._schema.measures]
        metadata = [column.name for column in self._schema.metadata]
        for idx in range(batch_size):
            base = {timestamp_column: f"2024-01-01T00:00:{(offset + idx) % 60:02d}Z"}
            for dimension in dimensions:
                base[dimension] = f"value_{dimension}_{(offset + idx) % 5}"
            for measure in measures:
                base[measure] = float(offset + idx)
            for column in metadata:
                base[column] = f"meta_{column}"
            yield base

    def _query_parameters(self, total_rows: int) -> Mapping[str, object]:
        return {
            "start_ts": "2024-01-01T00:00:00Z",
            "end_ts": "2024-01-02T00:00:00Z",
            "symbol": "value_symbol_1" if total_rows else "value_symbol_0",
        }
