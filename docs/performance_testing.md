# Multi-Exchange Replay Performance Testing

## Overview

The TradePulse performance testing infrastructure provides comprehensive replay-based testing for multi-exchange market data with automated regression detection and CI/CD integration.

## Features

- **Multi-Exchange Support**: Test performance across different exchanges (Coinbase, Binance, synthetic data, etc.)
- **Comprehensive Metrics**: Measure latency, throughput, and slippage
- **Performance Budgets**: Define and enforce performance thresholds
- **Regression Detection**: Automatically detect performance regressions
- **CI/CD Integration**: GitHub Actions workflow with artifact publishing
- **Visualization**: Generate charts showing performance trends
- **Issue Tracking**: Auto-generate GitHub issues for regressions

## Architecture

### Core Components

#### 1. Multi-Exchange Replay Loader

Located in `tests/performance/multi_exchange_replay.py`, this module provides:

- `ExchangeTick`: Data structure for market data ticks
- `ReplayMetadata`: Metadata describing replay recordings
- `PerformanceMetrics`: Container for collected metrics
- `PerformanceBudget`: Performance threshold configuration
- `load_replay_recording()`: Load recordings from JSONL files
- `compute_performance_metrics()`: Calculate performance metrics
- `check_regression()`: Compare metrics against budgets

#### 2. Artifact Generator

Located in `tests/performance/performance_artifacts.py`, this module provides:

- `PerformanceRun`: Single test run result
- `PerformanceReport`: Aggregated test results
- `PerformanceArtifactGenerator`: Generate reports, charts, and issues

#### 3. Test Suite

Located in `tests/performance/test_multi_exchange_replay_regression.py`:

- Integration tests with performance budgets
- Parametrized tests for individual recordings
- Stress tests for high-throughput scenarios
- Nightly tests with historical comparison

## Usage

### Recording Format

Recordings are stored as JSONL files with optional metadata:

**Recording File** (`coinbase_btcusd.jsonl`):
```json
{"exchange_ts": "2024-03-05T14:30:00.123456Z", "ingest_ts": "2024-03-05T14:30:00.168923Z", "bid": 64123.12, "ask": 64123.54, "last": 64123.33, "volume": 0.18}
{"exchange_ts": "2024-03-05T14:30:00.223456Z", "ingest_ts": "2024-03-05T14:30:00.268104Z", "bid": 64123.34, "ask": 64123.76, "last": 64123.51, "volume": 0.12}
```

**Metadata File** (`coinbase_btcusd.metadata.json`):
```json
{
  "name": "coinbase_btcusd",
  "exchange": "coinbase",
  "symbol": "BTC-USD",
  "start_time": "2024-03-05T14:30:00.123456Z",
  "end_time": "2024-03-05T14:30:01.023456Z",
  "tick_count": 10,
  "description": "Coinbase BTC-USD live market data recording",
  "tags": ["coinbase", "live", "btc-usd", "performance"]
}
```

### Running Tests

#### Run all regression tests:
```bash
pytest tests/performance/test_multi_exchange_replay_regression.py -v
```

#### Run tests for a specific recording:
```bash
pytest tests/performance/test_multi_exchange_replay_regression.py::test_coinbase_btcusd_replay_meets_budget -v
```

#### Run with integration marker:
```bash
pytest -m integration tests/performance/test_multi_exchange_replay_regression.py
```

#### Run nightly extended tests:
```bash
pytest -m nightly tests/performance/test_multi_exchange_replay_regression.py
```

### CLI Tool

Generate reports manually using the CLI tool:

```bash
python scripts/performance/generate_replay_report.py \
  --recordings-dir tests/fixtures/recordings \
  --output-dir .ci_artifacts/performance \
  --latency-median-ms 60.0 \
  --latency-p95-ms 100.0 \
  --throughput-min-tps 10.0 \
  --slippage-median-bps 5.0 \
  --generate-charts \
  --fail-on-regression
```

**Options**:
- `--recordings-dir`: Directory containing recordings (default: `tests/fixtures/recordings`)
- `--output-dir`: Output directory for artifacts (default: `.ci_artifacts/multi-exchange-replay`)
- `--latency-median-ms`: Median latency budget in ms
- `--latency-p95-ms`: P95 latency budget in ms
- `--latency-max-ms`: Maximum latency budget in ms
- `--throughput-min-tps`: Minimum throughput in ticks/second
- `--slippage-median-bps`: Median slippage budget in bps
- `--slippage-p95-bps`: P95 slippage budget in bps
- `--fail-on-regression`: Exit with non-zero status on regression
- `--generate-charts`: Generate visualization charts
- `--generate-issues`: Generate GitHub issue templates

### Programmatic Usage

```python
from pathlib import Path
from tests.performance.multi_exchange_replay import (
    PerformanceBudget,
    load_replay_recording,
    compute_performance_metrics,
    check_regression,
)

# Load recording
ticks, metadata = load_replay_recording(
    Path("tests/fixtures/recordings/coinbase_btcusd.jsonl"),
    exchange="coinbase"
)

# Compute metrics
metrics = compute_performance_metrics(ticks)

print(f"Latency median: {metrics.latency_median_ms:.2f}ms")
print(f"Latency P95: {metrics.latency_p95_ms:.2f}ms")
print(f"Throughput: {metrics.throughput_tps:.2f} tps")

# Check against budget
budget = PerformanceBudget(
    latency_median_ms=60.0,
    latency_p95_ms=100.0,
    throughput_min_tps=10.0,
)

result = check_regression(metrics, budget)
if not result.passed:
    for violation in result.violations:
        print(f"⚠️  {violation}")
```

