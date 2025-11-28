# TradePulse Sample Data

This directory contains sample datasets for testing, development, and demonstration purposes.

## Available Datasets

| File | Description | Rows | Use Case |
|------|-------------|------|----------|
| `sample.csv` | Simple price/volume time series | 500 | Basic indicator testing |
| `sample_ohlc.csv` | OHLCV candlestick data | 300 | Advanced indicator testing |
| `sample_crypto_ohlcv.csv` | Multi-asset crypto (BTC, ETH, SOL) | 504 | Multi-asset analysis |
| `sample_stocks_daily.csv` | Daily stock data (AAPL, SPY) | 60 | Portfolio analysis |

## Golden Datasets

The `golden/` subdirectory contains versioned baseline datasets for regression testing:

- `indicator_macd_baseline.csv` - MACD indicator validation data

## Data Formats

### Simple Price/Volume (sample.csv)

```csv
ts,price,volume
1,100.15,1010
2,100.30,1020
...
```

### OHLCV Format (sample_ohlc.csv, sample_crypto_ohlcv.csv)

```csv
timestamp,symbol,open,high,low,close,volume
2024-01-01 00:00:00+00:00,BTC,45173.76,45200.71,44948.90,45084.24,7985.28
...
```

## Generating New Sample Data

Use the data generation script to create custom datasets:

```bash
# Generate single asset data
python scripts/generate_sample_ohlcv.py --output data/my_data.csv --symbols ASSET

# Generate multi-asset crypto data
python scripts/generate_sample_ohlcv.py --symbols BTC ETH SOL --days 30 --timeframe 1h

# Generate daily stock data
python scripts/generate_sample_ohlcv.py --symbols AAPL SPY --days 90 --timeframe 1d

# Generate 1-minute high-frequency data
python scripts/generate_sample_ohlcv.py --symbols BTC --days 1 --timeframe 1m
```

### Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `--output, -o` | Output file path | `data/sample_ohlcv_generated.csv` |
| `--symbols, -s` | Asset symbols to generate | `ASSET` |
| `--days, -d` | Number of days of data | 7 |
| `--timeframe, -t` | Bar timeframe (1m, 5m, 15m, 30m, 1h, 4h, 1d) | `1h` |
| `--seed` | Random seed for reproducibility | 42 |
| `--start-date` | Start date in ISO format | `2024-01-01` |

## Data Validation

Validate data quality before using in analysis:

```python
from core.data.validation import validate_ohlcv
import pandas as pd

df = pd.read_csv("data/sample_crypto_ohlcv.csv")
result = validate_ohlcv(df, price_col="close")

if result.valid:
    print("Data passed validation")
else:
    print(f"Issues: {result.issues}")
```

Run validation script on golden datasets:

```bash
python scripts/data_sanity.py data/golden
```

## Usage Examples

### Quick Start Analysis

```python
import pandas as pd
from core.indicators.kuramoto_ricci_composite import TradePulseCompositeEngine

# Load sample data
df = pd.read_csv("data/sample_crypto_ohlcv.csv")
btc = df[df["symbol"] == "BTC"].copy()
btc.set_index("timestamp", inplace=True)

# Analyze market regime
engine = TradePulseCompositeEngine()
snapshot = engine.analyze_market(btc)

print(f"Phase: {snapshot.phase.value}")
print(f"Confidence: {snapshot.confidence:.3f}")
```

### Backtesting

```python
import numpy as np
import pandas as pd
from backtest.event_driven import EventDrivenBacktestEngine

# Load data
df = pd.read_csv("data/sample_ohlc.csv")
prices = df["close"].values

# Define simple momentum strategy
def momentum_signal(prices):
    returns = np.diff(prices, prepend=prices[0])
    signal = np.where(returns > 0, 1.0, -1.0)
    signal[:20] = 0  # Warmup
    return signal

# Run backtest
engine = EventDrivenBacktestEngine()
result = engine.run(prices, momentum_signal, initial_capital=100_000)

print(f"PnL: ${result.pnl:,.2f}")
print(f"Max Drawdown: {result.max_dd:.2%}")
```

## Maintenance

- Sample datasets should remain stable for reproducibility
- Update checksums in `docs/data/sample_market_data.md` when modifying files
- Add new datasets to this README when created
- Run validation tests before committing changes

## Related Documentation

- [Data Validation Guide](../docs/data/sample_market_data.md)
- [Testing Guide](../TESTING.md)
- [Examples](../examples/)
