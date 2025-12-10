# Hero Scenario: Simple BTC Backtest Example

This document describes the "hero scenario" - a simple, reproducible backtest example that demonstrates TradePulse's core backtesting capabilities with minimal dependencies.

## Overview

The hero scenario is a **one-command, reproducible backtest** that:
- ✅ Runs on a single computer with minimal dependencies
- ✅ Uses real hourly BTC/USD data (7 days, 168 data points)
- ✅ Implements a simple 24-hour momentum strategy
- ✅ Produces equity curve, P&L, Sharpe ratio, and other metrics
- ✅ Has a "golden snapshot" for regression testing
- ✅ Takes < 5 seconds to run

## Quick Start

```bash
# 1. Install dependencies
pip install numpy pandas matplotlib

# 2. Run the complete scenario (3 steps)
cd examples/hero_scenario/
python 01_prepare_data.py      # Extract BTC data
python 02_run_backtest.py       # Run backtest
python 03_plot_equity.py        # Generate plot (optional)

# 3. View results
cat ../../results/hero/metrics.json
open ../../results/hero/equity_curve.png  # macOS
# or: xdg-open ../../results/hero/equity_curve.png  # Linux
```

## Scenario Details

### Data
- **Symbol:** BTC/USD
- **Timeframe:** 1 hour
- **Period:** January 1-7, 2024 (7 days, 168 bars)
- **Source:** Pre-existing `data/sample_crypto_ohlcv.csv`
- **Size:** 13.5 KB

### Strategy
- **Type:** Simple momentum
- **Logic:** If price > price 24 hours ago, go long; if price < price 24 hours ago, go short
- **Position sizing:** Fixed (±1 unit)
- **Transaction cost:** 0.1% per trade

### Initial Conditions
- **Capital:** $100,000
- **Leverage:** None (cash-only)
- **Slippage:** None (uses close prices)

### Expected Results
Based on golden snapshot (as of 2024-12-10):

| Metric | Value |
|--------|-------|
| **P&L** | $827.93 (+0.83%) |
| **Max Drawdown** | -$2,946.93 (-2.95%) |
| **Number of Trades** | 15 |
| **Sharpe Ratio** | 0.521 (annualized) |
| **Commission Cost** | $662.52 |

## Step-by-Step Guide

### Step 1: Prepare Data

```bash
cd examples/hero_scenario/
python 01_prepare_data.py
```

**What it does:**
- Loads `data/sample_crypto_ohlcv.csv`
- Filters to BTC only (168 rows)
- Validates data quality (no NaNs, positive prices)
- Saves to `data/hero/btc_1h.csv`

**Output:**
```
============================================================
HERO SCENARIO: Data Preparation
============================================================

Loading data from: /path/to/data/sample_crypto_ohlcv.csv
  Total rows loaded: 504
  Symbols: ['BTC', 'ETH', 'SOL']

Filtering to BTC only: 168 rows
  Date range: 2024-01-01 00:00:00+00:00 to 2024-01-07 23:00:00+00:00
  Price range: $41970.59 to $46546.09

✓ Data saved to: /path/to/data/hero/btc_1h.csv
```

### Step 2: Run Backtest

```bash
python 02_run_backtest.py
```

**What it does:**
- Loads BTC data from `data/hero/btc_1h.csv`
- Executes simple momentum backtest
- Calculates performance metrics
- Saves results to:
  - `results/hero/equity_curve.csv` - Timestamped equity values
  - `results/hero/metrics.json` - Performance metrics

**Output:**
```
============================================================
HERO SCENARIO: Backtest Execution
============================================================

Loading data from: /path/to/data/hero/btc_1h.csv
  Data points: 168
  Price range: $41970.59 to $46546.09

Configuration:
  Initial capital: $100,000.00
  Transaction fee: 0.10%
  Strategy: Simple Momentum (24h lookback)

Running backtest...
✓ Backtest complete

============================================================
RESULTS
============================================================
P&L: $827.93 (+0.83%)
Max Drawdown: $2,946.93 (2.95%)
Number of Trades: 15
Sharpe Ratio (annualized): 0.521
Commission Cost: $662.52

✓ Equity curve saved to: /path/to/results/hero/equity_curve.csv
✓ Metrics saved to: /path/to/results/hero/metrics.json
```

### Step 3: Plot Results (Optional)

```bash
python 03_plot_equity.py
```

**What it does:**
- Loads equity curve and metrics
- Generates visualization with matplotlib
- Saves to `results/hero/equity_curve.png`

**Requires:** `pip install matplotlib`

## Integration with CI

