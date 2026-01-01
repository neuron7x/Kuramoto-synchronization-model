---
owner: runtime-platform@tradepulse
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# TradePulse Runtime Contracts

**Version:** 1.0.0  
**Status:** Active  
**Scope:** Scheduler, orchestration, and lifecycle management for runtime services.

## Purpose

Define runtime-control contracts with explicit inputs/outputs, SLAs, error handling, and versioning for deterministic execution environments.

## Contract Matrix

| Contract | Primary Interface | Scope | Criticality |
| --- | --- | --- | --- |
| Job Scheduling | `runtime/` | Job admission and scheduling | P0 |
| Service Lifecycle | `runtime/` | Start/stop/health | P0 |
| State Checkpointing | `runtime/` | Durable state snapshots | P1 |

## 1. Job Scheduling Contract

### Formal Inputs

| Field | Type | Description | Constraints |
| --- | --- | --- | --- |
| `job_id` | `str` | Job identifier | Globally unique |
| `priority` | `int` | Scheduling priority | 0-10 |
| `deadline` | `datetime?` | Execution deadline | Optional |
| `resources` | `ResourceSpec` | CPU/GPU/memory | Must be allocatable |

### Formal Outputs

| Field | Type | Description | Guarantees |
| --- | --- | --- | --- |
| `status` | `ADMITTED | QUEUED | REJECTED` | Admission status | Deterministic |
| `scheduled_time` | `datetime?` | Planned start | UTC |
| `reason` | `str?` | Rejection reason | Populated on reject |

### SLA

- **Admission latency:** p95 ≤ 50 ms
- **Queue time:** p95 ≤ 500 ms for priority ≥ 8
- **Availability:** 99.8% monthly

### Error Model

| Error Class | Trigger | Handling | Client Action |
| --- | --- | --- | --- |
| `InsufficientResources` | Resource cap exceeded | Reject | Reduce footprint |
| `DeadlineMiss` | Cannot meet SLA | Reject | Extend deadline |

### Versioning

- `ResourceSpec` versioned with runtime release.

## 2. Service Lifecycle Contract

### Formal Inputs

| Field | Type | Description | Constraints |
| --- | --- | --- | --- |
| `service_id` | `str` | Service identifier | Unique |
| `action` | `START | STOP | RESTART` | Lifecycle action | Required |
| `config_version` | `str` | Config snapshot | Immutable |

### Formal Outputs

| Field | Type | Description | Guarantees |
| --- | --- | --- | --- |
| `state` | `RUNNING | STOPPED | DEGRADED` | Service state | Deterministic |
| `health` | `HealthStatus` | Health summary | Updated within 30s |
| `transition_time` | `datetime` | Action completion | UTC |

### SLA

- **Start latency:** p95 ≤ 2 s
- **Stop latency:** p95 ≤ 1 s
- **Health refresh:** ≤ 30 s

### Error Model

| Error Class | Trigger | Handling | Client Action |
| --- | --- | --- | --- |
| `ConfigMismatch` | Invalid config version | Reject | Sync config |
| `DependencyUnavailable` | Dependency down | Degraded state | Trigger failover |

### Versioning

- Lifecycle API versioned by runtime control plane release.

## 3. State Checkpointing Contract

### Formal Inputs

| Field | Type | Description | Constraints |
| --- | --- | --- | --- |
| `state_id` | `str` | State snapshot id | Unique |
| `payload` | `bytes` | Serialized state | Max 50 MB |
| `checksum` | `str` | Integrity hash | SHA-256 |

### Formal Outputs

| Field | Type | Description | Guarantees |
| --- | --- | --- | --- |
| `checkpoint_id` | `str` | Stored checkpoint id | Immutable |
| `stored_at` | `datetime` | Storage time | UTC |
| `verified` | `bool` | Checksum verified | True on success |

### SLA

- **Checkpoint latency:** p95 ≤ 500 ms for 10 MB payloads
- **Retention:** 30 days hot, 180 days cold

### Error Model

| Error Class | Trigger | Handling | Client Action |
| --- | --- | --- | --- |
| `ChecksumMismatch` | Hash mismatch | Reject | Recompute + retry |
| `StorageUnavailable` | Storage down | Retry | Backoff |

### Versioning

- State serializers versioned with model/runtime release.

## Cross-Links

- **Schemas:** [docs/schemas/index.json](../schemas/index.json)
- **Canonical Schemas:** [schemas/](../../schemas/)
- **Interfaces:** [runtime/](../../runtime/), [interfaces/cli.py](../../interfaces/cli.py)
- **Related Docs:** [docs/OPERATIONS.md](../OPERATIONS.md), [docs/runbook_time_synchronization.md](../runbook_time_synchronization.md)
