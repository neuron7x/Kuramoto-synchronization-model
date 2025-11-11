# Performance Gate Quick Start

> Automated performance benchmarking and regression detection for TradePulse

## 🚀 Quick Start

### Run Benchmarks Locally
```bash
python scripts/performance/benchmark_components.py \
  --config configs/perf_budgets.yaml \
  --output reports/performance/results.json \
  --fail-on-violation
```

### Generate Flamegraphs
```bash
python scripts/performance/generate_flamegraphs.py \
  --output-dir reports/performance/flamegraphs \
  --duration 10
```

### View Trends
```bash
python scripts/performance/track_historical_trends.py \
  --history-file reports/performance/history.json \
  report --lookback 20
```

## 📊 What Gets Measured

| Component | What It Does | p50 Budget | p95 Budget | p99 Budget |
|-----------|--------------|------------|------------|------------|
| **order_router** | Order execution routing | 85ms | 120ms | 150ms |
| **link_activator** | Protocol activation | 65ms | 90ms | 110ms |
| **thermo_validator** | Energy calculations | 40ms | 65ms | 80ms |

## 🎯 Performance Budgets

Budgets are defined in `configs/perf_budgets.yaml`:

```yaml
components:
  order_router:
    percentiles:
      p50_ms: 85.0   # median
      p95_ms: 120.0  # 95th percentile
      p99_ms: 150.0  # 99th percentile
    stability:
      max_variance: 0.15  # 15% max coefficient of variation
```

## 🔄 GitHub Actions Workflow

The performance gate runs automatically on:
- ✅ Pull requests to main/develop
- ✅ Pushes to main
- ✅ Nightly at 3 AM UTC
- ✅ Manual workflow dispatch

### What Happens
1. Runs benchmarks for all components
2. Generates flamegraphs for profiling
3. Updates historical performance data
4. Creates trend analysis report
5. Posts summary to PR as comment
6. **Fails PR if budgets are violated** ❌

## 📁 Output Artifacts

All results are uploaded as GitHub Actions artifacts:
- `benchmark_results.json` - Raw benchmark data
- `performance_report.md` - Comprehensive report
- `trend_report.md` - Historical trend analysis
- `flamegraphs/*.svg` - Profiling visualizations
- `history.json` - Performance history database

## ✅ Passing Build

```
order_router: ✓ PASS
  p50: 82.5ms (budget: 85.0ms)
  p95: 115.3ms (budget: 120.0ms)
  p99: 145.2ms (budget: 150.0ms)
```

## ❌ Failing Build

```
order_router: ✗ FAIL
  p50: 95.2ms (budget: 85.0ms)
  p95: 135.4ms (budget: 120.0ms)
  p99: 175.8ms (budget: 150.0ms)

  Violations:
    • p50: 95.2ms exceeds budget 85.0ms (+10.2ms, +12.0%)
    • p95: 135.4ms exceeds budget 120.0ms (+15.4ms, +12.9%)
    • p99: 175.8ms exceeds budget 150.0ms (+25.8ms, +17.3%)
```

**Your PR will be blocked until violations are fixed!**

## 🔧 Fixing Violations

### 1. Profile with Flamegraphs
```bash
python scripts/performance/generate_flamegraphs.py \
  --components order_router \
  --duration 10
```

Open the generated SVG to identify hotspots.

### 2. Benchmark Locally
```bash
python scripts/performance/benchmark_components.py \
  --config configs/perf_budgets.yaml
```

### 3. Optimize the Code
Focus on:
- Reducing allocations
- Caching repeated calculations
- Using faster algorithms
- Lazy evaluation

### 4. Verify Improvement
```bash
python scripts/performance/benchmark_components.py \
  --config configs/perf_budgets.yaml \
  --fail-on-violation
```

### 5. Update Budgets (If Necessary)
If the performance change is intentional:
1. Update `configs/perf_budgets.yaml`
2. Document the reason in PR description
3. Get maintainer approval

## 📈 Trend Analysis

### Stable ✓
```
- Trend: stable
- Change: +0.3%
- Slope: +0.025ms/commit
```
No action needed.

### Degrading ⚠️
```
- Trend: degrading
- Change: +11.3%
- Slope: +0.489ms/commit
```
Investigate and optimize soon.

### Improving 📈
```
- Trend: improving
- Change: -10.2%
- Slope: -0.541ms/commit
```
Optimizations working!

## 🧪 Testing

Run the test suite:
```bash
pytest tests/performance/test_benchmark_components.py -v
pytest tests/performance/test_historical_trends.py -v
```

## 📚 Full Documentation

See [docs/performance_gate.md](docs/performance_gate.md) for complete documentation including:
- Detailed component descriptions
- Configuration options
- Troubleshooting guide
- Best practices
- Integration examples

## 🆘 Common Issues

### Import Errors
```bash
pip install -e .
```

### py-spy Not Found
```bash
pip install py-spy>=0.4.1
```

### High Variance
- Close background applications
- Increase iteration count
- Use dedicated hardware

### Flamegraphs Not Working
```bash
# Linux: may need to adjust ptrace_scope
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

## 📞 Support

- 📖 [Full Documentation](docs/performance_gate.md)
- 🐛 [Report Issue](https://github.com/neuron7x/TradePulse/issues)
- 💬 [Discussions](https://github.com/neuron7x/TradePulse/discussions)

---

**Quick Links:**
- [Performance Budgets](configs/perf_budgets.yaml)
- [Benchmark Script](scripts/performance/benchmark_components.py)
- [GitHub Workflow](.github/workflows/performance-gate.yml)
- [Performance Regression Guide](PERFORMANCE_REGRESSION_GUIDE.md)
