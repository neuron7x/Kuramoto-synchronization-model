# Cortex Service Architecture

## Overview

The Cortex Service follows a **layered architecture** pattern with clear separation of concerns:

1. **API Layer** (`api.py`, `schemas.py`): HTTP interface and request/response handling
2. **Service Layer** (`services/`): Business logic orchestration
3. **Domain Layer** (`core/`, `ethics/`, `modulation/`): Core algorithms and domain models
4. **Persistence Layer** (`memory/`, `models.py`): Data access and repository pattern
5. **Infrastructure Layer** (`middleware.py`, `decorators.py`, `metrics.py`): Cross-cutting concerns

## Component Diagram

```mermaid
graph TB
    Client[HTTP Client] --> MW[Request ID Middleware]
    MW --> API[FastAPI Endpoints]
    API --> SigSvc[Signal Service]
    API --> RiskSvc[Risk Service]
    API --> RegimeSvc[Regime Service]
    API --> Repo[Memory Repository]
    
    SigSvc --> SigCore[Signal Core]
    SigSvc --> Ensemble[Ensemble Sync]
    RiskSvc --> RiskCore[Risk Assessment]
    RegimeSvc --> RegimeCore[Regime Modulator]
    RegimeSvc --> Cache[Regime Cache]
    RegimeSvc --> Repo
    
    Repo --> DB[(PostgreSQL)]
    
    API --> EH[Exception Handlers]
    EH --> Metrics[Prometheus Metrics]
    
    style API fill:#e1f5ff
    style SigSvc fill:#fff4e1
    style RiskSvc fill:#fff4e1
    style RegimeSvc fill:#fff4e1
    style Repo fill:#e1ffe1
```

## Signal Computation Flow

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant Middleware
    participant SignalService
    participant SignalCore
    participant EnsembleSync
    participant Metrics
    
    Client->>Middleware: POST /signals (features)
    Middleware->>Middleware: Generate/Extract Request ID
    Middleware->>API: Forward Request
    API->>API: Validate Pydantic Schema
    API->>Metrics: Increment inflight gauge
    API->>SignalService: compute_signals(features)
    SignalService->>SignalCore: build_signal_ensemble()
    loop For each instrument
        SignalCore->>SignalCore: Group features
        SignalCore->>SignalCore: Compute z-scores
        SignalCore->>SignalCore: Weight & smooth
        SignalCore->>SignalCore: Rescale to bounds
    end
    SignalCore-->>SignalService: List[Signal]
    SignalService->>EnsembleSync: aggregate_strength()
    SignalService->>EnsembleSync: kuramoto_order_parameter()
    EnsembleSync-->>SignalService: ensemble_strength, synchrony
    SignalService->>Metrics: Record signal distributions
    SignalService-->>API: signals, strength, synchrony
    API->>Metrics: Record latency
    API->>Metrics: Decrement inflight gauge
    API->>Middleware: Return response
    Middleware->>Middleware: Add X-Request-ID header
    Middleware->>Metrics: Log request completion
    Middleware-->>Client: SignalsResponse + headers
```

## Risk Assessment Flow

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant RiskService
    participant RiskCore
    participant Metrics
    
    Client->>API: POST /risk (exposures)
    API->>API: Validate exposures
    API->>Metrics: Increment inflight
    API->>RiskService: assess_risk(exposures)
    RiskService->>RiskCore: compute_risk()
    
    RiskCore->>RiskCore: Calculate aggregate VaR
    loop For each exposure
        RiskCore->>RiskCore: Check limit breaches
        RiskCore->>RiskCore: Compute exposure * volatility
    end
    RiskCore->>RiskCore: Apply stress scenarios
    RiskCore->>RiskCore: Calculate confidence scale
    RiskCore->>RiskCore: Compute risk score
    
    RiskCore-->>RiskService: RiskAssessment
    RiskService->>Metrics: Record risk score
    RiskService-->>API: assessment
    API->>Metrics: Record latency
    API->>Metrics: Decrement inflight
    API-->>Client: RiskResponse
```

## Regime Update Flow

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant RegimeService
    participant Cache
    participant RegimeModulator
    participant Repository
    participant DB
    participant Metrics
    
    Client->>API: POST /regime (feedback, volatility)
    API->>API: Validate request
    API->>Metrics: Increment inflight
    API->>RegimeService: update_regime()
    
    RegimeService->>Cache: get()
    alt Cache Hit
        Cache-->>RegimeService: Previous RegimeState
    else Cache Miss
        RegimeService->>Repository: latest_regime()
        Repository->>DB: SELECT ... ORDER BY as_of DESC LIMIT 1
        DB-->>Repository: MarketRegime
        Repository-->>RegimeService: RegimeState
        RegimeService->>Metrics: Record DB latency
    end
    
    RegimeService->>RegimeModulator: update(previous, feedback, volatility)
    RegimeModulator->>RegimeModulator: Apply exponential decay
    RegimeModulator->>RegimeModulator: Clip valence to bounds
    RegimeModulator->>RegimeModulator: Compute confidence (1 - volatility)
    RegimeModulator->>RegimeModulator: Classify regime label
    RegimeModulator-->>RegimeService: Updated RegimeState
    
    RegimeService->>Repository: store_regime()
    Repository->>DB: INSERT INTO cortex_market_regimes
    DB-->>Repository: Success
    Repository-->>RegimeService: Success
    RegimeService->>Metrics: Record DB latency
    
    RegimeService->>Cache: set(updated_state)
    RegimeService->>Metrics: Increment regime_updates_total
    
    alt Regime Changed
        RegimeService->>Metrics: Increment regime_transition_total
    end
    
    RegimeService-->>API: Updated RegimeState
    API->>Metrics: Record latency
    API->>Metrics: Decrement inflight
    API-->>Client: RegimeResponse
