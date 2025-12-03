# MFN Ingestion Specification (MFN-UPSTREAM-CONNECTOR)

## Overview

MFN-UPSTREAM-CONNECTOR provides a unified data ingestion layer for the Mycelium Fractal Net (MFN) platform. It enables standardized connection to external data sources (REST APIs, file feeds, message queues) and transformation of raw data into MFN-compatible requests for feature extraction and simulation.

The ingestion layer follows a pipeline architecture:

```
External Source → Connector → RawEvent → Transformer → MFNRequest → Backend → MFN Core
```

## Architecture

### Components

1. **BaseIngestor** (`connectors/base.py`)
   - Abstract interface for all data connectors
   - Defines `connect()`, `fetch()`, `close()` methods
   - Provides async context manager support

2. **RawEvent** (`connectors/base.py`)
   - Pydantic model representing raw ingested data
   - Fields: `source`, `timestamp`, `payload`, `meta`
   - Immutable (frozen) with automatic timestamp coercion

3. **Transformer** (`connectors/transform.py`)
   - Normalizes RawEvent → NormalizedEvent
   - Maps NormalizedEvent → MFNRequest
   - Configurable field extraction and validation

4. **Connectors**
   - `RestIngestor`: HTTP polling with retry logic
   - `FileFeedIngestor`: JSONL/CSV file reading
   - `KafkaIngestor`: Message queue stub (future)

5. **IngestionRunner** (`connectors/runner.py`)
   - Orchestrates ingestor + backend pipeline
   - Handles batching, backpressure, graceful shutdown
   - Collects metrics and statistics

6. **Backends**
   - `LocalBackend`: Direct Python function calls
   - `RemoteBackend`: gRPC/REST client to MFN service

7. **Configuration** (`connectors/config.py`)
   - Pydantic-based configuration models
   - Environment variable and JSON file support

8. **Metrics** (`connectors/metrics.py`)
   - Thread-safe counters and gauges
   - Event tracking, latency, queue depth

### Data Flow

```
┌─────────────────┐
│  External API   │
│  (REST/Kafka)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Connector     │
│ (RestIngestor)  │
└────────┬────────┘
         │ RawEvent
         ▼
┌─────────────────┐
│   Transformer   │
│  normalize()    │
└────────┬────────┘
         │ NormalizedEvent
         ▼
┌─────────────────┐
│   Transformer   │
│ to_*_request()  │
└────────┬────────┘
         │ MFNRequest
         ▼
┌─────────────────┐
│     Backend     │
│ (Local/Remote)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    MFN Core     │
│ Feature/Sim API │
└─────────────────┘
```

## Supported Sources

### REST API Source

HTTP endpoint polling with configurable interval, retry logic, and authentication.

```python
from mycelium_fractal_net.connectors import RestIngestor

ingestor = RestIngestor(
    url="https://api.example.com/market-data",
    poll_interval_seconds=30,
    batch_size=100,
    max_retries=3,
    timeout=30.0,
    headers={"Authorization": "Bearer ${API_KEY}"},
    params={"symbol": "BTCUSDT"},
)
```

Features:
- Automatic JSON response parsing
- Supports array, `data`, and `results` response formats
- Timestamp extraction from response fields
- Exponential backoff on server errors

### File Feed Source

Local file reading for JSONL and CSV formats.

```python
from mycelium_fractal_net.connectors import FileFeedIngestor

ingestor = FileFeedIngestor(
    path="/data/historical/prices.jsonl",
    format="jsonl",
    batch_size=1000,
    timestamp_field="event_time",
)

# CSV with field mapping
csv_ingestor = FileFeedIngestor(
    path="/data/signals.csv",
    format="csv",
    field_mapping={
        "price_col": "price",
        "vol_col": "volume",
    },
)
```

Features:
- JSON Lines (`.jsonl`) parsing
- CSV with automatic type coercion
- Custom field mapping
- Error handling for malformed records

### Kafka Source (Stub)

Message queue integration stub for future implementation.

```python
from mycelium_fractal_net.connectors import KafkaIngestor

ingestor = KafkaIngestor(
    bootstrap_servers="kafka:9092",
    topic="mfn-events",
    group_id="mfn-consumer",
    auto_offset_reset="latest",
)
```

To enable real Kafka support:
1. Install `aiokafka`: `pip install aiokafka`
2. Implement `_create_consumer()` method
3. Override message parsing in `_parse_message()`

## Configuration

### Environment Variables

```bash
# Source configuration
MFN_SOURCE_TYPE=rest                    # rest, file, kafka
MFN_REST_URL=https://api.example.com/data
MFN_REST_POLL_INTERVAL=60
MFN_FILE_PATH=/data/feed.jsonl
MFN_KAFKA_SERVERS=kafka:9092
MFN_KAFKA_TOPIC=mfn-events

# Backend configuration  
MFN_BACKEND_TYPE=local                  # local, remote
MFN_BACKEND_ENDPOINT=http://mfn:8080
MFN_BACKEND_PROTOCOL=rest               # rest, grpc
MFN_BACKEND_API_KEY=secret

# Processing configuration
MFN_MODE=feature                        # feature, simulation
MFN_BATCH_SIZE=10
MFN_MAX_QUEUE_SIZE=1000
MFN_WORKERS=1
```

### JSON Configuration File