The hero scenario includes a regression test that verifies results match the golden snapshot:

```bash
# Run the test
pytest tests/integration/test_hero_scenario.py

# Or directly
python -c "
import sys
sys.path.insert(0, 'tests/integration')
from test_hero_scenario import test_hero_scenario_metrics
test_hero_scenario_metrics()
"
```

**What it checks:**
- P&L within 5% of golden value
- Max drawdown within 5% of golden value
- Trade count within ±2 trades
- Sharpe ratio within 20% of golden value

### Adding to Release Gate

To include in the release-gate workflow, add to `.github/workflows/release-gate.yml`:

```yaml
- name: Run hero scenario test
  run: |
    python -c "
    import sys
    sys.path.insert(0, 'tests/integration')
    from test_hero_scenario import test_hero_scenario_metrics
    test_hero_scenario_metrics()
    "
```

This ensures the core backtesting engine doesn't regress.

## File Structure

```
examples/hero_scenario/
├── 01_prepare_data.py      # Data extraction and validation
├── 02_run_backtest.py       # Backtest execution
└── 03_plot_equity.py        # Visualization (optional)

data/hero/
└── btc_1h.csv              # Prepared BTC data

results/hero/
├── equity_curve.csv        # Timestamped equity values
├── equity_curve.png        # Equity plot (if step 3 run)
└── metrics.json            # Performance metrics

tests/
├── golden/
│   └── hero_scenario_metrics.json  # Golden snapshot
└── integration/
    └── test_hero_scenario.py       # Regression test
```

## Why This Scenario?

### Stability
- **No external APIs:** Uses pre-packaged sample data
- **No secrets:** No API keys or credentials required
- **Deterministic:** Same input → same output
- **Fast:** Completes in < 5 seconds

### Simplicity
- **One asset:** BTC only
- **Short period:** 7 days (manageable data size)
- **Simple strategy:** Easy to understand momentum logic
- **Minimal dependencies:** Only numpy, pandas (matplotlib optional)

### Representativeness
- **Real data structure:** Uses actual OHLCV format
- **Realistic costs:** 0.1% transaction fees
- **Core engine:** Tests actual backtest engine, not mocks

## Troubleshooting

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'pandas'`

**Solution:**
```bash
pip install numpy pandas
```

### Data Not Found

**Problem:** `ERROR: Data file not found`

**Solution:**
```bash
# Run step 1 first
python examples/hero_scenario/01_prepare_data.py
```

### Test Failures

**Problem:** Metrics don't match golden snapshot

**Possible causes:**
1. Code changes that affect backtest engine
2. Different numpy/pandas versions
3. Floating-point precision differences

**Investigation:**
```bash
# Run backtest and compare manually
python examples/hero_scenario/02_run_backtest.py
cat results/hero/metrics.json
cat tests/golden/hero_scenario_metrics.json
```

If the difference is < 5%, it may be acceptable floating-point variance.

### Plot Not Generated

**Problem:** Matplotlib not installed

**Solution:**
```bash
pip install matplotlib
python examples/hero_scenario/03_plot_equity.py
```

## Customization

### Different Time Period

Edit `01_prepare_data.py` to filter different date range:

```python
btc = btc[(btc['timestamp'] >= '2024-01-01') & 
          (btc['timestamp'] <= '2024-01-14')]  # 2 weeks
```

### Different Strategy

Edit `02_run_backtest.py` to implement your strategy:

```python
def my_strategy(prices, window=24):
    signal = np.zeros_like(prices)
    # Your logic here
    return signal
```

### Update Golden Snapshot

After validating new results are correct:

```bash
python examples/hero_scenario/02_run_backtest.py
cp results/hero/metrics.json tests/golden/hero_scenario_metrics.json
```

## Next Steps

After running the hero scenario:

1. **Explore other strategies:** Modify `02_run_backtest.py` with your own logic
2. **Add more symbols:** Edit `01_prepare_data.py` to include ETH, SOL
3. **Longer backtests:** Use full `data/sample_crypto_ohlcv.csv` (504 bars)
4. **Advanced metrics:** Add Sortino ratio, Calmar ratio, etc.
5. **Optimization:** Parameter sweep over different lookback windows

## Related Documentation

- [Backtest Engine](../backtest/README.md) - Full backtesting documentation
- [TEST_PLAN.md](../tests/TEST_PLAN.md) - Testing strategy
- [RELEASE_GATES.md](RELEASE_GATES.md) - CI/CD integration
- [Examples](../examples/) - More complex examples

---

**Last Updated:** 2024-12-10  
**Version:** 1.0.0  
**Status:** Production-ready