```

## Error Handling Flow

```mermaid
sequenceDiagram
    participant Client
    participant Middleware
    participant API
    participant Service
    participant ExceptionHandler
    participant Metrics
    
    Client->>Middleware: Request
    Middleware->>API: Forward with Request ID
    API->>Service: Operation
    Service->>Service: Validation fails
    Service-->>API: raise ValidationError
    
    API->>ExceptionHandler: Handle CortexError
    ExceptionHandler->>Metrics: Increment error_count{code}
    ExceptionHandler->>ExceptionHandler: Create ErrorResponse
    ExceptionHandler-->>Middleware: Response(400, JSON)
    Middleware->>Middleware: Add X-Request-ID
    Middleware-->>Client: Error with Request ID
```

## Data Flow - Memory Operations

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant Repository
    participant DB
    
    Note over Client,DB: Store Exposures
    Client->>API: POST /memory (exposures)
    API->>Repository: store_exposures()
    
    alt PostgreSQL
        Repository->>DB: INSERT ... ON CONFLICT DO UPDATE
    else SQLite/Other
        loop For each exposure
            Repository->>DB: SELECT (check existence)
            alt Exists
                Repository->>DB: UPDATE
            else New
                Repository->>DB: INSERT
            end
        end
    end
    
    DB-->>Repository: Success
    Repository-->>API: Success
    API-->>Client: 202 Accepted
    
    Note over Client,DB: Retrieve Exposures
    Client->>API: GET /memory/{portfolio_id}
    API->>Repository: fetch_exposures(portfolio_id)
    Repository->>DB: SELECT ... WHERE portfolio_id = ? ORDER BY as_of DESC LIMIT 50
    DB-->>Repository: List[PortfolioExposure]
    
    alt Exposures Found
        Repository-->>API: exposures
        API-->>Client: 200 OK + MemoryResponse
    else Not Found
        Repository-->>API: []
        API-->>API: raise NotFoundError
        API-->>Client: 404 + ErrorResponse
    end
```

## Middleware Pipeline

```mermaid
graph LR
    Request --> ReqID[Request ID Middleware]
    ReqID --> Endpoint[API Endpoint]
    Endpoint --> Service[Service Layer]
    Service --> Response
    Response --> ReqID2[Add Request ID Header]
    ReqID2 --> Log[Log Request Completion]
    Log --> Client
    
    style ReqID fill:#e1f5ff
    style ReqID2 fill:#e1f5ff
    style Log fill:#fff4e1
```

## Retry & Transaction Decorators

### Retry with Exponential Backoff

```mermaid
graph TD
    Start[Function Call] --> Try[Attempt Operation]
    Try --> Check{Success?}
    Check -->|Yes| Return[Return Result]
    Check -->|No DB Error| Count{Attempts < Max?}
    Check -->|Other Error| Raise[Raise Immediately]
    Count -->|Yes| Wait[Wait with Backoff]
    Wait --> Try
    Count -->|No| RaiseDB[Raise DatabaseError]
    
    style Start fill:#e1f5ff
    style Return fill:#e1ffe1
    style Raise fill:#ffe1e1
    style RaiseDB fill:#ffe1e1
```

### Transactional Decorator

```mermaid
graph TD
    Start[Function Call] --> Extract[Extract Session]
    Extract --> Try[Execute Function]
    Try --> Success{Success?}
    Success -->|Yes| Commit[Commit Transaction]
    Commit --> Return[Return Result]
    Success -->|SQLAlchemy Error| Rollback[Rollback]
    Success -->|Other Error| Rollback2[Rollback]
    Rollback --> RaiseDB[Raise DatabaseError]
    Rollback2 --> RaiseOther[Raise Original Error]
    
    style Start fill:#e1f5ff
    style Commit fill:#e1ffe1
    style Return fill:#e1ffe1
    style Rollback fill:#ffe1e1
    style Rollback2 fill:#ffe1e1
```

## Configuration Loading

