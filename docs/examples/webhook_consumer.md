---
owner: dx@geosync
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# Webhook Consumer Example

Consume `signal.published` and `prediction.completed` events with the schemas
listed in `docs/api/webhooks.md` and `schemas/events/json/1.0.0/*`.

## Prerequisites

- Public HTTPS endpoint for GeoSync to call (TLS 1.2+).
- **ed25519 verification key** for `X-GeoSync-Webhook` signatures.
- Dedupe store keyed by `event_id` (e.g., Redis, Postgres).
- Ability to respond **2xx within 2 seconds** and process asynchronously.

## Sample Handler (Pseudo-code)

```python
from geosync_webhooks import verify_signature

seen = set()

def handle_webhook(headers, body):
    if not verify_signature(headers, body):
        return 401

    event = json.loads(body)
    event_id = event["event_id"]

    if event_id in seen:
        return 200  # Idempotent replay

    seen.add(event_id)

    if "prediction" in event:
        process_prediction(event)
    else:
        process_signal(event)

    return 204
```

## Expected Outputs

- **2xx response with empty body** to acknowledge receipt.
- Event payloads match the schemas in `docs/api/webhooks.md`.

Example `signal.published` payload:
```json
{
  "event_id": "sig-20250201-001",
  "schema_version": "1.0.0",
  "symbol": "BTC-USD",
  "timestamp": 1738413000,
  "signal_type": "momentum",
  "strength": 0.72,
  "direction": "BUY",
  "ttl_seconds": 90,
  "metadata": {
    "venue": "BINANCE"
  }
}
```

Example `prediction.completed` payload:
```json
{
  "event_id": "pred-20250201-001",
  "schema_version": "1.0.0",
  "request_id": "pred-20250201-001",
  "symbol": "BTC-USD",
  "completed_at": "2025-02-01T12:32:30Z",
  "prediction": {
    "horizon_minutes": 30,
    "value": 0.0034,
    "confidence": 0.82,
    "distribution": {
      "p05": -0.0012,
      "p50": 0.0034,
      "p95": 0.0068
    }
  },
  "metadata": {
    "model": "online-inference-v1",
    "venue": "BINANCE"
  }
}
```

## Retry / Idempotency Scheme

- **Delivery attempts** (from `docs/api/webhooks.md`):
  - `signal.published`: 5 attempts with 30s backoff.
  - `prediction.completed`: 8 attempts with 45s backoff.
- **Idempotency**: use `event_id` as a dedupe key. Replays must return 2xx.
- **Timeouts**: return `202/204` immediately and process asynchronously to avoid
  repeat delivery.
