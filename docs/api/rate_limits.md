---
owner: integrations@geosync
review_cadence: quarterly
last_reviewed: 2026-01-01
links:
  - docs/api/overview.md
  - docs/api/contracts.md
  - docs/documentation_standardisation_playbook.md
---

# API Rate Limits

## Overview

GeoSync applies layered rate limits to protect system stability. Limits are
enforced per API key or signature identity and reset on rolling time windows.

## Current limits

| Route | Bucket | Limit | Notes |
| --- | --- | --- | --- |
| `GET /v1/signals/{symbol}` | minute | 180/min | Shared across all symbols. |
| `GET /v1/signals/{symbol}` | hour | 5,000/hour | Aggregated across minute buckets. |
| `GET /v1/signals/{symbol}` | day | 40,000/day | Hard quota reset at UTC midnight. |
| `POST /v1/predictions` | minute | 30/min | Idempotency required. |
| `POST /v1/predictions` | hour | 500/hour | Includes queued retries. |
| `POST /v1/predictions` | day | 3,000/day | Hard quota reset at UTC midnight. |

## Response headers

Rate limit metadata is returned on every response:

| Header | Description |
| --- | --- |
| `X-RateLimit-Limit` | Current bucket limit. |
| `X-RateLimit-Remaining` | Remaining requests in the bucket. |
| `X-RateLimit-Reset` | UTC epoch seconds when the bucket resets. |
| `Retry-After` | Seconds to wait before retrying (on 429 responses). |

## Security requirements

- **Never share API credentials** between tenants or environments to avoid
  cross-tenant throttling.
- **Monitor rate-limit headers** and alert on unexpected spikes to detect
  credential leakage.
- **Use TLS 1.2+** and validate certificates to prevent MITM interception of
  throttling metadata.

## Idempotency

- Keep the same `X-Idempotency-Key` when retrying throttled mutation requests.
- Idempotency guarantees prevent duplicate processing if a retry is accepted
  after a `429` response.

## Retry semantics

- Honor `Retry-After` when present. If absent, use exponential backoff with
  jitter starting at 1s (1s, 2s, 4s, 8s, ...).
- Avoid parallel retries; queue requests client-side to smooth bursts.
- Stop retries after 5 attempts or when the user-specified timeout is reached.

## Examples

### Successful request with limits

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 180
X-RateLimit-Remaining: 176
X-RateLimit-Reset: 1767270900
```

```json
{
  "as_of": "2026-01-01T10:15:00Z",
  "confidence": 0.82,
  "horizon_minutes": 30,
  "signal": "BUY",
  "symbol": "BTC-USD"
}
```

### Throttled request

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 4
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1767270904
```

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests. Retry after 4 seconds.",
    "status": 429,
    "request_id": "req-20260101-0145",
    "retryable": true
  }
}
```
