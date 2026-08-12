# Cognitive Dynamics Benchmark Profile

Status: BENCHMARK_PROFILE_ADDED

Purpose: compare the cognitive dynamics replay stack against local reference artifact writers and expose timing, memory, throughput, and relative ratios.

External benchmark methodology references:
- pyperf: Python benchmark methodology with calibration, repeated runs, statistics, instability checks, metadata, and JSON-oriented results.
- hyperfine: command benchmark methodology with warmups, repeated samples, relative comparisons, outlier awareness, and exportable JSON, CSV, and Markdown results.

Local benchmark command:

python scripts/cognitive_dynamics_lab/benchmark_runner.py --out artifacts/cognitive_dynamics_lab_benchmark

Benchmarks:
- reference_json_write: baseline JSON artifact write.
- reference_csv_write: baseline CSV artifact write.
- simulation_write: active simulation runner artifact write.
- parameter_review_write: active parameter review artifact write.

Outputs:
- benchmark_summary.json
- benchmark_table.csv
- benchmark_report.md

Measured fields:
- median_seconds
- mean_seconds
- stdev_seconds
- min_seconds
- max_seconds
- peak_bytes_median
- artifacts_per_second
- relative_to_json_baseline

Claim boundary:
- Local microbenchmark only.
- Not a system-wide production throughput claim.
- Not a hardware-independent benchmark.
- Results are comparable only inside the same runtime environment.

Pass condition:
- all benchmark rows are produced;
- all runners execute without import or output failure;
- benchmark_summary.json and benchmark_table.csv exist;
- relative_to_json_baseline is present for all rows.