```json
{
  "source_type": "rest",
  "rest_source": {
    "url": "https://api.example.com/data",
    "poll_interval_seconds": 30,
    "batch_size": 100,
    "headers": {
      "Authorization": "Bearer ${API_KEY}"
    }
  },
  "backend": {
    "type": "remote",
    "endpoint": "http://mfn-service:8080",
    "protocol": "rest",
    "api_key": "${MFN_API_KEY}"
  },
  "mode": "feature",
  "batch_size": 10
}
```

Load configuration:

```python
from mycelium_fractal_net.connectors import IngestionConfig

# From environment
config = IngestionConfig.from_env()

# From file
config = IngestionConfig.from_file("config/mfn_ingestion.json")
```

## Examples

### Basic Ingestion Pipeline

```python
import asyncio
from mycelium_fractal_net.connectors import (
    RestIngestor,
    LocalBackend,
    IngestionRunner,
)

async def main():
    ingestor = RestIngestor(
        url="https://api.example.com/prices",
        poll_interval_seconds=60,
    )
    
    backend = LocalBackend()
    
    runner = IngestionRunner(
        ingestor=ingestor,
        backend=backend,
        mode="feature",
        batch_size=10,
    )
    
    # Run until max_events reached
    stats = await runner.run(max_events=100)
    
    print(f"Processed: {stats.events_processed}")
    print(f"Failed: {stats.events_failed}")

asyncio.run(main())
```

### Custom Transformer

```python
from mycelium_fractal_net.connectors import Transformer

# Configure field extraction
transformer = Transformer(
    seed_fields=["values", "features", "data"],
    grid_field="dimensions",
    param_fields=["iterations", "threshold"],
)

runner = IngestionRunner(
    ingestor=ingestor,
    backend=backend,
    transformer=transformer,
)
```

### Remote gRPC Backend

```python
from mycelium_fractal_net.connectors import RemoteBackend

backend = RemoteBackend(
    endpoint="mfn-grpc.example.com:50051",
    protocol="grpc",
    api_key="your-api-key",
    timeout=30.0,
)
```

### File Feed Backfill

```python
from mycelium_fractal_net.connectors import FileFeedIngestor

async def backfill_historical_data():
    ingestor = FileFeedIngestor(
        path="/data/historical/2024-01.jsonl",
        format="jsonl",
    )
    
    runner = IngestionRunner(
        ingestor=ingestor,
        backend=LocalBackend(),
        mode="simulation",
    )
    
    stats = await runner.run()
    print(f"Backfill complete: {stats.events_processed} events")
```

## Integration with gRPC

When using the RemoteBackend with gRPC protocol:

1. Ensure MFN gRPC service is running
2. Configure backend endpoint:

```python
backend = RemoteBackend(
    endpoint="mfn-service.namespace.svc.cluster.local:50051",
    protocol="grpc",
    api_key=os.environ.get("MFN_API_KEY"),
)
```

3. The backend sends requests to:
   - `/api/v1/features/extract` for feature requests
   - `/api/v1/simulation/run` for simulation requests

For full gRPC client implementation, extend `RemoteBackend` with generated protobuf stubs.

## Error Handling

### Exception Classes

- `NormalizationError`: Raw event validation/normalization failed
- `MappingError`: Cannot map normalized event to MFN request

### Handling Errors

```python
from mycelium_fractal_net.connectors import (
    NormalizationError,
    MappingError,
)

try:
    normalized = transformer.normalize(raw_event)
    request = transformer.to_feature_request(normalized)
except NormalizationError as e:
    logger.warning(f"Invalid event from {e.source}: {e.reason}")
except MappingError as e:
    logger.error(f"Mapping failed for {e.request_type}: {e.reason}")
```

## Metrics and Observability

### IngestionMetrics

```python
from mycelium_fractal_net.connectors import IngestionMetrics

metrics = IngestionMetrics(source="rest_api")

# Record events
metrics.record_event_received()
metrics.record_event_processed(latency_ms=15.5)
metrics.record_event_failed()

# Get snapshot
snapshot = metrics.snapshot()
print(f"Success rate: {metrics.success_rate:.1f}%")
print(f"Avg latency: {metrics.avg_latency_ms:.2f}ms")

# Print summary
metrics.log_summary()
```

### Available Metrics

| Metric | Type | Description |
|--------|------|-------------|
| events_received | Counter | Total events from source |
| events_processed | Counter | Successfully processed |
| events_failed | Counter | Failed events |
| events_dropped | Counter | Dropped (queue overflow) |
| normalization_errors | Counter | Validation failures |
| mapping_errors | Counter | Mapping failures |
| backend_errors | Counter | Backend call failures |
| total_latency_ms | Counter | Cumulative latency |
| queue_length | Gauge | Current queue depth |
| lag_seconds | Gauge | Processing lag |

## Testing

Run connector tests:

```bash
pytest tests/connectors/ -v
```

Test files:
- `test_base_interface.py`: BaseIngestor contract tests
- `test_rest_source.py`: HTTP connector with mock server
- `test_file_feed.py`: File parsing scenarios
- `test_transform_mapping.py`: Normalization pipeline
- `test_runner_backend_local.py`: Orchestrator integration

## Future Connectors

Planned extensions beyond this implementation:

1. **Kafka Real Implementation**
   - Full aiokafka integration
   - Consumer group management
   - Offset tracking and commit

2. **Google Pub/Sub**
   - Cloud-native message queue
   - Push and pull subscription

3. **WebSocket Streaming**
   - Real-time data feeds
   - Reconnection handling

4. **Webhook Listener**
   - HTTP callback receiver
   - Event validation and routing

5. **Database CDC**
   - Change data capture
   - PostgreSQL/MySQL replication
