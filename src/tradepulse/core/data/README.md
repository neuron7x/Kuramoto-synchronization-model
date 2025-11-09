---
owner: data-platform@tradepulse
review_cadence: quarterly
last_reviewed: 2025-11-04
links:
  - ../../docs/architecture/system_modules_reference.md
  - ../../docs/dataset_catalog.md
  - ../../docs/feature_store_sync_and_registry.md
---

# Core Data Module

## Purpose

The `core/data` module serves as the **sensory cortex** of the TradePulse system, providing unified ingestion, validation, and lineage tracking for all market data and derived features. Inspired by how the brain's thalamus filters and routes sensory input to higher cortical areas, this module ensures only validated, normalized, and versioned data reaches the decision-making layers.

**Neuroeconomic Mapping:**
- **Thalamic Relay**: `ingestion.py` and `async_ingestion.py` act as the sensory gateway, filtering raw market feeds
- **Quality Assurance**: `quality_control.py` and `validation.py` mirror the brain's error detection mechanisms (anterior cingulate cortex)
- **Memory Consolidation**: `feature_store.py` and `versioning.py` provide hippocampal-like storage with full lineage tracking
- **Dead Letter Handling**: `dead_letter.py` implements a safety mechanism preventing corrupt data from reaching executive functions

**Key Objectives:**
- Guarantee data integrity with sub-second validation latency (P99 < 500ms)
- Provide deterministic versioning for reproducible research (audit trail up to 7 years)
- Enable seamless integration with 10+ exchange APIs (CCXT, Alpaca, Polygon, etc.)
- Maintain 99.99% uptime for real-time data ingestion pipelines
- Support both streaming (Kafka/Redpanda) and batch (Parquet/Iceberg) workflows

## Key Responsibilities

- **Multi-Source Data Ingestion**: Unified adapters for exchange APIs, websockets, CSV/Parquet files, and synthetic data generators
- **Schema Validation & Type Safety**: Enforce strict contracts via Pydantic models with automatic schema migration support
- **Temporal Normalization**: Align timestamps across venues, handle timezone conversions, detect and fill gaps
- **Quality Control Gates**: Statistical anomaly detection, range checks, cross-venue consistency validation
- **Feature Store Management**: Serve online features (Redis) and offline features (Parquet/Iceberg) with parity guarantees
- **Lineage Tracking**: Full provenance from raw tick → normalized bar → engineered feature with immutable audit logs
- **Dead Letter Queue**: Isolate malformed payloads for manual review without blocking healthy data flow
- **Backfill Orchestration**: Intelligent historical data retrieval with deduplication and gap detection
- **Catalog Governance**: Maintain asset metadata, symbol mappings, trading calendars, and data source reliability metrics

## Public Interfaces

| Interface | Type | Location | Description |
| --------- | ---- | -------- | ----------- |
| `DataIngestionPipeline` | Class | `ingestion.py` | Synchronous ingestion coordinator with quality gates |
| `AsyncDataIngestionPipeline` | Class | `async_ingestion.py` | High-throughput async ingestion for real-time feeds |
| `DataQualityController` | Class | `quality_control.py` | Statistical validation and anomaly detection engine |
| `DataValidator` | Class | `validation.py` | Schema and business rule validation with detailed error reports |
| `DataVersionManager` | Class | `versioning.py` | Immutable versioning system with snapshot manifests |
| `FeatureStore` | Class | `feature_store.py` | Unified interface for online (Redis) and offline (Parquet) features |
| `FeatureCatalog` | Class | `feature_catalog.py` | Searchable metadata catalog for all engineered features |
| `AssetCatalog` | Class | `asset_catalog.py` | Asset registry with symbol normalization and venue mappings |
| `DeadLetterQueue` | Class | `dead_letter.py` | Fault-tolerant queue for malformed or rejected data |
| `BackfillOrchestrator` | Class | `backfill.py` | Historical data retrieval with smart chunking and retry logic |
| `NormalizationPipeline` | Class | `normalization_pipeline.py` | Multi-stage data cleaning and standardization |
| `DataMaterializer` | Class | `materialization.py` | Feature computation and persistence coordinator |
| `PolarsPipeline` | Class | `polars_pipeline.py` | High-performance data transformation using Polars |
| `StreamingDataPipeline` | Class | `streaming.py` | Real-time event streaming with backpressure handling |

