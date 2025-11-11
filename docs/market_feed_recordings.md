# Market Feed Recordings for Dopamine Loop Testing

## Overview

The market feed recording infrastructure provides a complete solution for capturing,
validating, and replaying real market data for testing the dopamine loop system
(TD(0) RPE, DDM adaptation, Go/No-Go decisions).

## Features

- **Schema Validation**: Strict Pydantic v2 validation ensuring data quality
- **JSONL Format**: Efficient streaming format with one record per line
- **UTC Timezone**: All timestamps normalized to UTC for consistency
- **Quality Control**: Comprehensive validation (latency, monotonicity, spread checks)
- **S3 Storage**: Optional S3 upload/download with checksums and versioning
- **Reproducible**: Deterministic synthetic generation for stable regression tests
- **Regime Support**: Multiple market regimes (stable, trending, volatile, crashes)

## Schema

Each market feed record contains:

```json
{
  "exchange_ts": "2024-01-01T00:00:00.123456+00:00",
  "ingest_ts": "2024-01-01T00:00:00.168923+00:00",
  "bid": "50000.00",
  "ask": "50000.50",
  "last": "50000.25",
  "volume": "1.5"
}
```

### Fields

- **exchange_ts**: Exchange timestamp (ISO 8601 with timezone)
- **ingest_ts**: Ingestion timestamp (ISO 8601 with timezone)  
- **bid**: Best bid price (Decimal, > 0)
- **ask**: Best ask price (Decimal, > 0)
- **last**: Last traded price (Decimal, > 0)
- **volume**: Trade volume (Decimal, >= 0)

### Validations

- All timestamps must be UTC
- `ingest_ts >= exchange_ts` (allowing small clock skew)
- `bid <= ask`
- `last` within reasonable range of bid-ask spread
- Latency < 10 seconds
- All prices positive, volume non-negative

## Usage

### Reading Recordings

```python
from pathlib import Path
from core.data.market_feed import MarketFeedRecording

# Read JSONL file
recording = MarketFeedRecording.read_jsonl(Path("data/btcusd.jsonl"))

# Read with metadata
recording = MarketFeedRecording.read_with_metadata(
    jsonl_path=Path("data/btcusd.jsonl"),
    metadata_path=Path("data/btcusd.metadata.json"),
)

# Iterate over records
for record in recording.iter_records():
    print(f"Time: {record.exchange_ts}, Price: {record.last}")
```

### Generating Synthetic Data

```python
from core.data.market_feed_generator import SyntheticMarketFeedGenerator

# Create generator with seed for reproducibility
generator = SyntheticMarketFeedGenerator(seed=42)

# Generate stable market
recording = generator.generate(
    num_records=100,
    regime="stable",
)

# Generate flash crash
recording = generator.generate_flash_crash(
    num_records=100,
    crash_position=0.5,
    crash_magnitude=0.05,  # 5% drop
)

# Generate regime transitions
recording = generator.generate_regime_transition(
    num_records=300,
    regimes=["stable", "trending_up", "volatile"],
)

# Save to file
recording.write_with_metadata(
    jsonl_path=Path("data/recording.jsonl"),
    metadata_path=Path("data/recording.metadata.json"),
)
```

### Quality Validation

```python
from core.data.market_feed import validate_recording

validation = validate_recording(recording)

print(f"Valid: {validation['valid']}")
print(f"Record count: {validation['record_count']}")
print(f"Latency (median): {validation['latency_ms']['median']:.1f}ms")
print(f"Warnings: {validation['warnings']}")
```

### S3 Storage (Optional)

```python
from core.data.market_feed_storage import MarketFeedStorage

# Initialize storage backend
storage = MarketFeedStorage(
    bucket="tradepulse-market-feeds",
    prefix="recordings",
    region="us-east-1",
)

# Upload recording
result = storage.upload_recording(
    recording=recording,
    recording_name="btcusd_stable_20240101",
    include_metadata=True,
)
print(f"Uploaded to: {result['jsonl_uri']}")

# Download recording
recording = storage.download_recording(
    recording_name="btcusd_stable_20240101",
    include_metadata=True,
    verify_checksum=True,
)

# List available recordings
recordings = storage.list_recordings()
print(f"Available: {recordings}")
```

## Sample Recordings

Pre-generated stable samples are available in `tests/fixtures/recordings/`:

| File | Records | Regime | Purpose |
|------|---------|--------|---------|
| `stable_btcusd_100ticks.jsonl` | 100 | Stable | Basic dopamine tests |
| `trending_up_btcusd_200ticks.jsonl` | 200 | Trending Up | Positive RPE tests |
| `trending_down_btcusd_200ticks.jsonl` | 200 | Trending Down | Negative RPE tests |
| `volatile_btcusd_150ticks.jsonl` | 150 | Volatile | Go/No-Go threshold tests |
| `mean_reverting_btcusd_250ticks.jsonl` | 250 | Mean Reverting | DDM adaptation tests |
| `flash_crash_5pct_mid.jsonl` | 100 | Flash Crash | Stress testing |
| `regime_transitions_4phases.jsonl` | 300 | Multiple | Regime adaptation tests |

## Generating New Samples

Use the provided script to generate standard samples:

