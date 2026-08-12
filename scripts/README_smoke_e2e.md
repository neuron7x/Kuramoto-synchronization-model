# smoke_e2e.py

Nightly smoke end-to-end pipeline for GeoSync integration testing.

## Description

This script runs a comprehensive end-to-end smoke test of the GeoSync system, validating:

- Data ingestion from CSV sources
- CLI interface functionality
- Backtest engine execution
- Indicator calculation (Kuramoto-Ricci composite)
- Signal generation and trading logic
- Results aggregation and reporting

The smoke test is designed for nightly CI runs and pre-release validation.

## Usage

### Basic run with defaults

```bash
python scripts/smoke_e2e.py
```

This uses `data/sample.csv` and generates reports in `reports/smoke-e2e`.

### Specify input CSV

```bash
python scripts/smoke_e2e.py --csv data/custom_data.csv
```

### Custom output directory

```bash
python scripts/smoke_e2e.py --output-dir reports/e2e-$(date +%Y%m%d)
```

### Set random seed for reproducibility

```bash
python scripts/smoke_e2e.py --seed 42
```

### Configure backtest parameters

```bash
python scripts/smoke_e2e.py \
  --fee 0.001 \
  --momentum-window 20
```

### Combined example

```bash
python scripts/smoke_e2e.py \
  --csv data/btc_usd_2024.csv \
  --output-dir reports/validation \
  --seed 20241014 \
  --fee 0.0005 \
  --momentum-window 12
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--csv` | `data/sample.csv` | Path to CSV source data |
| `--output-dir` | `reports/smoke-e2e` | Directory for pipeline artifacts |
| `--seed` | `20240615` | Random seed for deterministic outputs |
| `--fee` | `0.0005` | Trading fee (0.05%) for backtest |
| `--momentum-window` | `12` | Lookback window for momentum signal |

## Pipeline Stages

The smoke test executes the following stages:

### 1. Data Ingestion
- Reads CSV data
- Validates required fields (ts, price, volume)
- Converts to internal Ticker format

### 2. CLI Analysis
- Executes `interfaces.cli analyze` command
- Parses JSON output
- Extracts metrics (delta_H, kappa_mean, etc.)

### 3. Signal Generation
- Builds momentum-based signal function
- Incorporates Kuramoto-Ricci metrics
- Applies smoothing and scaling

### 4. Backtest Execution
- Runs walk-forward backtest
- Applies trading fees
- Calculates performance metrics

### 5. Results Aggregation
- Collects all metrics
- Generates summary statistics
- Writes JSON report

## Output Files

The script generates several artifacts in the output directory:

- `results.json`: Complete pipeline results
- `backtest_metrics.json`: Trading performance metrics
- `signals.csv`: Generated trading signals
- `prices.csv`: Processed price data
- `analysis.json`: CLI analysis output
- `summary.txt`: Human-readable summary

## Exit Codes

- `0`: Success (all stages passed)
- `1`: Pipeline failure (any stage failed)

## Example Output

### Console Output

```
=== GeoSync Smoke E2E Pipeline ===

Stage 1: Data Ingestion
  ✓ Loaded 5000 ticks from data/sample.csv

Stage 2: CLI Analysis
  ✓ Analyzed data (delta_H=0.123, kappa_mean=-0.045)

Stage 3: Signal Generation
  ✓ Built signal function (window=12)

Stage 4: Backtest Execution
  ✓ Walk-forward backtest complete
    - Total Return: 15.3%
    - Sharpe Ratio: 1.42
    - Max Drawdown: -8.7%
    - Trades: 156

Stage 5: Results Aggregation
  ✓ Wrote results to reports/smoke-e2e/results.json

=== Pipeline Complete ===
Status: SUCCESS
Duration: 23.4s
```

### JSON Results

