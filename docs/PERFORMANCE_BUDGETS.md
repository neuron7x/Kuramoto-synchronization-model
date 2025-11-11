# Performance Budget System

## Overview

The TradePulse performance budget system provides comprehensive performance monitoring, validation, and regression detection for critical system components. It enforces performance standards through automated CI/CD gates that reject PRs violating budget constraints.

## Key Features

- **Percentile-based budgets** (p50, p95, p99) for fine-grained latency control
- **Stability metrics** tracking variance and error rates
- **Automated flamegraph collection** for performance profiling
- **Historical trend analysis** for long-term performance monitoring
- **PR rejection** on budget violations with detailed reports
- **Component-specific budgets** for order_router, link_activator, and thermo_validator

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Performance Gate CI/CD                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. Run Benchmarks       ┌──────────────────────┐           │
│     with py-spy          │  order_router        │           │
│     profiling            │  link_activator      │           │
│                          │  thermo_validator    │           │
│                          └──────────────────────┘           │
│                                    │                         │
│                                    ▼                         │
│  2. Collect Metrics      ┌──────────────────────┐           │
│     - Latencies (p50,    │  Benchmark Results   │           │
│       p95, p99, max)     │  + Flamegraphs       │           │
│     - Throughput         └──────────────────────┘           │
│     - Stability CoV                │                         │
│     - Error rates                  ▼                         │
│                          ┌──────────────────────┐           │
│  3. Validate Budgets     │  validate_budgets.py │           │
│     against config       │  (configs/           │           │
│                          │   perf_budgets.yaml) │           │
│                          └──────────────────────┘           │
│                                    │                         │
│                          ┌─────────┴──────────┐            │
│                          ▼                    ▼            │
│                    ✅ PASSED            ❌ FAILED          │
│                                              │              │
│  4. Generate Report      ┌──────────────────────┐          │
│     with trends          │  Performance Report  │          │
│     and recommendations  │  + Recommendations   │          │
│                          │  + Flamegraph refs   │          │
│                          └──────────────────────┘          │
│                                    │                        │
│  5. Fail PR if violations          ▼                        │
│     detected             [ Block PR Merge ]                 │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## Configuration

### Budget Configuration (`configs/perf_budgets.yaml`)

```yaml
version: "2.0.0"

components:
  order_router:
    description: "Resilient execution routing across multiple exchanges"
    latency_p50_ms: 85.0
    latency_p95_ms: 110.0
    latency_p99_ms: 145.0
    latency_max_ms: 200.0
    throughput_min_tps: 50.0
    stability_coefficient_max: 0.15
    error_rate_max_percent: 2.0
    
gate_thresholds:
  regression_threshold_percent: 10.0
  min_sample_size: 100
  confidence_level: 0.95
```

### Component Budgets

#### order_router
- **Purpose**: Execution routing across multiple broker/exchange connectors
- **Performance Targets**:
  - p50 latency: ≤ 85 ms
  - p95 latency: ≤ 110 ms
  - p99 latency: ≤ 145 ms
  - Throughput: ≥ 50 TPS
  - Stability: CoV ≤ 0.15

#### link_activator
- **Purpose**: Runtime protocol selection and activation
- **Performance Targets**:
  - p50 latency: ≤ 60 ms
  - p95 latency: ≤ 85 ms
  - p99 latency: ≤ 110 ms
  - Throughput: ≥ 100 TPS
  - Stability: CoV ≤ 0.12

#### thermo_validator
- **Purpose**: Thermodynamic state validation and constraint checking
- **Performance Targets**:
  - p50 latency: ≤ 35 ms
  - p95 latency: ≤ 60 ms
  - p99 latency: ≤ 80 ms
  - Throughput: ≥ 150 TPS
  - Stability: CoV ≤ 0.10

## CI/CD Integration

### Performance Gate Workflow

The performance gate runs automatically on all PRs:

```yaml
name: Performance Budget Gate
on: [pull_request]

jobs:
  performance-budget-validation:
    steps:
      - Run benchmarks with profiling
      - Validate against budgets
      - Generate flamegraphs
      - Create performance report
      - Fail if violations detected
```

### Workflow Artifacts

Each PR run produces:
- **Flamegraphs** (SVG format) for each component
- **Benchmark results** (JSON) with detailed metrics
- **Performance report** (Markdown) with analysis
- **Validation results** (JSON) with violations

Artifacts are retained for 30 days and available for download.

## Performance Reports

### Report Structure

```markdown
# Performance Budget Validation Report

## 📊 Summary
- Components Checked: 3
- Components Passed: 2
- Total Violations: 1

**Overall Status:** ❌ FAILED

## 🚨 Budget Violations

| Component | Metric | Budget | Actual | Diff | Severity |
|-----------|--------|--------|--------|------|----------|
| order_router | latency_p95_ms | 110.0 ms | 125.3 ms | +13.9% | 🟠 HIGH |

## 🎯 Recommendations

### order_router
**Latency Issues:**
- Review flamegraph for CPU hotspots
- Consider caching frequently accessed data
- Profile database queries and optimize indexes
```

### Violation Severity Levels

- 🔴 **CRITICAL**: >30% regression or error rate violations
- 🟠 **HIGH**: 20-30% regression or throughput violations
- 🟡 **MEDIUM**: 10-20% regression or minor issues

