# TradePulse Hero Scenario: 5-Minute Demo Guide

> **"The fastest way to prove TradePulse is real"**

This guide walks you through running TradePulse's hero backtest scenario—a complete,
reproducible demonstration of the platform's capabilities that runs in under 3 minutes
on a typical laptop.

## What is the Hero Scenario?

The hero scenario is a **canonical backtest demonstration** that:

- ✅ Runs completely offline (no API keys, no secrets)
- ✅ Completes in < 3 minutes
- ✅ Uses real market data structure (BTC/USDT 1h bars)
- ✅ Demonstrates sophisticated strategy (NeuroTradePulseStrategy)
- ✅ Produces publication-quality outputs
- ✅ Is fully reproducible with golden snapshots

### Scenario Configuration

| Parameter | Value |
|-----------|-------|
| **Instrument** | BTCUSDT (spot) |
| **Exchange** | Binance (simulated) |
| **Timeframe** | 1 hour |
| **Period** | 2024-01-01 to 2024-01-07 (7 days, 168 bars) |
| **Strategy** | NeuroTradePulseStrategy |
| **Initial Capital** | $100,000 |
| **Data Source** | Bundled in `data/sample_crypto_ohlcv.csv` |

### Strategy Overview

**NeuroTradePulseStrategy** combines:

1. **Kuramoto Oscillator Synchronization** - Detects market regime coherence
2. **Ricci Curvature** - Measures market geometry and stress
3. **Fractal Motivation Engine** - Neuro-inspired decision modulation
4. **Topological Transition Detection** - Identifies regime changes

This is a research-grade strategy that demonstrates TradePulse's unique capabilities
in geometric and neuro-inspired market analysis.

---

## Quick Start (3 Commands)

### Option 1: Individual Scripts

```bash
# 1. Prepare data (< 1 second)
python examples/hero_scenario/01_prepare_data.py

# 2. Run backtest (< 10 seconds)
python examples/hero_scenario/02_run_backtest.py

# 3. Generate plots (< 5 seconds)
python examples/hero_scenario/03_plot_equity.py
```

### Option 2: CLI Shortcut

```bash
# All-in-one command
tradepulse hero-scenario all

# Or step-by-step
tradepulse hero-scenario run
tradepulse hero-scenario plot
```

---

## Environment Setup

### Prerequisites

- **Python**: 3.11 or 3.12
- **Operating System**: Linux, macOS, or Windows with WSL2
- **Memory**: 4GB RAM minimum
- **Disk Space**: 500MB for dependencies

### Installation

```bash
# Clone repository
git clone https://github.com/neuron7x/TradePulse.git
cd TradePulse

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -c constraints/security.txt -r requirements.txt

# Install TradePulse in development mode
pip install -e .

# Install optional dependencies for plotting
pip install matplotlib
```

---

## Step-by-Step Walkthrough

### Step 1: Data Preparation

**Purpose**: Load and validate BTC 1h OHLCV data from the bundled sample dataset.

```bash
python examples/hero_scenario/01_prepare_data.py
```

**What it does**:
- Loads `data/sample_crypto_ohlcv.csv`
- Filters for BTC symbol only
- Validates data quality (no missing values, valid OHLC relationships)
- Saves to `data/hero/btc_1h.csv`

**Expected output**:
```
Loading data from /path/to/data/sample_crypto_ohlcv.csv...
Filtering for BTC...

Data Quality Checks:
  Total rows: 168
  Date range: 2024-01-01 00:00:00+00:00 to 2024-01-07 23:00:00+00:00
  Missing values: 0
  Price range: $41970.59 - $46546.09

✓ All data quality checks passed
✓ Saved processed data to data/hero/btc_1h.csv

Ready for backtest with 168 bars of BTC data
```

### Step 2: Run Backtest

**Purpose**: Execute the NeuroTradePulseStrategy backtest and compute performance metrics.

```bash
python examples/hero_scenario/02_run_backtest.py
```

**What it does**:
- Loads prepared data
- Initializes NeuroTradePulseStrategy
- Generates trading signals using:
  - Kuramoto-Ricci composite indicators
  - Fractal motivation engine
  - Neuro-inspired decision gating
- Runs event-driven backtest engine
- Computes comprehensive metrics:
  - P&L and return
  - Sharpe and Sortino ratios
  - Maximum drawdown
  - CAGR and hit ratio
