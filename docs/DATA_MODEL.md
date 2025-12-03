# TradePulse Data Model Documentation

This document describes the unified data layer for TradePulse, providing a single source of truth for all market data, trading events, and strategy inputs.

## Overview

The TradePulse data layer follows these core principles:

1. **Single Source of Truth** - All strategies, backtests, and live trading systems use the same data schemas
2. **Strict Validation** - Price > 0, volume >= 0, monotonic timestamps, OHLC relationships
3. **Type Safety** - Decimal for prices, timezone-aware UTC timestamps
4. **Immutability** - Frozen dataclasses prevent accidental mutations

## Data Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Raw Sources   │     │   Data Layer     │     │   Consumers     │
│                 │     │                  │     │                 │
│  • CSV files    │────▶│  load_historical │────▶│  • Strategies   │
│  • Exchange API │     │  _bars()         │     │  • Backtests    │
│  • WebSocket    │     │                  │     │  • Live Trading │
│  • Parquet      │     │  normalize_bars()│     │  • Analytics    │
│                 │     │                  │     │                 │
└─────────────────┘     │  validate_series │     └─────────────────┘
                        │  ()              │
                        │                  │
                        │  DataQualityGuard│
                        └──────────────────┘
```

## Core Schemas

### Bar / Candle

OHLCV bar representing aggregated price data for a time interval.

```python
from tradepulse.data.schema import Bar, Timeframe
from decimal import Decimal
from datetime import datetime, timezone

bar = Bar(
    timestamp=datetime.now(timezone.utc),
    symbol="BTCUSDT",
    timeframe=Timeframe.M1,
    open=Decimal("45000"),
    high=Decimal("45100"),
    low=Decimal("44900"),
    close=Decimal("45050"),
    volume=Decimal("100.5"),
    trades=50,  # optional
    vwap=Decimal("45025"),  # optional
)
```

**Fields:**
| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `timestamp` | `datetime` | Yes | Must be UTC timezone-aware |
| `symbol` | `str` | Yes | Non-empty, uppercased |
| `timeframe` | `Timeframe` | Yes | Must be valid enum value |
| `open` | `Decimal` | Yes | Must be > 0, between low and high |
| `high` | `Decimal` | Yes | Must be > 0, >= low |
| `low` | `Decimal` | Yes | Must be > 0, <= high |
| `close` | `Decimal` | Yes | Must be > 0, between low and high |
| `volume` | `Decimal` | Yes | Must be >= 0 |
| `trades` | `int` | No | Must be >= 0 |
| `vwap` | `Decimal` | No | Must be finite |

### Tick

Tick-level price update representing a single trade or quote.

```python
from tradepulse.data.schema import Tick, OrderSide

tick = Tick(
    timestamp=datetime.now(timezone.utc),
    symbol="BTCUSDT",
    price=Decimal("45000"),
    volume=Decimal("0.5"),
    side=OrderSide.BUY,
    trade_id="trade123",
)
```

**Fields:**
| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `timestamp` | `datetime` | Yes | Must be UTC |
| `symbol` | `str` | Yes | Non-empty, uppercased |
| `price` | `Decimal` | Yes | Must be > 0 |
| `volume` | `Decimal` | No | Default 0, must be >= 0 |
| `side` | `OrderSide` | No | BUY or SELL |
| `trade_id` | `str` | No | Exchange trade ID |

### FeatureVector

Structured feature vector for strategy consumption.

```python
from tradepulse.data.schema import FeatureVector

fv = FeatureVector(
    timestamp=datetime.now(timezone.utc),
    symbol="BTCUSDT",
    features={"rsi": 65.0, "macd": 0.5, "momentum": 1.2},
    metadata={"source": "binance", "version": "1.0"},
)

# Access features
rsi = fv.get("rsi")
macd = fv.get("macd", default=0.0)
```

### MarketSnapshot

Point-in-time market state for a symbol.

```python
from tradepulse.data.schema import MarketSnapshot

snapshot = MarketSnapshot(
    timestamp=datetime.now(timezone.utc),
    symbol="BTCUSDT",
    last_price=Decimal("45000"),
    bid=Decimal("44999"),
    ask=Decimal("45001"),
    bid_volume=Decimal("10.5"),
    ask_volume=Decimal("8.3"),
    last_bar=bar,  # Optional reference to last bar
    features=fv,   # Optional feature vector
)

# Computed properties
spread = snapshot.spread  # Decimal("2")
mid = snapshot.mid_price  # Decimal("45000")
```

### Timeframe

Supported timeframes for bar aggregation.

```python
from tradepulse.data.schema import Timeframe

# Available timeframes
Timeframe.S1   # 1 second
Timeframe.S5   # 5 seconds
Timeframe.S15  # 15 seconds
Timeframe.S30  # 30 seconds
Timeframe.M1   # 1 minute
Timeframe.M5   # 5 minutes
Timeframe.M15  # 15 minutes
Timeframe.M30  # 30 minutes
Timeframe.H1   # 1 hour
Timeframe.H4   # 4 hours
Timeframe.D1   # 1 day
Timeframe.W1   # 1 week
Timeframe.MN1  # 1 month

# Get duration in seconds
seconds = Timeframe.H1.seconds  # 3600

# Parse from string
tf = Timeframe.from_string("1h")  # Timeframe.H1
tf = Timeframe.from_string("1hour")  # Also works
```

## Data Quality

### DataQualityReport

Result of data quality validation.

```python
from tradepulse.data.quality import validate_series, DataQualityStatus

report = validate_series(bars)

