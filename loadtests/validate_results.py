# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validate Locust CSV output against throughput and error-rate thresholds."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

MIN_REQUESTS_PER_SECOND = 500.0
MAX_ERROR_RATE = 0.05


def _coerce_float(row: dict[str, str], *keys: str) -> float:
    for key in keys:
        value = row.get(key) or row.get(key.lower())
        if value is not None:
            return float(value)
    raise KeyError(f"Missing keys {keys!r} in row: {row!r}")


def _coerce_int(row: dict[str, str], *keys: str) -> int:
    return int(round(_coerce_float(row, *keys)))


def _find_total_row(rows: list[dict[str, str]]) -> dict[str, str]:
    for row in rows:
        name = row.get("Name") or row.get("name")
        if name and name.strip().lower() == "total":
            return row
    raise RuntimeError("Failed to locate total row in Locust statistics")


def validate(stats_path: Path) -> None:
    rows = list(csv.DictReader(stats_path.read_text(encoding="utf-8").splitlines()))
    if not rows:
        raise RuntimeError("No statistics found in Locust CSV output")
    total_row = _find_total_row(rows)
    total_requests = _coerce_int(total_row, "Requests", "requests")
    total_failures = _coerce_int(total_row, "Failures", "failures")
    requests_per_second = _coerce_float(total_row, "Requests/s", "requests/s")
    error_rate = total_failures / max(total_requests, 1)

    print(
        f"Total requests: {total_requests}, Failures: {total_failures}, "
        f"Requests/s: {requests_per_second:.2f}, Error rate: {error_rate:.4f}"
    )

    if requests_per_second < MIN_REQUESTS_PER_SECOND:
        raise SystemExit(
            f"Throughput below threshold: {requests_per_second:.2f} < {MIN_REQUESTS_PER_SECOND:.2f}"
        )
    if error_rate > MAX_ERROR_RATE:
        raise SystemExit(f"Error rate exceeded: {error_rate:.4f} > {MAX_ERROR_RATE:.4f}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python loadtests/validate_results.py <locust_stats_csv>")
    validate(Path(sys.argv[1]))