## Benchmark Tests

### Writing Benchmarks

Use `pytest-benchmark` for consistent measurements:

```python
def test_component_performance(benchmark):
    """Benchmark: Component operation."""
    
    def setup():
        # Prepare test fixtures
        component = Component()
        data = prepare_test_data()
        return (component, data), {}
    
    def run(component, data):
        # Execute operation under test
        return component.process(data)
    
    benchmark.pedantic(run, setup=setup, rounds=100, iterations=10)
```

### Running Benchmarks

```bash
# Run all component benchmarks
pytest tests/performance/test_component_benchmarks.py --benchmark-json=results.json

# Run specific component
pytest tests/performance/test_component_benchmarks.py::test_order_router_single_route_submission

# With profiling
py-spy record -o flamegraph.svg -- pytest tests/performance/...
```

## Scripts

### validate_budgets.py

Validates benchmark results against configured budgets:

```bash
./scripts/performance/validate_budgets.py \
  --config configs/perf_budgets.yaml \
  --benchmarks reports/performance/ \
  --output reports/performance/validation.json \
  --strict
```

**Output**: JSON file with violations and summary

### generate_performance_report.py

Generates comprehensive performance report:

```bash
./scripts/performance/generate_performance_report.py \
  --config configs/perf_budgets.yaml \
  --validation reports/performance/validation.json \
  --output reports/performance/report.md \
  --include-trends \
  --include-flamegraphs
```

**Output**: Markdown report with recommendations

## Flamegraph Analysis

### Collection

Flamegraphs are automatically collected using `py-spy`:

```bash
py-spy record -o flamegraph.svg \
  --format speedscope \
  --subprocesses \
  -- python -m pytest tests/performance/...
```

### Interpretation

- **Wide bars**: Functions consuming significant CPU time
- **Tall stacks**: Deep call chains (potential optimization)
- **Hot paths**: Frequently called functions (cache candidates)

### Common Patterns

```
┌─────────────────────────────────────────┐
│         Component.process()              │  ← Entry point
├─────────────────────────────────────────┤
│  DatabaseQuery.execute()    (40% time)   │  ← Optimization target
│  Validation.check()         (30% time)   │
│  Serialization.encode()     (20% time)   │
└─────────────────────────────────────────┘
```

## Historical Trends

### Trend Tracking

The system maintains historical performance data:

```yaml
trend_tracking:
  history_window: 50          # Keep last 50 runs
  auto_baseline_update: false # Manual baseline updates
  baseline_update_threshold: 10
```

### Trend Analysis

- **Latency trends**: Track p50/p95/p99 over time
- **Throughput evolution**: Detect capacity regressions
- **Stability changes**: Monitor variance increases
- **Violation frequency**: Alert on recurring issues

## Best Practices

### Setting Budgets

1. **Establish Baseline**: Run benchmarks on stable code
2. **Add Headroom**: Set budgets 10-20% above baseline
3. **Consider P99**: Don't ignore tail latencies
4. **Monitor Trends**: Adjust budgets as system evolves

### Avoiding False Positives

1. **Use adequate sample sizes** (min_sample_size: 100)
2. **Warm up** caches before measurements
3. **Control environment** (dedicated benchmark runners)
4. **Account for variance** (stability_coefficient_max)

### Debugging Violations

1. **Check flamegraph** for CPU hotspots
2. **Review recent changes** in git history
3. **Compare baselines** (before/after)
4. **Profile database queries** with explain plans
5. **Check resource limits** (CPU, memory, I/O)

## Troubleshooting

### Common Issues

#### High P99 Latency
```
Symptom: p99 exceeds budget but p50/p95 are fine
Cause: Outliers (GC pauses, lock contention)
Solution: Review flamegraph tail, optimize outlier cases
```

#### Low Throughput
```
Symptom: TPS below minimum threshold
Cause: Sequential operations, resource bottlenecks
Solution: Add parallelism, check resource limits
```

#### High Stability CoV
```
Symptom: Coefficient of variation exceeds limit
Cause: High variance in execution time
Solution: Investigate bimodal distributions, fix outliers
```

## Integration with Existing Systems

### Performance Regression Workflow

This system complements the existing `performance-regression.yml` workflow:

- **performance-regression.yml**: Compares PR vs main baseline
- **performance-gate.yml**: Validates absolute budgets

Both workflows run concurrently and must pass for PR merge.

### Budget Loader

The existing `BudgetLoader` class in `tests/performance/budget_loader.py` can be extended to support the new `perf_budgets.yaml` format.

## Future Enhancements

- [ ] Automated baseline updates after N passing runs
- [ ] Per-environment budgets (prod vs staging)
- [ ] Machine learning anomaly detection
- [ ] Performance budget visualization dashboard
- [ ] Integration with Prometheus metrics
- [ ] Automated performance regression git bisect

## References

- [pytest-benchmark documentation](https://pytest-benchmark.readthedocs.io/)
- [py-spy profiler](https://github.com/benfred/py-spy)
- [Performance budgets concept](https://web.dev/performance-budgets-101/)

## Support

For questions or issues:
1. Check workflow logs in GitHub Actions
2. Review flamegraphs for bottlenecks
3. Consult team performance expert
4. Open issue with performance label
