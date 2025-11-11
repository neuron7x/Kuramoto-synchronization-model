# TradePulse Cortex Service

Enterprise-grade cognitive signal orchestration microservice for TradePulse portfolios.

## Overview

The Cortex Service provides a unified API for:
- **Signal Computation**: Transform feature observations into actionable trading signals
- **Risk Assessment**: Evaluate portfolio risk with VaR, stress testing, and breach detection
- **Regime Modulation**: Track and classify market regimes based on feedback and volatility
- **Memory Management**: Persist and retrieve portfolio exposures

## Architecture

The service follows a clean layered architecture:

```
cortex_service/
├── app/
│   ├── api.py              # FastAPI endpoints
│   ├── schemas.py          # Pydantic request/response models
│   ├── middleware.py       # Request ID and middleware components
│   ├── services/           # Business logic layer
│   │   ├── signal_service.py
│   │   ├── risk_service.py
│   │   └── regime_service.py
│   ├── core/               # Domain models and algorithms
│   │   └── signals.py
│   ├── ethics/             # Risk assessment
│   │   └── risk.py
│   ├── modulation/         # Regime tracking
│   │   └── regime.py
│   ├── memory/             # Persistence layer
│   │   └── repository.py
│   ├── errors.py           # Unified error taxonomy
│   ├── decorators.py       # Retry and transactional decorators
│   ├── metrics.py          # Prometheus metrics
│   ├── config.py           # Configuration management
│   └── models.py           # SQLAlchemy models
└── tests/                  # Comprehensive test suite (50 tests, 87% coverage)
```

## API Endpoints

### Health & Monitoring

#### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "ok"
}
```

#### GET /ready
Readiness probe for Kubernetes/container orchestration.

**Response:**
```json
{
  "ready": true,
  "checks": {
    "database": true
  }
}
```

#### GET /metrics
Prometheus metrics endpoint (text format).

### Signal Computation

#### POST /signals
Compute trading signals from feature observations.

**Request:**
```json
{
  "as_of": "2025-01-15T10:30:00Z",
  "features": [
    {
      "instrument": "AAPL",
      "name": "momentum",
      "value": 1.3,
      "mean": 0.2,
      "std": 0.5,
      "weight": 1.5
    },
    {
      "instrument": "AAPL",
      "name": "volatility",
      "value": 0.4,
      "mean": 0.3,
      "std": 0.2,
      "weight": 0.7
    }
  ]
}
```

**Response:**
```json
{
  "signals": [
    {
      "instrument": "AAPL",
      "strength": 0.75,
      "contributors": ["momentum", "volatility"]
    }
  ],
  "ensemble_strength": 0.75,
  "synchrony": 0.92
}
```

### Risk Assessment

#### POST /risk
Assess portfolio risk from exposures.

**Request:**
```json
{
  "exposures": [
    {
      "portfolio_id": "alpha",
      "instrument": "AAPL",
      "exposure": 0.7,
      "leverage": 1.2,
      "as_of": "2025-01-15T10:30:00Z",
      "limit": 1.0,
      "volatility": 0.3
    }
  ]
}
```

**Response:**
```json
{
  "score": 0.35,
  "value_at_risk": 0.42,
  "stressed_var": [0.36, 0.21],
  "breached": []
}
```

### Regime Management

#### POST /regime
Update market regime based on feedback.

**Request:**
```json
{
  "feedback": 0.4,
  "volatility": 0.2,
  "as_of": "2025-01-15T10:30:00Z"
}
```

**Response:**
```json
{
  "label": "neutral",
  "valence": 0.32,
  "confidence": 0.80,
  "as_of": "2025-01-15T10:30:00Z"
}
```

### Memory Operations

#### POST /memory
Persist portfolio exposures.

**Request:**
```json
{
  "exposures": [
    {
      "portfolio_id": "alpha",
      "instrument": "AAPL",
      "exposure": 1.1,
      "leverage": 1.2,
      "as_of": "2025-01-15T10:30:00Z"
    }
  ]
}
```

**Status:** 202 Accepted

#### GET /memory/{portfolio_id}
Retrieve stored portfolio exposures.

**Response:**
```json
{
  "portfolio_id": "alpha",
  "exposures": [
    {
      "portfolio_id": "alpha",
      "instrument": "AAPL",
      "exposure": 1.1,
      "leverage": 1.2,
      "as_of": "2025-01-15T10:30:00Z"
    }
  ]
}
```

## Error Model

All errors return a unified JSON structure with request ID for tracing:

```json
{
  "error": "VALIDATION_ERROR",
  "message": "Request validation failed",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "details": [
    {
      "field": "features",
      "message": "At least one feature is required"
    }
  ]
}
```

### Error Codes

- `VALIDATION_ERROR` (400): Invalid request data
- `NOT_FOUND` (404): Resource not found
- `COMPUTATION_ERROR` (422): Invalid computation parameters
- `DATABASE_ERROR` (500): Database operation failed
- `INTERNAL_ERROR` (500): Unexpected error

All responses include the `X-Request-ID` header for distributed tracing.

## Prometheus Metrics

### Request Metrics
- `cortex_request_latency_seconds`: Request latency histogram (labels: endpoint, method, status)
- `cortex_request_inflight`: Currently processing requests (label: endpoint)
- `cortex_error_total`: Total errors by type (label: code)

### Signal Metrics
- `cortex_signal_strength`: Signal strength distribution
- `cortex_signal_distribution`: Individual signal value distribution

### Risk Metrics
- `cortex_risk_score`: Risk score distribution

### Regime Metrics
- `cortex_regime_updates_total`: Total regime updates (label: regime)
- `cortex_regime_transition_total`: Regime transitions (labels: from_regime, to_regime)

### Database Metrics
- `cortex_db_operation_latency_seconds`: Database operation latency (label: operation)

## Configuration

Configuration is loaded from YAML with environment variable overrides.

### Default Configuration Path
`cortex_service/config/service.yaml`

Override with: `CORTEX_CONFIG_PATH=/path/to/config.yaml`

### Configuration Keys

#### Service Settings
```yaml
service:
  name: TradePulse Cortex Service
  version: 1.0.0
  description: Cognitive signal orchestration
  metrics_path: /metrics
  log_level: INFO  # DEBUG, INFO, WARNING, ERROR
  host: 0.0.0.0
  port: 8001
