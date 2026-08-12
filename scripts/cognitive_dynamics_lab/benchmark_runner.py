#!/usr/bin/env python3
"""Dependency-free benchmark runner for the cognitive dynamics stack."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable, cast

DEFAULT_OUT = "artifacts/cognitive_dynamics_lab_benchmark"
BENCHMARK_VERSION = "benchmark-v0.1"
METHODOLOGY = {
    "profile": "stdlib_microbenchmark",
    "external_reference_methods": ["pyperf", "hyperfine"],
    "warmups": 3,
    "samples": 10,
    "clock": "time.perf_counter",
    "memory_probe": "tracemalloc_peak_bytes",
    "units": ["seconds", "bytes", "artifacts_per_second"],
}

BenchmarkFn = Callable[[], int]
BenchmarkRow = dict[str, str | int | float]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def reference_json_write() -> int:
    payload = {
        "metric_scale": "0..1",
        "normalized_metrics": {"a": 0.25, "b": 0.75},
        "objective_score": 0.5,
    }
    with tempfile.TemporaryDirectory() as tmp:
        write_json(Path(tmp) / "reference.json", payload)
    return 1


def reference_csv_write() -> int:
    rows = [["metric", "value"], ["a", "0.25"], ["b", "0.75"]]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "reference.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(rows)
    return 1


def simulation_write() -> int:
    root = repo_root()
    module = load_module(root / "scripts/cognitive_dynamics_lab/simulation_runner.py", "cdl_sim")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        module.write_outputs(out)
        return 2 + len(module.CASES)


def parameter_review_write() -> int:
    root = repo_root()
    module = load_module(
        root / "scripts/cognitive_dynamics_lab/parameter_review_runner.py", "cdl_param"
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        rows = module.build_rows(module.PARAMS)
        module.write_outputs(out, rows)
        return 3


def collect_sample(fn: BenchmarkFn) -> tuple[float, int, int]:
    tracemalloc.start()
    start = time.perf_counter()
    artifacts = fn()
    elapsed = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return elapsed, peak, artifacts


def run_benchmark(name: str, fn: BenchmarkFn, samples: int, warmups: int) -> BenchmarkRow:
    for _ in range(warmups):
        fn()
    elapsed_values: list[float] = []
    memory_values: list[int] = []
    artifacts_values: list[int] = []
    for _ in range(samples):
        elapsed, peak, artifacts = collect_sample(fn)
        elapsed_values.append(elapsed)
        memory_values.append(peak)
        artifacts_values.append(artifacts)
    median_seconds = statistics.median(elapsed_values)
    mean_seconds = statistics.fmean(elapsed_values)
    stdev_seconds = statistics.pstdev(elapsed_values)
    artifacts = max(1, int(statistics.median(artifacts_values)))
    return {
        "name": name,
        "samples": samples,
        "warmups": warmups,
        "artifacts": artifacts,
        "median_seconds": round(median_seconds, 9),
        "mean_seconds": round(mean_seconds, 9),
        "stdev_seconds": round(stdev_seconds, 9),
        "min_seconds": round(min(elapsed_values), 9),
        "max_seconds": round(max(elapsed_values), 9),
        "peak_bytes_median": int(statistics.median(memory_values)),
        "artifacts_per_second": round(artifacts / max(median_seconds, 1e-12), 3),
    }


def add_relative_scores(rows: list[BenchmarkRow]) -> list[BenchmarkRow]:
    json_baseline = float(
        next(row["median_seconds"] for row in rows if row["name"] == "reference_json_write")
    )
    for row in rows:
        median = float(row["median_seconds"])
        row["relative_to_json_baseline"] = round(median / max(json_baseline, 1e-12), 6)
    return rows


def build_summary(rows: list[BenchmarkRow]) -> dict[str, object]:
    slowest = max(rows, key=lambda row: float(row["median_seconds"]))
    fastest = min(rows, key=lambda row: float(row["median_seconds"]))
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "methodology": METHODOLOGY,
        "claim_tier": "local_microbenchmark_only",
        "external_methodology_references": {
            "pyperf": "calibration, repeated runs, statistics, JSON-oriented benchmark analysis",
            "hyperfine": "warmup runs, multiple samples, relative comparison, exportable results",
        },
        "benchmarks": rows,
        "fastest": fastest["name"],
        "slowest": slowest["name"],
        "total_benchmarks": len(rows),
        "pass_condition": "all benchmarks executed and produced bounded timing rows",
        "status": "BENCHMARK_BUILT",
    }


def write_csv_rows(path: Path, rows: list[BenchmarkRow]) -> None:
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, summary: dict[str, object]) -> None:
    rows = summary["benchmarks"]
    if not isinstance(rows, list):
        raise RuntimeError("invalid benchmark rows")
    lines = [
        "# Cognitive Dynamics Benchmark Report",
        "",
        f"Status: {summary['status']}",
        f"Claim tier: {summary['claim_tier']}",
        "",
        "| benchmark | median seconds | peak bytes | artifacts/sec | relative to json |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {name} | {median_seconds} | {peak_bytes_median} | {artifacts_per_second} | {relative_to_json_baseline} |".format(
                **row
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_suite(samples: int, warmups: int) -> dict[str, object]:
    benchmarks: list[tuple[str, BenchmarkFn]] = [
        ("reference_json_write", reference_json_write),
        ("reference_csv_write", reference_csv_write),
        ("simulation_write", simulation_write),
        ("parameter_review_write", parameter_review_write),
    ]
    rows = [run_benchmark(name, fn, samples=samples, warmups=warmups) for name, fn in benchmarks]
    return build_summary(add_relative_scores(rows))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--samples", type=int, default=int(METHODOLOGY["samples"]))
    parser.add_argument("--warmups", type=int, default=int(METHODOLOGY["warmups"]))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = run_suite(samples=args.samples, warmups=args.warmups)
    rows = summary["benchmarks"]
    if not isinstance(rows, list):
        raise RuntimeError("invalid benchmark rows")
    benchmark_rows = cast("list[BenchmarkRow]", rows)
    write_json(out / "benchmark_summary.json", summary)
    write_csv_rows(out / "benchmark_table.csv", benchmark_rows)
    write_markdown(out / "benchmark_report.md", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
