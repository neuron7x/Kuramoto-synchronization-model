---
owner: platform@geosync.example
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# GeoSync API & Contract Catalog

This catalog cross-checks the API docs in `docs/api/` against interface modules in
`interfaces/` and schema definitions in `schemas/`. It also expands each contract
with inputs/outputs, DTOs, and concrete examples.

## Coverage snapshot

| Contract | Primary docs | Interfaces | Schemas | Notes |
| --- | --- | --- | --- | --- |
| Public HTTP API (signals & predictions) | `docs/api/overview.md`, `docs/api/routes.json`, `docs/api/examples/` | — | `schemas/http/json/1.0.0/*` | `routes.json` documents `GET /v1/signals/{symbol}` + async `POST /v1/predictions`. OpenAPI currently omits `/v1/signals`. |
| Feature extraction API | `schemas/openapi/geosync-online-inference-v1.json` | — | `schemas/http/json/1.0.0/feature_request.schema.json`, `feature_response.schema.json` | Present in OpenAPI (`/v1/features`) but missing from `docs/api/routes.json`. |
| Prediction query API | `schemas/openapi/geosync-online-inference-v1.json` | — | `schemas/http/json/1.0.0/prediction_response.schema.json` | OpenAPI exposes a synchronous `POST /v1/predictions` returning `PredictionResponse`. `routes.json` instead describes async submission (`PredictionCreateResponse`). |
| Admin remote control API | `docs/api/admin_remote_control_openapi.yaml` | — | Inline OpenAPI schemas | Matches OpenAPI in `schemas/openapi/geosync-online-inference-v1.json` under `/admin/kill-switch`. |
| Webhooks | `docs/api/webhooks.md` | — | `schemas/events/json/1.0.0/*` | Covers `signal.published` + `prediction.completed`. |
| CLI contract | `interfaces/README.md` | `interfaces/cli.py` | — | Structured JSON output for analyze/backtest/live commands. |
| Python interface contracts | — | `interfaces/ingestion.py`, `interfaces/backtest.py`, `interfaces/execution/base.py` | `core.data.models` | Not previously documented in `docs/api/`. |

---

## Public HTTP API

### Market signal (GET `/v1/signals/{symbol}`)

**owner:** Platform Engineering (platform@geosync.example)  
**last_reviewed:** 2025-12-28

**Inputs**
- Path parameters: `symbol` (string, canonical symbol like `BTC-USD`).
- Headers: `X-GeoSync-Signature` (ed25519, required), `X-Idempotency-Key` (optional).

**Output**
- **200** `MarketSignalResponse`

**DTO / data types** (`schemas/http/json/1.0.0/market_signal_response.schema.json`)
- `symbol` (string)
- `as_of` (RFC 3339 timestamp)
- `signal` (enum: `BUY`, `SELL`, `HOLD`)
- `confidence` (float 0..1)
- `horizon_minutes` (int 1..1440)
- `ttl_seconds` (int | null)
- `metadata` (object, free-form)

**Example**

_Request_
```bash
curl -H "X-GeoSync-Signature: <sig>" \
  https://api.geosync.example/v1/signals/BTC-USD
```

_Response_
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

---

### Prediction submission (async) (POST `/v1/predictions`)

**owner:** Platform Engineering (platform@geosync.example)  
**last_reviewed:** 2025-12-28

**Inputs**
- Body: `PredictionCreateRequest` JSON.
- Headers: `X-GeoSync-Signature` (required), `X-Idempotency-Key` (required).

**Output**
- **202** `PredictionCreateResponse` (acknowledges async processing).

**DTO / data types** (`schemas/http/json/1.0.0/prediction_create_request.schema.json`)
- `symbol` (string)
- `horizon_minutes` (int 1..1440)
- `features` (object<string, number>)
- `correlation_id` (string, optional)
- `delivery.webhook` (URI, optional)
- `delivery.idempotency_key` (string, optional)

**DTO / data types** (`schemas/http/json/1.0.0/prediction_create_response.schema.json`)
- `request_id` (string)
- `status` (enum: `accepted`, `queued`, `rejected`)
- `submitted_at` (RFC 3339 timestamp)
- `estimated_completion_at` (RFC 3339 timestamp | null)
- `links.status` / `links.webhook` (URI)
- `warnings` (array<string>, optional)

**Example**

_Request_
```json
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
```

_Response_
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

---

### Feature extraction (POST `/v1/features`)

**owner:** Platform Engineering (platform@geosync.example)  
**last_reviewed:** 2025-12-28

**Inputs**
- Body: `FeatureRequest` JSON.
- Query parameters (from OpenAPI): `limit`, `cursor`, `startAt`, `endAt`, `featurePrefix`, `feature`.

**Output**
- **200** `FeatureResponse`

**DTO / data types** (`schemas/http/json/1.0.0/feature_request.schema.json`)
- `symbol` (string)
- `bars` (array of `MarketBar`)
  - `timestamp` (RFC 3339)
  - `open` (number | null)
  - `high` (number)
  - `low` (number)
  - `close` (number)
  - `volume` / `bidVolume` / `askVolume` / `signedVolume` (number | null)

