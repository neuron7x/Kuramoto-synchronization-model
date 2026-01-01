---
owner: dx@tradepulse
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# SDK Integration Flow

This example outlines a minimal client SDK that wraps TradePulse public API
requests and aligns with `docs/api/contracts.md` and `docs/api/authentication.md`.

## Prerequisites

- HTTP client with TLS 1.2+ support.
- ed25519 signing library for `X-TradePulse-Signature`.
- Persistent store for `X-Idempotency-Key` values (required for predictions).
- Optional webhook endpoint for async completion events.

## Suggested SDK Shape

```python
class TradePulseClient:
    def __init__(self, base_url, signer, idempotency_store):
        self.base_url = base_url
        self.signer = signer
        self.idempotency_store = idempotency_store

    def get_signal(self, symbol):
        path = f"/v1/signals/{symbol}"
        headers = self.signer.sign("GET", path)
        return http.get(self.base_url + path, headers=headers)

    def submit_prediction(self, payload, request_key=None):
        path = "/v1/predictions"
        key = request_key or self.idempotency_store.next_key()
        headers = self.signer.sign("POST", path, body=payload)
        headers["X-Idempotency-Key"] = key
        return http.post(self.base_url + path, json=payload, headers=headers)
```

## Expected Outputs

- `get_signal(...)` returns a `MarketSignalResponse` as documented in
  `docs/api/contracts.md`.
- `submit_prediction(...)` returns a `PredictionCreateResponse` and the
  `request_id` will later appear in a `prediction.completed` webhook.

## Retry / Idempotency Scheme

- **Read calls** (`GET /v1/signals/{symbol}`): retry `429/5xx` with exponential
  backoff + jitter.
- **Write calls** (`POST /v1/predictions`):
  - Always include `X-Idempotency-Key` and persist it alongside the request.
  - Retry `429/5xx` using the **same** key to avoid duplicate predictions.
  - If payload changes, generate a new idempotency key and signature.

## Contract Alignment Notes

- Headers, routes, and payloads mirror the public API contracts in
  `docs/api/contracts.md` and governance guidance in `docs/api/overview.md`.
- Webhook expectations match `docs/api/webhooks.md`.
