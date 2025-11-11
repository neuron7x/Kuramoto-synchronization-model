# Performance Gate Documentation

## Overview

The Performance Gate system provides automated performance benchmarking and regression detection for critical TradePulse components. It runs in GitHub Actions and enforces performance budgets on pull requests.

## Components Monitored

### 1. **order_router**
- **Path**: `execution/router.py`
- **What it does**: Resilient execution routing across multiple broker/exchange connectors
- **Key operations**: Order normalization, slippage modeling, venue-specific routing
- **Performance budgets**:
  - p50: 85.0ms
  - p95: 120.0ms  
  - p99: 150.0ms
  - Stability: Max CoV 15%

### 2. **link_activator**
- **Path**: `runtime/link_activator.py`
- **What it does**: Maps thermodynamic bond abstractions to concrete communication protocols
- **Key operations**: Protocol activation (RDMA, CRDT, gRPC, shared memory, gossip)
- **Performance budgets**:
  - p50: 65.0ms
  - p95: 90.0ms
  - p99: 110.0ms
  - Stability: Max CoV 12%

### 3. **thermo_validator**
- **Path**: `runtime/thermo_controller.py` (validation functions)
- **What it does**: Thermodynamic energy calculations for system optimization
- **Key operations**: Bond energy calculations, free energy delta computation
- **Performance budgets**:
  - p50: 40.0ms
  - p95: 65.0ms
  - p99: 80.0ms
  - Stability: Max CoV 10%

## Performance Metrics

### Percentiles
- **p50 (median)**: Typical performance - 50% of operations complete within this time
- **p95**: High-load performance - 95% of operations complete within this time
- **p99**: Worst-case performance - 99% of operations complete within this time

### Stability Metrics
- **Coefficient of Variation (CoV)**: Standard deviation / mean
  - Measures consistency of performance
  - Lower is better (more stable)
- **Outlier detection**: Values beyond 3 standard deviations

## How It Works

### 1. **Benchmark Execution**
```bash
python scripts/performance/benchmark_components.py \
  --config configs/perf_budgets.yaml \
  --output reports/performance/benchmark_results.json \
  --fail-on-violation
```

Each component is benchmarked with:
- 10 warmup iterations (discarded)
- 100 measurement iterations
- Percentile calculation from timing samples
- Validation against budgets

### 2. **Flamegraph Generation**
```bash
python scripts/performance/generate_flamegraphs.py \
  --output-dir reports/performance/flamegraphs \
  --duration 10
```

Uses py-spy to profile components and generate SVG flamegraphs showing:
- Function call hierarchy
- Time spent in each function
- Hotspots and bottlenecks

### 3. **Historical Trend Tracking**
```bash
# Update history
python scripts/performance/track_historical_trends.py \
  --history-file reports/performance/history.json \
  update \
  --benchmark-results reports/performance/benchmark_results.json \
  --commit-sha $(git rev-parse HEAD) \
  --branch $(git branch --show-current)

# Generate trend report
python scripts/performance/track_historical_trends.py \
  --history-file reports/performance/history.json \
  report \
  --output reports/performance/trend_report.md \
  --lookback 20
```

Tracks performance over time:
- Linear regression for trend detection
- Identifies degrading/improving/stable trends
- Stores historical data with commit SHA and branch
- Calculates percentage change over lookback period

### 4. **Performance Report Generation**
```bash
python scripts/performance/generate_performance_report.py \
  --benchmark-results reports/performance/benchmark_results.json \
  --output reports/performance/performance_report.md \
  --trend-report reports/performance/trend_report.md \
  --flamegraph-dir reports/performance/flamegraphs
```

Generates comprehensive markdown report with:
- Summary table of all components
- Pass/fail status
- Detailed violation descriptions
- Stability metrics
- Historical trends
- Links to flamegraphs

## GitHub Actions Workflow