```

#### Database Settings
```yaml
database:
  url: postgresql+psycopg://user@host:5432/db?sslmode=verify-full
  pool_size: 10
  pool_timeout: 30
  echo: false
```

#### Signal Settings
```yaml
signals:
  rescale_min: -1.0
  rescale_max: 1.0
  smoothing_factor: 0.25  # 0-1, higher = more smoothing
  volatility_floor: 1e-6  # Minimum std for z-score
```

#### Risk Settings
```yaml
risk:
  max_absolute_exposure: 2.0
  var_confidence: 0.95  # 0-1, typical: 0.95 or 0.99
  stress_scenarios:  # Multipliers for stress testing (must be unique, positive)
    - 0.85
    - 0.5
```

#### Regime Settings
```yaml
regime:
  decay: 0.2  # 0-1, higher = faster adaptation
  min_valence: -1.0
  max_valence: 1.0
  confidence_floor: 0.1
```

### Environment Variable Overrides

Use the `CORTEX__` prefix with double underscores for nested keys:

```bash
# Override database URL
export CORTEX__DATABASE__URL="postgresql://localhost/cortex"

# Override signal smoothing
export CORTEX__SIGNALS__SMOOTHING_FACTOR="0.3"

# Override risk confidence
export CORTEX__RISK__VAR_CONFIDENCE="0.99"
```

## Running the Service

### Development
```bash
# Install dependencies
pip install -e ".[dev]"

# Run with uvicorn (HTTP)
uvicorn cortex_service.app.api:create_app --factory --reload

# Run with TLS (production-like)
python -m cortex_service.app.runtime
```

### Production (Docker)
```bash
docker build -t cortex-service .
docker run -p 8001:8001 \
  -e CORTEX__DATABASE__URL="postgresql://..." \
  -v /path/to/certs:/service/tls:ro \
  cortex-service
```

## Testing

### Run All Tests
```bash
pytest cortex_service/tests/ -v
```

### Run with Coverage
```bash
pytest cortex_service/tests/ --cov=cortex_service/app --cov-report=html
```

### Run Property Tests
```bash
pytest cortex_service/tests/test_property.py -v
```

### Current Test Coverage
- **50 passing tests**
- **86.98% code coverage**
- Comprehensive unit, integration, and property-based tests

## Code Quality

### Type Checking
```bash
mypy cortex_service/app --strict
```
✓ Zero errors with `--strict` mode

### Linting
```bash
ruff check cortex_service/
```
✓ Clean

### Formatting
```bash
black cortex_service/
```
✓ Formatted

## Development

### Architecture Decisions
- **Layered Architecture**: Clear separation between API, services, domain, and persistence
- **Service Layer**: Business logic isolated from HTTP concerns
- **Frozen Dataclasses**: Immutable domain models prevent accidental mutation
- **Unified Error Taxonomy**: All errors inherit from `CortexError`
- **Request ID Middleware**: Every request gets a unique ID for tracing
- **Retry with Backoff**: Transient database errors are automatically retried
- **TTL Caching**: Latest regime state cached for 5 seconds to reduce DB load

### Adding a New Endpoint
1. Define request/response schemas in `schemas.py`
2. Implement business logic in appropriate service
3. Add endpoint to `api.py` with proper tags and documentation
4. Add comprehensive tests
5. Update this README

## License

See [LICENSE](../LICENSE) in the repository root.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## Architecture Details

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture documentation and sequence diagrams.
