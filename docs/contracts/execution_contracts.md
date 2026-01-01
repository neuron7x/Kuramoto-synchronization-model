---
owner: execution-platform@tradepulse
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# TradePulse Execution Contracts

**Version:** 1.0.0  
**Status:** Active  
**Scope:** Order routing, risk checks, and execution acknowledgements.

## Purpose

Specify formal execution-plane contracts: required inputs/outputs, SLAs, error models, and versioning to ensure deterministic trade lifecycle behavior.

## Contract Matrix

| Contract | Primary Interface | Scope | Criticality |
| --- | --- | --- | --- |
| Order Submission | `interfaces/execution/base.py` | New order placement | P0 |
| Order Amend/Cancel | `interfaces/execution/base.py` | Order lifecycle actions | P0 |
| Pre-Trade Risk | `interfaces/execution/common.py` | Risk gating | P0 |
| Execution Report | `interfaces/execution/common.py` | Trade confirmations | P0 |

## 1. Order Submission Contract

### Formal Inputs

| Field | Type | Description | Constraints |
| --- | --- | --- | --- |
| `client_order_id` | `str` | Client-generated id | Unique per session |
| `symbol` | `str` | Asset symbol | Must be supported by venue |
| `side` | `BUY | SELL` | Order side | Required |
| `order_type` | `LIMIT | MARKET | STOP` | Order type | Required |
| `quantity` | `Decimal` | Order quantity | > 0 |
| `limit_price` | `Decimal?` | Limit price | Required for LIMIT |
| `time_in_force` | `GTC | IOC | FOK` | TIF policy | Required |

### Formal Outputs

| Field | Type | Description | Guarantees |
| --- | --- | --- | --- |
| `order_id` | `str` | Venue order id | Immutable per order |
| `status` | `ACK | REJECT` | Submission status | Deterministic |
| `timestamp` | `datetime` | Acknowledgement time | UTC |
| `reason` | `str?` | Reject reason | Populated on reject |

### SLA

- **Ack latency:** p95 ≤ 120 ms to venue ack
- **Availability:** 99.95% monthly
- **Order integrity:** 0 duplicate submissions per idempotency key

### Error Model

| Error Class | Trigger | Handling | Client Action |
| --- | --- | --- | --- |
| `RiskRejected` | Pre-trade risk fail | Reject | Update position/limits |
| `VenueRejected` | Venue rejects | Reject | Inspect reason and retry if allowed |
| `ConnectivityError` | Network failure | Retry with backoff | Idempotent retry |

### Versioning

- `OrderRequest` and `OrderAck` schemas versioned by major release.
- Backward compatibility maintained for 2 minor versions.

## 2. Order Amend / Cancel Contract

### Formal Inputs

| Field | Type | Description | Constraints |
| --- | --- | --- | --- |
| `order_id` | `str` | Venue order id | Must exist |
| `client_order_id` | `str` | Client id | Required for cancel |
| `new_quantity` | `Decimal?` | Updated quantity | > 0 |
| `new_limit_price` | `Decimal?` | Updated limit price | Required for amend |

### Formal Outputs

| Field | Type | Description | Guarantees |
| --- | --- | --- | --- |
| `status` | `CANCELLED | AMENDED | REJECT` | Action status | Deterministic |
| `effective_time` | `datetime` | When change applied | UTC |
| `reason` | `str?` | Reject reason | Populated on reject |

### SLA

- **Cancel latency:** p95 ≤ 150 ms
- **Amend latency:** p95 ≤ 180 ms

### Error Model

| Error Class | Trigger | Handling | Client Action |
| --- | --- | --- | --- |
| `OrderNotFound` | Unknown order | Reject | Sync order state |
| `AlreadyFilled` | Order filled before cancel | Reject | Update position |

### Versioning

- Amend/cancel payloads tied to venue adapter version.

## 3. Pre-Trade Risk Contract

### Formal Inputs

| Field | Type | Description | Constraints |
| --- | --- | --- | --- |
| `risk_profile` | `RiskProfile` | Limits & thresholds | Must be current |
| `order_request` | `OrderRequest` | Proposed order | Must be valid |

### Formal Outputs

| Field | Type | Description | Guarantees |
| --- | --- | --- | --- |
| `decision` | `ALLOW | BLOCK` | Risk decision | Deterministic |
| `rule_hits` | `List[str]` | Violated rules | Ordered by severity |

### SLA

- **Decision latency:** p99 ≤ 20 ms

### Error Model

| Error Class | Trigger | Handling | Client Action |
| --- | --- | --- | --- |
| `RiskProfileStale` | Profile older than TTL | Block | Refresh profile |
| `RiskEngineUnavailable` | Risk service down | Fail closed | Trigger circuit-breaker |

### Versioning

- Risk rule set versions captured in decision metadata.

## 4. Execution Report Contract

### Formal Inputs

| Field | Type | Description | Constraints |
| --- | --- | --- | --- |
| `order_id` | `str` | Venue order id | Must exist |
| `execution_id` | `str` | Fill id | Unique per fill |
| `filled_qty` | `Decimal` | Filled quantity | ≥ 0 |
| `fill_price` | `Decimal` | Fill price | > 0 |

### Formal Outputs

| Field | Type | Description | Guarantees |
| --- | --- | --- | --- |
| `position_update` | `PositionDelta` | Post-trade delta | Exact match to fill |
| `execution_status` | `PARTIAL | FILLED | CANCELLED` | Execution state | Deterministic |

### SLA

- **Report latency:** p95 ≤ 200 ms after venue fill
- **Delivery guarantee:** At-least-once with idempotent consumer

### Error Model

| Error Class | Trigger | Handling | Client Action |
| --- | --- | --- | --- |
| `DuplicateFill` | Already processed fill | Ignore | Idempotent handling |
| `OutOfOrderFill` | Fill before ack | Buffer | Reorder by timestamp |

### Versioning

- Execution report schemas versioned per venue adapter.

## Cross-Links

- **Schemas:** [docs/schemas/index.json](../schemas/index.json)
- **Canonical Schemas:** [schemas/](../../schemas/)
- **Interfaces:** [interfaces/execution/base.py](../../interfaces/execution/base.py), [interfaces/execution/common.py](../../interfaces/execution/common.py)
- **Related Docs:** [docs/execution.md](../execution.md), [docs/risk_controls.md](../risk_controls.md)
