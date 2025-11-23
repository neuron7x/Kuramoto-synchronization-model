# Data Module

## Overview

The `data` module handles data ingestion, storage, validation, and retrieval for TradePulse. It provides unified interfaces for accessing market data from various sources.

## Purpose

- **Data Ingestion**: Import data from exchanges and data providers
- **Data Storage**: Efficient storage and retrieval of time series data
- **Data Validation**: Ensure data quality and consistency
- **Data Transformation**: Normalize and clean market data

## Key Features

- 📥 **Multi-Source**: Ingest from exchanges, files, and APIs
- 💾 **Efficient Storage**: Optimized time series storage
- ✅ **Validation**: Automated data quality checks
- 🔄 **Streaming**: Real-time data streaming support
- 📊 **Caching**: High-performance data caching

## Usage Examples

### Data Ingestion

```python
from data import DataIngester, DataSource

ingester = DataIngester()
ingester.add_source(DataSource.BINANCE)

# Ingest historical data
await ingester.ingest(
    symbol="BTC/USDT",
    timeframe="1h",
    start_date="2023-01-01",
    end_date="2023-12-31"
)
```

### Data Retrieval

```python
from data import DataManager

data_mgr = DataManager()

# Get historical data
df = await data_mgr.get_historical_data(
    symbol="BTC/USDT",
    timeframe="1h",
    start_date="2023-01-01",
    end_date="2023-12-31"
)
```

### Data Validation

```python
from data import DataValidator

validator = DataValidator()
issues = validator.validate(df)

if issues:
    print(f"Data quality issues: {issues}")
```

## Configuration

```yaml
# config/data.yaml
data:
  sources:
    binance:
      enabled: true
      rate_limit: 1200
      
  storage:
    backend: postgresql
    cache_enabled: true
    cache_ttl_seconds: 300
    
  validation:
    strict_mode: true
    max_missing_ratio: 0.01
```

## Related Modules

- [`core`](../core/README.md): Core data processing
- [`markets`](../markets/README.md): Market data structures

## Documentation

- [Data Management Guide](https://docs.tradepulse.io/data)

## License

See [LICENSE](../LICENSE) for licensing information.
