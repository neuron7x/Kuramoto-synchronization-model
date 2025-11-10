# TradePulse API Integration Guide

Complete guide for integrating TradePulse API into your trading applications.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Integration Patterns](#integration-patterns)
3. [Client Libraries](#client-libraries)
4. [Production Deployment](#production-deployment)
5. [Monitoring & Observability](#monitoring--observability)
6. [Security Best Practices](#security-best-practices)

## Architecture Overview

```
┌─────────────────┐
│  Your Trading   │
│   Application   │
└────────┬────────┘
         │
         │ HTTPS + OAuth 2.0
         │
         ▼
┌─────────────────┐
│   TradePulse    │
│   API Gateway   │
└────────┬────────┘
         │
    ┌────┴────┬────────────┬──────────┐
    ▼         ▼            ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Features│ │Predict │ │ Admin  │ │Metrics │
│  API   │ │  API   │ │  API   │ │  API   │
└────────┘ └────────┘ └────────┘ └────────┘
```

### Key Components

1. **API Gateway**: Rate limiting, authentication, routing
2. **Features API**: Technical indicator computation
3. **Predictions API**: ML-powered signal generation
4. **Admin API**: Risk controls and kill-switch
5. **Metrics API**: Prometheus metrics export

## Integration Patterns

### Pattern 1: Real-Time Signal Generation

Use this pattern for live trading with real-time market data.

```python
import asyncio
import websockets
import json
from datetime import datetime, timezone

class RealTimeTrader:
    def __init__(self, api_client):
        self.client = api_client
        self.position = None
    
    async def on_market_data(self, symbol: str, bar: dict):
        """Called when new market bar arrives"""
        # Generate prediction
        result = await self.client.generate_prediction(
            symbol=symbol,
            bars=[bar],
            horizon_seconds=300
        )
        
        signal = result['signal']
        
        # Execute trade logic
        if signal['confidence'] > 0.75:
            await self.execute_signal(symbol, signal)
    
    async def execute_signal(self, symbol: str, signal: dict):
        """Execute trading action based on signal"""
        action = signal['action']
        
        if action == 'buy' and not self.position:
            await self.open_position(symbol, 'long')
        elif action == 'sell' and self.position:
            await self.close_position(symbol)
    
    async def open_position(self, symbol: str, side: str):
        print(f"Opening {side} position for {symbol}")
        self.position = {'symbol': symbol, 'side': side}
    
    async def close_position(self, symbol: str):
        print(f"Closing position for {symbol}")
        self.position = None

# Usage
trader = RealTimeTrader(api_client)

async def market_data_stream():
    async with websockets.connect('ws://exchange.example/stream') as ws:
        async for message in ws:
            data = json.loads(message)
            await trader.on_market_data(data['symbol'], data['bar'])
```

### Pattern 2: Batch Processing

Use this for backtesting or batch analysis of historical data.

```python
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

class BatchProcessor:
    def __init__(self, api_client, max_workers=10):
        self.client = api_client
        self.max_workers = max_workers
    
    def process_symbols(self, symbols: list, historical_data: dict):
        """Process multiple symbols in parallel"""
        results = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self.process_symbol, 
                    symbol, 
                    historical_data[symbol]
                ): symbol 
                for symbol in symbols
            }
            
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    results[symbol] = future.result()
                except Exception as e:
                    print(f"Error processing {symbol}: {e}")
        
        return results
    
    def process_symbol(self, symbol: str, bars: list):
        """Process a single symbol"""
        # Split into batches to respect API limits
        batch_size = 100
        signals = []
        
        for i in range(0, len(bars), batch_size):
            batch = bars[i:i + batch_size]
            result = self.client.generate_prediction(symbol, batch)
            signals.extend(result['items'])
        
        return self.analyze_signals(signals)
    
    def analyze_signals(self, signals: list):
        """Analyze signal quality"""
        df = pd.DataFrame(signals)
        
        return {
            'total_signals': len(signals),
            'buy_signals': (df['signal'].apply(lambda x: x['action']) == 'buy').sum(),
            'sell_signals': (df['signal'].apply(lambda x: x['action']) == 'sell').sum(),
            'avg_confidence': df['signal'].apply(lambda x: x['confidence']).mean(),
        }

# Usage
processor = BatchProcessor(api_client)
results = processor.process_symbols(
    symbols=['BTC-USD', 'ETH-USD', 'SOL-USD'],
    historical_data=load_historical_data()
)
```

### Pattern 3: Multi-Timeframe Analysis

Analyze multiple timeframes simultaneously for better signal quality.

```python
from datetime import timedelta

class MultiTimeframeAnalyzer:
    def __init__(self, api_client):
        self.client = api_client
        self.timeframes = {
            '5m': 300,    # 5 minutes
            '15m': 900,   # 15 minutes
            '1h': 3600,   # 1 hour
            '4h': 14400,  # 4 hours
        }
    
    def analyze(self, symbol: str, bars: dict):
        """
        Analyze signal across multiple timeframes.
        bars: dict with keys '5m', '15m', '1h', '4h'
        """
        signals = {}
        
        for tf, horizon in self.timeframes.items():
            if tf not in bars:
                continue
            
            result = self.client.generate_prediction(
                symbol=symbol,
                bars=bars[tf],
                horizon_seconds=horizon
            )
            
            signals[tf] = result['signal']
        
        return self.compute_consensus(signals)
    
    def compute_consensus(self, signals: dict):
        """Compute consensus signal from multiple timeframes"""
        # Weight timeframes (longer = more weight)
        weights = {'5m': 1, '15m': 2, '1h': 3, '4h': 4}
        
        buy_score = sum(
            weights[tf] * (1 if s['action'] == 'buy' else 0) * s['confidence']
            for tf, s in signals.items()
        )
        
        sell_score = sum(
            weights[tf] * (1 if s['action'] == 'sell' else 0) * s['confidence']
            for tf, s in signals.items()
        )
        
        total_weight = sum(weights[tf] for tf in signals.keys())
        
        if buy_score > sell_score and buy_score / total_weight > 0.5:
            action = 'buy'
            confidence = buy_score / total_weight
        elif sell_score > buy_score and sell_score / total_weight > 0.5:
            action = 'sell'
            confidence = sell_score / total_weight
        else:
            action = 'hold'
            confidence = 0.5
        
        return {
            'action': action,
            'confidence': confidence,
            'timeframe_signals': signals,
            'buy_score': buy_score,
            'sell_score': sell_score,
        }

# Usage
analyzer = MultiTimeframeAnalyzer(api_client)

bars = {
    '5m': get_bars('BTC-USD', '5m'),
    '15m': get_bars('BTC-USD', '15m'),
    '1h': get_bars('BTC-USD', '1h'),
    '4h': get_bars('BTC-USD', '4h'),
}

consensus = analyzer.analyze('BTC-USD', bars)
print(f"Consensus: {consensus['action']} ({consensus['confidence']:.2%})")
```

### Pattern 4: Circuit Breaker Integration

Integrate with the admin kill-switch for risk management.

```python
import time
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Trading halted
    HALF_OPEN = "half_open"  # Testing recovery

class CircuitBreaker:
    def __init__(self, admin_client, failure_threshold=5, reset_timeout=300):
        self.admin_client = admin_client
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
    
    async def check_kill_switch(self):
        """Check if kill-switch is engaged"""
        status = await self.admin_client.get_kill_switch_status()
        
        if status['kill_switch_engaged']:
            self.state = CircuitState.OPEN
            return False
        
        return True
    
    def record_failure(self, error: Exception):
        """Record a trading failure"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.engage_kill_switch(
                f"Circuit breaker triggered after {self.failure_count} failures"
            )
    
    def record_success(self):
        """Record a successful trade"""
        if self.state == CircuitState.HALF_OPEN:
            # Recovery successful
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.reset_kill_switch()
    
    async def engage_kill_switch(self, reason: str):
        """Engage the kill-switch"""
        self.state = CircuitState.OPEN
        await self.admin_client.engage_kill_switch(reason)
        print(f"🚨 Kill-switch engaged: {reason}")
    
    async def reset_kill_switch(self):
        """Reset the kill-switch"""
        await self.admin_client.reset_kill_switch()
        print("✅ Kill-switch reset")
    
    def can_trade(self) -> bool:
        """Check if trading is allowed"""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # Check if timeout has passed
            if (time.time() - self.last_failure_time) > self.reset_timeout:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        
        # HALF_OPEN: allow limited trading to test
        return True

# Usage
breaker = CircuitBreaker(admin_client)

async def execute_trade(signal):
    if not breaker.can_trade():
        print("⛔ Trading halted by circuit breaker")
        return
    
    try:
        # Execute trade
        result = await exchange.place_order(signal)
        breaker.record_success()
        return result
    except Exception as e:
        breaker.record_failure(e)
        raise
```

## Client Libraries

### Python Client (Production-Ready)

```python
import requests
import hashlib
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class TradePulseClient:
    """Production-ready TradePulse API client with retry logic."""
    
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'User-Agent': 'TradePulse-Client/1.0',
        })
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        reraise=True,
    )
    def _request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> requests.Response:
        """Make HTTP request with retry logic."""
        url = f'{self.base_url}{path}'
        
        try:
            response = self.session.request(
                method,
                url,
                timeout=self.timeout,
                **kwargs
            )
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            # Don't retry client errors
            if 400 <= e.response.status_code < 500:
                logger.error(f"Client error: {e.response.text}")
                raise
            # Retry server errors
            logger.warning(f"Server error, retrying: {e}")
            raise
    
    def health_check(self) -> Dict[str, Any]:
        """Check API health."""
        response = self._request('GET', '/health')
        return response.json()
    
    def compute_features(
        self,
        symbol: str,
        bars: List[Dict[str, Any]],
        idempotency_key: Optional[str] = None,
        **params
    ) -> Dict[str, Any]:
        """Compute features from market bars."""
        payload = {'symbol': symbol, 'bars': bars}
        
        headers = {}
        if idempotency_key:
            headers['Idempotency-Key'] = idempotency_key
        elif not params.get('skip_idempotency'):
            # Auto-generate idempotency key
            headers['Idempotency-Key'] = self._generate_idempotency_key(payload)
        
        response = self._request(
            'POST',
            '/api/v1/features',
            json=payload,
            headers=headers,
            params=params,
        )
        
        return response.json()
    
    def generate_prediction(
        self,
        symbol: str,
        bars: List[Dict[str, Any]],
        horizon_seconds: int = 900,
        idempotency_key: Optional[str] = None,
        **params
    ) -> Dict[str, Any]:
        """Generate trading signal prediction."""
        payload = {
            'symbol': symbol,
            'bars': bars,
            'horizon_seconds': horizon_seconds,
        }
        
        headers = {}
        if idempotency_key:
            headers['Idempotency-Key'] = idempotency_key
        elif not params.get('skip_idempotency'):
            headers['Idempotency-Key'] = self._generate_idempotency_key(payload)
        
        response = self._request(
            'POST',
            '/api/v1/predictions',
            json=payload,
            headers=headers,
            params=params,
        )
        
        return response.json()
    
    def _generate_idempotency_key(self, payload: Dict[str, Any]) -> str:
        """Generate idempotency key from payload."""
        data = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:32]
    
    def close(self):
        """Close the session."""
        self.session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()

# Usage
with TradePulseClient('https://api.tradepulse.example.com', 'TOKEN') as client:
    health = client.health_check()
    print(f"API Status: {health['status']}")
```

### TypeScript Client

```typescript
import axios, { AxiosInstance, AxiosResponse } from 'axios';
import crypto from 'crypto';

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

interface PredictionResponse {
  symbol: string;
  signal: Signal;
  score: number;
  generated_at: string;
  horizon_seconds: number;
}

export class TradePulseClient {
  private client: AxiosInstance;
  private baseUrl: string;

  constructor(baseUrl: string, token: string) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.client = axios.create({
      baseURL: this.baseUrl,
      timeout: 30000,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        'User-Agent': 'TradePulse-Client-TS/1.0',
      },
    });

    // Add retry interceptor
    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        const config = error.config;
        
        // Don't retry if no config or max retries reached
        if (!config || config.__retryCount >= 3) {
          return Promise.reject(error);
        }

        config.__retryCount = config.__retryCount || 0;
        config.__retryCount += 1;

        // Only retry on 5xx errors or network errors
        if (error.response?.status >= 500 || !error.response) {
          const delay = Math.min(1000 * Math.pow(2, config.__retryCount), 60000);
          await new Promise(resolve => setTimeout(resolve, delay));
          return this.client(config);
        }

        return Promise.reject(error);
      }
    );
  }

  async healthCheck(): Promise<any> {
    const response = await this.client.get('/health');
    return response.data;
  }

  async computeFeatures(
    symbol: string,
    bars: MarketBar[],
    options: {
      idempotencyKey?: string;
      params?: Record<string, any>;
    } = {}
  ): Promise<any> {
    const payload = { symbol, bars };
    const headers: Record<string, string> = {};

    if (options.idempotencyKey) {
      headers['Idempotency-Key'] = options.idempotencyKey;
    } else {
      headers['Idempotency-Key'] = this.generateIdempotencyKey(payload);
    }

    const response = await this.client.post(
      '/api/v1/features',
      payload,
      { headers, params: options.params }
    );

    return response.data;
  }

  async generatePrediction(
    symbol: string,
    bars: MarketBar[],
    options: {
      horizonSeconds?: number;
      idempotencyKey?: string;
      params?: Record<string, any>;
    } = {}
  ): Promise<PredictionResponse> {
    const payload = {
      symbol,
      bars,
      horizon_seconds: options.horizonSeconds || 900,
    };

    const headers: Record<string, string> = {};

    if (options.idempotencyKey) {
      headers['Idempotency-Key'] = options.idempotencyKey;
    } else {
      headers['Idempotency-Key'] = this.generateIdempotencyKey(payload);
    }

    const response = await this.client.post(
      '/api/v1/predictions',
      payload,
      { headers, params: options.params }
    );

    return response.data;
  }

  private generateIdempotencyKey(payload: any): string {
    const data = JSON.stringify(payload);
    return crypto.createHash('sha256').update(data).digest('hex').substring(0, 32);
  }
}

// Usage
const client = new TradePulseClient(
  'https://api.tradepulse.example.com',
  process.env.TRADEPULSE_TOKEN!
);

const result = await client.generatePrediction('BTC-USD', [
  {
    timestamp: new Date().toISOString(),
    high: 42100,
    low: 41900,
    close: 42050,
    volume: 18.5,
  },
]);

console.log(`Action: ${result.signal.action}`);
console.log(`Confidence: ${result.signal.confidence}`);
```

## Production Deployment

### Environment Configuration

```bash
# .env.production
TRADEPULSE_API_URL=https://api.tradepulse.example.com
TRADEPULSE_TOKEN=<your-token>
TRADEPULSE_TIMEOUT=30
TRADEPULSE_MAX_RETRIES=3
TRADEPULSE_CACHE_TTL=30

# Admin API (optional)
TRADEPULSE_ADMIN_TOKEN=<admin-token>
TRADEPULSE_2FA_SECRET=<2fa-secret>
```

### Docker Deployment

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV TRADEPULSE_API_URL=https://api.tradepulse.example.com

CMD ["python", "trading_bot.py"]
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tradepulse-trader
spec:
  replicas: 3
  selector:
    matchLabels:
      app: tradepulse-trader
  template:
    metadata:
      labels:
        app: tradepulse-trader
    spec:
      containers:
      - name: trader
        image: tradepulse-trader:latest
        env:
        - name: TRADEPULSE_API_URL
          value: "https://api.tradepulse.example.com"
        - name: TRADEPULSE_TOKEN
          valueFrom:
            secretKeyRef:
              name: tradepulse-secrets
              key: api-token
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
```

## Monitoring & Observability

### Metrics Collection

```python
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Define metrics
api_requests_total = Counter(
    'tradepulse_api_requests_total',
    'Total API requests',
    ['endpoint', 'status']
)

api_request_duration = Histogram(
    'tradepulse_api_request_duration_seconds',
    'API request duration',
    ['endpoint']
)

api_cache_hits = Counter(
    'tradepulse_api_cache_hits_total',
    'Total cache hits'
)

signals_generated = Counter(
    'tradepulse_signals_generated_total',
    'Total trading signals generated',
    ['symbol', 'action']
)

class MonitoredClient:
    def __init__(self, client):
        self.client = client
    
    def generate_prediction(self, symbol, bars, **kwargs):
        with api_request_duration.labels(endpoint='predictions').time():
            try:
                result = self.client.generate_prediction(symbol, bars, **kwargs)
                api_requests_total.labels(endpoint='predictions', status='200').inc()
                
                # Track signal
                action = result['signal']['action']
                signals_generated.labels(symbol=symbol, action=action).inc()
                
                # Check cache status
                if result.get('_cache_status') == 'hit':
                    api_cache_hits.inc()
                
                return result
            except Exception as e:
                api_requests_total.labels(
                    endpoint='predictions',
                    status=getattr(e, 'response', {}).status_code or '500'
                ).inc()
                raise

# Start metrics server
start_http_server(8000)
```

### Logging

```python
import logging
import json
from pythonjsonlogger import jsonlogger

# Configure structured logging
logger = logging.getLogger('tradepulse')
handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter(
    '%(asctime)s %(name)s %(levelname)s %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Log API calls
def log_api_call(endpoint, symbol, duration, status, **extra):
    logger.info(
        'API call completed',
        extra={
            'endpoint': endpoint,
            'symbol': symbol,
            'duration_ms': duration * 1000,
            'status': status,
            **extra
        }
    )

# Usage
start = time.time()
try:
    result = client.generate_prediction('BTC-USD', bars)
    log_api_call(
        'predictions',
        'BTC-USD',
        time.time() - start,
        200,
        action=result['signal']['action'],
        confidence=result['signal']['confidence']
    )
except Exception as e:
    log_api_call(
        'predictions',
        'BTC-USD',
        time.time() - start,
        500,
        error=str(e)
    )
    raise
```

### Alerting

```yaml
# Prometheus alerting rules
groups:
- name: tradepulse_api
  rules:
  - alert: HighErrorRate
    expr: rate(tradepulse_api_requests_total{status=~"5.."}[5m]) > 0.05
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High API error rate"
      description: "API error rate is {{ $value }} req/s"

  - alert: SlowAPIResponses
    expr: histogram_quantile(0.95, tradepulse_api_request_duration_seconds_bucket) > 5
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: "Slow API responses"
      description: "95th percentile latency is {{ $value }}s"

  - alert: LowCacheHitRate
    expr: rate(tradepulse_api_cache_hits_total[5m]) / rate(tradepulse_api_requests_total[5m]) < 0.5
    for: 15m
    labels:
      severity: info
    annotations:
      summary: "Low cache hit rate"
      description: "Cache hit rate is {{ $value | humanizePercentage }}"
```

## Security Best Practices

### 1. Token Management

```python
import os
from cryptography.fernet import Fernet

class SecureTokenManager:
    """Secure token storage and retrieval."""
    
    def __init__(self, encryption_key: bytes):
        self.cipher = Fernet(encryption_key)
    
    def store_token(self, token: str, path: str = '.token'):
        """Encrypt and store token."""
        encrypted = self.cipher.encrypt(token.encode())
        with open(path, 'wb') as f:
            f.write(encrypted)
        os.chmod(path, 0o600)  # Owner read/write only
    
    def load_token(self, path: str = '.token') -> str:
        """Load and decrypt token."""
        with open(path, 'rb') as f:
            encrypted = f.read()
        return self.cipher.decrypt(encrypted).decode()

# Usage
key = Fernet.generate_key()
manager = SecureTokenManager(key)
manager.store_token(os.environ['TRADEPULSE_TOKEN'])

# Later
token = manager.load_token()
client = TradePulseClient('https://api.tradepulse.example.com', token)
```

### 2. Request Signing

```python
import hmac
import hashlib
import time
from typing import Dict, Any

def sign_request(payload: Dict[str, Any], secret: str) -> str:
    """Sign request payload with HMAC-SHA256."""
    timestamp = str(int(time.time()))
    message = f"{timestamp}.{json.dumps(payload, sort_keys=True)}"
    signature = hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return f"{timestamp},{signature}"

def verify_signature(payload: Dict[str, Any], signature: str, secret: str) -> bool:
    """Verify request signature."""
    timestamp, sig = signature.split(',')
    expected = sign_request(payload, secret)
    return hmac.compare_digest(signature, expected)

# Usage
payload = {'symbol': 'BTC-USD', 'bars': [...]}
signature = sign_request(payload, SECRET_KEY)

headers = {
    'X-Signature': signature,
    'Authorization': f'Bearer {token}'
}
```

### 3. Rate Limit Handling

```python
import time
from collections import deque

class RateLimiter:
    """Client-side rate limiter."""
    
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = deque()
    
    def wait_if_needed(self):
        """Wait if rate limit would be exceeded."""
        now = time.time()
        
        # Remove old requests outside window
        while self.requests and self.requests[0] < now - self.window_seconds:
            self.requests.popleft()
        
        # Check if we're at limit
        if len(self.requests) >= self.max_requests:
            sleep_time = self.window_seconds - (now - self.requests[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
                self.requests.popleft()
        
        self.requests.append(now)

# Usage
limiter = RateLimiter(max_requests=100, window_seconds=60)

def call_api():
    limiter.wait_if_needed()
    return client.generate_prediction(...)
```

## Testing

### Integration Tests

```python
import pytest
from unittest.mock import Mock, patch

def test_generate_prediction_success():
    client = TradePulseClient('https://api.example.com', 'token')
    
    with patch.object(client.session, 'request') as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'signal': {'action': 'buy', 'confidence': 0.8},
            'score': 0.42
        }
        mock_request.return_value = mock_response
        
        result = client.generate_prediction('BTC-USD', [{}])
        
        assert result['signal']['action'] == 'buy'
        assert result['signal']['confidence'] == 0.8

def test_retry_on_server_error():
    client = TradePulseClient('https://api.example.com', 'token')
    
    with patch.object(client.session, 'request') as mock_request:
        # First two calls fail, third succeeds
        mock_request.side_effect = [
            requests.exceptions.HTTPError(response=Mock(status_code=503)),
            requests.exceptions.HTTPError(response=Mock(status_code=503)),
            Mock(status_code=200, json=lambda: {'signal': {}}),
        ]
        
        result = client.generate_prediction('BTC-USD', [{}])
        
        assert mock_request.call_count == 3
```

## Next Steps

- Review [Comprehensive API Guide](comprehensive_guide.md) for detailed endpoint documentation
- Check [Quick Start Guide](quick_start.md) for getting started
- Join our [Discord community](https://discord.gg/tradepulse) for support

---

**Last Updated**: 2025-01-10