```mermaid
graph TD
    Start[Application Start] --> LoadYAML[Load service.yaml]
    LoadYAML --> ApplyEnv[Apply Environment Overrides]
    ApplyEnv --> ValidateTLS{TLS Config?}
    ValidateTLS -->|Yes| CheckFiles[Validate Certificate Files]
    ValidateTLS -->|No| ValidateRisk
    CheckFiles --> ValidateCiphers[Validate Cipher Suites]
    ValidateCiphers --> WarnDeprecated{Deprecated TLS?}
    WarnDeprecated -->|Yes| LogWarn[Log Warning]
    WarnDeprecated -->|No| ValidateRisk
    LogWarn --> ValidateRisk[Validate Risk Settings]
    ValidateRisk --> CheckUnique{Stress Scenarios Unique?}
    CheckUnique -->|No| RaiseError[Raise ConfigurationError]
    CheckUnique -->|Yes| CheckPositive{All Positive?}
    CheckPositive -->|No| RaiseError
    CheckPositive -->|Yes| CheckConfidence{Valid Confidence?}
    CheckConfidence -->|No| RaiseError
    CheckConfidence -->|Yes| CreateSettings[Create CortexSettings]
    CreateSettings --> Return[Return Settings]
    
    style Start fill:#e1f5ff
    style Return fill:#e1ffe1
    style RaiseError fill:#ffe1e1
```

## Testing Strategy

### Test Pyramid

```
                    /\
                   /  \
                  / E2E \ (6 tests - API integration)
                 /______\
                /        \
               /Integration\ (28 tests - services + repo)
              /____________\
             /              \
            /   Unit Tests   \ (9 tests - decorators, core)
           /                  \
          /____________________\
         /                      \
        /   Property-Based Tests \ (7 tests - Hypothesis)
       /__________________________\
```

### Test Coverage by Layer

- **API Layer** (91.50%): Endpoint testing, error handlers, middleware
- **Service Layer** (92-95%): Business logic, caching, metrics
- **Domain Layer** (90-100%): Signals, risk, regime algorithms
- **Persistence Layer** (87.80%): Repository operations, bulk upsert
- **Infrastructure** (96-100%): Decorators, middleware, metrics

## Deployment Architecture

```mermaid
graph TB
    LB[Load Balancer] --> C1[Cortex Instance 1]
    LB --> C2[Cortex Instance 2]
    LB --> C3[Cortex Instance 3]
    
    C1 --> PG[(PostgreSQL Primary)]
    C2 --> PG
    C3 --> PG
    
    PG --> Replica1[(Read Replica 1)]
    PG --> Replica2[(Read Replica 2)]
    
    C1 --> Prom[Prometheus]
    C2 --> Prom
    C3 --> Prom
    
    Prom --> Graf[Grafana]
    
    style LB fill:#e1f5ff
    style C1 fill:#fff4e1
    style C2 fill:#fff4e1
    style C3 fill:#fff4e1
    style PG fill:#e1ffe1
```

## Key Design Patterns

1. **Repository Pattern**: Abstracts data access, enables testing with in-memory DB
2. **Service Layer Pattern**: Business logic separate from HTTP concerns
3. **Decorator Pattern**: Cross-cutting concerns (retry, transactions) as decorators
4. **Middleware Pattern**: Request ID propagation and logging
5. **Frozen Dataclasses**: Immutable domain models prevent bugs
6. **Global Exception Handlers**: Unified error responses
7. **TTL Caching**: Performance optimization for frequently accessed data
8. **Metrics at Boundaries**: Observability without business logic pollution

## Performance Considerations

- **Signal Computation**: O(n) complexity where n = number of features
- **Risk Assessment**: O(m) where m = number of exposures
- **Regime Caching**: 5-second TTL reduces DB load for high-frequency updates
- **Bulk Upsert**: PostgreSQL-specific optimization with ON CONFLICT
- **Connection Pooling**: Configurable pool size for database connections
- **Retry with Backoff**: Exponential backoff prevents thundering herd

## Security Measures

1. **Input Validation**: Pydantic models with length limits
2. **TLS Configuration Validation**: Cipher suite checks, deprecation warnings
3. **SQL Injection Prevention**: SQLAlchemy ORM, parameterized queries
4. **Error Information Leakage**: Generic error messages, detailed logs server-side
5. **Request ID Tracking**: Enables security audit trails
6. **Rate Limiting Ready**: Middleware placeholder for future rate limiting

## Observability

- **Structured Logging**: JSON format with request IDs
- **Prometheus Metrics**: 9 metric families covering all operations
- **Request Tracing**: X-Request-ID propagates through entire request lifecycle
- **Health Checks**: Separate /health and /ready endpoints
- **Error Tracking**: Errors counted by code for alert rules

## Future Enhancements

1. **OpenTelemetry**: Distributed tracing integration
2. **Rate Limiting**: Token bucket or sliding window implementation
3. **Caching Layer**: Redis for distributed caching
4. **Event Sourcing**: Store regime transitions as events
5. **GraphQL API**: Alternative to REST for complex queries
6. **WebSocket Support**: Real-time signal streaming
