# TradePulse API Reference

Complete reference documentation for all TradePulse API endpoints.

## Table of Contents

- [Base Information](#base-information)
- [Health & Monitoring](#health--monitoring)
- [Features API](#features-api)
- [Predictions API](#predictions-api)
- [Admin API](#admin-api)
- [WebSocket API](#websocket-api)
- [GraphQL API](#graphql-api)
- [Common Types](#common-types)

## Base Information

### Base URLs

| Environment | URL |
|------------|-----|
| Production | `https://api.tradepulse.example.com` |
| Staging | `https://staging-api.tradepulse.example.com` |

### Versioning

The API supports multiple URL patterns:

```
/api/v1/{endpoint}     # Recommended
/v1/{endpoint}         # Legacy support
/{endpoint}            # Deprecated
```

### Authentication

All requests require an OAuth 2.0 Bearer token:

```http
Authorization: Bearer YOUR_ACCESS_TOKEN
```

### Content Type

All requests and responses use JSON:

```http
Content-Type: application/json
```

### Common Headers

#### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | Bearer token for authentication |
| `Content-Type` | Yes (POST/PUT) | Must be `application/json` |
| `Idempotency-Key` | Recommended | Unique key for idempotent requests |
| `X-Request-ID` | Optional | Request tracking identifier |

#### Response Headers

| Header | Description |
|--------|-------------|
| `ETag` | Entity tag for caching |
| `X-Cache-Status` | Cache hit/miss indicator |
| `X-RateLimit-Limit` | Rate limit threshold |
| `X-RateLimit-Remaining` | Remaining requests |
| `X-RateLimit-Reset` | Rate limit reset timestamp |
| `Idempotency-Key` | Echoed idempotency key |
| `X-Idempotent-Replay` | Present if replayed from cache |

---

## Health & Monitoring

### GET /health

Check API health and component status.

#### Request

```http
GET /health HTTP/1.1
Host: api.tradepulse.example.com
```

#### Response: 200 OK

```json
{
  "status": "ready" | "degraded" | "failed",
  "timestamp": "2025-01-01T00:00:00Z",
  "components": {
    "risk_manager": {
      "healthy": true,
      "status": "operational" | "degraded" | "failed",
      "detail": "string | null",
      "metrics": {
        "kill_switch_engaged": false
      }
    },
    "inference_cache": {
      "healthy": true,
      "status": "operational",
      "metrics": {
        "entries": 42,
        "max_entries": 512,
        "ttl_seconds": 30,
        "utilization": 0.082
      }
    },
    "client_rate_limiter": {
      "healthy": true,
      "status": "operational",
      "metrics": {
        "backend": "memory",
        "tracked_keys": 15,
        "max_utilization": 0.45,
        "saturated_keys": [],
        "default_policy": {
          "max_requests": 100,
          "window_seconds": 60
        }
      }
    },
    "idempotency_ledger": {
      "healthy": true,
      "status": "operational",
      "metrics": {
        "entries": 128,
        "ttl_seconds": 900
      }
    },
    "admin_rate_limiter": {
      "healthy": true,
      "status": "operational",
      "metrics": {
        "tracked_identifiers": 3,
        "max_attempts": 30,
        "interval_seconds": 60,
        "max_utilization": 0.2,
        "saturated_identifiers": []
      }
    }
  }
}
```

#### Response: 503 Service Unavailable

When the service is degraded or unavailable.

---

### GET /metrics

Export Prometheus-compatible metrics.

#### Request

```http
GET /metrics HTTP/1.1
Host: api.tradepulse.example.com
```

#### Response: 200 OK

```
# HELP api_requests_total Total API requests
# TYPE api_requests_total counter
api_requests_total{method="POST",endpoint="/api/v1/features",status="200"} 1234.0
api_requests_total{method="POST",endpoint="/api/v1/predictions",status="200"} 567.0

# HELP api_request_duration_seconds API request duration
# TYPE api_request_duration_seconds histogram
api_request_duration_seconds_bucket{endpoint="/api/v1/features",le="0.1"} 856.0
api_request_duration_seconds_bucket{endpoint="/api/v1/features",le="0.5"} 1200.0
api_request_duration_seconds_sum{endpoint="/api/v1/features"} 234.5
api_request_duration_seconds_count{endpoint="/api/v1/features"} 1234.0

# HELP cache_hits_total Total cache hits
# TYPE cache_hits_total counter
cache_hits_total 789.0
```

---

## Features API

### POST /api/v1/features

Compute engineered features from market data.

#### Request

```http
POST /api/v1/features HTTP/1.1
Host: api.tradepulse.example.com
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json
Idempotency-Key: unique-key-123

{
  "symbol": "BTC-USD",
  "bars": [
    {
      "timestamp": "2025-01-01T00:00:00Z",
      "open": 42000.1,
      "high": 42010.5,
      "low": 41980.0,
      "close": 42005.2,
      "volume": 18.2,
      "bidVolume": 9.1,
      "askVolume": 9.0,
      "signedVolume": 0.25
    }
  ]
}
```

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 1 | Number of snapshots (1-500) |
| `cursor` | string (ISO 8601) | No | null | Pagination cursor |
| `startAt` | string (ISO 8601) | No | null | Filter after timestamp |
| `endAt` | string (ISO 8601) | No | null | Filter before timestamp |
| `featurePrefix` | string | No | null | Filter by feature prefix |
| `feature` | array[string] | No | [] | Specific features to include |

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `symbol` | string | Yes | Instrument identifier (e.g., "BTC-USD") |
| `bars` | array[MarketBar] | Yes | Market bars to analyze (min 1) |

#### Response: 200 OK

```json
{
  "symbol": "BTC-USD",
  "generated_at": "2025-01-01T00:00:30Z",
  "features": {
    "macd": 0.42,
    "macd_signal": 0.37,
    "macd_histogram": 0.05,
    "rsi": 61.2,
    "return_1": 0.0012,
    "volatility_20": 0.025,
    "queue_imbalance": 0.011,
    "ema_12": 41995.3,
    "ema_26": 41985.7
  },
  "items": [
    {
      "timestamp": "2025-01-01T00:00:30Z",
      "features": {
        "macd": 0.42,
        "macd_signal": 0.37,
        "macd_histogram": 0.05,
        "rsi": 61.2
      }
    }
  ],
  "pagination": {
    "cursor": null,
    "next_cursor": "2025-01-01T00:00:00Z",
    "limit": 1,
    "returned": 1
  },
  "filters": {
    "start_at": null,
    "end_at": null,
    "feature_prefix": null,
    "feature_keys": []
  }
}
```

#### Response Headers

```http
ETag: "abc123def456..."
X-Cache-Status: miss
Cache-Control: private, max-age=30
Idempotency-Key: unique-key-123
```

#### Error Responses

| Status | Error Code | Description |
|--------|-----------|-------------|
| 400 | `FEATURES_EMPTY` | No features could be computed |
| 404 | `FEATURES_FILTER_MISMATCH` | No features matched filters |
| 409 | `IDEMPOTENCY_CONFLICT` | Key reused with different payload |
| 422 | `FEATURES_MISSING` | Required features unavailable |
| 422 | `FEATURES_INVALID` | Invalid feature values |
| 429 | `RATE_LIMIT_EXCEEDED` | Too many requests |

#### Example

```bash
curl -X POST https://api.tradepulse.example.com/api/v1/features \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC-USD",
    "bars": [{
      "timestamp": "2025-01-01T00:00:00Z",
      "high": 42100.0,
      "low": 41900.0,
      "close": 42050.0,
      "volume": 18.5
    }]
  }'
```

---

## Predictions API

### POST /api/v1/predictions

Generate trading signal predictions from market data.

#### Request

```http
POST /api/v1/predictions HTTP/1.1
Host: api.tradepulse.example.com
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json
Idempotency-Key: unique-key-456

{
  "symbol": "BTC-USD",
  "horizon_seconds": 900,
  "bars": [
    {
      "timestamp": "2025-01-01T00:00:00Z",
      "open": 42000.1,
      "high": 42010.5,
      "low": 41980.0,
      "close": 42005.2,
      "volume": 18.2,
      "bidVolume": 9.1,
      "askVolume": 9.0,
      "signedVolume": 0.25
    }
  ]
}
```

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 1 | Number of predictions (1-500) |
| `cursor` | string (ISO 8601) | No | null | Pagination cursor |
| `startAt` | string (ISO 8601) | No | null | Filter after timestamp |
| `endAt` | string (ISO 8601) | No | null | Filter before timestamp |
| `action` | array[string] | No | [] | Filter by action (buy/sell/hold) |
| `minConfidence` | number | No | null | Minimum confidence (0-1) |

#### Request Body

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `symbol` | string | Yes | - | Instrument identifier |
| `bars` | array[MarketBar] | Yes | - | Market bars (min 1) |
| `horizon_seconds` | integer | No | 900 | Prediction horizon (60-3600) |

#### Response: 200 OK

```json
{
  "symbol": "BTC-USD",
  "generated_at": "2025-01-01T00:00:30Z",
  "horizon_seconds": 900,
  "score": 0.42,
  "signal": {
    "action": "buy",
    "confidence": 0.78,
    "rationale": "Composite heuristic weighting MACD trend, crossover momentum, histogram strength, RSI, returns, and book imbalance",
    "metadata": {
      "score": 0.42,
      "horizon_seconds": 900,
      "component_contributions": {
        "macd_trend": 0.22,
        "macd_crossover": 0.18,
        "macd_histogram": 0.12,
        "macd_balance": 0.08,
        "rsi_bias": 0.027,
        "return_momentum": 0.014,
        "order_flow": 0.007,
        "volatility_risk": -0.001
      },
      "macd_component_explanations": {
        "macd_trend": "Measures overall EMA divergence; positive values indicate bullish acceleration.",
        "macd_crossover": "Rewards MACD leading the signal line; negative values highlight bearish crossovers.",
        "macd_histogram": "Scales the magnitude of MACD vs signal separation to favour decisive momentum.",
        "macd_balance": "Penalises divergence and convergence disagreement so MACD structure remains balanced."
      }
    }
  },
  "items": [
    {
      "timestamp": "2025-01-01T00:00:30Z",
      "score": 0.42,
      "signal": {
        "action": "buy",
        "confidence": 0.78,
        "rationale": "...",
        "metadata": {}
      }
    }
  ],
  "pagination": {
    "cursor": null,
    "next_cursor": "2025-01-01T00:00:00Z",
    "limit": 1,
    "returned": 1
  },
  "filters": {
    "start_at": null,
    "end_at": null,
    "actions": [],
    "min_confidence": null
  }
}
```

#### Error Responses

| Status | Error Code | Description |
|--------|-----------|-------------|
| 404 | `PREDICTIONS_FILTER_MISMATCH` | No predictions matched filters |
| 409 | `IDEMPOTENCY_CONFLICT` | Key reused with different payload |
| 422 | `FEATURES_MISSING` | Required features unavailable |
| 422 | `FEATURES_INVALID` | Invalid feature values |
| 429 | `RATE_LIMIT_EXCEEDED` | Too many requests |

#### Example

```bash
curl -X POST https://api.tradepulse.example.com/api/v1/predictions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "ETH-USD",
    "horizon_seconds": 900,
    "bars": [{
      "timestamp": "2025-01-01T00:00:00Z",
      "high": 3100.0,
      "low": 2950.0,
      "close": 3050.0,
      "volume": 125.0
    }]
  }'
```

---

## Admin API

### GET /admin/kill-switch

Get current kill-switch state.

#### Request

```http
GET /admin/kill-switch HTTP/1.1
Host: api.tradepulse.example.com
Authorization: Bearer ADMIN_TOKEN
X-TradePulse-2FA: 123456
```

#### Response: 200 OK

```json
{
  "status": "disengaged" | "engaged",
  "kill_switch_engaged": false,
  "reason": null,
  "already_engaged": false
}
```

---

### POST /admin/kill-switch

Engage the kill-switch to halt all trading.

#### Request

```http
POST /admin/kill-switch HTTP/1.1
Host: api.tradepulse.example.com
Authorization: Bearer ADMIN_TOKEN
X-TradePulse-2FA: 123456
Content-Type: application/json

{
  "reason": "Market anomaly detected - halting trading"
}
```

#### Request Body

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `reason` | string | Yes | 3-256 chars | Justification for engagement |

#### Response: 200 OK

```json
{
  "status": "engaged",
  "kill_switch_engaged": true,
  "reason": "Market anomaly detected - halting trading",
  "already_engaged": false
}
```

---

### DELETE /admin/kill-switch

Reset the kill-switch to resume trading.

#### Request

```http
DELETE /admin/kill-switch HTTP/1.1
Host: api.tradepulse.example.com
Authorization: Bearer ADMIN_TOKEN
X-TradePulse-2FA: 123456
```

#### Response: 200 OK

```json
{
  "status": "reset",
  "kill_switch_engaged": false,
  "reason": null,
  "already_engaged": false
}
```

#### Admin Error Responses

| Status | Description |
|--------|-------------|
| 401 | Missing or invalid authentication |
| 403 | Insufficient admin privileges |
| 403 | Invalid or missing 2FA code |
| 403 | Client certificate not valid (mTLS) |
| 429 | Admin rate limit exceeded |

---

## WebSocket API

### WS /ws/stream

Real-time streaming of analytics events.

#### Connection

```javascript
const ws = new WebSocket(
  'wss://api.tradepulse.example.com/ws/stream',
  {
    headers: {
      'Authorization': 'Bearer YOUR_TOKEN'
    }
  }
);
```

#### Initial Message

Upon connection, receive current analytics snapshot:

```json
{
  "total_feature_computations": 1234,
  "total_predictions": 567,
  "recent_symbols": ["BTC-USD", "ETH-USD", "SOL-USD"],
  "average_confidence": 0.72
}
```

#### Event Messages

Subsequent messages are real-time events:

```json
{
  "event_type": "feature_computed",
  "timestamp": "2025-01-01T00:00:30Z",
  "symbol": "BTC-USD",
  "data": {
    "features": {
      "macd": 0.42,
      "rsi": 61.2
    }
  }
}
```

```json
{
  "event_type": "prediction_generated",
  "timestamp": "2025-01-01T00:00:31Z",
  "symbol": "BTC-USD",
  "data": {
    "signal": {
      "action": "buy",
      "confidence": 0.78
    },
    "score": 0.42
  }
}
```

#### Error Handling

Connection closed with reason code:

- `1008` - Policy violation (authentication failed)
- `1011` - Internal error

---

## GraphQL API

### POST /graphql

Flexible query interface for analytics data.

#### Request

```http
POST /graphql HTTP/1.1
Host: api.tradepulse.example.com
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "query": "query { analyticsSnapshot { totalFeatureComputations totalPredictions } }"
}
```

#### Example Queries

**Get Analytics Snapshot**

```graphql
query AnalyticsSnapshot {
  analyticsSnapshot {
    totalFeatureComputations
    totalPredictions
    recentSymbols
    averageConfidence
  }
}
```

**Feature History**

```graphql
query FeatureHistory($symbol: String!, $limit: Int) {
  featureHistory(symbol: $symbol, limit: $limit) {
    timestamp
    features
  }
}
```

Variables:
```json
{
  "symbol": "BTC-USD",
  "limit": 10
}
```

---

## Common Types

### MarketBar

Market data for a single bar/candle.

```typescript
{
  timestamp: string;      // ISO 8601 format (required)
  open?: number;          // Opening price (optional)
  high: number;           // High price (required)
  low: number;            // Low price (required)
  close: number;          // Close price (required)
  volume?: number;        // Traded volume (optional)
  bidVolume?: number;     // Bid-side volume (optional)
  askVolume?: number;     // Ask-side volume (optional)
  signedVolume?: number;  // Signed volume (optional)
}
```

### Signal

Trading signal with action and confidence.

```typescript
{
  action: "buy" | "sell" | "hold";  // Trading action
  confidence: number;                // 0.0 to 1.0
  rationale: string;                 // Human-readable explanation
  metadata?: {                       // Additional context
    score: number;
    horizon_seconds: number;
    component_contributions: Record<string, number>;
  };
}
```

### PaginationMeta

Pagination information for collection responses.

```typescript
{
  cursor: string | null;       // Current pagination cursor
  next_cursor: string | null;  // Next page cursor (null if last page)
  limit: number;               // Requested page size
  returned: number;            // Actual items in response
}
```

### ErrorResponse

Standard error response format.

```typescript
{
  detail: {
    code: string;              // Machine-readable error code
    message: string;           // Human-readable message
    meta?: Record<string, any>;  // Additional context
  };
}
```

### ComponentHealth

Health status for a system component.

```typescript
{
  healthy: boolean;                         // Overall health status
  status: "operational" | "degraded" | "failed";  // Status level
  detail?: string;                          // Optional description
  metrics: Record<string, any>;             // Component-specific metrics
}
```

---

## Rate Limits

### Default Limits

| Endpoint Type | Rate Limit |
|--------------|-----------|
| Public Endpoints | 100 requests/minute |
| Admin Endpoints | 30 requests/minute |

### Headers

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1704067200
```

### 429 Response

```json
{
  "detail": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Please retry after the reset time.",
    "meta": {
      "retry_after": 60,
      "limit": 100,
      "window_seconds": 60
    }
  }
}
```

---

## Idempotency

### Requirements

- Max 128 characters
- Alphanumeric, hyphens, underscores, periods, colons only
- Valid for 15 minutes
- Returns 409 if reused with different payload

### Example

```http
POST /api/v1/predictions
Idempotency-Key: unique-key-12345-67890
```

Response includes:
```http
Idempotency-Key: unique-key-12345-67890
X-Idempotent-Replay: true  # If replayed
```

---

## Caching

### Cache Headers

```http
ETag: "abc123def456"  # Example ETag value
X-Cache-Status: hit | miss
Cache-Control: private, max-age=30
```

### Conditional Requests

```http
GET /api/v1/features
If-None-Match: "abc123def456"  # pragma: allowlist secret
```

Returns `304 Not Modified` if unchanged.

---

## Deprecation Policy

- Breaking changes require new major version
- 90-day overlap for deprecated versions
- Notification via:
  - Release notes
  - Status page
  - API response headers

---

**Last Updated**: 2025-01-10  
**API Version**: 0.2.0  
**OpenAPI Spec**: [tradepulse-online-inference-v1.json](../../schemas/openapi/tradepulse-online-inference-v1.json)