```bash
# Generate all samples
python scripts/generate_market_feed_samples.py --all

# Generate only standard samples
python scripts/generate_market_feed_samples.py --standard

# Generate flash crash samples
python scripts/generate_market_feed_samples.py --flash-crash

# Custom output directory
python scripts/generate_market_feed_samples.py --output-dir data/recordings
```

## Integration with Dopamine Loop

The recordings are designed for testing TD(0) RPE, DDM, and Go/No-Go systems:

```python
from core.data.market_feed import MarketFeedRecording
from tradepulse.core.neuro.dopamine import adapt_ddm_parameters

# Load recording
recording = MarketFeedRecording.read_jsonl("tests/fixtures/recordings/volatile_btcusd_150ticks.jsonl")

# Calculate rewards from price movements
prices = [float(r.last) for r in recording.records]
rewards = []
for i in range(len(prices)):
    if i < 5:
        rewards.append(0.0)
    else:
        momentum = (prices[i] - prices[i-5]) / prices[i-5]
        reward = max(-1.0, min(1.0, momentum * 100))
        rewards.append(reward)

# Test DDM adaptation
for reward in rewards:
    # Simulate dopamine level from reward
    import math
    dopamine_level = 1.0 / (1.0 + math.exp(-reward * 5))
    
    # Adapt DDM parameters
    ddm_params = adapt_ddm_parameters(
        dopamine_level=dopamine_level,
        base_drift=0.5,
        base_boundary=1.0,
    )
    
    print(f"Reward: {reward:.3f}, DA: {dopamine_level:.3f}, "
          f"Drift: {ddm_params.drift:.3f}, Boundary: {ddm_params.boundary:.3f}")
```

## Market Regimes

### Stable
- Low volatility
- Minimal price drift
- Tight spreads
- **Use case**: Baseline dopamine behavior, threshold calibration

### Trending Up
- Moderate positive drift
- Lower volatility
- **Use case**: Positive RPE testing, reward learning

### Trending Down
- Moderate negative drift
- Lower volatility
- **Use case**: Negative RPE testing, loss aversion

### Volatile
- High volatility
- Wide spreads
- Frequent direction changes
- **Use case**: Go/No-Go decision making, stress testing

### Mean Reverting
- Negative autocorrelation
- Regular oscillations
- **Use case**: DDM adaptation, regime detection

### Flash Crash
- Sudden price drop
- Rapid recovery
- High volume spike
- **Use case**: Crisis response, emergency protocols

## Quality Metrics

The validation system checks:

- **Latency**: Median, P95, max ingestion latency
- **Spread**: Median, min, max bid-ask spread
- **Volume**: Mean volume, zero-volume count
- **Time Gaps**: Median, max time between ticks
- **Monotonicity**: Strictly increasing timestamps
- **Price Validity**: Positive prices, reasonable ranges

## Best Practices

1. **Use Reproducible Seeds**: Always set seed for deterministic generation
2. **Validate Before Use**: Run `validate_recording()` on all recordings
3. **Check Metadata**: Include metadata for provenance tracking
4. **Version Control**: Store sample recordings in version control
5. **Test Coverage**: Use multiple regimes to cover edge cases
6. **Realistic Parameters**: Match base_price and spread to actual markets
7. **Monitor Warnings**: Address quality warnings before production use

## Performance

- **Reading**: ~100,000 records/second
- **Validation**: ~50,000 records/second
- **Generation**: ~10,000 records/second
- **Storage**: Minimal (JSONL is compact)

## Dependencies

### Core
- `pydantic>=2.12.3` - Schema validation
- `pandas` - Data manipulation (optional)
- `numpy` - Synthetic generation

### Optional
- `boto3` - S3 storage backend
- `pyarrow` - Parquet export (future)

## Testing

```bash
# Run all market feed tests
pytest tests/unit/data/test_market_feed.py -v
pytest tests/unit/data/test_market_feed_generator.py -v
pytest tests/integration/test_market_feed_recordings.py -v

# With coverage
pytest tests/unit/data/test_market_feed*.py --cov=core.data.market_feed --cov-report=html
```

## Troubleshooting

### Validation Errors

**"Bid must be <= Ask"**
- Check data source for inverted quotes
- Verify price precision/rounding

**"Latency exceeds maximum threshold"**
- Check ingestion pipeline performance
- Verify timestamp synchronization

**"Timestamps not monotonic"**
- Sort records by exchange_ts before creating recording
- Check for clock drift in data source

### Performance Issues

- Use streaming for large files (read line by line)
- Enable parallel validation for multi-file processing
- Consider Parquet for analytical workloads

## Future Enhancements

- [ ] Real-time streaming support (WebSocket)
- [ ] Orderbook depth (L2/L3 data)
- [ ] Trade tape reconstruction
- [ ] Cross-exchange synchronization
- [ ] Parquet export for analysis
- [ ] Compression (gzip, zstd)
- [ ] Real exchange connectors (Binance, Coinbase, etc.)

## References

- [Pydantic Documentation](https://docs.pydantic.dev/)
- [JSONL Format](https://jsonlines.org/)
- [TD(0) Learning](https://en.wikipedia.org/wiki/Temporal_difference_learning)
- [Drift-Diffusion Model](https://en.wikipedia.org/wiki/Drift-diffusion_model)

## Support

For issues or questions:
- Check existing tests for usage examples
- Review validation warnings for data quality issues
- Contact the TradePulse team for production deployment
