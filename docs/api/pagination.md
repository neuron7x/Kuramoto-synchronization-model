---
owner: integrations@geosync
review_cadence: quarterly
last_reviewed: 2026-01-01
links:
  - docs/api/overview.md
  - docs/api/contracts.md
  - docs/documentation_standardisation_playbook.md
---

# API Pagination

## Overview

GeoSync uses cursor-based pagination for endpoints that return collections,
including feature extraction and prediction query APIs. Pagination state is
returned inside the response `pagination` object.

## Pagination model

**Request parameters**

| Parameter | Type | Description |
| --- | --- | --- |
| `limit` | integer | Maximum items to return (default 100, max 500). |
| `cursor` | string | Opaque continuation token returned by previous response. |

**Response payload**

```json
"pagination": {
  "cursor": "eyJvZmZzZXQiOjEwMH0=",
  "limit": 100,
  "next_cursor": "eyJvZmZzZXQiOjIwMH0=",
  "returned": 100
}
```

## Security requirements

- **Treat cursors as opaque secrets**; they may embed encoded offsets or
  filters and should not be logged or exposed to end users.
- **Use TLS 1.2+** for all paginated responses to prevent leakage of cursor
  tokens.
- **Validate input limits** client-side to avoid accidental quota exhaustion.

## Idempotency

- Paginated GET requests are idempotent and can be retried safely.
- If a POST endpoint supports pagination (for large query bodies), include
  `X-Idempotency-Key` to guarantee consistent results across retries.

## Retry semantics

- Retrying with the same `cursor` and `limit` should return the same page unless
  the underlying dataset has changed.
- For stable pagination, use time-bounded filters (e.g., `startAt`, `endAt`) to
  avoid page drift as new data arrives.
- Apply exponential backoff on `429` and `503` responses.

## Examples

### Request with cursor

```http
POST /v1/features?limit=100&cursor=eyJvZmZzZXQiOjEwMH0= HTTP/1.1
Host: api.geosync.example
X-GeoSync-Signature: v1=<ed25519_signature>
X-Idempotency-Key: 7f79c786-1f7d-4f77-a3c8-4c8f460b6d43
```

```json
{
  "symbol": "BTC-USD",
  "bars": [
    {
      "timestamp": "2026-01-01T10:00:00Z",
      "open": 43120.5,
      "high": 43190.2,
      "low": 43080.1,
      "close": 43110.8,
      "volume": 124.3
    }
  ]
}
```

### Paginated response

```json
{
  "symbol": "BTC-USD",
  "generated_at": "2026-01-01T10:00:01Z",
  "features": {
    "entropy": 3.2,
    "hurst": 0.62,
    "ricci": 0.34
  },
  "items": [
    {
      "timestamp": "2026-01-01T10:00:00Z",
      "features": {
        "entropy": 3.2,
        "hurst": 0.62,
        "ricci": 0.34
      }
    }
  ],
  "pagination": {
    "cursor": "eyJvZmZzZXQiOjEwMH0=",
    "limit": 100,
    "next_cursor": "eyJvZmZzZXQiOjIwMH0=",
    "returned": 100
  }
}
```