The performance gate runs automatically on:
- **Pull requests** to main/develop branches
- **Pushes** to main branch
- **Nightly** at 3 AM UTC (for trend tracking)
- **Manual** workflow dispatch

### Workflow Steps

1. **Setup**: Install Python, dependencies, and py-spy
2. **Benchmark**: Run all component benchmarks
3. **Flamegraphs**: Generate profiling flamegraphs (5 seconds each)
4. **History**: Update performance history with results
5. **Trends**: Generate trend report from historical data
6. **Report**: Create comprehensive performance report
7. **Artifacts**: Upload results, flamegraphs, and reports
8. **Comment**: Post report to PR (if applicable)
9. **Gate**: Fail PR if any budget violations detected

### Artifacts

All performance data is uploaded as workflow artifacts:
- `benchmark_results.json` - Raw benchmark data
- `trend_report.md` - Historical trend analysis
- `performance_report.md` - Comprehensive report
- `flamegraphs/*.svg` - Profiling flamegraphs
- `history.json` - Historical performance data

Retention: 30 days

## Configuration

### Performance Budgets

Budgets are defined in `configs/perf_budgets.yaml`:

```yaml
components:
  order_router:
    observed_ms: 92.0
    budget_ms: 110.0
    percentiles:
      p50_ms: 85.0
      p95_ms: 120.0
      p99_ms: 150.0
    stability:
      max_variance: 0.15  # 15% coefficient of variation
      min_sample_size: 100
      outlier_threshold: 3.0
```

To update budgets:
1. Edit `configs/perf_budgets.yaml`
2. Commit changes
3. New budgets will be used in next run

### Benchmark Parameters

Default parameters in `benchmark_components.py`:
- **Warmup**: 10 iterations
- **Iterations**: 100 samples
- **Timing**: `time.perf_counter()` for microsecond precision

To customize:
```python
timings = benchmark_function(workload, iterations=200, warmup=20)
```

## Interpreting Results

### ✅ Passing Component
```
order_router: ✓ PASS
  p50: 82.15ms (budget: 85.00ms)
  p95: 115.23ms (budget: 120.00ms)
  p99: 145.67ms (budget: 150.00ms)
```
All percentiles within budget, no violations.

### ❌ Failing Component
```
order_router: ✗ FAIL
  p50: 95.23ms (budget: 85.00ms)
  p95: 135.45ms (budget: 120.00ms)
  p99: 175.89ms (budget: 150.00ms)

  Violations:
    • p50: 95.23ms exceeds budget 85.00ms (+10.23ms, +12.0%)
    • p95: 135.45ms exceeds budget 120.00ms (+15.45ms, +12.9%)
    • p99: 175.89ms exceeds budget 150.00ms (+25.89ms, +17.3%)
```
Multiple percentiles exceed budgets, PR will be blocked.

### ⚠️ Stability Warning
```
link_activator: ✗ FAIL
  p50: 62.50ms (budget: 65.00ms)
  p95: 88.20ms (budget: 90.00ms)
  p99: 108.45ms (budget: 110.00ms)

  Violations:
    • Stability: coefficient of variation 0.245 exceeds threshold 0.120
```
Percentiles are within budget but performance is inconsistent.

## Trend Analysis

### Stable Trend ✓
```
### order_router ✓

- **Trend**: stable
- **Data points**: 10
- **Current p50**: 85.23ms
- **Baseline p50**: 84.98ms
- **Change**: +0.3%
- **Slope**: +0.025ms/commit
```
Performance is consistent over time.

### Degrading Trend ⚠️
```
### link_activator ⚠️

- **Trend**: degrading
- **Data points**: 15
- **Current p50**: 72.45ms
- **Baseline p50**: 65.12ms
- **Change**: +11.3%
- **Slope**: +0.489ms/commit
```
Performance is gradually degrading, investigate soon.

