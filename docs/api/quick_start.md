# TradePulse API Quick Start Guide

Get started with the TradePulse API in 5 minutes.

## Prerequisites

- OAuth 2.0 Bearer token (contact your administrator)
- Basic knowledge of REST APIs
- HTTP client (curl, Python requests, or similar)

## Step 1: Verify Access

Test your token with a health check:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://api.tradepulse.example.com/health
```

Expected response:
```json
{
  "status": "ready",
  "timestamp": "2025-01-01T00:00:00Z",
  "components": {...}
}
```

## Step 2: Compute Features

Send market data to compute technical features:

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

Response includes computed features:
```json
{
  "symbol": "BTC-USD",
  "features": {
    "macd": 0.42,
    "macd_signal": 0.37,
    "rsi": 61.2,
    "volatility_20": 0.025
  }
}
```

## Step 3: Generate Trading Signals

Get AI-powered trading signals:

```bash
curl -X POST https://api.tradepulse.example.com/api/v1/predictions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC-USD",
    "horizon_seconds": 900,
    "bars": [{
      "timestamp": "2025-01-01T00:00:00Z",
      "high": 42100.0,
      "low": 41900.0,
      "close": 42050.0,
      "volume": 18.5
    }]
  }'
```

Response includes trading signal:
```json
{
  "symbol": "BTC-USD",
  "signal": {
    "action": "buy",
    "confidence": 0.78,
    "rationale": "Composite heuristic weighting MACD trend..."
  },
  "score": 0.42
}
```

## Step 4: Integrate into Your Application

### Python Example

```python
import requests

class TradePulseClient:
    def __init__(self, token):
        self.base_url = 'https://api.tradepulse.example.com'
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    
    def get_signal(self, symbol, bars):
        response = requests.post(
            f'{self.base_url}/api/v1/predictions',
            json={'symbol': symbol, 'bars': bars},
            headers=self.headers
        )
        return response.json()

# Usage
client = TradePulseClient('YOUR_TOKEN')
signal = client.get_signal('BTC-USD', [
    {
        'timestamp': '2025-01-01T00:00:00Z',
        'high': 42100.0,
        'low': 41900.0,
        'close': 42050.0,
        'volume': 18.5
    }
])

print(f"Action: {signal['signal']['action']}")
print(f"Confidence: {signal['signal']['confidence']}")
```

### JavaScript Example

```javascript
async function getTradingSignal(symbol, bars) {
  const response = await fetch(
    'https://api.tradepulse.example.com/api/v1/predictions',
    {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer YOUR_TOKEN',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        symbol: symbol,
        bars: bars,
      }),
    }
  );
  
  return response.json();
}

// Usage
const signal = await getTradingSignal('BTC-USD', [
  {
    timestamp: new Date().toISOString(),
    high: 42100.0,
    low: 41900.0,
    close: 42050.0,
    volume: 18.5,
  },
]);

console.log(`Action: ${signal.signal.action}`);
console.log(`Confidence: ${signal.signal.confidence}`);
```

## Next Steps

- 📖 Read the [Comprehensive API Guide](comprehensive_guide.md)
- 🔐 Learn about [Authentication](comprehensive_guide.md#authentication)
- ⚡ Optimize with [Caching and Performance](comprehensive_guide.md#caching-and-performance)
- 🚨 Implement [Error Handling](comprehensive_guide.md#error-handling)
- 💬 Join our [Discord community](https://discord.gg/tradepulse)

## Common Patterns

### Rate Limiting
```python
import time

def call_with_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return func()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                time.sleep(2 ** attempt)
            else:
                raise
    raise Exception("Max retries exceeded")
```

### Idempotency
```python
import hashlib
import json

def generate_idempotency_key(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()[:32]

headers['Idempotency-Key'] = generate_idempotency_key(payload)
```

### Pagination
```python
def fetch_all_features(client, symbol, bars):
    features = []
    cursor = None
    
    while True:
        params = {'limit': 100}
        if cursor:
            params['cursor'] = cursor
        
        response = client.compute_features(symbol, bars, params=params)
        features.extend(response['items'])
        
        cursor = response['pagination']['next_cursor']
        if not cursor:
            break
    
    return features
```

## Troubleshooting

### Issue: 401 Unauthorized
**Solution**: Verify your token is valid
```bash
# Test token
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://api.tradepulse.example.com/health
```

### Issue: 429 Too Many Requests
**Solution**: Implement rate limiting and backoff
```python
import time

def exponential_backoff(attempt):
    time.sleep(min(2 ** attempt, 60))
```

### Issue: 422 Validation Error
**Solution**: Check request format
```json
{
  "detail": {
    "code": "UNPROCESSABLE",
    "message": "Validation error: ...",
    "meta": {...}
  }
}
```

## Support

Need help? We're here:
- 📧 platform@tradepulse.example
- 💬 [Discord Community](https://discord.gg/tradepulse)
- 🐛 [GitHub Issues](https://github.com/neuron7x/TradePulse/issues)

---

**Ready to build?** Start with the [comprehensive guide](comprehensive_guide.md) for advanced features!