print(f"Status: {report.status}")  # OK, WARN, or CRITICAL
print(f"Bar count: {report.bar_count}")
print(f"Gaps: {report.gaps_count}")
print(f"Outliers: {report.outliers_count}")
print(f"Duplicates: {report.duplicates_count}")

if not report.is_valid():
    for issue in report.issues:
        print(f"[{issue.severity}] {issue.code}: {issue.message}")
```

### Validation Functions

```python
from tradepulse.data.quality import (
    validate_series,
    detect_gaps,
    detect_outliers,
    detect_duplicates,
    check_monotonic_time,
    require_valid_data,
)

# Full validation
report = validate_series(
    bars,
    check_gaps=True,
    check_outliers=True,
    check_duplicates=True,
    check_monotonic=True,
    price_change_threshold_pct=20.0,
    volume_spike_multiplier=10.0,
)

# Individual checks
gap_issues = detect_gaps(bars, expected_interval_seconds=60)
outlier_issues = detect_outliers(bars)
duplicate_issues = detect_duplicates(bars)
monotonic_issues = check_monotonic_time(bars)

# Strict validation (raises exception on failure)
try:
    require_valid_data(bars, allow_warnings=False)
except DataQualityError as e:
    print(f"Validation failed: {e.report}")
```

### Issue Severity Levels

| Severity | Description |
|----------|-------------|
| `INFO` | Informational, no action needed |
| `WARNING` | Potential issue, proceed with caution |
| `ERROR` | Significant issue, may affect results |
| `CRITICAL` | Data unusable, must be fixed |

## Data API

### Loading Historical Data

```python
from tradepulse.data.api import load_historical_bars, DataSourceConfig

# Simple CSV loading
bars = load_historical_bars(
    "data/btcusdt_1m.csv",
    symbol="BTCUSDT",
    timeframe=Timeframe.M1,
)

# With custom configuration
config = DataSourceConfig(
    source_type="csv",
    path="data/custom.csv",
    symbol="ETHUSDT",
    timeframe=Timeframe.H1,
    timestamp_column="ts",
    ohlcv_columns={
        "open": "o",
        "high": "h",
        "low": "l",
        "close": "c",
        "volume": "vol",
    },
)
bars = load_historical_bars(config)
```

### Getting Data Windows

```python
from tradepulse.data.api import get_historical_window, get_latest_snapshot

# Get a time window
window = get_historical_window(
    all_bars,
    symbol="BTCUSDT",
    timeframe=Timeframe.M1,
    start=datetime(2024, 1, 1, tzinfo=timezone.utc),
    end=datetime(2024, 1, 31, tzinfo=timezone.utc),
)

# Get latest snapshot
snapshot = get_latest_snapshot(all_bars, "BTCUSDT")
```

### Normalizing Data

```python
from tradepulse.data.api import normalize_bars

normalized = normalize_bars(
    raw_bars,
    sort_by_time=True,
    remove_duplicates=True,
)
```

## Trading Events (from core/events/models.py)

### OrderEvent

```python
from core.events.models import OrderEvent, OrderSide, OrderType

order = OrderEvent(
    event_id="order_123",
    schema_version="1.0",
    symbol="BTCUSDT",
    timestamp=1700000000,
    order_id="ord_456",
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    quantity=0.5,
    price=45000.0,
)
```

### FillEvent

```python
from core.events.models import FillEvent, FillStatus

fill = FillEvent(
    event_id="fill_789",
    schema_version="1.0",
    symbol="BTCUSDT",
    timestamp=1700000001,
    order_id="ord_456",
    fill_id="fill_001",
    status=FillStatus.FILLED,
    filled_qty=0.5,
    fill_price=45000.0,
    fees=2.25,
)
```

## Adding a New Data Source

To add a new data source:

1. **Create an adapter** that converts raw data to `Bar` objects:

```python
def load_from_new_source(config: DataSourceConfig) -> list[Bar]:
    # Fetch raw data
    raw_data = fetch_from_source(...)
    
    # Convert to Bar objects
    bars = []
    for row in raw_data:
        bar = Bar(
            timestamp=parse_timestamp(row["ts"]),
            symbol=config.symbol,
            timeframe=config.timeframe,
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
            volume=Decimal(str(row["volume"])),
        )
        bars.append(bar)
    
    return bars
```

2. **Register the adapter** in `api.py`:

```python
# In load_historical_bars()
if config.source_type == "new_source":
    bars = load_from_new_source(config)
```

3. **Add tests** for the new source in `tests/unit/data/`.

## Best Practices

1. **Always validate data** before running backtests:
   ```python
   report = validate_series(bars)
   if not report.is_valid():
       raise ValueError(f"Data quality issues: {report}")
   ```

2. **Use the API**, not direct file access:
   ```python
   # Good
   bars = load_historical_bars("data.csv", symbol="BTCUSDT")
   
   # Bad
   df = pd.read_csv("data.csv")
   ```

3. **Keep timestamps in UTC**:
   ```python
   # Good
   bar = Bar(timestamp=datetime.now(timezone.utc), ...)
   
   # Bad
   bar = Bar(timestamp=datetime.now(), ...)  # No timezone
   ```

4. **Use Decimal for prices**:
   ```python
   # Good
   price = Decimal("45000.123456789")
   
   # Bad
   price = 45000.123456789  # Float precision issues
   ```

## Module Structure

```
src/tradepulse/data/
├── __init__.py     # Public API exports
├── schema.py       # Core data models (Bar, Tick, etc.)
├── quality.py      # Data quality validation
├── api.py          # Data access API
└── validation.py   # Additional validation (re-exports from core)
```
