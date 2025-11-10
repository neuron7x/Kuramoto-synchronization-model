# TradePulse API Comprehensive Guide

## Overview

The TradePulse API provides production-ready endpoints for computing feature vectors and generating lightweight trading signals from streaming market data. The API is built with FastAPI and follows RESTful principles with support for versioning, rate limiting, caching, and idempotency.

## Table of Contents

1. [Base URL and Versioning](#base-url-and-versioning)
2. [Authentication](#authentication)
3. [Rate Limiting](#rate-limiting)
4. [Endpoints](#endpoints)
5. [Request/Response Formats](#requestresponse-formats)
6. [Error Handling](#error-handling)
7. [Caching and Performance](#caching-and-performance)
8. [Examples](#examples)

## Base URL and Versioning

### Production Environment
```
https://api.tradepulse.example.com
```

### Staging Environment
```
https://staging-api.tradepulse.example.com
```

### API Versioning

The API supports multiple version access patterns:

1. **Versioned Path** (Recommended): `/api/v1/features`
2. **Legacy Path**: `/v1/features`
3. **Unversioned Path** (Deprecated): `/features`

**Example:**
```bash
# Recommended
curl https://api.tradepulse.example.com/api/v1/features

# Also supported
curl https://api.tradepulse.example.com/v1/features
```

## Authentication

The TradePulse API uses OAuth 2.0 Bearer tokens for authentication.

### Obtaining a Token

Contact your administrator to obtain OAuth 2.0 credentials. The token must include:
- **Issuer**: Your configured OAuth2 provider
- **Audience**: `tradepulse-api`
- **Required Scopes**: `api:read`, `api:write`

### Using Authentication

Include the Bearer token in the `Authorization` header:

```http
Authorization: Bearer YOUR_ACCESS_TOKEN
```

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  https://api.tradepulse.example.com/api/v1/features
```

### Admin Endpoints

Administrative endpoints (e.g., `/admin/kill-switch`) require:
1. **OAuth 2.0 Bearer token** with admin privileges
2. **Mutual TLS (mTLS)** - Client certificate verification
3. **Two-Factor Authentication** - TOTP code via `X-TradePulse-2FA` header

## Rate Limiting

The API implements sliding window rate limiting to ensure fair usage.

### Default Limits

| Endpoint Type | Rate Limit |
|--------------|-----------|
| Public Endpoints | 100 requests/minute per user |
| Admin Endpoints | 30 requests/minute per admin |

### Rate Limit Headers

Every response includes rate limit information:

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1704067200
```

### Handling Rate Limits

When rate limited, you'll receive a `429 Too Many Requests` response:

```json
{
  "detail": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Please retry after the reset time.",
    "meta": {
      "retry_after": 60
    }
  }
}
```

**Best Practices:**
- Implement exponential backoff
- Cache responses when possible
- Batch requests where applicable

## Endpoints

### Health Check

Check API health and component status.

#### Request
```http
GET /health
```

#### Response
```json
{
  "status": "ready",
  "timestamp": "2025-01-01T00:00:00Z",
  "components": {
    "risk_manager": {
      "healthy": true,
      "status": "operational",
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
        "utilization": 0.082
      }
    }
  }
}
```

### Prometheus Metrics

Export Prometheus-compatible metrics.

#### Request
```http
GET /metrics
```

#### Response
```
# TYPE api_requests_total counter
api_requests_total{method="POST",endpoint="/api/v1/features",status="200"} 1234
# TYPE api_request_duration_seconds histogram
api_request_duration_seconds_bucket{le="0.1"} 856
```

### Features API

Compute engineered features from market data.

#### Request
```http
POST /api/v1/features
Content-Type: application/json
Authorization: Bearer YOUR_TOKEN
```

**Request Body:**
```json
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

**Query Parameters:**
- `limit` (int, 1-500): Number of feature snapshots to return (default: 1)
- `cursor` (ISO 8601 timestamp): Pagination cursor
- `startAt` (ISO 8601 timestamp): Filter snapshots after this time
- `endAt` (ISO 8601 timestamp): Filter snapshots before this time
- `featurePrefix` (string): Return only features with this prefix
- `feature` (array[string]): Specific feature keys to include

#### Response
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
    "queue_imbalance": 0.011
  },
  "items": [
    {
      "timestamp": "2025-01-01T00:00:30Z",
      "features": {
        "macd": 0.42,
        "macd_signal": 0.37,
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

**Response Headers:**
```http
ETag: "sha256-hash-of-response"
X-Cache-Status: hit | miss
Cache-Control: private, max-age=30
```

### Predictions API

Generate trading signals from market data.

#### Request
```http
POST /api/v1/predictions
Content-Type: application/json
Authorization: Bearer YOUR_TOKEN
```

**Request Body:**
```json
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

**Query Parameters:**
- `limit` (int, 1-500): Number of predictions to return (default: 1)
- `cursor` (ISO 8601 timestamp): Pagination cursor
- `startAt` (ISO 8601 timestamp): Filter predictions after this time
- `endAt` (ISO 8601 timestamp): Filter predictions before this time
- `action` (array[string]): Filter by signal action (`buy`, `sell`, `hold`)
- `minConfidence` (float, 0-1): Minimum confidence threshold

#### Response
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
      }
    }
  },
  "items": [
    {
      "timestamp": "2025-01-01T00:00:30Z",
      "score": 0.42,
      "signal": {
        "action": "buy",
        "confidence": 0.78
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

### Admin Kill-Switch API

Administrative endpoints for managing the risk kill-switch.

#### Get Kill-Switch State

```http
GET /admin/kill-switch
Authorization: Bearer ADMIN_TOKEN
X-TradePulse-2FA: 123456
```

**Response:**
```json
{
  "status": "disengaged",
  "kill_switch_engaged": false,
  "reason": null,
  "already_engaged": false
}
```

#### Engage Kill-Switch

```http
POST /admin/kill-switch
Authorization: Bearer ADMIN_TOKEN
X-TradePulse-2FA: 123456
Content-Type: application/json

{
  "reason": "Market anomaly detected - halting trading"
}
```

**Response:**
```json
{
  "status": "engaged",
  "kill_switch_engaged": true,
  "reason": "Market anomaly detected - halting trading",
  "already_engaged": false
}
```

#### Reset Kill-Switch

```http
DELETE /admin/kill-switch
Authorization: Bearer ADMIN_TOKEN
X-TradePulse-2FA: 123456
```

**Response:**
```json
{
  "status": "reset",
  "kill_switch_engaged": false,
  "reason": null,
  "already_engaged": false
}
```

## Request/Response Formats

### Data Types

#### MarketBar

Represents a single OHLCV bar:

```typescript
{
  timestamp: string;      // ISO 8601 format
  open?: number;          // Opening price (optional)
  high: number;           // High price
  low: number;            // Low price
  close: number;          // Close price
  volume?: number;        // Traded volume (optional)
  bidVolume?: number;     // Bid-side volume (optional)
  askVolume?: number;     // Ask-side volume (optional)
  signedVolume?: number;  // Signed volume (optional)
}
```

#### Signal

Trading signal with action and confidence:

```typescript
{
  action: "buy" | "sell" | "hold";
  confidence: number;     // 0.0 to 1.0
  rationale: string;
  metadata?: object;      // Additional context
}
```

#### PaginationMeta

Pagination information:

```typescript
{
  cursor: string | null;      // Current cursor
  next_cursor: string | null; // Next page cursor
  limit: number;              // Requested limit
  returned: number;           // Actual items returned
}
```

## Error Handling

### Error Response Format

All errors follow a consistent structure:

```json
{
  "detail": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "meta": {
      "additional": "context"
    }
  }
}
```

### Common Error Codes

| HTTP Status | Error Code | Description |
|------------|-----------|-------------|
| 400 | `INVALID_REQUEST` | Malformed request body or parameters |
| 400 | `FEATURES_EMPTY` | No features could be computed |
| 400 | `IDEMPOTENCY_INVALID` | Invalid idempotency key format |
| 401 | `UNAUTHORIZED` | Missing or invalid authentication |
| 403 | `FORBIDDEN` | Insufficient permissions |
| 404 | `NOT_FOUND` | Resource not found |
| 404 | `FEATURES_FILTER_MISMATCH` | No features matched filters |
| 404 | `PREDICTIONS_FILTER_MISMATCH` | No predictions matched filters |
| 409 | `IDEMPOTENCY_CONFLICT` | Idempotency key reused with different payload |
| 413 | `PAYLOAD_TOO_LARGE` | Request body exceeds limit |
| 422 | `UNPROCESSABLE` | Validation error |
| 422 | `FEATURES_MISSING` | Required features not available |
| 422 | `FEATURES_INVALID` | Feature values are invalid |
| 429 | `RATE_LIMIT_EXCEEDED` | Too many requests |
| 500 | `INTERNAL_ERROR` | Server error |
| 503 | `SERVICE_UNAVAILABLE` | Service temporarily unavailable |

### Error Handling Best Practices

1. **Always check HTTP status code first**
2. **Parse the error code for programmatic handling**
3. **Log the complete error response for debugging**
4. **Implement retry logic with exponential backoff for 5xx errors**
5. **Display the error message to users for 4xx errors**

**Example Error Handling (Python):**
```python
import requests
import time

def call_api_with_retry(url, payload, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                # Rate limited - wait and retry
                retry_after = int(response.headers.get('Retry-After', 60))
                time.sleep(retry_after)
                continue
            elif 500 <= response.status_code < 600:
                # Server error - exponential backoff
                time.sleep(2 ** attempt)
                continue
            else:
                # Client error - don't retry
                error = response.json()
                raise ValueError(f"API Error: {error['detail']['message']}")
                
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
    
    raise Exception("Max retries exceeded")
```

## Caching and Performance

### Response Caching

The API implements aggressive caching for feature and prediction responses:

- **TTL**: 30 seconds
- **Cache Key**: SHA-256 hash of request payload + query parameters
- **Cache Status**: Check `X-Cache-Status` header (`hit` or `miss`)
- **ETag**: Use for conditional requests

**Example with ETag:**
```bash
# First request
curl -H "Authorization: Bearer TOKEN" \
  https://api.tradepulse.example.com/api/v1/features \
  -d '{"symbol": "BTC-USD", "bars": [...]}' \
  -i

# Response includes: ETag: "abc123..."

# Conditional request
curl -H "Authorization: Bearer TOKEN" \
  -H "If-None-Match: abc123..." \
  https://api.tradepulse.example.com/api/v1/features \
  -d '{"symbol": "BTC-USD", "bars": [...]}'

# Returns 304 Not Modified if unchanged
```

### Idempotency

Protect against duplicate requests using idempotency keys:

**Request:**
```http
POST /api/v1/predictions
Authorization: Bearer TOKEN
Idempotency-Key: unique-key-12345
Content-Type: application/json

{"symbol": "BTC-USD", ...}
```

**Response (First Request):**
```http
HTTP/1.1 200 OK
Idempotency-Key: unique-key-12345
X-Cache-Status: miss
```

**Response (Duplicate Request):**
```http
HTTP/1.1 200 OK
Idempotency-Key: unique-key-12345
X-Idempotent-Replay: true
X-Cache-Status: hit
```

**Idempotency Key Requirements:**
- Maximum 128 characters
- Alphanumeric, hyphens, underscores, periods, and colons only
- Valid for 15 minutes
- Conflict (409) if reused with different payload

### Performance Tips

1. **Batch Similar Requests**: Group requests when possible
2. **Use Pagination**: Don't request more data than needed
3. **Leverage Caching**: Reuse cached responses within TTL
4. **Filter Results**: Use query parameters to reduce payload size
5. **Connection Pooling**: Reuse HTTP connections
6. **Compress Requests**: Use `Content-Encoding: gzip`

## Examples

### Python Example

```python
import requests
import hashlib
import json
from datetime import datetime, timezone

class TradePulseClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
    
    def compute_features(self, symbol: str, bars: list) -> dict:
        """Compute features for the given market bars."""
        payload = {
            'symbol': symbol,
            'bars': bars
        }
        
        # Generate idempotency key
        idempotency_key = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()[:32]
        
        response = self.session.post(
            f'{self.base_url}/api/v1/features',
            json=payload,
            headers={'Idempotency-Key': idempotency_key}
        )
        response.raise_for_status()
        return response.json()
    
    def generate_prediction(self, symbol: str, bars: list, 
                          horizon_seconds: int = 900) -> dict:
        """Generate a trading signal prediction."""
        payload = {
            'symbol': symbol,
            'horizon_seconds': horizon_seconds,
            'bars': bars
        }
        
        response = self.session.post(
            f'{self.base_url}/api/v1/predictions',
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    def health_check(self) -> dict:
        """Check API health status."""
        response = self.session.get(f'{self.base_url}/health')
        response.raise_for_status()
        return response.json()

# Usage
client = TradePulseClient(
    base_url='https://api.tradepulse.example.com',
    token='your-token-here'
)

# Check health
health = client.health_check()
print(f"API Status: {health['status']}")

# Prepare market data
bars = [{
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'open': 42000.0,
    'high': 42100.0,
    'low': 41900.0,
    'close': 42050.0,
    'volume': 18.5
}]

# Compute features
features = client.compute_features('BTC-USD', bars)
print(f"Features: {features['features']}")

# Generate prediction
prediction = client.generate_prediction('BTC-USD', bars)
print(f"Signal: {prediction['signal']['action']}")
print(f"Confidence: {prediction['signal']['confidence']}")
```

### JavaScript/TypeScript Example

```typescript
interface MarketBar {
  timestamp: string;
  open?: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

interface Signal {
  action: 'buy' | 'sell' | 'hold';
  confidence: number;
  rationale: string;
  metadata?: any;
}

class TradePulseClient {
  private baseUrl: string;
  private token: string;

  constructor(baseUrl: string, token: string) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.token = token;
  }

  private async request(
    path: string,
    options: RequestInit = {}
  ): Promise<any> {
    const url = `${this.baseUrl}${path}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(
        `API Error: ${error.detail?.message || response.statusText}`
      );
    }

    return response.json();
  }

  async computeFeatures(
    symbol: string,
    bars: MarketBar[]
  ): Promise<any> {
    return this.request('/api/v1/features', {
      method: 'POST',
      body: JSON.stringify({ symbol, bars }),
    });
  }

  async generatePrediction(
    symbol: string,
    bars: MarketBar[],
    horizonSeconds: number = 900
  ): Promise<{ signal: Signal; score: number }> {
    return this.request('/api/v1/predictions', {
      method: 'POST',
      body: JSON.stringify({
        symbol,
        bars,
        horizon_seconds: horizonSeconds,
      }),
    });
  }

  async healthCheck(): Promise<any> {
    return this.request('/health');
  }
}

// Usage
const client = new TradePulseClient(
  'https://api.tradepulse.example.com',
  'your-token-here'
);

const bars: MarketBar[] = [{
  timestamp: new Date().toISOString(),
  open: 42000,
  high: 42100,
  low: 41900,
  close: 42050,
  volume: 18.5,
}];

// Generate prediction
const result = await client.generatePrediction('BTC-USD', bars);
console.log(`Action: ${result.signal.action}`);
console.log(`Confidence: ${result.signal.confidence}`);
```

### cURL Examples

#### Compute Features
```bash
curl -X POST https://api.tradepulse.example.com/api/v1/features \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "symbol": "BTC-USD",
    "bars": [{
      "timestamp": "2025-01-01T00:00:00Z",
      "high": 42100,
      "low": 41900,
      "close": 42050,
      "volume": 18.5
    }]
  }'
```

#### Generate Prediction
```bash
curl -X POST https://api.tradepulse.example.com/api/v1/predictions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "ETH-USD",
    "horizon_seconds": 900,
    "bars": [{
      "timestamp": "2025-01-01T00:00:00Z",
      "high": 3100,
      "low": 2950,
      "close": 3050,
      "volume": 125.0
    }]
  }'
```

#### Paginated Features
```bash
curl -X POST "https://api.tradepulse.example.com/api/v1/features?limit=10&featurePrefix=macd" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{...}'
```

## WebSocket Streaming

The API supports real-time streaming of analytics events via WebSocket.

### Connect to Stream

```javascript
const ws = new WebSocket(
  'wss://api.tradepulse.example.com/ws/stream',
  {
    headers: {
      'Authorization': 'Bearer YOUR_TOKEN'
    }
  }
);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Analytics update:', data);
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('WebSocket connection closed');
};
```

### Stream Events

The WebSocket sends real-time updates for:
- Feature computations
- Prediction generation
- System metrics

**Event Format:**
```json
{
  "event_type": "feature_computed",
  "timestamp": "2025-01-01T00:00:30Z",
  "symbol": "BTC-USD",
  "data": {
    "features": {...}
  }
}
```

## GraphQL API

The API also exposes a GraphQL endpoint for flexible queries.

### Endpoint
```
POST /graphql
```

### Example Query

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

### Example with Variables

```graphql
query FeatureHistory($symbol: String!, $limit: Int) {
  featureHistory(symbol: $symbol, limit: $limit) {
    timestamp
    features
  }
}
```

**Variables:**
```json
{
  "symbol": "BTC-USD",
  "limit": 10
}
```

## Best Practices

### 1. Authentication
- Store tokens securely (never in source code)
- Rotate tokens regularly
- Use environment variables for credentials

### 2. Rate Limiting
- Implement client-side rate limiting
- Cache responses appropriately
- Use exponential backoff for retries

### 3. Error Handling
- Always check response status codes
- Log errors with context
- Implement graceful degradation

### 4. Performance
- Use connection pooling
- Batch requests when possible
- Leverage idempotency for retries
- Monitor cache hit rates

### 5. Security
- Always use HTTPS
- Validate TLS certificates
- Never log sensitive data
- Implement request timeouts

## Troubleshooting

### Common Issues

#### 401 Unauthorized
- Verify token is valid and not expired
- Check token includes required scopes
- Ensure `Authorization` header is properly formatted

#### 429 Rate Limited
- Implement exponential backoff
- Check `X-RateLimit-*` headers
- Consider caching responses

#### 422 Unprocessable Entity
- Validate request payload against schema
- Check all required fields are present
- Verify data types match specification

#### Connection Timeouts
- Increase client timeout settings
- Check network connectivity
- Verify API endpoint is accessible

### Debug Mode

For debugging, check the `/health` endpoint:

```bash
curl https://api.tradepulse.example.com/health | jq
```

This returns detailed component status information.

## Support

For API support and questions:
- **Documentation**: https://docs.tradepulse.example/api
- **GitHub Issues**: https://github.com/neuron7x/TradePulse/issues
- **Email**: platform@tradepulse.example
- **Discord**: https://discord.gg/tradepulse

## Changelog

### Version 0.2.0
- Added idempotency support
- Enhanced caching with ETag
- GraphQL API endpoint
- WebSocket streaming
- Improved error responses

### Version 0.1.0
- Initial API release
- Feature computation endpoint
- Prediction generation endpoint
- Basic authentication and rate limiting

## License

The TradePulse API is available under the TradePulse Proprietary License Agreement (TPLA).

---

**Last Updated**: 2025-01-10
**API Version**: 0.2.0
