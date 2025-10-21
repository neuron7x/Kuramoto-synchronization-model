# Webhook Contracts

## signal.published
Emitted whenever a new trading signal is available.

- Method: `POST`
- Schema: `/workspace/TradePulse/schemas/events/json/1.0.0/signals.schema.json`
- Delivery: max attempts 5 with 30s backoff
- Signature: `X-TradePulse-Webhook` via `ed25519` (version v1)

## prediction.completed
Delivered when an asynchronous prediction finishes execution.

- Method: `POST`
- Schema: `/workspace/TradePulse/schemas/events/json/1.0.0/prediction_completed.schema.json`
- Delivery: max attempts 8 with 45s backoff
- Signature: `X-TradePulse-Webhook` via `ed25519` (version v1)
