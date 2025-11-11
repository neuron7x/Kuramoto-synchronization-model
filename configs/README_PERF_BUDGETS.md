# Performance Budgets Configuration

## Quick Reference

This file (`perf_budgets.yaml`) defines performance budgets for critical TradePulse components. Budgets are enforced via CI/CD gates that automatically reject PRs violating performance constraints.

## Configuration Structure

```yaml
version: "2.0.0"

components:
  component_name:
    description: "Component description"
    # Latency budgets (milliseconds)
    latency_p50_ms: 50.0       # Median latency
    latency_p95_ms: 100.0      # 95th percentile
    latency_p99_ms: 150.0      # 99th percentile
    latency_max_ms: 200.0      # Maximum allowed
    
    # Throughput budgets
    throughput_min_tps: 100.0  # Minimum transactions/sec
    
    # Stability metrics
    stability_coefficient_max: 0.15    # Max coefficient of variation
    error_rate_max_percent: 1.0        # Max error rate
    
    # Historical baselines (for tracking)
    observed_p50_ms: 45.0
    observed_p95_ms: 85.0
    observed_p99_ms: 120.0
```

## Monitored Components

### 1. order_router
**Location**: `execution/router.py`  
**Function**: Routes orders across multiple exchange connectors

**Critical Path**:
```python
router.submit_order()
  → resolve_route()
  → apply_slippage()
  → connector.place_order()
  → normalize()
```

**Budget Rationale**:
- p50: 85ms - Normal execution path
- p95: 110ms - Includes occasional network delays
- p99: 145ms - Accounts for circuit breaker checks
- Throughput: 50 TPS - Multi-exchange capacity

### 2. link_activator
**Location**: `runtime/link_activator.py`  
**Function**: Selects and activates communication protocols

**Critical Path**:
```python
activator.apply()
  → select_protocol()
  → fallback_chain()
  → track_activation()
```

**Budget Rationale**:
- p50: 60ms - Protocol selection overhead
- p95: 85ms - Includes fallback attempts
- p99: 110ms - Complex bond type resolution
- Throughput: 100 TPS - High-frequency activation

### 3. thermo_validator
**Location**: `runtime/thermo_controller.py`  
**Function**: Validates thermodynamic constraints

**Critical Path**:
```python
validate_state()
  → check_energy_bounds()
  → check_entropy_constraints()
  → check_stability()
```

**Budget Rationale**:
- p50: 35ms - Fast-path validation
- p95: 60ms - Complex constraint checks
- p99: 80ms - Full state validation
- Throughput: 150 TPS - Frequent validation calls

## Gate Thresholds

```yaml
gate_thresholds:
  regression_threshold_percent: 10.0   # Allow 10% regression
  min_sample_size: 100                 # Statistical validity
  confidence_level: 0.95               # 95% confidence
  variance_increase_threshold_percent: 20.0
```

## Workflow Integration

### Automated Checks

The `.github/workflows/performance-gate.yml` workflow:

1. **Runs benchmarks** for each component
2. **Collects flamegraphs** using py-spy profiler
3. **Validates budgets** using `validate_budgets.py`
4. **Generates report** with recommendations
5. **Fails PR** if violations detected

### Manual Validation

```bash
# Run benchmarks locally
pytest tests/performance/test_component_benchmarks.py \
  --benchmark-json=results.json

# Validate against budgets
./scripts/performance/validate_budgets.py \
  --config configs/perf_budgets.yaml \
  --benchmarks . \
  --output validation.json
```

## Updating Budgets

### When to Update

- ✅ After verified performance improvements
- ✅ When baselines stabilize after changes
- ✅ When adding new functionality (increase budget)
- ❌ To "fix" failing tests without investigation
- ❌ Arbitrary increases without justification

### Update Process

1. **Document reason** in PR description
2. **Include benchmarks** showing new baseline
3. **Update observed_* values** to match reality
4. **Adjust budgets** with appropriate headroom (10-20%)
5. **Update description** if component behavior changed

### Example PR Description

```markdown
## Performance Budget Update: order_router

**Reason**: Optimized database query path (#1234)

**Benchmark Results**:
- p50: 82ms → 68ms (17% improvement)
- p95: 92ms → 78ms (15% improvement)
- Throughput: 50 TPS → 65 TPS (30% improvement)

**Proposed Changes**:
- latency_p50_ms: 85 → 75 (-10ms headroom)
- latency_p95_ms: 110 → 90 (-12ms headroom)
- observed_p50_ms: 82 → 68
- observed_p95_ms: 92 → 78
```

## Troubleshooting

### PR Failed: Budget Violations

1. **Check workflow summary** for specific violations
2. **Download flamegraphs** from artifacts
3. **Identify hotspots** in flamegraph
4. **Profile locally** with py-spy
5. **Fix or justify** the regression

### False Positives

If you believe a violation is a false positive:

1. **Check variance**: High stability_coefficient indicates noisy measurements
2. **Verify sample size**: Ensure min_sample_size met
3. **Review environment**: CI runners may have variable performance
4. **Re-run workflow**: Occasional outliers happen
5. **Consult team**: Discuss if budget adjustment needed

### Debugging Performance

```bash
# Profile specific test
py-spy record -o profile.svg -- \
  pytest tests/performance/test_component_benchmarks.py::test_order_router_single_route_submission

# Run with increased verbosity
pytest tests/performance/test_component_benchmarks.py -vv --benchmark-verbose

# Compare with baseline
pytest --benchmark-compare=baseline.json --benchmark-compare-fail=mean:10%
```

## Metrics Explained

### Percentiles

- **p50 (median)**: Half of requests faster, half slower
- **p95**: 95% of requests faster, 5% slower
- **p99**: 99% of requests faster, 1% slower

**Why p99 matters**: In high-volume systems, 1% still means many users affected.

### Stability Coefficient

```
Coefficient of Variation (CoV) = std_dev / mean
```

- CoV < 0.10: Very stable
- CoV 0.10-0.20: Moderate variance
- CoV > 0.20: High variance (investigate)

### Throughput

Transactions per second (TPS) under sustained load.

**Note**: Peak TPS may differ from sustained TPS.

## Best Practices

### Do's ✅

- Set budgets based on real measurements
- Include headroom (10-20%) above baseline
- Monitor trends over time
- Update budgets after verified improvements
- Document budget changes

### Don'ts ❌

- Set arbitrary budgets without data
- Ignore p99 latencies
- Update budgets to "fix" tests
- Forget to update observed baselines
- Skip flamegraph analysis

## Related Documentation

- [Full Performance Budgets Guide](../docs/PERFORMANCE_BUDGETS.md)
- [Benchmark Tests](../tests/performance/test_component_benchmarks.py)
- [Validation Script](../scripts/performance/validate_budgets.py)
- [Report Generator](../scripts/performance/generate_performance_report.py)

## Contact

For questions about performance budgets:
- Review workflow logs in GitHub Actions
- Check flamegraphs for bottlenecks
- Consult team performance expert
- Open issue with `performance` label