## Configuration

### Environment Variables:
- `TRADEPULSE_DATA_ROOT`: Base directory for all data storage (default: `~/.tradepulse/data`)
- `TRADEPULSE_FEATURE_STORE_BACKEND`: Backend type: `redis`, `parquet`, `feast` (default: `redis`)
- `TRADEPULSE_DLQ_RETENTION_DAYS`: Dead letter queue retention period (default: `30`)
- `TRADEPULSE_ENABLE_DATA_LINEAGE`: Enable full lineage tracking (default: `true`, incurs 5-10% overhead)
- `TRADEPULSE_INGESTION_WORKERS`: Parallel ingestion workers (default: `4`)
- `TRADEPULSE_KAFKA_BOOTSTRAP_SERVERS`: Kafka/Redpanda brokers for streaming ingestion
- `TRADEPULSE_S3_BUCKET`: S3-compatible bucket for Iceberg lakehouse (e.g., `s3://tradepulse-features`)

### Configuration Files:
Data pipelines are configured via `configs/data/`:
- `ingestion.yaml`: Exchange connectors, rate limits, retry policies
- `quality.yaml`: Validation thresholds, anomaly detection parameters
- `feature_store.yaml`: Online/offline store configuration, TTL policies
- `catalog.yaml`: Asset definitions, symbol mappings, trading calendars

### Feature Flags:
- `data.enable_quality_gates`: Enforce quality checks (disable for raw data dumps)
- `data.enable_versioning`: Track data lineage (disable for ephemeral testing)
- `data.enable_dlq`: Route bad data to dead letter queue vs reject
- `data.enable_parity_checks`: Validate online/offline feature consistency

## Dependencies

### Internal:
- `core.utils.logging`: Structured logging with trace IDs
- `core.utils.metrics`: Prometheus metrics for pipeline observability
- `core.utils.schemas`: Pydantic base models and schema registry
- `domain`: Core domain models (Asset, Bar, Tick, Order)

### External Services/Libraries:
- **Pandas** (>=2.0): DataFrame operations and time series manipulation
- **Polars** (>=0.19): High-performance alternative to Pandas (10x faster on large datasets)
- **Pydantic** (>=2.0): Data validation and serialization
- **CCXT** (>=4.0): Unified exchange API abstraction (100+ exchanges)
- **Redis** (>=7.0): Online feature store and caching layer
- **Apache Kafka/Redpanda**: Streaming event bus for real-time ingestion
- **PyArrow** (>=13.0): Parquet file I/O and schema evolution
- **PyIceberg** (>=0.5): Iceberg table format for analytical lakehouse
- **Boto3**: S3-compatible object storage client
- **SQLAlchemy** (>=2.0): Metadata database (PostgreSQL) for catalog and lineage

## Module Structure

