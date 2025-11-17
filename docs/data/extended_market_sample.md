---
owner: data@tradepulse
review_cadence: quarterly
artifacts:
  - path: sample.csv
    checksum: sha256:fc4f2b24beb89d6b0ee458ee5c6a49e679e330be9968a8e826bc6f3d6339fbc0
    size_bytes: 114240
---

# Extended Market Sample Dataset

## Overview

This dataset contract defines the extended sample market data artifact located in the repository root. This is a larger-scale version of the standard sample datasets, providing extended historical data for comprehensive testing and analysis scenarios.

## Artifacts

### sample.csv

**Format**: CSV (Comma-Separated Values)

**Description**: Extended price/volume time series dataset with 2001 data points. This dataset provides sufficient historical depth for sophisticated indicator calculations, backtesting scenarios, and statistical analysis that require larger sample sizes.

**Schema**:
- `ts` (integer): Timestamp/sequence number
- `price` (float): Market price in base currency units  
- `volume` (integer): Trading volume

**Characteristics**:
- 2001 data points (4x larger than data/sample.csv)
- Continuous time series without gaps
- Realistic price evolution with multiple market regimes
- Variable volume patterns reflecting market microstructure
- Deterministic generation for reproducibility

**Statistical Properties**:
- Price range: ~100 to varying end price depending on regime
- Volume distribution: Log-normal with parameters suitable for realistic simulation
- Autocorrelation structure: Reflects momentum and mean-reversion patterns
- Volatility clustering: Present in price changes

**Use Cases**:
- **Long-horizon Backtesting**: Testing strategies over extended periods
- **Statistical Indicator Validation**: Indicators requiring large lookback windows (e.g., 200-period moving averages)
- **Regime Detection**: Identifying multiple market phases within single dataset
- **Performance Testing**: Benchmarking indicator calculation speed on realistic data volumes
- **Documentation Examples**: Comprehensive examples in README and guides
- **Integration Testing**: End-to-end system tests with substantial data

**Advantages Over Smaller Samples**:
1. **Statistical Significance**: Larger sample size improves statistical test power
2. **Multiple Regimes**: Contains trending, ranging, and volatile periods
3. **Edge Cases**: More opportunities to encounter rare market conditions
4. **Scalability Testing**: Validates performance with production-like data volumes
5. **Warm-up Periods**: Allows indicators with long lookbacks to stabilize

## Generation Methodology

This dataset is generated using `interfaces/generate_sample_data.py` with the following parameters:

```python
# Pseudocode for generation
generate_trending_prices(
    n=2001,
    initial_price=100.0,
    trend=0.02,
    volatility=1.0,
    seed=42  # For reproducibility
)
```

The generation process ensures:
- **Reproducibility**: Fixed random seed produces identical output
- **Realism**: Price follows geometric Brownian motion with drift
- **Consistency**: No arbitrage opportunities or impossible price jumps
- **Testability**: Known properties enable verification of indicator correctness

## Validation

To validate this artifact:

```bash
python scripts/validate_sample_data.py --repo-root . --format text
```

Expected checksum: `sha256:fc4f2b24beb89d6b0ee458ee5c6a49e679e330be9968a8e826bc6f3d6339fbc0`

## Integration Examples

### Loading with Pandas

```python
import pandas as pd

# Load the extended sample
df = pd.read_csv("sample.csv")
print(f"Loaded {len(df)} data points")

# Set timestamp as index
df['ts'] = pd.to_datetime(df['ts'], unit='s', origin='unix')
df = df.set_index('ts')

# Calculate simple statistics
print(f"Price range: {df['price'].min():.2f} to {df['price'].max():.2f}")
print(f"Average volume: {df['volume'].mean():.0f}")
```

### Using with TradePulse Indicators

```python
from core.indicators.kuramoto_ricci_composite import TradePulseCompositeEngine

# Load data
df = pd.read_csv("sample.csv")

# Analyze with composite engine
engine = TradePulseCompositeEngine()
snapshot = engine.analyze_market(df[['price', 'volume']])

print(f"Detected regime: {snapshot.phase.value}")
print(f"Entry signal strength: {snapshot.entry_signal:.3f}")
```

### Backtesting Example

```python
from backtest.event_driven import CSVMarketDataSource

# Use as backtesting data source
data_source = CSVMarketDataSource("sample.csv")

# Run backtest (simplified)
for event in data_source.stream():
    # Process market events
    strategy.on_market_data(event)
```

## Comparison with Other Datasets

| Dataset | Size | Use Case | Characteristics |
|---------|------|----------|----------------|
| `data/sample.csv` | 500 | Quick tests, demos | Simple trending |
| `data/sample_ohlc.csv` | 300 | OHLC analysis | Candlestick data |
| **`sample.csv`** | **2001** | **Extended testing** | **Multiple regimes** |
| Generated samples | Variable | Custom scenarios | Configurable properties |

## Maintenance Guidelines

This artifact should be:

1. **Immutable**: Treat as read-only reference data
2. **Versioned**: Any changes require new version with migration guide
3. **Validated**: Must pass checksum validation in CI pipeline
4. **Documented**: Keep this contract synchronized with actual file
5. **Backed Up**: Include in data backup procedures

**Update Process**:
1. Generate new data with updated parameters
2. Save with new filename (e.g., `sample_v2.csv`)
3. Compute new checksum
4. Update this contract document
5. Update all references in code and documentation
6. Add deprecation notice for old version if applicable
7. Update tests to use new version

## Known Limitations

- **Synthetic Data**: Not real market data; may not capture all real-world phenomena
- **Single Asset**: Represents single trading pair; not suitable for multi-asset correlation analysis
- **Fixed Regime Mix**: Regime transitions at predetermined points
- **No Microstructure**: Lacks bid-ask spreads, order book dynamics
- **Deterministic**: Same seed always produces same data; limited variation

## Related Artifacts

- `data/sample.csv`: Smaller version (500 points) for quick tests
- `data/sample_ohlc.csv`: OHLC format with 300 bars
- `interfaces/generate_sample_data.py`: Data generation script
- `scripts/generate_market_feed_samples.py`: Market feed sample generator

## References

- [Sample Data Documentation](../templates/sample_data.md)
- [Data Generation Guide](../../interfaces/generate_sample_data.py)
- [Testing Documentation](../../TESTING.md)
- [Backtest Documentation](../../backtest/)

## Changelog

### 2025-11-17
- Initial dataset contract creation
- Documented extended sample.csv artifact (2001 data points)
- Added checksum and size validation metadata
- Defined schema, use cases, and integration examples
- Documented generation methodology and statistical properties
- Added comparison with other sample datasets
