---
owner: data-platform@tradepulse
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# TradePulse Data Contracts

**Version:** 1.0.0  
**Status:** Active  
**Scope:** Market data ingestion, feature storage, and data delivery surfaces.

## Purpose

Define formal data-plane contracts with explicit inputs/outputs, SLAs, error models, and versioning rules for reproducible data workflows.

## Contract Matrix

| Contract | Primary Interface | Scope | Criticality |
| --- | --- | --- | --- |
| Market Data Ingestion | `interfaces/ingestion.py` | Raw market data intake | P0 |
| Feature Store Publish | `interfaces/backtest.py` | Feature materialization | P1 |
| Data Retrieval | `interfaces/ingestion.py` | Time-travel queries | P0 |

## 1. Market Data Ingestion Contract

### Formal Inputs

| Field | Type | Description | Constraints |
| --- | --- | --- | --- |
| `data_batch` | `List[MarketDataPoint]` | OHLCV bars with metadata | Non-empty, sorted by timestamp |
| `idempotency_key` | `str?` | Deduplication key | Unique per logical batch |
| `source` | `str` | Provider identifier | Must exist in source registry |

### Formal Outputs

| Field | Type | Description | Guarantees |
| --- | --- | --- | --- |
| `version_id` | `UUID` | Immutable batch version | Stable across retries |
| `accepted_count` | `int` | Accepted records | `accepted + rejected = total` |
| `rejected_count` | `int` | Rejected records | Validation failures only |
| `quality_score` | `float` | Quality score | [0, 1] inclusive |
| `errors` | `List[str]` | Validation errors | Deterministic ordering |

### SLA

- **Ingestion latency:** p95 ≤ 150 ms for ≤ 1k bars per symbol
- **Throughput:** ≥ 100k bars/sec sustained
- **Availability:** 99.9% monthly

### Error Model

| Error Class | Trigger | Handling | Client Action |
| --- | --- | --- | --- |
| `ValidationError` | OHLCV invariant violated | Batch rejected | Fix data & retry |
| `DeduplicationError` | Idempotency key reused | Return prior result | Treat as success |
| `DependencyUnavailable` | Storage or queue unavailable | Exponential backoff | Retry with jitter |

### Versioning

- **Schema:** Semantic versioning of `MarketDataPoint` schema.
- **Batch:** `version_id` immutable per accepted batch.
- **Backward compatibility:** Deserialization supports N-2 versions.

## 2. Feature Store Publish Contract

### Formal Inputs

| Field | Type | Description | Constraints |
| --- | --- | --- | --- |
| `feature_set` | `FeatureSet` | Feature vectors | Immutable, versioned |
| `entity_key` | `str` | Asset or portfolio key | Must exist in catalog |
| `feature_time` | `datetime` | Point-in-time timestamp | UTC, monotonic |

### Formal Outputs

| Field | Type | Description | Guarantees |
| --- | --- | --- | --- |
| `feature_version` | `UUID` | Feature snapshot id | Idempotent per key/time |
| `published` | `bool` | Publish outcome | True on success |
| `lineage` | `dict` | Source + transform metadata | Non-empty on success |

### SLA

- **Publish latency:** p95 ≤ 250 ms per feature set
- **Availability:** 99.7% monthly

### Error Model

| Error Class | Trigger | Handling | Client Action |
| --- | --- | --- | --- |
| `LineageError` | Missing upstream metadata | Publish blocked | Fix lineage metadata |
| `StoreConflict` | Version conflict | Return latest id | Refresh + retry |

### Versioning

- Feature schemas adhere to `features/v{major}` namespace.
- Version pinning required in model registry.

## 3. Data Retrieval Contract

### Formal Inputs

| Field | Type | Description | Constraints |
| --- | --- | --- | --- |
| `symbol` | `str` | Asset symbol | Valid catalog entry |
| `start_time` | `datetime` | Inclusive start | `< end_time` |
| `end_time` | `datetime` | Exclusive end | UTC |
| `version_id` | `UUID?` | Snapshot id | Optional |

### Formal Outputs

| Field | Type | Description | Guarantees |
| --- | --- | --- | --- |
| `data_frame` | `DataFrame` | OHLCV time series | Gap-free or annotated |
| `version_id` | `UUID` | Snapshot used | Deterministic |
| `lineage` | `dict` | Provenance metadata | Must include source |

### SLA

- **Query latency:** p95 ≤ 400 ms for ≤ 30 days per symbol
- **Availability:** 99.9% monthly

### Error Model

| Error Class | Trigger | Handling | Client Action |
| --- | --- | --- | --- |
| `NotFound` | Symbol or version missing | Return 404 | Correct query |
| `Timeout` | Query exceeds SLA | Return partial? no | Retry with narrower range |

### Versioning

- Queryable versions retained for ≥ 90 days.
- Time-travel reads require explicit `version_id` beyond retention window.

## Cross-Links

- **Schemas:** [docs/schemas/index.json](../schemas/index.json), [docs/schemas/BacktestResult.json](../schemas/BacktestResult.json)
- **Canonical Schemas:** [schemas/](../../schemas/)
- **Interfaces:** [interfaces/ingestion.py](../../interfaces/ingestion.py), [interfaces/backtest.py](../../interfaces/backtest.py)
- **Related Docs:** [docs/MFN_INGESTION_SPEC.md](../MFN_INGESTION_SPEC.md), [docs/DATA_GOVERNANCE.md](../DATA_GOVERNANCE.md)