```json
{
  "status": "success",
  "duration_seconds": 23.4,
  "data": {
    "ticks": 5000,
    "start": "2024-01-01T00:00:00Z",
    "end": "2024-12-31T23:59:59Z"
  },
  "analysis": {
    "delta_H": 0.123,
    "kappa_mean": -0.045
  },
  "backtest": {
    "total_return": 0.153,
    "sharpe_ratio": 1.42,
    "max_drawdown": -0.087,
    "num_trades": 156
  }
}
```

## CI Integration

### GitHub Actions

The smoke test is configured to run nightly:

```yaml
name: Nightly Smoke E2E

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM UTC daily
  workflow_dispatch:

jobs:
  smoke-e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      
      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: pip install -c constraints/security.txt -r requirements.txt
      
      - name: Run smoke E2E
        run: |
          python scripts/smoke_e2e.py \
            --csv data/sample.csv \
            --seed 1337 \
            --output-dir reports/smoke-e2e
      
      - name: Upload artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: smoke-e2e-artifacts
          path: reports/smoke-e2e
```

### Local CI Simulation

```bash
# Simulate nightly run
PYTHONHASHSEED=1337 python scripts/smoke_e2e.py \
  --csv data/sample.csv \
  --seed 1337 \
  --output-dir /tmp/smoke-test

# Check results
cat /tmp/smoke-test/results.json | jq '.status'
```

## Performance Profiling

Run with profiling enabled:

```bash
python -m cProfile -o profiles/smoke-e2e.pstats \
  scripts/smoke_e2e.py \
  --csv data/sample.csv \
  --seed 1337

# Analyze profile
python -m pstats profiles/smoke-e2e.pstats
```

## Troubleshooting

### Missing Dependencies

```bash
# Install required packages
pip install -c constraints/security.txt -r requirements.txt

# Verify installation
python -c "import pandas, numpy, scipy; print('OK')"
```

### Data File Not Found

```bash
# Check file exists
ls -lh data/sample.csv

# Use absolute path
python scripts/smoke_e2e.py --csv "$(pwd)/data/sample.csv"
```

### Backtest Failures

```bash
# Reduce data size for testing
head -1000 data/large.csv > /tmp/test.csv
python scripts/smoke_e2e.py --csv /tmp/test.csv

# Adjust parameters
python scripts/smoke_e2e.py --momentum-window 5 --fee 0
```

### Reproducibility Issues

```bash
# Ensure deterministic seed
PYTHONHASHSEED=42 python scripts/smoke_e2e.py --seed 42

# Check Python version (should be 3.11+)
python --version
```

## Requirements

- Python 3.11+
- pandas
- numpy
- GeoSync modules:
  - backtest.engine
  - core.data.ingestion
  - interfaces.cli

## Performance

Typical execution times:

| Data Size | Duration |
|-----------|----------|
| 1K rows   | ~5s      |
| 5K rows   | ~15-25s  |
| 10K rows  | ~30-45s  |
| 50K rows  | ~2-3min  |

## Use Cases

1. **Nightly validation**: Ensure system integrity before releases
2. **Regression testing**: Catch breaking changes early
3. **Performance monitoring**: Track execution time trends
4. **Pre-deployment checks**: Validate before production updates
5. **Development workflow**: Quick end-to-end sanity checks

## Alerts

The CI workflow sends alerts on failure:

- **Slack**: Notification to `#geosync-alerts` channel
- **Email**: Alert to on-call engineer
- **GitHub**: Failed workflow status

Configure alerts via GitHub Secrets:
- `SMOKE_SLACK_WEBHOOK_URL`
- `SMOKE_ALERT_EMAIL_SERVER`
- `SMOKE_ALERT_EMAIL_TO`

## Best Practices

1. **Run regularly**: Schedule nightly or on every PR
2. **Monitor trends**: Track execution time and metrics over time
3. **Keep data fresh**: Update sample.csv periodically
4. **Review failures**: Investigate all smoke test failures promptly
5. **Profile periodically**: Identify performance regressions

## Related Scripts

- `data_sanity.py`: Validate CSV data quality
- `integrate_kuramoto_ricci.py`: Run detailed indicator analysis
- `resilient_data_sync.py`: Download test data reliably
