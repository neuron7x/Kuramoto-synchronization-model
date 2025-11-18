# Performance Regression Testing Guide

## Quick Start

This guide shows how to use the multi-exchange replay performance testing infrastructure to detect regressions and ensure system performance remains within acceptable bounds.

## 🚀 Running Performance Tests

### Run all performance regression tests:
```bash
pytest tests/performance/test_multi_exchange_replay_regression.py -v
```

### Run tests for specific exchange:
```bash
pytest tests/performance/test_multi_exchange_replay_regression.py::test_coinbase_btcusd_replay_meets_budget -v
```

### Generate performance reports:
```bash
python scripts/performance/generate_replay_report.py \
  --output-dir reports/performance \
  --generate-charts \
  --fail-on-regression
```

## 📊 What Gets Measured

### Latency Metrics
- **Median**: Typical processing time (50th percentile)
- **P95**: 95% of requests complete within this time
- **P99**: 99% of requests complete within this time  
- **Max**: Worst-case latency observed

### Throughput Metrics
- **Ticks per Second (TPS)**: Rate of market data processing
- Indicates system capacity and scalability

### Slippage Metrics
- **Median Spread**: Typical bid-ask spread cost
- **P95 Spread**: High-impact scenario cost
- Measured in basis points (bps)

## 🎯 Performance Budgets

Budgets are defined in `configs/performance_budgets.yaml`:

```yaml
exchanges:
  coinbase:
    latency_median_ms: 50.0
    latency_p95_ms: 90.0
    throughput_min_tps: 5.0
    slippage_median_bps: 3.0
```

### Priority Order
1. **Scenario** (e.g., flash_crash, stable_market)
2. **Exchange** (e.g., coinbase, binance)
3. **Environment** (e.g., production, staging)
4. **Component** (e.g., ingestion, execution)
5. **Default** (fallback)

## 📝 Recording Format

Create recordings in JSONL format:

```json
{"exchange_ts": "2024-03-05T14:30:00.123456Z", "ingest_ts": "2024-03-05T14:30:00.168923Z", "bid": 64123.12, "ask": 64123.54, "last": 64123.33, "volume": 0.18}
```

With optional metadata file (`recording.metadata.json`):

```json
{
  "name": "coinbase_btcusd",
  "exchange": "coinbase",
  "symbol": "BTC-USD",
  "start_time": "2024-03-05T14:30:00.123456Z",
  "end_time": "2024-03-05T14:30:01.023456Z",
  "tick_count": 10,
  "description": "Live market data for performance testing",
  "tags": ["coinbase", "live", "performance"]
}
```

## 🔄 CI/CD Integration

The GitHub Actions workflow runs automatically:
- ✅ On pull requests affecting performance-critical code
- ✅ On pushes to main branch
- ✅ Nightly at 2 AM UTC for trend analysis
- ✅ Manual workflow dispatch

### Artifacts Published
1. **performance_report.json** - Complete metrics
2. **performance_summary.md** - Human-readable summary
3. **latency_chart.png** - Latency visualization
4. **throughput_chart.png** - Throughput comparison
5. **slippage_chart.png** - Slippage distribution
6. **issue_template_*.md** - GitHub issue templates for regressions

## 🔍 Interpreting Results

### ✅ Passing Test
```
✅ Passed
Latency median: 44.57ms (budget: 50.00ms)
Throughput: 11.11 tps (budget: 5.00 tps)
Slippage median: 0.06bps (budget: 3.00bps)
```

### ⚠️ Regression Detected
```
⚠️  REGRESSION DETECTED
- Latency P95 105.00ms exceeds budget 100.00ms
- Throughput 4.5 tps below budget 5.0 tps
```

## 🛠️ CLI Options

```bash
# Basic usage
python scripts/performance/generate_replay_report.py

# Custom budgets
python scripts/performance/generate_replay_report.py \
  --latency-median-ms 40.0 \
  --throughput-min-tps 15.0

# Generate artifacts
python scripts/performance/generate_replay_report.py \
  --generate-charts \
  --generate-issues

# Fail on regression (for CI)
python scripts/performance/generate_replay_report.py \
  --fail-on-regression
```

## 📈 Viewing Reports

### In GitHub Actions
1. Go to Actions → Multi-Exchange Replay Regression
2. Click on a run
3. View summary in step summary
4. Download artifacts for detailed reports

### Locally
```bash
# Generate report
python scripts/performance/generate_replay_report.py --output-dir ./reports

# View summary
cat reports/performance_summary.md

# View JSON
cat reports/performance_report.json | jq
```

## 🔧 Adding New Recordings

1. **Record exchange data** to JSONL file
2. **Create metadata** file (optional but recommended)
3. **Place in** `tests/fixtures/recordings/`
4. **Run tests** to validate
5. **Commit** both files

Example:
```bash
# Create recording
echo '{"exchange_ts": "...", "ingest_ts": "...", ...}' > tests/fixtures/recordings/my_data.jsonl

# Create metadata
cat > tests/fixtures/recordings/my_data.metadata.json << EOF
{
  "name": "my_data",
  "exchange": "binance",
  "symbol": "BTC-USDT",
  "start_time": "2024-01-01T00:00:00Z",
  "end_time": "2024-01-01T01:00:00Z",
  "tick_count": 1000,
  "description": "Binance BTC-USDT recording",
  "tags": ["binance", "live"]
}
EOF

# Test
pytest tests/performance/test_multi_exchange_replay_regression.py -v
```

## 📚 Further Reading

- [Full Documentation](docs/performance_testing.md)
- [Budget Configuration](configs/performance_budgets.yaml)
- [GitHub Workflow](.github/workflows/multi-exchange-replay-regression.yml)
- [Test Suite](tests/performance/test_multi_exchange_replay_regression.py)

## 🤝 Contributing

When adding performance-sensitive code:
1. Add replay recordings for test coverage
2. Define appropriate budgets
3. Run regression tests locally
4. Check CI reports in PR

## 🆘 Troubleshooting

### Tests failing with regressions?
- Check if budgets are realistic for your data
- Review violation messages
- Compare against historical baselines
- Consider environment factors (CPU, network)

### Charts not generating?
- Install matplotlib: `pip install matplotlib`
- Or disable: `--no-generate-charts`

### Recording format errors?
- Validate JSON: `cat recording.jsonl | jq`
- Check timestamp format: ISO 8601 with timezone
- Ensure all required fields present

## 📊 Performance Goals

| Environment | Latency (P95) | Throughput | Slippage (P95) |
|-------------|---------------|------------|----------------|
| Production  | < 80ms        | > 15 tps   | < 10 bps       |
| Staging     | < 100ms       | > 8 tps    | < 15 bps       |
| Development | < 200ms       | > 1 tps    | < 100 bps      |

---

**Last Updated**: 2025-11-11  
**Version**: 1.0.0  
**Maintainer**: TradePulse Team