### Improving Trend 📈
```
### thermo_validator 📈

- **Trend**: improving
- **Data points**: 8
- **Current p50**: 38.23ms
- **Baseline p50**: 42.56ms
- **Change**: -10.2%
- **Slope**: -0.541ms/commit
```
Performance is improving, optimizations are working.

## Troubleshooting

### Tests Failing Locally
```bash
# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run benchmarks
python scripts/performance/benchmark_components.py --config configs/perf_budgets.yaml

# Run tests
pytest tests/performance/test_benchmark_components.py -v
```

### Import Errors
Ensure current directory is in Python path:
```python
import sys
sys.path.insert(0, '.')
```

Or install package in editable mode:
```bash
pip install -e .
```

### py-spy Not Found
Install py-spy:
```bash
pip install py-spy>=0.4.1
```

### Flamegraphs Not Generating
Check py-spy permissions:
```bash
# On Linux, may need to adjust ptrace_scope
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

Or use Docker:
```bash
docker run --cap-add=SYS_PTRACE -v $(pwd):/app -w /app python:3.11 \
  python scripts/performance/generate_flamegraphs.py
```

### High Variance / Instability
Common causes:
1. **Background processes**: Close unnecessary applications
2. **CPU throttling**: Check thermal throttling, power settings
3. **GC pauses**: Python garbage collection during timing
4. **Network latency**: If benchmarks involve network calls
5. **Disk I/O**: If benchmarks involve file operations

Solutions:
- Run on dedicated hardware
- Increase sample size (more iterations)
- Use process isolation (taskset, nice)
- Profile with py-spy to identify sources

## Best Practices

### 1. **Update Budgets Conservatively**
- Base on p95, not p50 (allows for variance)
- Add 20% margin for safety
- Review historical trends before tightening

### 2. **Monitor Trends Regularly**
- Check nightly trend reports
- Investigate degrading trends early
- Don't wait for budget violations

### 3. **Use Flamegraphs for Optimization**
- Profile before optimizing
- Focus on hotspots shown in flamegraphs
- Verify improvements with benchmarks

### 4. **Document Performance Changes**
- Note optimizations in commit messages
- Update budgets when making intentional changes
- Link to flamegraphs in discussions

### 5. **Test Locally First**
```bash
# Before pushing
python scripts/performance/benchmark_components.py \
  --config configs/perf_budgets.yaml \
  --fail-on-violation
```

## Integration with CI/CD

### Workflow Dependencies
```yaml
jobs:
  performance-gate:
    needs: [tests, lint]  # Run after other checks
```

### Manual Override
If a violation is acceptable (e.g., new feature with known cost):
1. Update budgets in `configs/perf_budgets.yaml`
2. Document reason in PR description
3. Get approval from maintainer

### Bypass for Urgent Fixes
```yaml
# Add to commit message to skip gate
[skip-perf-gate]
```

## Additional Resources

- [Performance Regression Guide](../PERFORMANCE_REGRESSION_GUIDE.md)
- [Benchmark Components Script](../scripts/performance/benchmark_components.py)
- [Performance Budgets Config](../configs/perf_budgets.yaml)
- [GitHub Actions Workflow](../.github/workflows/performance-gate.yml)

## FAQ

**Q: Why are my local results different from CI?**  
A: Hardware differences, background processes, and environment variability. CI runs on standardized runners.

**Q: Can I run benchmarks for specific components?**  
A: Yes, edit `benchmark_components.py` to comment out unwanted benchmarks.

**Q: How do I update the observed baseline?**  
A: Update `observed_ms` in `configs/perf_budgets.yaml` based on recent p50 values.

**Q: What if I need to make a change that degrades performance?**  
A: Update budgets, document the tradeoff, and ensure it's reviewed by maintainers.

**Q: How long are artifacts retained?**  
A: 30 days. Download important artifacts before they expire.

---

**Last Updated**: 2025-11-11  
**Version**: 1.0.0  
**Maintainer**: TradePulse Team
