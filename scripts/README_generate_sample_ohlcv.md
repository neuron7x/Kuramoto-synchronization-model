# generate_sample_ohlcv.py

Generate comprehensive OHLCV (Open, High, Low, Close, Volume) sample data for testing and development.

## Overview

This script creates realistic OHLCV time series data with configurable market regimes, useful for testing trading algorithms, indicators, and market analysis tools. It supports:

- Single and multi-asset generation
- Multiple timeframes (1m to 1d)
- Configurable date ranges
- Reproducible output with seed control
- Asset-specific price levels and volatility

## Quick Start

```bash
# Generate default single asset data
python scripts/generate_sample_ohlcv.py

# Generate multi-asset crypto data for 7 days
python scripts/generate_sample_ohlcv.py --symbols BTC ETH SOL --days 7

# Generate daily stock data for 30 days
python scripts/generate_sample_ohlcv.py --symbols AAPL SPY --days 30 --timeframe 1d

# Generate 1-minute high-frequency data
python scripts/generate_sample_ohlcv.py --symbols BTC --days 1 --timeframe 1m
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--output, -o` | Output CSV file path | `data/sample_ohlcv_generated.csv` |
| `--symbols, -s` | Asset symbols to generate (space-separated) | `ASSET` |
| `--days, -d` | Number of days of data to generate | 7 |
| `--timeframe, -t` | Bar timeframe: 1m, 5m, 15m, 30m, 1h, 4h, 1d | `1h` |
| `--seed` | Random seed for reproducibility | 42 |
| `--start-date` | Start date in ISO format (YYYY-MM-DD) | `2024-01-01` |
| `--verbose, -v` | Enable verbose logging | False |

## Supported Assets

The following assets have pre-configured base prices and volatility:

| Symbol | Base Price | Daily Volatility | Asset Type |
|--------|------------|------------------|------------|
| BTC | $45,000 | 3% | Cryptocurrency |
| ETH | $2,500 | 4% | Cryptocurrency |
| SOL | $100 | 5% | Cryptocurrency |
| AAPL | $180 | 1.5% | Stock |
| SPY | $480 | 1% | ETF |
| EURUSD | $1.08 | 0.5% | Forex |
| GOLD | $2,000 | 0.8% | Commodity |

Unknown symbols use default values: base_price=100.0, volatility=0.02

## Output Format

The generated CSV has the following columns:

```csv
timestamp,symbol,open,high,low,close,volume
2024-01-01 00:00:00+00:00,BTC,45173.76,45200.71,44948.90,45084.24,7985.28
```

### Column Descriptions

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | datetime (UTC) | Bar timestamp with timezone |
| `symbol` | string | Asset symbol |
| `open` | float | Opening price (4 decimal places) |
| `high` | float | Highest price during bar |
| `low` | float | Lowest price during bar |
| `close` | float | Closing price |
| `volume` | float | Trading volume (2 decimal places) |

## Data Generation Method

1. **Price Series**: Uses geometric Brownian motion with configurable drift and volatility
2. **OHLC Generation**: 
   - Open = previous close with small gap noise
   - High = max(open, close) × (1 + random deviation)
   - Low = min(open, close) × (1 − random deviation)
   - Close = from price series
3. **Volume**: Log-normal distribution scaled by timeframe
4. **Volatility Scaling**: Automatically scaled for different timeframes

## Data Quality Guarantees

The generated data satisfies the following constraints:

- ✅ High ≥ Low (always)
- ✅ High ≥ max(Open, Close)
- ✅ Low ≤ min(Open, Close)
- ✅ All prices > 0
- ✅ All volumes > 0
- ✅ No NaN values
- ✅ Sequential timestamps
- ✅ Consistent timezone (UTC)

## Python API

The script can be imported and used programmatically:

```python
from scripts.generate_sample_ohlcv import (
    generate_market_data,
    generate_multi_asset_data,
)

# Generate single asset data
df = generate_market_data(
    symbol="BTC",
    days=7,
    timeframe="1h",
    base_price=45000.0,
    volatility=0.03,
    seed=42,
)

# Generate multi-asset data
df = generate_multi_asset_data(
    symbols=["BTC", "ETH", "SOL"],
    days=30,
    timeframe="1h",
    seed=42,
)
```

## Use Cases

### Testing Indicators

```python
import pandas as pd
from core.indicators.kuramoto_ricci_composite import TradePulseCompositeEngine

df = pd.read_csv("data/sample_crypto_ohlcv.csv")
btc = df[df["symbol"] == "BTC"].copy()

engine = TradePulseCompositeEngine()
snapshot = engine.analyze_market(btc)
print(f"Phase: {snapshot.phase.value}")
```

### Backtesting

```python
from backtest.event_driven import EventDrivenBacktestEngine, CSVChunkDataHandler

handler = CSVChunkDataHandler(
    path="data/sample_crypto_ohlcv.csv",
    price_column="close",
    symbol="BTC",
)

engine = EventDrivenBacktestEngine()
result = engine.run(
    prices=df[df["symbol"] == "BTC"]["close"].values,
    signal_fn=my_signal_function,
    data_handler=handler,
)
```

### Multi-Asset Analysis

```python
df = pd.read_csv("data/sample_crypto_ohlcv.csv")
for symbol in df["symbol"].unique():
    asset_df = df[df["symbol"] == symbol]
    print(f"{symbol}: {len(asset_df)} bars")
```

## Related Scripts

- [gen_synth_amm_data.py](README_gen_synth_amm_data.md) - Generate AMM-specific synthetic data
- [data_sanity.py](README_data_sanity.md) - Validate generated data quality
- [data_annotation_cli.py](README_data_annotation.md) - Add labels and annotations

## Testing

Run the unit tests for this script:

```bash
pytest tests/unit/test_generate_sample_ohlcv.py -v
```

## Changelog

### 2025-11-28
- Initial implementation with multi-asset support
- Added comprehensive test suite
- Documented API and CLI usage