**DTO / data types** (`schemas/http/json/1.0.0/feature_response.schema.json`)
- `symbol` (string)
- `generated_at` (RFC 3339)
- `features` (object<string, number>)
- `items` (array of `FeatureSnapshot`)
- `filters`, `pagination` (objects)

**Example**

_Request_
```json
{
  "symbol": "BTC-USD",
  "bars": [
    {
      "timestamp": "2025-02-01T12:00:00Z",
      "open": 43120.5,
      "high": 43190.2,
      "low": 43080.1,
      "close": 43110.8,
      "volume": 124.3
    }
  ]
}
```

_Response_
```json
{
  "symbol": "BTC-USD",
  "generated_at": "2025-02-01T12:00:01Z",
  "features": {
    "entropy": 3.2,
    "hurst": 0.62,
    "ricci": 0.34
  },
  "items": [
    {
      "timestamp": "2025-02-01T12:00:00Z",
      "features": {
        "entropy": 3.2,
        "hurst": 0.62,
        "ricci": 0.34
      }
    }
  ],
  "filters": {
    "feature_prefix": null,
    "feature_keys": null,
    "start_at": null,
    "end_at": null
  },
  "pagination": {
    "cursor": null,
    "limit": 1,
    "next_cursor": null,
    "returned": 1
  }
}
```

---

### Prediction query (sync) (POST `/v1/predictions`)

**owner:** Platform Engineering (platform@geosync.example)  
**last_reviewed:** 2025-12-28

**Inputs**
- Body: `PredictionRequest` JSON (bars + horizon seconds).
- Query parameters (from OpenAPI): `limit`, `cursor`, `startAt`, `endAt`, `action`, `minConfidence`.

**Output**
- **200** `PredictionResponse` (synchronous payload with snapshots).

**DTO / data types** (`schemas/http/json/1.0.0/prediction_request.schema.json`)
- `symbol` (string)
- `horizon_seconds` (int 60..3600)
- `bars` (array of `MarketBar` as in `FeatureRequest`)

**DTO / data types** (`schemas/http/json/1.0.0/prediction_response.schema.json`)
- `symbol` (string)
- `generated_at` (RFC 3339)
- `horizon_seconds` (int)
- `score` (number | null)
- `signal` (object | null)
- `items` (array of `PredictionSnapshot`)
- `filters`, `pagination` (objects)

**Example**

_Request_
```json
{
  "symbol": "BTC-USD",
  "horizon_seconds": 1800,
  "bars": [
    {
      "timestamp": "2025-02-01T12:30:00Z",
      "open": 43100.1,
      "high": 43190.2,
      "low": 43080.1,
      "close": 43110.8,
      "volume": 124.3
    }
  ]
}
```

_Response_
```json
{
  "symbol": "BTC-USD",
  "generated_at": "2025-02-01T12:31:05Z",
  "horizon_seconds": 1800,
  "score": 0.42,
  "signal": {
    "action": "buy",
    "confidence": 0.82
  },
  "items": [
    {
      "timestamp": "2025-02-01T12:31:05Z",
      "score": 0.42,
      "signal": {
        "action": "buy",
        "confidence": 0.82
      }
    }
  ],
  "filters": {
    "actions": null,
    "min_confidence": null,
    "start_at": null,
    "end_at": null
  },
  "pagination": {
    "cursor": null,
    "limit": 1,
    "next_cursor": null,
    "returned": 1
  }
}
```

---

## Webhook contracts

### signal.published

**owner:** Platform Engineering (platform@geosync.example)  
**last_reviewed:** 2025-12-28

**Inputs**
- HTTP `POST` payload matching `SignalEvent`.

**Output**
- Receiver should acknowledge with **2xx** and no body.

**DTO / data types** (`schemas/events/json/1.0.0/signals.schema.json`)
- `event_id` (string)
- `schema_version` (string)
- `symbol` (string)
- `timestamp` (unix-time integer)
- `signal_type` (string)
- `strength` (number -1..1)
- `direction` (enum defined in schema)
- `ttl_seconds` (int | null)
- `metadata` (object<string, string>)

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

---

### prediction.completed

**owner:** Platform Engineering (platform@geosync.example)  
**last_reviewed:** 2025-12-28

**Inputs**
- HTTP `POST` payload matching `PredictionCompletedEvent`.

**Output**
- Receiver should acknowledge with **2xx** and no body.

**DTO / data types** (`schemas/events/json/1.0.0/prediction_completed.schema.json`)
- `event_id` (string)
- `schema_version` (string, semver)
- `request_id` (string)
- `symbol` (string)
- `completed_at` (RFC 3339 timestamp)
- `prediction.horizon_minutes` (int)
- `prediction.value` (number)
- `prediction.confidence` (number 0..1)
- `prediction.distribution.p05/p50/p95` (number, optional)
- `metadata` (object<string, string | number | boolean | null>)

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

