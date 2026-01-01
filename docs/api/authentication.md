---
owner: integrations@tradepulse
review_cadence: quarterly
last_reviewed: 2026-01-01
links:
  - docs/api/overview.md
  - docs/api/contracts.md
  - docs/documentation_standardisation_playbook.md
---

# API Authentication

## Overview

TradePulse API requests must be authenticated before any trading signal or
prediction data is returned. The public HTTP API relies on **ed25519 request
signatures** provided via `X-TradePulse-Signature`. Admin-only routes use OAuth2
bearer tokens and are documented in the admin OpenAPI spec.

**Supported methods**

| API Surface | Authentication | Header(s) | Notes |
| --- | --- | --- | --- |
| Public HTTP API | ed25519 signature | `X-TradePulse-Signature` | Required for all public routes. |
| Admin remote control | OAuth2 bearer token | `Authorization: Bearer <token>` | Admin scope required. |

## Security requirements

- **TLS 1.2+ required.** Requests sent over plain HTTP or deprecated TLS
  protocols are rejected.
- **Rotate signing keys** at least every 90 days and immediately after any
  suspected compromise.
- **Use least-privilege scopes** for admin tokens; avoid sharing tokens across
  environments.
- **Never log raw secrets** (private keys, bearer tokens, signatures). Log only
  truncated fingerprints or key IDs.
- **Time sync** clients to a trusted NTP source to avoid signature validation
  failures caused by clock drift.

## Idempotency

- **Required for non-GET mutation requests** such as `POST /v1/predictions`.
- Provide a unique `X-Idempotency-Key` per logical request (UUID recommended).
- Replays using the same key within the retention window return the original
  response payload, ensuring safe retries.

## Retry semantics

- **Do not retry** `401` or `403` responses. Re-authenticate and resolve
  credentials first.
- **Retry** `429` and transient `5xx` responses using exponential backoff with
  jitter. Preserve the original `X-Idempotency-Key` for retries.
- **Regenerate signatures** if the request body or headers change; signatures
  are bound to the exact payload.

## Examples

### Signed request (public API)

```http
GET /v1/signals/BTC-USD HTTP/1.1
Host: api.tradepulse.example
X-TradePulse-Signature: v1=<ed25519_signature>
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

### Authentication failure

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
```

```json
{
  "error": {
    "code": "SIGNATURE_INVALID",
    "message": "The request signature could not be verified.",
    "status": 401,
    "request_id": "req-20260101-0007",
    "retryable": false
  }
}
```
