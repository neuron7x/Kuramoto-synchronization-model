# Hero Backtest Scenario

This directory contains the **5-minute demo that proves TradePulse is real**.

## Quick Start

Run the complete hero scenario in three commands:

```bash
# 1. Prepare data (filters BTC 1h from bundled sample)
python examples/hero_scenario/01_prepare_data.py

# 2. Run backtest (NeuroTradePulseStrategy on BTC)
python examples/hero_scenario/02_run_backtest.py

# 3. Plot equity curve
python examples/hero_scenario/03_plot_equity.py
```

Or use the CLI shortcut (once implemented):

```bash
tradepulse hero-scenario run
tradepulse hero-scenario plot
```

## What It Does

The hero scenario runs a complete, reproducible backtest demonstrating TradePulse's capabilities:

- **Instrument**: BTCUSDT spot (1-hour bars)
- **Period**: ~3 weeks (January 2024)
- **Strategy**: NeuroTradePulseStrategy
  - Combines Kuramoto oscillator synchronization
  - Ricci curvature for market geometry
  - Fractal motivation engine for neuro-inspired decisions
- **Capital**: $100,000 initial
- **Data**: Bundled in `data/sample_crypto_ohlcv.csv` (no API keys needed)

## Output

Results are saved to `results/hero/`:

- `metrics.json` - Complete performance metrics (P&L, Sharpe, drawdown, etc.)
- `equity_curve.csv` - Time series of portfolio value
- `equity_curve.png` - Publication-quality plot
- `equity_curve.pdf` - Vector graphics version
- `trades_summary.json` - Trade statistics

## Why This Scenario?

This is the **canonical demo** for TradePulse because:

1. **No secrets required** - Uses bundled data, no API keys
2. **Fast** - Runs in < 3 minutes on a typical laptop
3. **Reproducible** - Deterministic results with fixed seed
4. **Realistic** - Real market data structure with sophisticated strategy
5. **Complete** - Shows full pipeline: data → signals → backtest → metrics → visualization
6. **Tested** - Golden snapshot test ensures consistency

## Files

- `01_prepare_data.py` - Load and validate OHLCV data
- `02_run_backtest.py` - Run backtest and compute metrics
- `03_plot_equity.py` - Generate equity curve visualization
- `README.md` - This file

## Advanced Usage

Customize parameters:

```bash
# Use different symbol (if available in data)
python 01_prepare_data.py --symbol ETH

# Different initial capital
python 02_run_backtest.py --capital 50000

# Custom output location
python 02_run_backtest.py --output results/my_test
```

## Integration Testing

The hero scenario is covered by golden snapshot tests:

```bash
# Run hero scenario test
pytest tests/integration/test_hero_scenario.py -v

# Regenerate golden snapshot (after intentional algorithm changes)
python examples/hero_scenario/02_run_backtest.py
cp results/hero/metrics.json tests/golden/hero_scenario_metrics.json
```

See `tests/integration/test_hero_scenario.py` for tolerance details.