---

## Admin remote control API

### Kill-switch management (GET/POST/DELETE `/admin/kill-switch`)

**owner:** Platform Engineering (platform@geosync.example)  
**last_reviewed:** 2025-12-28

**Inputs**
- Auth: OAuth2 bearer token with admin scope.
- POST body: `KillSwitchRequest`.

**Output**
- **200** `KillSwitchResponse` for all operations.

**DTO / data types** (`docs/api/admin_remote_control_openapi.yaml`)
- `KillSwitchRequest.reason` (string, 3..256 chars)
- `KillSwitchResponse.status` (string)
- `KillSwitchResponse.kill_switch_engaged` (boolean)
- `KillSwitchResponse.reason` (string)
- `KillSwitchResponse.already_engaged` (boolean)

**Example**

_Request_
```json
{
  "reason": "Latency anomaly detected in venue connectors."
}
```

_Response_
```json
{
  "status": "engaged",
  "kill_switch_engaged": true,
  "reason": "Latency anomaly detected in venue connectors.",
  "already_engaged": false
}
```

---

## Interface layer contracts (Python)

### CLI entry points (`interfaces/cli.py`)

**owner:** Developer Experience (devex@geosync.example)  
**last_reviewed:** 2025-12-28

**Inputs**
- Command-line flags for `geosync analyze`, `geosync backtest`, `geosync live`.

**Output**
- JSON payloads on stdout, structured errors on stderr.

**DTO / data types**
- `analyze` output: numeric indicators (`R`, `H`, `delta_H`, `kappa_mean`, `Hurst`, `phase`, `metadata`).
- `backtest` output: analytics summary (`pnl`, `max_dd`, `trades`, `sharpe_ratio`, `metadata`).
- `live` output: exit code + logs (no structured JSON on success).

**Example**
```bash
geosync analyze --csv prices.csv --window 100
```

```json
{
  "R": 0.85,
  "H": 3.2,
  "delta_H": -0.05,
  "kappa_mean": 0.34,
  "Hurst": 0.62,
  "phase": "trending",
  "metadata": {
    "window_size": 200,
    "data_points": 1000,
    "bins": 30,
    "delta": 0.005
  }
}
```

---

### Data ingestion contracts (`interfaces/ingestion.py`)

**owner:** Developer Experience (devex@geosync.example)  
**last_reviewed:** 2025-12-28

**Inputs**
- `DataIngestionService.historical_csv(path, on_tick, required_fields, timestamp_field, price_field, volume_field, symbol, venue, instrument_type, market)`
- `DataIngestionService.binance_ws(symbol, on_tick, interval)`
- `AsyncDataIngestionService.read_csv(path, symbol, venue, instrument_type, market, chunk_size, delay_ms, required_fields, timestamp_field, price_field, volume_field)`
- `AsyncDataIngestionService.stream_ticks(source, symbol, instrument_type, interval_ms, max_ticks)`
- `AsyncDataIngestionService.batch_process(ticks, callback, batch_size)`

**Output**
- Sync methods return `None` (emit `core.data.models.PriceTick` via callbacks).
- Async methods yield `AsyncIterator[PriceTick]` or return processed count (int).

**Example**
```python
from interfaces.ingestion import DataIngestionService

class CsvIngestor(DataIngestionService):
    def historical_csv(self, path, on_tick, **kwargs):
        ...

    def binance_ws(self, symbol, on_tick, interval="1m"):
        ...
```

---

### Backtest engine contract (`interfaces/backtest.py`)

**owner:** Developer Experience (devex@geosync.example)  
**last_reviewed:** 2025-12-28

**Inputs**
- `BacktestEngine.run(prices, signal_fn, fee, initial_capital, strategy_name, **kwargs)`

**Output**
- Returns `ResultT` (engine-defined report object).

**Example**
```python
from interfaces.backtest import BacktestEngine

class SimpleEngine(BacktestEngine[dict]):
    def run(self, prices, signal_fn, **kwargs):
        return {"pnl": 0.0}
```

---

### Execution & risk contracts (`interfaces/execution/base.py`)

**owner:** Developer Experience (devex@geosync.example)  
**last_reviewed:** 2025-12-28

**Inputs**
- `PositionSizer.size(balance, risk, price, max_leverage)` → float size.
- `RiskController.validate_order(symbol, side, qty, price)` → raises on violation.
- `RiskController.register_fill(symbol, side, qty, price)` → update exposures.
- `RiskController.current_position(symbol)` / `current_notional(symbol)` → floats.
- `PortfolioRiskAnalyzer.heat(positions)` → float risk metric.

**Output**
- Scalar sizes / risk metrics or exceptions for invalid orders.

**Example**
```python
from interfaces.execution.base import PositionSizer

class FixedSizer(PositionSizer):
    def size(self, balance, risk, price, max_leverage=5.0):
        return balance * risk / price
```