## Performance Budgets

### Default Budget

```python
PerformanceBudget(
    latency_median_ms=60.0,    # Median latency under 60ms
    latency_p95_ms=100.0,       # P95 latency under 100ms
    latency_max_ms=200.0,       # Max latency under 200ms
    throughput_min_tps=5.0,     # At least 5 ticks/second
    slippage_median_bps=5.0,    # Median slippage under 5bps
    slippage_p95_bps=15.0,      # P95 slippage under 15bps
)
```

### Exchange-Specific Budgets

Configure different budgets for different exchanges in the test file:

```python
BUDGETS = {
    "coinbase": PerformanceBudget(
        latency_median_ms=50.0,
        latency_p95_ms=90.0,
        throughput_min_tps=5.0,
    ),
    "binance": PerformanceBudget(
        latency_median_ms=45.0,
        latency_p95_ms=80.0,
        throughput_min_tps=10.0,
    ),
}
```

## CI/CD Integration

### GitHub Actions Workflow

The workflow runs automatically on:
- Pull requests that modify recordings, performance tests, or core modules
- Pushes to main branch
- Nightly at 2 AM UTC
- Manual workflow dispatch

**Workflow file**: `.github/workflows/multi-exchange-replay-regression.yml`

### Artifacts

The workflow generates and uploads:

1. **JSON Report** (`performance_report.json`):
   - Complete test results
   - All metrics for each run
   - Git metadata and environment info

2. **Markdown Summary** (`performance_summary.md`):
   - Human-readable summary
   - Tables with pass/fail indicators
   - Regression violations

3. **Visualization Charts**:
   - `latency_chart.png`: Latency distribution
   - `throughput_chart.png`: Throughput comparison
   - `slippage_chart.png`: Slippage distribution

4. **Issue Templates**:
   - Auto-generated GitHub issue templates for regressions
   - Include metrics, violations, and git context

### Viewing Results

1. Navigate to the Actions tab in GitHub
2. Select the "Multi-Exchange Replay Regression" workflow
3. Click on a run to see the summary
4. Download artifacts to view detailed reports and charts

## Metrics Explained

### Latency

Measures the time between exchange timestamp and ingestion timestamp:

- **Median**: Middle value, represents typical latency
- **P95**: 95th percentile, catches most outliers
- **P99**: 99th percentile, catches rare spikes
- **Max**: Maximum observed latency

### Throughput

Measures processing rate:

- **Formula**: `ticks_processed / duration_seconds`
- **Unit**: Ticks per second (tps)
- **Indicates**: System capacity and efficiency

### Slippage

Measures bid-ask spread as a proxy for slippage:

- **Formula**: `(ask - bid) / mid_price * 10000`
- **Unit**: Basis points (bps)
- **Median**: Typical spread cost
- **P95**: High-impact scenarios

## Adding New Recordings

1. **Create the recording file**:
   ```bash
   touch tests/fixtures/recordings/my_exchange_data.jsonl
   ```

2. **Add ticks in JSONL format**:
   ```json
   {"exchange_ts": "2024-...", "ingest_ts": "2024-...", "bid": 100.0, "ask": 100.1, "last": 100.05, "volume": 1.0}
   ```

3. **Create metadata file** (optional but recommended):
   ```bash
   touch tests/fixtures/recordings/my_exchange_data.metadata.json
   ```

4. **Add metadata**:
   ```json
   {
     "name": "my_exchange_data",
     "exchange": "my_exchange",
     "symbol": "BTC-USD",
     "start_time": "2024-01-01T00:00:00Z",
     "end_time": "2024-01-01T00:01:00Z",
     "tick_count": 100,
     "description": "My exchange BTC-USD data",
     "tags": ["my_exchange", "live"]
   }
   ```

5. **Run tests** to verify:
   ```bash
   pytest tests/performance/test_multi_exchange_replay_regression.py -v
   ```

## Troubleshooting

### Test Failures

If tests fail with regression violations:

1. Check if the budget is realistic for your data
2. Review the violation messages to identify the issue
3. Adjust budgets if needed or investigate performance degradation
4. Use the CLI tool to generate detailed reports

### Missing Artifacts

If artifacts aren't generated:

1. Ensure the output directory exists and is writable
2. Check for matplotlib installation if charts are missing
3. Verify test execution completed successfully

### High Latency

If latency metrics are unexpectedly high:

1. Check recording timestamps are correctly formatted
2. Verify system clock is synchronized
3. Consider network delays in live recordings
4. Review ingestion pipeline for bottlenecks

## Best Practices

1. **Version Control**: Always commit recordings with metadata
2. **Naming Convention**: Use descriptive names: `{exchange}_{symbol}_{scenario}.jsonl`
3. **Budget Tuning**: Start with relaxed budgets, tighten based on baselines
4. **Regular Updates**: Update recordings to reflect current market conditions
5. **Documentation**: Document special scenarios in metadata descriptions
6. **CI Integration**: Review performance reports in every PR
7. **Historical Tracking**: Keep baselines for trend analysis

## Future Enhancements

- [ ] Historical baseline comparison dashboard
- [ ] Automated issue creation on regression
- [ ] Multi-version comparison (current vs. previous release)
- [ ] Interactive performance dashboards
- [ ] Real-time monitoring integration
- [ ] Cross-exchange performance comparison
- [ ] Custom metric plugins
- [ ] Performance prediction models

## References

- [Performance Testing Guide](./testing.md)
- [CI/CD Documentation](../README.md#cicd)
- [Replay Recording Format](./data_formats.md)