```
core/data/
├── __init__.py                      # Public API exports
├── models.py                        # Pydantic models: Tick, Bar, Feature
├── ingestion.py                     # Synchronous ingestion pipeline
├── async_ingestion.py               # Async ingestion for high-throughput
├── validation.py                    # Schema and business rule validation
├── quality_control.py               # Statistical quality gates
├── normalization_pipeline.py        # Data cleaning and standardization
├── pipeline.py                      # Generic pipeline orchestration
├── polars_pipeline.py               # Polars-based transformations
├── streaming.py                     # Real-time streaming pipeline
├── feature_store.py                 # Feature store interface (online/offline)
├── feature_catalog.py               # Feature metadata catalog
├── asset_catalog.py                 # Asset registry and normalization
├── catalog.py                       # Generic catalog interface
├── versioning.py                    # Immutable versioning system
├── materialization.py               # Feature computation coordinator
├── backfill.py                      # Historical data retrieval
├── dead_letter.py                   # Dead letter queue management
├── resampling.py                    # Time series resampling utilities
├── timeutils.py                     # Timezone and timestamp handling
├── path_guard.py                    # Filesystem safety guards
├── parity.py                        # Online/offline parity verification
├── preprocess.py                    # Data preprocessing utilities
├── connectors/                      # Exchange-specific adapters
│   ├── ccxt_adapter.py
│   ├── alpaca_adapter.py
│   ├── polygon_adapter.py
│   └── ...
├── adapters/                        # Storage backend adapters
│   ├── redis_adapter.py
│   ├── parquet_adapter.py
│   ├── iceberg_adapter.py
│   └── feast_adapter.py
└── warehouses/                      # Data warehouse integrations
    ├── clickhouse.py
    ├── timescale.py
    └── base.py
```

## Neuroeconomic Principles

### Sensory Filtering (Thalamic Relay)
The ingestion layer implements a two-stage filtering mechanism analogous to the brain's thalamic gating:
1. **Pre-attentive filtering** (`validation.py`): Fast schema checks (< 1ms) reject obviously malformed data
2. **Attentive validation** (`quality_control.py`): Statistical analysis (outlier detection, cross-venue consistency) for accepted payloads

This mirrors how the thalamus rapidly filters irrelevant stimuli before cortical processing.

### Error Detection (Anterior Cingulate Cortex)
`quality_control.py` implements conflict monitoring similar to the ACC:
- Detect unexpected price jumps (> 5σ from recent mean)
- Flag cross-venue price discrepancies (> 1% spread)
- Alert on volume anomalies (> 10× rolling average)
- Trigger automatic quality degradation signals to downstream strategies

### Memory Consolidation (Hippocampus)
The versioning system (`versioning.py`) provides episodic-like memory:
- **Short-term memory**: Redis cache with 1-hour TTL for hot features
- **Long-term memory**: Immutable Parquet snapshots with content-addressable hashing
- **Replay capability**: Reconstruct any historical state from manifest + deltas

### Safety Mechanisms (Amygdala)
The dead letter queue (`dead_letter.py`) acts as a threat isolation circuit:
- Quarantine suspicious data without halting the entire pipeline
- Maintain audit trail for forensic analysis
- Automatic escalation alerts when DLQ threshold exceeded (> 1% of total volume)

## Operational Notes

### SLIs / Metrics:
- `data_ingestion_latency_seconds{source, symbol}`: P50/P99/P99.9 ingestion latency
- `data_validation_error_rate{error_type}`: Rate of validation failures by type
- `feature_store_read_latency_seconds{store_type}`: Online vs offline read performance
- `data_quality_score{symbol, metric}`: Continuous quality score (0.0 to 1.0)
- `dlq_message_count{source}`: Dead letter queue depth by source
- `data_lineage_trace_duration_seconds`: Lineage query performance
- `feature_parity_violation_total{feature_name}`: Online/offline consistency breaches

### Alarms:
- **Critical: Ingestion Pipeline Down**: No data received for > 60 seconds
- **High: DLQ Overflow**: Dead letter queue > 10,000 messages
- **High: Quality Degradation**: Quality score < 0.8 for > 5 minutes
- **Medium: Feature Parity Violation**: Online/offline mismatch detected
- **Medium: Backfill Lag**: Historical data gaps > 7 days