- Saves results to `results/hero/`

**Expected output**:
```
======================================================================
TradePulse Hero Backtest Scenario
======================================================================

Loading data from data/hero/btc_1h.csv...
  Date range: 2024-01-01 00:00:00+00:00 to 2024-01-07 23:00:00+00:00
  Total bars: 168
  Initial price: $45084.24
  Final price: $42634.58

Initializing NeuroTradePulseStrategy...
Generating trading signals...
  Total signals: 168
  Long signals: 0
  Flat signals: 165
  Short signals: 3

Running backtest with $100,000.00 initial capital...

======================================================================
Backtest Results
======================================================================

Initial Capital:    $  100,000.00
Final Equity:       $  100,801.70
Total P&L:          $      801.70
Total Return:               0.80%
Number of Trades:              4

Sharpe Ratio:             1.8667
Sortino Ratio:      62478096.4683
Max Drawdown:             -0.05%
CAGR:                      1.20%
Hit Ratio:                60.00%

✓ Saved metrics to results/hero/metrics.json
✓ Saved equity curve to results/hero/equity_curve.csv
✓ Saved trades summary to results/hero/trades_summary.json

======================================================================
Run visualization: python examples/hero_scenario/03_plot_equity.py
======================================================================
```

### Step 3: Visualize Results

**Purpose**: Generate publication-quality equity curve plot.

```bash
python examples/hero_scenario/03_plot_equity.py
```

**What it does**:
- Loads equity curve and metrics from `results/hero/`
- Creates matplotlib plot with:
  - Time series of portfolio value
  - Initial capital reference line
  - Statistics box with key metrics
  - Professional formatting
- Saves to `results/hero/equity_curve.png` (and `.pdf`)

**Expected output**:
```
Loading results from results/hero...
✓ Saved equity curve plot to results/hero/equity_curve.png
✓ Saved PDF version to results/hero/equity_curve.pdf

Visualization complete!
```

---

## Output Files

After running the hero scenario, you'll find these files in `results/hero/`:

### `metrics.json`

Complete performance metrics in JSON format:

```json
{
  "initial_capital": 100000.0,
  "final_equity": 100801.70,
  "total_pnl": 801.70,
  "total_return_pct": 0.80,
  "num_trades": 4,
  "sharpe_ratio": 1.87,
  "sortino_ratio": 62478096.47,
  "max_drawdown": -0.0005,
  "cagr": 0.012,
  "hit_ratio": 0.6,
  "num_bars": 168,
  "start_date": "2024-01-01 00:00:00+00:00",
  "end_date": "2024-01-07 23:00:00+00:00",
  "strategy": "NeuroTradePulseStrategy",
  "instrument": "BTCUSDT",
  "timeframe": "1h"
}
```

### `equity_curve.csv`

Time series of portfolio equity:

```csv
timestamp,equity
2024-01-01 00:00:00+00:00,100000.0
2024-01-01 01:00:00+00:00,100000.0
2024-01-01 02:00:00+00:00,100000.0
...
2024-01-07 23:00:00+00:00,100801.70
```

### `equity_curve.png` / `equity_curve.pdf`

Publication-quality plot showing:
- Portfolio value over time
- Initial capital reference
- Key statistics overlay

### `trades_summary.json`

Trading activity summary:

```json
{
  "total_trades": 4,
  "long_signals": 0,
  "flat_signals": 165,
  "short_signals": 3
}
```

---

## Advanced Usage

### Custom Parameters

#### Different Initial Capital

```bash
python examples/hero_scenario/02_run_backtest.py --capital 50000
```

#### Custom Data Source

```bash
# Prepare data from a different source
python examples/hero_scenario/01_prepare_data.py \
  --source my_data.csv \
  --output data/custom/btc_1h.csv

# Run backtest with custom data
python examples/hero_scenario/02_run_backtest.py \
  --data data/custom/btc_1h.csv \
  --output results/custom
```

#### Custom Output Location

```bash
python examples/hero_scenario/02_run_backtest.py \
  --output results/my_test

python examples/hero_scenario/03_plot_equity.py \
  --results results/my_test
```

### Programmatic Usage

