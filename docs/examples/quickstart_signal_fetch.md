---
owner: dx@geosync
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# Quickstart: Market Signal Fetch

Fetch the latest trading signal using the public HTTP API (`GET /v1/signals/{symbol}`),
following the contract definitions in `docs/api/overview.md` and
`docs/api/contracts.md`.

## Prerequisites

- **API base URL**: `https://api.geosync.example` (or staging equivalent).
- **ed25519 signing key** configured for `X-GeoSync-Signature` as described in
  `docs/api/authentication.md`.
- **Symbol catalog knowledge** (e.g., `BTC-USD`).
- **Time sync** (NTP) to avoid signature drift.

## Request

```bash
curl -sS \
  -H "X-GeoSync-Signature: v1=<ed25519_signature>" \
  https://api.geosync.example/v1/signals/BTC-USD
```

## Expected Outputs

**200 OK** — `MarketSignalResponse`
```json
{
  "as_of": "2025-02-01T12:30:00Z",
  "confidence": 0.82,
  "horizon_minutes": 30,
  "metadata": {
    "market": "crypto",
    "venue": "BINANCE"
  },
  "signal": "BUY",
  "symbol": "BTC-USD",
  "ttl_seconds": 90
}
```

If authentication fails, the API returns a structured error as defined in
`docs/api/error_model.md`.

## Retry / Idempotency Scheme

- **Idempotency**: Optional for `GET`. If you supply `X-Idempotency-Key`, replays
  within the retention window return the same payload.
- **Retry policy**:
  - **Do not retry** `401/403` responses (fix credentials/signatures first).
  - **Retry** `429` or transient `5xx` with exponential backoff and jitter.
  - **Regenerate signatures** if request headers or payload change.

## Contract Alignment Notes

- Route, headers, and response schema match the `MarketSignalResponse` contract in
  `docs/api/contracts.md` and the governance table in `docs/api/overview.md`.
- Example payload matches `docs/api/examples/get-market-signal-200.json`.
