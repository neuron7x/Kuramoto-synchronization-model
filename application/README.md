# Application Module

## Overview

The `application` module implements the application layer following Clean Architecture principles. It contains use cases, application services, and orchestrates interactions between the domain and infrastructure layers.

## Purpose

This module provides:

- **Use Cases**: Application-specific business rules and workflows
- **Application Services**: Coordinate between domain entities and infrastructure
- **DTOs**: Data transfer objects for API boundaries
- **Command/Query Handlers**: CQRS pattern implementation
- **Orchestration**: Coordinate complex multi-step operations

## Key Features

- 🎯 **Use Case Driven**: Clear separation of application logic
- 🔄 **CQRS**: Command Query Responsibility Segregation
- 📦 **DTOs**: Type-safe data transfer objects
- 🎭 **Facades**: Simplified interfaces for complex subsystems
- 🔌 **Dependency Injection**: Loose coupling via DI
- 📝 **Transaction Management**: Atomic operations across domain

## Module Structure

```
application/
├── use_cases/              # Application use cases
│   ├── trading/           # Trading-related use cases
│   ├── portfolio/         # Portfolio management
│   └── analysis/          # Analytics use cases
├── services/              # Application services
├── dto/                   # Data transfer objects
├── commands/              # Command handlers (CQRS)
├── queries/               # Query handlers (CQRS)
└── facades/               # Simplified interfaces
```

## Technology Stack

- **Python**: 3.11+ with type annotations
- **Pydantic**: DTO validation
- **Dependency Injector**: DI container

## Usage Examples

### Use Cases

```python
from application.use_cases.trading import PlaceOrderUseCase
from application.dto import PlaceOrderRequest

# Inject dependencies
use_case = PlaceOrderUseCase(
    order_repository=order_repo,
    execution_service=execution_svc,
    risk_service=risk_svc
)

# Execute use case
request = PlaceOrderRequest(
    symbol="BTC/USDT",
    side="buy",
    quantity=0.5,
    order_type="market"
)

result = await use_case.execute(request)
if result.success:
    print(f"Order placed: {result.order_id}")
else:
    print(f"Error: {result.error}")
```

### CQRS Commands

```python
from application.commands import CreatePortfolioCommand
from application.command_handlers import CreatePortfolioHandler

command = CreatePortfolioCommand(
    name="Alpha Portfolio",
    initial_capital=100000,
    currency="USD"
)

handler = CreatePortfolioHandler(portfolio_repo)
result = await handler.handle(command)
```

### CQRS Queries

```python
from application.queries import GetPortfolioPerformanceQuery
from application.query_handlers import GetPortfolioPerformanceHandler

query = GetPortfolioPerformanceQuery(
    portfolio_id="PORT-001",
    start_date="2023-01-01",
    end_date="2023-12-31"
)

handler = GetPortfolioPerformanceHandler(portfolio_repo, analytics_svc)
performance = await handler.handle(query)
```

## Architecture

```
┌──────────────────────────────────────────────────┐
│           Presentation Layer (API/CLI)           │
├──────────────────────────────────────────────────┤
│           Application Layer                      │
│  ├─ Use Cases  ├─ Commands  ├─ Queries          │
├──────────────────────────────────────────────────┤
│           Domain Layer                           │
│  ├─ Entities  ├─ Value Objects  ├─ Services     │
├──────────────────────────────────────────────────┤
│           Infrastructure Layer                   │
│  ├─ Repositories  ├─ External APIs  ├─ DB       │
└──────────────────────────────────────────────────┘
```

## Related Modules

- [`domain`](../domain/README.md): Domain entities and logic
- [`core`](../core/README.md): Core infrastructure
- [`execution`](../execution/README.md): Trade execution

## Documentation

- [Clean Architecture](https://docs.tradepulse.io/architecture/clean)
- [Use Cases](https://docs.tradepulse.io/architecture/use-cases)

## License

See [LICENSE](../LICENSE) for licensing information.
