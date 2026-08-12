---
owner: integrations@geosync
review_cadence: quarterly
last_reviewed: 2026-01-01
links:
  - docs/api/overview.md
  - docs/api/contracts.md
  - docs/documentation_standardisation_playbook.md
---

# API Error Model

## Overview

All GeoSync API errors follow a consistent JSON envelope. Clients should
parse the `error` object, map it to retries or user messaging, and capture the
`request_id` for support escalation.

## Error envelope

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests. Retry after 4 seconds.",
    "status": 429,
    "request_id": "req-20260101-0042",
    "retryable": true,
    "details": {
      "limit": "180/min",
      "retry_after": 4
    }
  }
}
```

**Field glossary**

| Field | Type | Description |
| --- | --- | --- |
| `code` | string | Stable error identifier (machine-readable). |
| `message` | string | Human-friendly summary. |
| `status` | integer | HTTP status code. |
| `request_id` | string | Correlation ID for support. |
| `retryable` | boolean | Whether the request can be retried safely. |
| `details` | object | Optional structured metadata. |

## HTTP status mapping

| Status | Example code | Description | Retry guidance |
| --- | --- | --- | --- |
| 400 | `INVALID_ARGUMENT` | Malformed request body or headers. | Do not retry until fixed. |
| 401 | `SIGNATURE_INVALID` | Missing/invalid signature or token. | Re-authenticate; do not auto-retry. |
| 403 | `SCOPE_DENIED` | Authenticated but insufficient scope. | Do not retry without scope change. |
| 404 | `NOT_FOUND` | Resource does not exist. | Do not retry unless resource is created. |
| 409 | `IDEMPOTENCY_CONFLICT` | Idempotency key reused with different payload. | Resolve client logic before retrying. |
| 422 | `VALIDATION_FAILED` | Schema or constraint validation failed. | Do not retry until fixed. |
| 429 | `RATE_LIMIT_EXCEEDED` | Rate or quota exceeded. | Retry after backoff or `Retry-After`. |
| 500 | `INTERNAL_ERROR` | Unexpected server failure. | Retry with backoff. |
| 503 | `SERVICE_UNAVAILABLE` | Transient overload or maintenance. | Retry with backoff and jitter. |

## Security requirements

- **Mask sensitive fields** (signatures, bearer tokens, webhook secrets) in
  request/response logs.
- **Use TLS 1.2+** for all error responses to prevent exposure of metadata.
- **Avoid leaking PII** inside `details`; provide redacted or hashed references
  where possible.

## Idempotency

- Errors returned for idempotent requests must preserve the original
  `request_id` when the same `X-Idempotency-Key` is replayed.
- For `IDEMPOTENCY_CONFLICT`, clients must generate a new key or ensure the
  payload matches the original request.

## Retry semantics

- Retry **only** when `retryable=true` or when status is `429`, `500`, `503`.
- Apply **exponential backoff with jitter** and respect `Retry-After` headers.
- Preserve the original idempotency key for safe retries of mutation requests.

## Examples

### Validation failure

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json
```

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "horizon_minutes must be between 1 and 1440.",
    "status": 422,
    "request_id": "req-20260101-0113",
    "retryable": false,
    "details": {
      "field": "horizon_minutes",
      "constraint": "1..1440"
    }
  }
}
```

### Rate limit response

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 4
```

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests. Retry after 4 seconds.",
    "status": 429,
    "request_id": "req-20260101-0145",
    "retryable": true,
    "details": {
      "limit": "180/min",
      "retry_after": 4
    }
  }
}
```