### Runbooks:
- [Data Pipeline Incident Response](../../docs/runbook_data_incident.md)
- [Feature Store Recovery](../../docs/operational_handbook.md#feature-store-recovery)
- [Quality Gate Tuning](../../docs/quality_gates.md#data-quality-thresholds)
- [Dead Letter Queue Management](../../docs/operational_handbook.md#dlq-management)

## Testing Strategy

### Unit Tests:
- **Test Coverage**: 88% (target: 90%)
- **Location**: `tests/core/test_data*.py`
- **Focus Areas**:
  - Schema validation correctness (valid/invalid payloads)
  - Quality gate statistical accuracy (false positive rate < 1%)
  - Versioning determinism (same input → same hash)
  - DLQ isolation (no healthy data affected by bad data)
  - Timestamp normalization edge cases (DST, leap seconds)

### Integration Tests:
- **Location**: `tests/integration/test_data_pipelines.py`
- **Scenarios**:
  - End-to-end ingestion from CCXT → validation → feature store
  - Backfill orchestration with deduplication
  - Feature store parity verification (online vs offline)
  - Dead letter queue recovery and replay

### End-to-End Tests:
- **Location**: `tests/e2e/test_live_ingestion.py`
- **Validation**:
  - Real exchange websocket ingestion (Binance testnet)
  - Quality gates triggered on synthetic anomalies
  - Feature materialization and retrieval within SLA (< 100ms)

### Property-Based Tests:
- **Framework**: Hypothesis
- **Properties Validated**:
  - Versioning: hash(data) deterministic across runs
  - Quality control: no false negatives on known-good data
  - Timestamp normalization: monotonicity preserved
  - Feature store: write-then-read returns identical data

## Usage Examples

### Basic Data Ingestion
```python
from core.data import DataIngestionPipeline, CCXTConnector

# Configure pipeline
pipeline = DataIngestionPipeline(
    connectors=[CCXTConnector(exchange="binance")],
    quality_gates_enabled=True,
    enable_versioning=True,
)

# Ingest OHLCV data
bars = pipeline.ingest_ohlcv(
    symbol="BTC/USDT",
    timeframe="1h",
    since="2024-01-01T00:00:00Z",
    limit=1000,
)

print(f"Ingested {len(bars)} bars")
print(f"Quality score: {bars.metadata['quality_score']:.3f}")
```

### Async Streaming Ingestion
```python
from core.data import AsyncDataIngestionPipeline
import asyncio

async def ingest_realtime():
    pipeline = AsyncDataIngestionPipeline(
        kafka_bootstrap_servers="localhost:9092",
        topics=["market.ticks.btcusdt"],
    )
    
    async for tick in pipeline.stream_ticks():
        print(f"Price: {tick.price}, Volume: {tick.volume}")
        # Quality validation happens automatically
        if tick.quality_flags.has_anomaly:
            print(f"⚠️ Anomaly detected: {tick.quality_flags.reason}")

asyncio.run(ingest_realtime())
```

### Feature Store Operations
```python
from core.data import FeatureStore

# Initialize feature store (Redis + Parquet)
store = FeatureStore(
    online_backend="redis",
    offline_backend="parquet",
    enable_parity_checks=True,
)

# Write feature
store.write_feature(
    name="btc_momentum_5m",
    value=0.42,
    timestamp="2024-11-04T15:30:00Z",
    metadata={"strategy": "momentum", "version": "v2.1"},
)

# Read online feature (< 1ms)
value = store.read_online("btc_momentum_5m")

# Read offline feature batch (historical analysis)
df = store.read_offline(
    features=["btc_momentum_5m", "eth_volatility_1h"],
    start="2024-11-01",
    end="2024-11-04",
)
```

### Quality Control Validation
```python
from core.data import DataQualityController

# Configure quality gates
qc = DataQualityController(
    outlier_threshold_sigma=5.0,
    cross_venue_spread_pct=1.0,
    volume_spike_threshold=10.0,
)

# Validate data batch
validation_result = qc.validate_batch(bars)

if not validation_result.passed:
    print(f"Quality issues detected:")
    for issue in validation_result.issues:
        print(f"  - {issue.type}: {issue.description}")
        print(f"    Severity: {issue.severity}, Affected: {issue.row_indices}")
```

### Dead Letter Queue Management
```python
from core.data import DeadLetterQueue

# Initialize DLQ
dlq = DeadLetterQueue(
    storage_path="./data/dlq",
    retention_days=30,
)

# Retrieve failed messages for review
failed_messages = dlq.get_messages(
    source="binance",
    error_type="schema_validation",
    limit=100,
)

for msg in failed_messages:
    print(f"Failed at: {msg.timestamp}")
    print(f"Error: {msg.error_reason}")
    print(f"Payload: {msg.raw_payload}")
    
    # Optionally replay after fixing issue
    if should_replay(msg):
        dlq.replay_message(msg.id)
```

### Data Versioning
```python
from core.data import DataVersionManager

# Initialize version manager
version_mgr = DataVersionManager(
    storage_backend="parquet",
    enable_compression=True,
)

# Create immutable snapshot
version_id = version_mgr.create_snapshot(
    data=bars_df,
    metadata={
        "source": "binance",
        "symbols": ["BTC/USDT", "ETH/USDT"],
        "timeframe": "1h",
    },
)

print(f"Snapshot ID: {version_id}")

# Retrieve exact snapshot later
bars_restored = version_mgr.load_snapshot(version_id)
assert bars_df.equals(bars_restored)  # Exact reproduction
```

### Backfill Orchestration
```python
from core.data import BackfillOrchestrator

# Configure backfill
backfill = BackfillOrchestrator(
    connectors=[CCXTConnector(exchange="binance")],
    chunk_size_hours=24,
    max_retries=3,
)

# Intelligent gap detection and filling
backfill.fill_gaps(
    symbol="BTC/USDT",
    timeframe="1h",
    start="2023-01-01",
    end="2024-11-04",
    deduplicate=True,
)

# Monitor progress
status = backfill.get_status()
print(f"Progress: {status.completed_pct:.1f}%")
print(f"Gaps remaining: {status.gaps_count}")
```

## Performance Characteristics

### Throughput:
- **Sync ingestion**: 1,000 bars/second per worker
- **Async ingestion**: 50,000 ticks/second (websocket)
- **Feature store writes**: 100,000 features/second (Redis)
- **Feature store reads**: 1M features/second (Redis), 10K features/second (Parquet)

### Latency (P99):
- Schema validation: 0.5ms
- Quality control: 5ms
- Feature store write: 2ms (online), 50ms (offline)
- Feature store read: 1ms (online), 100ms (offline)
- End-to-end ingestion: 50ms (REST), 10ms (websocket)

### Storage Efficiency:
- Raw tick data: ~100 bytes/tick (uncompressed), ~20 bytes/tick (Parquet + zstd)
- OHLCV bars: ~50 bytes/bar (uncompressed), ~10 bytes/bar (compressed)
- Feature vectors: ~8 bytes/feature (float64), ~4 bytes (float32)
- Lineage metadata: ~200 bytes/dataset

### Scalability:
- Horizontal: Deploy multiple ingestion workers (tested up to 32 workers)
- Vertical: Redis sharding for online store (tested up to 1TB)
- Storage: Iceberg lakehouse scales to petabytes with partition pruning

## Changelog

| Date | Author | Change |
| ---- | ------ | ------ |
| 2025-11-04 | data-platform@tradepulse | Created comprehensive README with neuroeconomic context |

## See Also

- [Dataset Catalog](../../docs/dataset_catalog.md)
- [Feature Store Sync and Registry](../../docs/feature_store_sync_and_registry.md)
- [System Modules Reference](../../docs/architecture/system_modules_reference.md)
- [Data Quality Gates](../../docs/quality_gates.md#data-quality)
- [Runbook: Data Incident Response](../../docs/runbook_data_incident.md)
