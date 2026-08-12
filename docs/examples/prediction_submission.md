---
owner: dx@geosync
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# Prediction Submission (Async)

Submit an asynchronous prediction request to `POST /v1/predictions` using the
`PredictionCreateRequest` contract in `docs/api/contracts.md`.

## Prerequisites

- **API base URL**: `https://api.geosync.example` (or staging).
- **ed25519 signing key** for `X-GeoSync-Signature`.
- **Idempotency key generator** (UUID recommended).
- **Webhook endpoint** (optional) for `prediction.completed` events.

## Request

```bash
curl -sS -X POST https://api.geosync.example/v1/predictions \
  -H "Content-Type: application/json" \
  -H "X-GeoSync-Signature: v1=<ed25519_signature>" \
  -H "X-Idempotency-Key: 0a6b5c2b-5338-4f0d-8b85-887d9306a63f" \
  -d @- <<'JSON'
{
  "symbol": "BTC-USD",
  "horizon_minutes": 30,
  "features": {
    "entropy": 3.2,
    "hurst": 0.62,
    "ricci": 0.34
  },
  "delivery": {
    "webhook": "https://hooks.example.com/predictions"
  }
}
JSON
```

## Expected Outputs

**202 Accepted** — `PredictionCreateResponse`
```json
{
  "estimated_completion_at": "2025-02-01T12:32:30Z",
  "links": {
    "status": "https://api.geosync.example/v1/predictions/pred-20250201-001",
    "webhook": "https://webhooks.geosync.example/predictions/pred-20250201-001"
  },
  "request_id": "pred-20250201-001",
  "status": "accepted",
  "submitted_at": "2025-02-01T12:31:00Z"
}
```

When processing completes, a `prediction.completed` webhook is delivered per
`docs/api/webhooks.md`.

## Retry / Idempotency Scheme

- **Idempotency**: `X-Idempotency-Key` is **required** for `POST /v1/predictions`.
  - Replays with the same key return the original `202` response payload.
  - Keep the key stable across retries and client restarts.
- **Retry policy**:
  - **Do not retry** `4xx` except `429`.
  - **Retry** `429`/`5xx` with exponential backoff + jitter.
  - Preserve the original idempotency key and regenerate the signature only if
    the payload changes.

## Contract Alignment Notes

- Request/response fields and headers are aligned with the `PredictionCreateRequest`
  and `PredictionCreateResponse` contracts in `docs/api/contracts.md`.
- Example response matches `docs/api/examples/create-prediction-202.json`.
