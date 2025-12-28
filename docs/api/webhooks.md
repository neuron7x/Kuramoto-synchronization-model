# Webhook Contracts

## signal.published
Emitted whenever a new trading signal is available.

**owner:** Platform Engineering (platform@tradepulse.example)  
**last_reviewed:** 2025-12-28

**Inputs**
- Method: `POST`
- Schema: `/workspace/TradePulse/schemas/events/json/1.0.0/signals.schema.json`
- Signature: `X-TradePulse-Webhook` via `ed25519` (version v1)
- Delivery: max attempts 5 with 30s backoff

**Outputs**
- Consumers should respond with **2xx** and an empty body.

**Example**
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

## prediction.completed
Delivered when an asynchronous prediction finishes execution.

**owner:** Platform Engineering (platform@tradepulse.example)  
**last_reviewed:** 2025-12-28

**Inputs**
- Method: `POST`
- Schema: `/workspace/TradePulse/schemas/events/json/1.0.0/prediction_completed.schema.json`
- Signature: `X-TradePulse-Webhook` via `ed25519` (version v1)
- Delivery: max attempts 8 with 45s backoff

**Outputs**
- Consumers should respond with **2xx** and an empty body.

**Example**
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
