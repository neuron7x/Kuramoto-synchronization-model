---
owner: observability@geosync
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# GeoSync Observability Contracts

**Version:** 1.0.0  
**Status:** Active  
**Scope:** Logging, metrics, tracing, and alerting signals.

## Purpose

Formalize observability signals with strict input/output definitions, SLAs, error models, and versioning for reliable telemetry pipelines.

## Contract Matrix

| Contract | Primary Interface | Scope | Criticality |
| --- | --- | --- | --- |
| Logging | `observability/` | Structured logs | P0 |
| Metrics | `monitoring/` | Metrics emission | P0 |
| Tracing | `observability/` | Distributed tracing | P1 |
| Alerting | `monitoring/` | SLO/SLA alerts | P0 |

## 1. Logging Contract

### Formal Inputs

| Field | Type | Description | Constraints |
| --- | --- | --- | --- |
| `timestamp` | `datetime` | Log event time | UTC |
| `level` | `DEBUG/INFO/WARN/ERROR` | Severity | Required |
| `service` | `str` | Service name | Required |
| `message` | `str` | Human message | Required |
| `trace_id` | `str?` | Correlation id | Optional |
| `payload` | `dict` | Structured context | JSON-serializable |

### Formal Outputs

| Field | Type | Description | Guarantees |
| --- | --- | --- | --- |
| `ingested` | `bool` | Ingestion result | True on success |
| `log_id` | `str` | Event id | Stable idempotency key |

### SLA

- **Ingestion latency:** p95 ≤ 200 ms
- **Delivery:** 99.9% of logs delivered within 1 min

### Error Model

| Error Class | Trigger | Handling | Client Action |
| --- | --- | --- | --- |
| `PayloadTooLarge` | > 256 KB | Reject | Truncate payload |
| `SerializationError` | Non-JSON payload | Reject | Fix payload |

### Versioning

- Log schema versioned with `log_schema_version` field.

## 2. Metrics Contract

### Formal Inputs

| Field | Type | Description | Constraints |
| --- | --- | --- | --- |
| `metric_name` | `str` | Metric id | snake_case |
| `value` | `float` | Metric value | Finite |
| `labels` | `dict` | Dimensions | ≤ 10 labels |
| `timestamp` | `datetime?` | Event time | Optional |

### Formal Outputs

| Field | Type | Description | Guarantees |
| --- | --- | --- | --- |
| `accepted` | `bool` | Ingest outcome | True on success |
| `series_id` | `str` | Series hash | Deterministic |

### SLA

- **Ingestion latency:** p95 ≤ 100 ms
- **Availability:** 99.95% monthly

### Error Model

| Error Class | Trigger | Handling | Client Action |
| --- | --- | --- | --- |
| `LabelCardinalityExceeded` | > 10 labels | Reject | Reduce labels |
| `MetricTypeMismatch` | Wrong type | Reject | Fix metric type |

### Versioning

- Metric naming conventions versioned in metrics catalog.

## 3. Tracing Contract

### Formal Inputs

| Field | Type | Description | Constraints |
| --- | --- | --- | --- |
| `trace_id` | `str` | Trace identifier | 16-byte hex |
| `span_id` | `str` | Span identifier | 8-byte hex |
| `parent_span_id` | `str?` | Parent span | Optional |
| `operation` | `str` | Operation name | Required |
| `duration_ms` | `float` | Span duration | ≥ 0 |

### Formal Outputs

| Field | Type | Description | Guarantees |
| --- | --- | --- | --- |
| `indexed` | `bool` | Trace indexed | True on success |
| `trace_uri` | `str` | Trace lookup | Stable permalink |

### SLA

- **Indexing latency:** p95 ≤ 5 s

### Error Model

| Error Class | Trigger | Handling | Client Action |
| --- | --- | --- | --- |
| `SamplingDropped` | Sampling policy | Dropped | No retry |
| `TraceMalformed` | Invalid ids | Reject | Fix instrumentation |

### Versioning

- Trace payload versioned by OpenTelemetry spec version.

## 4. Alerting Contract

### Formal Inputs

| Field | Type | Description | Constraints |
| --- | --- | --- | --- |
| `alert_name` | `str` | Alert identifier | Unique |
| `severity` | `P1/P2/P3` | Severity | Required |
| `condition` | `str` | Trigger condition | Must map to SLO |
| `runbook` | `str` | Runbook URL | Required |

### Formal Outputs

| Field | Type | Description | Guarantees |
| --- | --- | --- | --- |
| `triggered` | `bool` | Trigger status | Deterministic |
| `incident_id` | `str?` | Incident id | Populated on trigger |

### SLA

- **Alert evaluation:** every 30 s
- **Notification latency:** p95 ≤ 60 s

### Error Model

| Error Class | Trigger | Handling | Client Action |
| --- | --- | --- | --- |
| `AlertDefinitionInvalid` | Malformed condition | Reject | Fix alert definition |
| `NotificationFailure` | Pager failure | Retry | Escalate to backup channel |

### Versioning

- Alert definitions versioned per release, stored in monitoring registry.

## Cross-Links

- **Schemas:** [docs/schemas/index.json](../schemas/index.json)
- **Canonical Schemas:** [schemas/](../../schemas/)
- **Interfaces:** [observability/](../../observability/), [monitoring/](../../monitoring/)
- **Related Docs:** [docs/OBSERVABILITY_SPEC.md](../OBSERVABILITY_SPEC.md), [docs/metrics_discipline.md](../metrics_discipline.md)
