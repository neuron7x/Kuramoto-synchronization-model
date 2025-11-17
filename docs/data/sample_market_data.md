---
owner: data@tradepulse
review_cadence: quarterly
artifacts:
  - path: data/sample.csv
    checksum: sha256:5eb16d5e9b45f4a21772ef1500cbe7a9923c897ae38483c71cd4e917600861b8
    size_bytes: 13797
  - path: data/sample_ohlc.csv
    checksum: sha256:8abd15eacb86ad090bc0c43b197d87f5fa97f640e77226e0813e59a384befec0
    size_bytes: 13170
---

# Sample Market Data

## Overview

This dataset contract defines the standard sample market data artifacts used throughout TradePulse for testing, demonstrations, and documentation examples. These datasets provide realistic synthetic market data suitable for development and testing scenarios.

## Artifacts

### data/sample.csv

**Format**: CSV (Comma-Separated Values)

**Description**: Simple price/volume time series data with 500 data points. This dataset is used for basic indicator testing, visualization examples, and quick development iterations.

**Schema**:
- `ts` (integer): Timestamp/sequence number
- `price` (float): Market price in base currency units
- `volume` (integer): Trading volume

**Characteristics**:
- 500 data points
- Trending price pattern with gradual increase
- Regular volume pattern alternating between levels
- Deterministic generation for reproducibility

**Use Cases**:
- Basic indicator calculations
- CLI testing and demos
- Documentation examples
- Unit test fixtures

**Generation**: Created using `interfaces/generate_sample_data.py` with trending regime parameters.

### data/sample_ohlc.csv

**Format**: CSV (Comma-Separated Values)

**Description**: OHLC (Open, High, Low, Close) candlestick data with volume for 300 periods. This dataset represents more realistic market data structure used in production trading systems.

**Schema**:
- `ts` (integer): Timestamp/sequence number
- `open` (float): Opening price for the period
- `high` (float): Highest price during the period
- `low` (float): Lowest price during the period
- `close` (float): Closing price for the period
- `volume` (integer): Trading volume for the period

**Characteristics**:
- 300 OHLC bars
- Realistic price relationships (high >= open,close >= low)
- Variable volume patterns
- Moderate volatility regime
- Suitable for candlestick analysis

**Use Cases**:
- Advanced indicator testing (RSI, MACD, Bollinger Bands)
- Backtesting framework validation
- Pattern recognition algorithms
- Market regime detection

**Generation**: Created using `interfaces/generate_sample_data.py` with OHLC generation mode.

## Validation

To validate these artifacts, run:

```bash
python scripts/validate_sample_data.py --repo-root . --format text
```

All checksums must match the values declared in this contract's YAML front matter.

## Maintenance

These sample datasets should be:
- **Stable**: Never modified without updating checksums
- **Versioned**: Changes require new versions with clear migration path
- **Documented**: Any schema changes must be reflected in this document
- **Validated**: Must pass validation checks in CI pipeline

## Related Artifacts

- `sample.csv` (root): Extended version with 2001 data points for larger-scale testing
- `examples/orchestrator_output_example.json`: Configuration example using these datasets
- `scripts/generate_market_feed_samples.py`: Generator for additional market feed samples

## References

- [Data Generation Documentation](../templates/sample_data.md)
- [Market Feed Implementation](../../MARKET_FEED_IMPLEMENTATION_SUMMARY.md)
- [Testing Guide](../../TESTING.md)

## Changelog

### 2025-11-17
- Initial dataset contract creation
- Documented existing sample.csv and sample_ohlc.csv artifacts
- Added checksums and size validation metadata
- Defined schemas and use cases