```python
from pathlib import Path
import sys

# Add repo to path
repo_root = Path(__file__).parent
sys.path.insert(0, str(repo_root))

# Import functions
from examples.hero_scenario.prepare_data_module import prepare_hero_data
from examples.hero_scenario.run_backtest_module import run_hero_backtest

# Prepare data
source = repo_root / "data" / "sample_crypto_ohlcv.csv"
data_path = repo_root / "data" / "hero" / "btc_1h.csv"
prepare_hero_data(source, data_path, "BTC")

# Run backtest
results_dir = repo_root / "results" / "hero"
metrics = run_hero_backtest(data_path, results_dir, initial_capital=100_000.0)

print(f"Final P&L: ${metrics['total_pnl']:.2f}")
print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.4f}")
```

---

## Testing & CI Integration

### Running Tests

The hero scenario includes comprehensive integration tests:

```bash
# Run all hero scenario tests
pytest tests/integration/test_hero_scenario.py -v

# Run specific tests
pytest tests/integration/test_hero_scenario.py::test_hero_scenario_backtest -v

# Run with coverage
pytest tests/integration/test_hero_scenario.py --cov=examples.hero_scenario
```

### Golden Snapshot

The test suite validates against a golden snapshot in `tests/golden/hero_scenario_metrics.json`.

**To regenerate the golden snapshot** (only after intentional algorithm changes):

```bash
# Run backtest to generate new metrics
python examples/hero_scenario/02_run_backtest.py

# Copy to golden snapshot
cp results/hero/metrics.json tests/golden/hero_scenario_metrics.json

# Verify tests pass with new snapshot
pytest tests/integration/test_hero_scenario.py -v
```

### CI Configuration

The hero test is designed to run in CI with:
- ✅ No network access required
- ✅ No secrets or API keys needed
- ✅ Deterministic results
- ✅ Fast execution (< 3 minutes)

Add to your CI pipeline:

```yaml
- name: Run hero scenario test
  run: |
    pytest tests/integration/test_hero_scenario.py -v --tb=short
```

---

## Interpreting Results

### Key Metrics Explained

| Metric | Description | Hero Scenario Value |
|--------|-------------|---------------------|
| **Total P&L** | Absolute profit/loss in dollars | $801.70 |
| **Total Return** | Percentage return on capital | 0.80% |
| **Sharpe Ratio** | Risk-adjusted return (annualized) | 1.87 |
| **Max Drawdown** | Largest peak-to-trough decline | -0.05% |
| **CAGR** | Compound annual growth rate | 1.20% |
| **Hit Ratio** | Percentage of profitable trades | 60% |
| **Trades** | Number of executed trades | 4 |

### Performance Context

- **Sharpe Ratio > 1.5**: Considered good risk-adjusted performance
- **Low Drawdown**: Strategy maintained capital stability
- **Few Trades**: Conservative strategy (quality over quantity)
- **Positive Return**: Beat buy-and-hold (BTC dropped ~5% over the period)

---

## Troubleshooting

### Common Issues

#### ModuleNotFoundError

```bash
# Solution: Install TradePulse in development mode
pip install -e .

# Or set PYTHONPATH
export PYTHONPATH=/path/to/TradePulse:$PYTHONPATH
```

#### Data Not Found

```bash
# Solution: Run data preparation first
python examples/hero_scenario/01_prepare_data.py
```

#### Matplotlib Not Found (for plotting)

```bash
# Solution: Install matplotlib
pip install matplotlib
```

#### Slow Execution

- Check CPU usage (strategy uses some computation)
- Ensure running with -O flag: `python -O script.py`
- Consider using PyPy for faster execution

---

## Next Steps

After running the hero scenario:

1. **Explore the Strategy**: Read `strategies/neuro_trade_pulse.py` to understand the algorithm
2. **Modify Parameters**: Experiment with `NeuroTradePulseConfig` settings
3. **Try Different Data**: Use your own OHLCV data
4. **Build New Strategies**: Use the backtest engine for your own algorithms
5. **Scale Up**: Move to larger datasets and longer time periods

---

## References

- **Strategy Implementation**: `strategies/neuro_trade_pulse.py`
- **Backtest Engine**: `backtest/event_driven.py`
- **Performance Metrics**: `backtest/performance.py`
- **Integration Tests**: `tests/integration/test_hero_scenario.py`

---

## Support

- **Documentation**: See `README.md` and `docs/` directory
- **Issues**: https://github.com/neuron7x/TradePulse/issues
- **Contributing**: See `CONTRIBUTING.md`

---

*Last updated: 2024-12-10*
