---
owner: performance@geosync
review_cadence: quarterly
last_reviewed: 2025-12-28
links:
  - docs/metrics_discipline.md
  - docs/risk_ml_observability.md
---

# Performance Optimization Guide

This guide covers performance optimization techniques and best practices for GeoSync, including memory management, execution profiling, and GPU acceleration.

## Table of Contents

- [Overview](#overview)
- [Memory Optimization](#memory-optimization)
- [Execution Profiling](#execution-profiling)
- [Chunked Processing](#chunked-processing)
- [GPU Acceleration](#gpu-acceleration)
- [Prometheus Metrics](#prometheus-metrics)
- [Best Practices](#best-practices)
- [Performance Examples](#performance-examples)
- [Troubleshooting](#troubleshooting)

## Overview

GeoSync provides several performance optimization features for resource-intensive computations:

1. **Float32 precision**: Reduce memory usage by 50% with minimal accuracy loss
2. **Chunked processing**: Handle large datasets efficiently by processing in batches
3. **Structured logging**: Track execution time for performance bottlenecks
4. **Prometheus metrics**: Monitor system performance in production
5. **GPU acceleration**: Leverage CuPy for GPU-accelerated computations

## Memory Optimization

### Float32 Precision

All main indicator functions support `use_float32` parameter to reduce memory consumption:

```python
import numpy as np
from core.indicators.entropy import entropy, EntropyFeature
from core.indicators.hurst import hurst_exponent, HurstFeature
from core.indicators.ricci import mean_ricci, MeanRicciFeature
from core.indicators.kuramoto import compute_phase, KuramotoOrderFeature
from core.data.preprocess import scale_series, normalize_df

# Example with large dataset (1M points)
large_data = np.random.randn(1_000_000)

# Standard float64 (8 bytes per element = 8MB)
H_64 = entropy(large_data, bins=50)

# Memory-efficient float32 (4 bytes per element = 4MB)
H_32 = entropy(large_data, bins=50, use_float32=True)
```

### When to Use Float32

**Use float32 when:**
- Processing very large datasets (>100K points)
- Memory is constrained
- Small accuracy differences are acceptable
- Running multiple parallel computations

**Avoid float32 when:**
- High numerical precision is critical
- Dataset is small (<10K points)
- Accumulating many operations (numerical stability)

### DataFrame Memory Optimization

```python
import pandas as pd

# Load large DataFrame
df = pd.read_csv('large_dataset.csv')

# Optimize numeric columns to float32
df_optimized = normalize_df(df, use_float32=True)

# Check memory usage
print(f"Original: {df.memory_usage(deep=True).sum() / 1e6:.2f} MB")
print(f"Optimized: {df_optimized.memory_usage(deep=True).sum() / 1e6:.2f} MB")
```

### Polars Lazy Pipelines

Use the optional Polars backend for zero-copy ingestion pipelines when you need to
chain multiple stages without materialising intermediate frames:

```python
pip install "polars>=0.20" pyarrow
```

```python
from pathlib import Path
import polars as pl

from core.data.polars_pipeline import (
    apply_vectorized,
    cache_lazy_frame,
    collect_streaming,
    enable_global_string_cache,
    enforce_schema,
    lazy_column_zero_copy,
    profile_lazy_frame,
    scan_lazy,
    summarize_parquet_dataset,
    use_arrow_memory_pool,
)

# Ensure categorical joins reuse string buffers across stages
enable_global_string_cache(True)

lazy_scan = scan_lazy(
    Path("data/trades"),
    columns=["ts", "price", "volume"],
    partition_filters={"symbol": ["AAPL", "MSFT"]},
    row_count_name="row_id",
    cache=True,
)

# Apply feature engineering lazily; nothing is evaluated yet
lazy_features = apply_vectorized(
    lazy_scan,
    expressions={
        "returns": lambda pl: pl.col("price").pct_change(),
        "vol_ma": lambda pl: pl.col("volume").rolling_mean(window_size=10),
    },
)

# Ensure downstream consumers see stable dtypes
lazy_features = enforce_schema(
    lazy_features,
    {
        "returns": float,
        "vol_ma": float,
    },
)

# Cache shared intermediates for reuse by multiple sinks
lazy_features = cache_lazy_frame(lazy_features)

# Route allocations through a dedicated Arrow memory pool to avoid fragmentation
import pyarrow as pa

with use_arrow_memory_pool(pa.proxy_memory_pool(pa.default_memory_pool())):
    df = collect_streaming(lazy_features, streaming=True)

# Extract numpy views with zero-copy hand-off between stages
returns = lazy_column_zero_copy(lazy_features, "returns")

# Inspect plans and parquet metadata for hot-path diagnostics
profile = profile_lazy_frame(lazy_features)
parquet_summaries = summarize_parquet_dataset(Path("data/trades"))
```

**Key benefits:**

- `scan_lazy` automatically detects parquet layouts, applies column/predicate
  pushdown, and prunes partitions before hitting the filesystem.
- `apply_vectorized` keeps transformations lazy and SIMD-friendly.
- `cache_lazy_frame` avoids recomputing shared branches across multiple sinks.
- `collect_streaming(..., streaming=True)` keeps peak memory flat on wide datasets.
- `lazy_column_zero_copy` hands Arrow buffers to NumPy without copying so downstream
  indicator kernels run on the same memory.
- `profile_lazy_frame` and `summarize_parquet_dataset` surface hot-path plans,
  compression codecs, and file sizes for rapid diagnostics.
- The optional `use_arrow_memory_pool` context keeps Arrow allocations inside a
  shared pool, reducing fragmentation when many tasks run concurrently.

## Execution Profiling

### Structured Logging

All optimized functions include structured logging for execution time tracking:

```python
from core.utils.logging import configure_logging, get_logger

# Configure JSON logging
configure_logging(level="INFO", use_json=True)

# Get logger for your module
logger = get_logger(__name__)

# Execute function - automatically logs execution time
from core.indicators.entropy import entropy
result = entropy(data, bins=30)

# Log output includes:
# - timestamp
# - operation name
# - duration_seconds
# - status (success/failure)
# - context parameters (data_size, bins, use_float32, etc.)
```

### Operation Context Manager

Track custom operations:

```python
from core.utils.logging import get_logger

logger = get_logger(__name__)

with logger.operation("custom_computation", data_size=len(prices)) as op:
    # Your computation here
    result = compute_complex_indicator(prices)
    op["result_value"] = result
    op["iterations"] = 100
```

### Sampling Profilers

GeoSync includes `scalene` and `py-spy` in the development dependencies so
you can capture CPU and memory profiles without modifying source code.

*Scalene*

```bash
scalene --cpu-only --outfile reports/scalene.html src/your_entrypoint.py --arg=value
```

This produces an interactive HTML report under `reports/scalene.html` that
pinpoints hotspots at the function and line level.

*py-spy*

```bash
py-spy record -o reports/py-spy.svg -- python src/your_entrypoint.py --arg=value
```

`py-spy` generates a flamegraph that visualises stack traces aggregated over
time, which is ideal for spotting intermittent slow paths.

### Microbenchmarks

Critical pipeline stages have dedicated microbenchmarks in `bench/` to track
regressions:

```bash
python bench/bench_pipeline.py
# normalize_df                   best=  7.42 ms  avg=  7.95 ms
# ricci_feature                  best= 11.31 ms  avg= 11.88 ms
# strategy_simulation            best= 18.04 ms  avg= 18.65 ms
# matching_engine_submit         best=  1.92 ms  avg=  2.10 ms
```

Run the script before and after optimisations to measure impact or to populate
baseline data in CI.

### Cold vs Hot Indicator Profiles

Use `bench/bench_indicators.py` to compare cold-start costs (allocations, cache
misses) against hot-loop performance of heavy indicators:

```bash
python bench/bench_indicators.py --repeat 10 --warmup 5
# entropy                 cold_best= 14.11 ms  hot_best=  8.63 ms  hot/ cold= 0.61
# hurst_exponent          cold_best= 28.54 ms  hot_best= 16.02 ms  hot/ cold= 0.56
# compute_phase           cold_best= 19.97 ms  hot_best= 11.33 ms  hot/ cold= 0.57
# mean_ricci              cold_best= 42.18 ms  hot_best= 24.90 ms  hot/ cold= 0.59
```

**Workflow recommendations:**

- Run the indicator microbenchmarks locally before sending a PR when touching
  indicator kernels.
- Export the CSV-friendly output to `reports/performance/indicators_<commit>.txt`
  so CI jobs can diff against the latest baseline.
- Track the ratio (`hot/cold`) to confirm cache-aware optimisations are working
  and to ensure cold-start regressions stay within budget.

**CI regression budget:** wire the benchmark into CI (e.g. via `pytest-benchmark`)
and fail the pipeline if median cold timings degrade by more than 10% or if hot
timings exceed 5% of the stored baseline. Persist baseline stats under
`tests/performance/baselines/` and update them intentionally when optimisations
land.

### Regression Automation with `asv` and `pytest-benchmark`

1. **Author benchmark suites** – Keep deterministic harnesses in `bench/` and
   mirror the entry points inside `tests/performance/` so that the same kernels
   can be invoked under `pytest --benchmark-only`.
2. **Capture baselines** – Run `pytest tests/performance --benchmark-save=baseline`
   on a clean workstation. Store the resulting JSON under
   `tests/performance/baselines/` and commit alongside the change.
3. **Integrate ASV** – Initialise an Airspeed Velocity project with
   `asv quickstart` and point `asv.conf.json` at the `bench/` scripts. Pin the
   `project_url` to the GeoSync repository and enable the `virtualenv`
   builder so CI can reproduce runs on tagged commits.
4. **Gate regressions** – Configure CI to execute `pytest --benchmark-compare=baseline`
   and `asv run --quick` on each PR, failing if median runtime drifts by more
   than ±10%. Update the tolerance based on the budgets agreed in
   [`docs/quality_gates.md`](quality_gates.md).
5. **Publish flamegraphs** – `.github/workflows/tests.yml` already archives
   profiling traces from `pytest-profiling`. Enhance the workflow with
   `py-spy record --flame` so each regression run includes a flamegraph for
   automatic upload to the build artifacts.

## Chunked Processing

### Entropy with Chunking

Process large arrays by splitting into manageable chunks:

```python
from core.indicators.entropy import entropy

# Very large dataset (10M points)
huge_data = np.random.randn(10_000_000)

# Process in chunks of 100K points
# Computes weighted average entropy across chunks
H = entropy(huge_data, bins=50, chunk_size=100_000, use_float32=True)
```

**Benefits:**
- Reduces peak memory usage
- Better cache locality
- Prevents memory overflow on large datasets

**Chunk size recommendations:**
- Small datasets (<1M): No chunking needed (chunk_size=None)
- Medium datasets (1M-10M): chunk_size=100_000 to 500_000
- Large datasets (>10M): chunk_size=500_000 to 1_000_000

### Ricci Curvature with Chunking

Process graph edges in batches:

```python
from core.indicators.ricci import build_price_graph, mean_ricci

# Build graph from prices
prices = np.random.randn(10_000) + 100
G = build_price_graph(prices, delta=0.005)

# Process edges in chunks (important for large graphs)
ricci = mean_ricci(G, chunk_size=1000, use_float32=True)
```

**Graph size guidelines:**
- Small graphs (<1000 edges): No chunking (chunk_size=None)
- Medium graphs (1K-10K edges): chunk_size=500 to 2000
- Large graphs (>10K edges): chunk_size=2000 to 5000

## GPU Acceleration

### CuPy Setup

Install CuPy for GPU acceleration:

```bash
# For CUDA 11.x
pip install cupy-cuda11x

# For CUDA 12.x
pip install cupy-cuda12x
```

### GPU-Accelerated Phase Computation

```python
from core.indicators.kuramoto import compute_phase_gpu
import numpy as np

# Large time series
data = np.random.randn(1_000_000)

# GPU computation (if CuPy available, otherwise falls back to CPU)
phases_gpu = compute_phase_gpu(data)
```

**GPU acceleration benefits:**
- 5-50x speedup for large arrays (>100K points)
- Adaptive backend selection automatically routes workloads to GPU when the
  dataset is large enough and device memory is sufficient, otherwise staying on
  CPU to avoid unnecessary transfers.
- Automatic fallback to CPU if GPU unavailable
- Built-in error handling and logging

### Checking GPU Availability

```python
try:
    import cupy as cp
    print(f"CuPy available: {cp.cuda.is_available()}")
    print(f"Device: {cp.cuda.Device().compute_capability}")
except ImportError:
    print("CuPy not installed - using CPU")
```

### Numba CUDA Kernels for Heavy Indicators

CuPy interops with `numba.cuda` so you can JIT bespoke kernels for the
computation-heavy portions of an indicator while still orchestrating from Python:

```python
import math

import cupy as cp
from numba import cuda


@cuda.jit
def rolling_zscore(values, window, out):
    i = cuda.grid(1)
    if i >= values.size or i < window:
        return
    mean = 0.0
    var = 0.0
    for j in range(window):
        x = values[i - j]
        mean += x
        var += x * x
    mean /= window
    std = math.sqrt(max(var / window - mean * mean, 1e-9))
    out[i] = (values[i] - mean) / std


values = cp.asarray(prices, dtype=cp.float32)
out = cp.empty_like(values)

threads = 128
blocks = (values.size + threads - 1) // threads
rolling_zscore[blocks, threads](values, 64, out)
```

### Track Host ↔ Device Copies

Always validate that expensive buffers stay on the GPU. For CuPy kernels use the
memory pool metrics:

```python
pool = cp.cuda.MemoryPool()
with cp.cuda.using_allocator(pool.malloc):
    values = cp.asarray(prices, dtype=cp.float32)
    result = cp.fft.fft(values)
    pool_used = pool.used_bytes()
    ptr_meta = cp.cuda.runtime.pointerGetAttributes(int(result.data.ptr))
    assert ptr_meta["memoryType"] == cp.cuda.runtime.cudaMemoryTypeDevice
```

When you must share data with NumPy/pandas, prefer zero-copy Arrow buffers from
`lazy_column_zero_copy` and then pin the host memory before transferring:

```python
import cupy as cp
from numba import cuda

host_buffer = lazy_column_zero_copy(lazy_features, "returns")
pinned = cuda.pinned_array_like(host_buffer)
pinned[:] = host_buffer  # fast copy into pinned memory
device = cp.asarray(pinned)

# Work on GPU without further host transfers
device_result = cp.log1p(device)
```

CuPy also exposes the default memory pool via `cp.cuda.set_allocator`. Configure
it at startup so repeated indicator transforms reuse allocations instead of
thrashing the allocator.

## Prometheus Metrics

### Enabling Metrics Collection

```python
from core.utils.metrics import get_metrics_collector, start_metrics_server

# Get global metrics collector
metrics = get_metrics_collector()

# Start metrics HTTP server (optional, for production)
start_metrics_server(port=8000)
```

### Automatic Feature Metrics

All feature classes automatically record metrics:

```python
from core.indicators.entropy import EntropyFeature

# Create feature with metrics enabled
feature = EntropyFeature(bins=30, use_float32=True)

# Transform automatically records:
# - geosync_feature_transform_duration_seconds
# - geosync_feature_transform_total
# - geosync_feature_value
result = feature.transform(prices)
```

### Available Metrics

**Feature Metrics:**
- `geosync_feature_transform_duration_seconds`: Histogram of transform times
- `geosync_feature_transform_total`: Counter of transforms by status
- `geosync_feature_value`: Gauge of current feature values

**Custom Metrics:**
```python
from core.utils.metrics import get_metrics_collector

metrics = get_metrics_collector()

# Measure feature transformation
with metrics.measure_feature_transform("my_indicator", "custom"):
    result = compute_my_indicator(data)

# Record feature value
metrics.record_feature_value("my_indicator", result)
```

### Viewing Metrics

```bash
# Metrics exposed at /metrics endpoint
curl http://localhost:8000/metrics

# Example output:
# geosync_feature_transform_duration_seconds_sum{feature_name="entropy",feature_type="entropy"} 12.34
# geosync_feature_transform_total{feature_name="entropy",feature_type="entropy",status="success"} 1000
```

## Best Practices

### 1. Start with Profiling

Always profile before optimizing:

```python
import time
from core.utils.logging import get_logger

logger = get_logger(__name__)

# Baseline measurement
start = time.time()
result_baseline = entropy(data, bins=30)
baseline_time = time.time() - start
logger.info(f"Baseline: {baseline_time:.3f}s")

# Optimized version
start = time.time()
result_optimized = entropy(data, bins=30, use_float32=True, chunk_size=10000)
optimized_time = time.time() - start
logger.info(f"Optimized: {optimized_time:.3f}s, speedup: {baseline_time/optimized_time:.2f}x")
```

### 2. Choose Appropriate Chunk Sizes

```python
# Rule of thumb: chunk_size ≈ sqrt(data_size) to 2*sqrt(data_size)
import numpy as np

data_size = len(data)
recommended_chunk = int(np.sqrt(data_size))
chunk_size = min(max(recommended_chunk, 1000), 1_000_000)

result = entropy(data, chunk_size=chunk_size)
```

### 3. Combine Optimizations

```python
# For maximum efficiency, combine multiple optimizations
def process_large_dataset(data):
    """Process large dataset with all optimizations."""
    from core.indicators.entropy import EntropyFeature
    from core.data.preprocess import scale_series
    
    # Scale with float32
    scaled = scale_series(data, method="zscore", use_float32=True)
    
    # Compute entropy with chunking and float32
    feature = EntropyFeature(
        bins=50,
        use_float32=True,
        chunk_size=100_000
    )
    
    result = feature.transform(scaled)
    return result
```

### 4. Monitor in Production

```python
from core.utils.metrics import get_metrics_collector, start_metrics_server
from core.utils.logging import configure_logging

# Setup monitoring
configure_logging(level="INFO", use_json=True)
start_metrics_server(port=8000)

# Your application code
metrics = get_metrics_collector()
# ... metrics are automatically collected
```

## Performance Examples

### Example 1: Memory-Constrained Environment

```python
"""Optimize for low-memory environments."""
import numpy as np
from core.indicators.entropy import EntropyFeature
from core.indicators.hurst import HurstFeature
from core.indicators.ricci import MeanRicciFeature

# Create memory-efficient features
entropy_feat = EntropyFeature(
    bins=30,
    use_float32=True,
    chunk_size=50_000
)

hurst_feat = HurstFeature(
    min_lag=2,
    max_lag=50,
    use_float32=True
)

ricci_feat = MeanRicciFeature(
    delta=0.005,
    chunk_size=1000,
    use_float32=True
)

# Process large dataset
large_data = np.random.randn(5_000_000) + 100

# Memory-efficient processing
entropy_result = entropy_feat.transform(large_data)
hurst_result = hurst_feat.transform(large_data)
ricci_result = ricci_feat.transform(large_data[:10_000])  # Subsample for Ricci

print(f"Entropy: {entropy_result.value:.4f}")
print(f"Hurst: {hurst_result.value:.4f}")
print(f"Ricci: {ricci_result.value:.4f}")
```

### Example 2: High-Throughput Pipeline

```python
"""Optimize for maximum throughput."""
from concurrent.futures import ProcessPoolExecutor
from core.indicators.entropy import entropy
from core.indicators.hurst import hurst_exponent
import numpy as np

def process_batch(data_batch):
    """Process a batch of time series."""
    results = []
    for data in data_batch:
        h = entropy(data, bins=30, use_float32=True, chunk_size=10_000)
        hurst = hurst_exponent(data, use_float32=True)
        results.append({"entropy": h, "hurst": hurst})
    return results

# Generate test data
batches = [
    [np.random.randn(100_000) for _ in range(10)]
    for _ in range(100)
]

# Parallel processing
with ProcessPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(process_batch, batches))

print(f"Processed {len(batches) * 10} time series")
```

### Strategy Batch Evaluator

```python
"""Evaluate large populations of strategies in parallel."""
import pandas as pd
from core.agent import Strategy, StrategyBatchEvaluator


class MeanReversion(Strategy):
    def simulate_performance(self, data: pd.DataFrame) -> float:
        return super().simulate_performance(data)


dataset = pd.read_parquet("/data/market.parquet")
strategies = [
    MeanReversion(name=f"mean_rev_{lookback}", params={"lookback": lookback})
    for lookback in range(10, 110, 10)
]

evaluator = StrategyBatchEvaluator(max_workers=8, chunk_size=8)
results = evaluator.evaluate(strategies, dataset)

for outcome in results:
    if outcome.succeeded:
        print(f"{outcome.strategy.name}: score={outcome.score:.3f}")
    else:
        print(f"{outcome.strategy.name} failed: {outcome.error}")
```

### Example 3: Production Monitoring

```python
"""Full production setup with monitoring."""
from core.utils.logging import configure_logging, get_logger
from core.utils.metrics import get_metrics_collector, start_metrics_server
from core.indicators.entropy import EntropyFeature
from core.indicators.hurst import HurstFeature
import numpy as np

# Setup
configure_logging(level="INFO", use_json=True)
start_metrics_server(port=8000)

logger = get_logger(__name__)
metrics = get_metrics_collector()

# Create features
entropy_feat = EntropyFeature(bins=30, use_float32=True, chunk_size=100_000)
hurst_feat = HurstFeature(use_float32=True)

def process_market_data(prices):
    """Process market data with full observability."""
    with logger.operation("process_market_data", data_size=len(prices)):
        # Compute indicators
        entropy_result = entropy_feat.transform(prices)
        hurst_result = hurst_feat.transform(prices)
        
        # Log results
        logger.info(
            "Indicators computed",
            entropy=entropy_result.value,
            hurst=hurst_result.value
        )
        
        return {
            "entropy": entropy_result.value,
            "hurst": hurst_result.value
        }

# Simulate real-time processing
while True:
    prices = np.random.randn(100_000) + 100
    result = process_market_data(prices)
    # ... continue processing
```

## Frontend Performance (Next.js)

GeoSync dashboards rely on Next.js for research and execution workflows. The
following tactics keep interaction latency low while preserving real-time
integrations.

### Code-Splitting and Bundle Hygiene

- Use [dynamic imports](https://nextjs.org/docs/pages/building-your-application/optimizing/lazy-loading)
  for heavy analytics widgets (`dynamic(() => import('./heatmap'), { ssr: false })`).
- Create route-level segments for rarely used tools (e.g., strategy wizards) so
  they ship as independent chunks.
- Enable the Webpack bundle analyzer locally (`ANALYZE=true next build`) and
  flag modules >150 KB. Move shared charting libraries to CDN-backed
  `<script>` tags when possible.
- Tree-shake date/time and math libraries by importing module-scoped functions
  (`import { differenceInMinutes } from 'date-fns'`).

### ISR/SSR Strategy

- **Order blotters and live dashboards**: Server-Side Rendering (SSR) with
  streaming to reduce Time-To-First-Byte (TTFB). Hydrate only controls that
  require client interactivity.
- **Research reports and analytics**: Incremental Static Regeneration (ISR)
  with `revalidate` windows aligned to data freshness SLIs (e.g., 300 seconds
  for signal explainers).
- Cache SSR responses via the Next.js `Cache-Control` header using `s-maxage`
  derived from service SLOs.

### API Cache Coordination

- Back caching decisions with the observability platform. Tag responses with
  `x-geosync-cache-hit` headers and export them to Grafana.
- For GraphQL endpoints, enable Apollo persisted queries and configure Redis
  TTLs to match ISR intervals.
- Use SWR or React Query on the client with background revalidation to prevent
  cascade reloads.

### Measuring LCP and TTFB

- Instrument Web Vitals via `next/script` or the built-in `reportWebVitals`
  hook. Ship metrics to the central telemetry topic with the following
  dimensions: `route`, `deployment`, `device`, `connectionType`.
- For local measurements use `npx next build && npx next start` paired with
  Lighthouse CI. Capture TTFB using Chrome DevTools' Web Vitals overlay.
- Investigate LCP regressions by correlating waterfall charts with chunk names
  from the bundle analyzer. Prioritise reducing render-blocking fonts and
  third-party scripts.

### Performance Budgets

- Set budgets per route: LCP ≤ 2.0 s (desktop), ≤ 2.5 s (mobile); TTFB ≤ 500 ms.
- Add `lighthouse-ci` assertions in CI pipelines and fail builds when metrics
  exceed thresholds.
- Track bundle size budgets: initial JavaScript ≤ 200 KB, route-specific chunks
  ≤ 150 KB, CSS ≤ 70 KB.
- Document exceptions with expiry dates in the quality gates (see
  `docs/quality_gates.md`).

## Troubleshooting

### High Memory Usage

**Problem:** Memory usage grows over time

**Solutions:**
1. Enable float32 precision
2. Use chunked processing
3. Clear intermediate results
4. Check for memory leaks

```python
import gc

# Process with cleanup
result = entropy(large_data, use_float32=True, chunk_size=100_000)
del large_data  # Release memory
gc.collect()    # Force garbage collection
```

### Slow Performance

**Problem:** Functions taking too long

**Solutions:**
1. Check data size - use chunking for large datasets
2. Enable float32 for faster computation
3. Use GPU acceleration if available
4. Profile to find bottlenecks

```python
# Profile with structured logging
from core.utils.logging import configure_logging

configure_logging(level="DEBUG", use_json=False)

# Check logs for duration_seconds in operation messages
result = entropy(data, bins=30)
```

### CuPy Import Errors

**Problem:** CuPy not working

**Solutions:**
1. Verify CUDA installation: `nvidia-smi`
2. Match CuPy version to CUDA version
3. Check GPU availability

```python
import sys
try:
    import cupy as cp
    print(f"CuPy version: {cp.__version__}")
    print(f"CUDA available: {cp.cuda.is_available()}")
except ImportError as e:
    print(f"CuPy import failed: {e}")
    print("Install with: pip install cupy-cuda11x")
```

### Numerical Instability with Float32

**Problem:** Results differ significantly with float32

**Solutions:**
1. Use float64 for accumulations
2. Normalize data before processing
3. Check for overflow/underflow

```python
# Mixed precision approach
data_scaled = scale_series(data, use_float32=False)  # Use float64 for scaling
result = entropy(data_scaled, use_float32=True)      # Then use float32
```

## Performance Benchmarks

Typical performance improvements:

| Function | Dataset Size | Baseline | With float32 | With Chunking | With Both |
|----------|-------------|----------|--------------|---------------|-----------|
| entropy | 1M points | 2.5s | 1.8s (1.4x) | 2.2s (1.1x) | 1.5s (1.7x) |
| hurst_exponent | 1M points | 4.2s | 3.1s (1.4x) | N/A | 3.1s (1.4x) |
| mean_ricci | 10K edges | 8.5s | 6.2s (1.4x) | 7.1s (1.2x) | 5.3s (1.6x) |
| compute_phase | 1M points | 3.8s | 2.7s (1.4x) | N/A | 2.7s (1.4x) |
| scale_series | 1M points | 0.3s | 0.2s (1.5x) | N/A | 0.2s (1.5x) |

Memory savings with float32:
- **50% reduction** in array memory usage
- **30-40% reduction** in peak memory usage during computation

## Additional Resources

- [Structured Logging Documentation](monitoring.md#structured-logging)
- [Prometheus Metrics Guide](monitoring.md#prometheus-metrics)
- [Troubleshooting Guide](troubleshooting.md)
- [Performance Testing](../tests/performance/test_stress.py)

## Summary

Key takeaways for optimal performance:

1. ✅ **Always profile first** - measure before optimizing
2. ✅ **Use float32 for large datasets** - 50% memory savings
3. ✅ **Enable chunked processing** - handle datasets of any size
4. ✅ **Monitor with Prometheus** - track performance in production
5. ✅ **Leverage GPU when available** - 5-50x speedup
6. ✅ **Combine optimizations** - multiply benefits
7. ✅ **Test accuracy** - verify optimizations don't break correctness

### Rust Numeric Accelerators

For CPU-bound workloads we provide a thin Rust extension, built with
[`maturin`](https://github.com/PyO3/maturin), that implements common numeric
primitives such as sliding window extraction, quantile estimation, and
1D convolution. These helpers are exposed via ``core.accelerators.numeric`` and
automatically fall back to the NumPy implementations when the compiled module is
not available.

Build and install the extension in editable mode:

```bash
pip install maturin
maturin develop --manifest-path rust/geosync-accel/Cargo.toml --release
```

Usage from Python:

```python
from core.accelerators import sliding_windows, quantiles, convolve

windows = sliding_windows(series, window=64, step=8)
percentiles = quantiles(series, (0.1, 0.5, 0.9))
smoothed = convolve(series, kernel, mode="same")
```

Each wrapper exposes a ``use_rust`` flag if you want to force the pure Python
fallback for validation or benchmarking.
