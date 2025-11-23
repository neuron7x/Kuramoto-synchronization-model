# Domain Module

## Overview

The `domain` module contains the core business domain models and entities for the TradePulse trading platform. It implements Domain-Driven Design (DDD) principles with rich domain models, value objects, and business logic encapsulation.

## Purpose

This module provides:

- **Domain Entities**: Core business objects (Orders, Positions, Signals, Portfolio)
- **Value Objects**: Immutable domain values with validation
- **Business Logic**: Domain-specific rules and constraints
- **Type Safety**: Strongly typed domain models with Pydantic validation
- **Ubiquitous Language**: Shared vocabulary between domain experts and developers

## Key Features

- 🏗️ **Clean Architecture**: Separation of domain logic from infrastructure
- 🔒 **Immutability**: Value objects prevent accidental state mutations
- ✅ **Validation**: Automatic validation of domain invariants
- 📝 **Type Safety**: Full type annotations with runtime checking
- 🎯 **Rich Models**: Business logic lives in domain entities, not services
- 🔄 **Event Sourcing Ready**: Entities emit domain events for changes

## Module Structure

```
domain/
├── __init__.py                # Public API exports
├── order.py                   # Order entity
├── orders/
│   ├── entity.py             # Order domain entity
│   ├── value_objects.py      # Order-related value objects
│   └── __init__.py
├── position.py               # Position entity
├── positions/
│   ├── entity.py             # Position domain entity
│   └── __init__.py
├── signal.py                 # Trading signal entity
├── signals/
│   ├── entity.py             # Signal domain entity
│   ├── value_objects.py      # Signal-related value objects
│   └── __init__.py
└── portfolio/
    ├── accounting.py         # Portfolio accounting logic
    └── __init__.py
```

## Technology Stack

- **Python**: 3.11+ with full type annotations
- **Pydantic**: Data validation and settings management
- **Dataclasses**: Lightweight entity definitions
- **Decimal**: Precise financial calculations

## Installation

```bash
# Base installation (domain is always included)
pip install -e .
```

## Usage Examples

### Working with Orders

```python
from domain import Order, OrderSide, OrderType, OrderStatus
from decimal import Decimal

# Create a market order
order = Order(
    order_id="ORD-12345",
    symbol="BTC/USDT",
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    quantity=Decimal("0.5"),
    timestamp="2025-01-15T10:30:00Z"
)

print(f"Order: {order.order_id}")
print(f"Symbol: {order.symbol}")
print(f"Side: {order.side}")
print(f"Quantity: {order.quantity}")

# Create a limit order
limit_order = Order(
    order_id="ORD-12346",
    symbol="ETH/USDT",
    side=OrderSide.SELL,
    order_type=OrderType.LIMIT,
    quantity=Decimal("10.0"),
    limit_price=Decimal("3000.00"),
    time_in_force="GTC",
    timestamp="2025-01-15T10:31:00Z"
)

# Order lifecycle
order.submit()
print(f"Status: {order.status}")  # OrderStatus.SUBMITTED

order.accept()
print(f"Status: {order.status}")  # OrderStatus.ACCEPTED

order.fill(
    fill_price=Decimal("50000.00"),
    fill_quantity=Decimal("0.5"),
    fill_timestamp="2025-01-15T10:30:05Z"
)
print(f"Status: {order.status}")  # OrderStatus.FILLED
print(f"Average Fill Price: {order.average_fill_price}")
```

### Working with Positions

```python
from domain import Position, PositionSide
from decimal import Decimal

# Create a long position
position = Position(
    position_id="POS-789",
    symbol="BTC/USDT",
    side=PositionSide.LONG,
    quantity=Decimal("0.5"),
    entry_price=Decimal("50000.00"),
    timestamp="2025-01-15T10:30:00Z"
)

# Calculate P&L
current_price = Decimal("51000.00")
pnl = position.calculate_pnl(current_price)
pnl_pct = position.calculate_pnl_percent(current_price)

print(f"Position: {position.symbol}")
print(f"Side: {position.side}")
print(f"Entry Price: ${position.entry_price}")
print(f"Current Price: ${current_price}")
print(f"P&L: ${pnl:.2f}")
print(f"P&L %: {pnl_pct:.2f}%")

# Update position
position.update_quantity(Decimal("0.7"))  # Add to position
position.update_avg_entry_price(Decimal("50500.00"))

# Close position
position.close(
    exit_price=Decimal("51500.00"),
    exit_timestamp="2025-01-15T15:00:00Z"
)
print(f"Position closed. Realized P&L: ${position.realized_pnl:.2f}")
```

### Working with Trading Signals

```python
from domain import Signal, SignalDirection, SignalStrength
from decimal import Decimal

# Create a trading signal
signal = Signal(
    signal_id="SIG-456",
    symbol="AAPL",
    direction=SignalDirection.LONG,
    strength=SignalStrength.HIGH,
    confidence=Decimal("0.85"),
    timestamp="2025-01-15T10:30:00Z",
    source="momentum_strategy",
    metadata={
        "indicator": "kuramoto",
        "sync_score": 0.92,
        "regime": "trending"
    }
)

# Check signal validity
if signal.is_valid():
    print(f"Valid Signal: {signal.direction} {signal.symbol}")
    print(f"Strength: {signal.strength}")
    print(f"Confidence: {signal.confidence:.2%}")
    
# Signals expire after a certain time
if not signal.is_expired(max_age_seconds=300):
    # Signal is still fresh, act on it
    print("Signal is fresh, proceeding with trade")
else:
    print("Signal expired, ignoring")
```

### Portfolio Accounting

```python
from domain.portfolio import Portfolio, PortfolioSnapshot
from decimal import Decimal

# Create portfolio
portfolio = Portfolio(
    portfolio_id="PORT-001",
    initial_capital=Decimal("100000.00"),
    currency="USD"
)

# Add positions
portfolio.add_position(position1)
portfolio.add_position(position2)

# Calculate portfolio metrics
total_value = portfolio.calculate_total_value(current_prices)
total_pnl = portfolio.calculate_total_pnl(current_prices)
exposure = portfolio.calculate_exposure()

print(f"Portfolio Value: ${total_value:,.2f}")
print(f"Total P&L: ${total_pnl:,.2f}")
print(f"Exposure: ${exposure:,.2f}")

# Portfolio allocation
allocation = portfolio.get_allocation()
for symbol, pct in allocation.items():
    print(f"  {symbol}: {pct:.2%}")

# Risk metrics
leverage = portfolio.calculate_leverage()
concentration = portfolio.calculate_concentration()

print(f"Leverage: {leverage:.2f}x")
print(f"Max Concentration: {concentration.max_position:.2%}")

# Create snapshot for audit/analysis
snapshot = PortfolioSnapshot.from_portfolio(
    portfolio=portfolio,
    prices=current_prices,
    timestamp="2025-01-15T16:00:00Z"
)
```

### Value Objects

```python
from domain.orders.value_objects import OrderId, Price, Quantity
from domain.signals.value_objects import Confidence, SignalMetadata
from decimal import Decimal

# Strongly typed value objects prevent invalid states
order_id = OrderId("ORD-12345")
price = Price(Decimal("50000.00"))
quantity = Quantity(Decimal("0.5"))

# Value objects enforce constraints
try:
    invalid_price = Price(Decimal("-100.00"))  # Raises ValueError
except ValueError as e:
    print(f"Invalid price: {e}")

try:
    invalid_quantity = Quantity(Decimal("0"))  # Raises ValueError
except ValueError as e:
    print(f"Invalid quantity: {e}")

# Confidence value object ensures [0, 1] range
confidence = Confidence(Decimal("0.85"))
print(f"Confidence: {confidence.value:.2%}")

# Value objects are immutable
try:
    confidence.value = Decimal("0.95")  # Raises FrozenInstanceError
except Exception as e:
    print(f"Cannot modify: {e}")
```

## Domain Entities

### Order Entity

Represents a trading order with full lifecycle management:

**States**: `PENDING` → `SUBMITTED` → `ACCEPTED` → `PARTIALLY_FILLED` → `FILLED`
           
**Side effects**: Can also transition to `REJECTED`, `CANCELLED`, or `EXPIRED`

**Key Methods**:
- `submit()`: Submit order to exchange
- `accept()`: Mark as accepted by exchange
- `fill()`: Record order fill
- `cancel()`: Cancel pending order
- `calculate_filled_value()`: Total value of fills

### Position Entity

Represents an open trading position:

**Key Properties**:
- Entry price and quantity
- Current P&L (unrealized)
- Realized P&L on close
- Position side (long/short)

**Key Methods**:
- `calculate_pnl(current_price)`: Unrealized P&L
- `calculate_pnl_percent(current_price)`: P&L percentage
- `update_quantity()`: Add to or reduce position
- `close()`: Close position and realize P&L

### Signal Entity

Represents a trading signal from a strategy:

**Key Properties**:
- Direction (long/short/neutral)
- Strength (high/medium/low)
- Confidence score
- Source strategy
- Metadata

**Key Methods**:
- `is_valid()`: Check signal validity
- `is_expired(max_age_seconds)`: Check if signal is stale
- `to_order()`: Convert signal to order

### Portfolio Entity

Represents a collection of positions:

**Key Methods**:
- `add_position()`: Add new position
- `remove_position()`: Remove position
- `calculate_total_value()`: Current portfolio value
- `calculate_total_pnl()`: Total P&L across positions
- `calculate_leverage()`: Portfolio leverage
- `get_allocation()`: Asset allocation breakdown

## Domain Events

Entities emit domain events on state changes:

```python
from domain import OrderFilledEvent, PositionClosedEvent

# Domain events are emitted automatically
order.fill(...)  # Emits OrderFilledEvent

# Subscribe to domain events
@event_bus.subscribe(OrderFilledEvent)
def on_order_filled(event: OrderFilledEvent):
    print(f"Order {event.order_id} filled at {event.fill_price}")
    # Update positions, notify risk system, etc.
```

## Validation Rules

Domain models enforce business rules:

### Order Validation
- Quantity must be positive
- Limit price required for limit orders
- Stop price required for stop orders
- Valid symbol format
- Supported order types and time-in-force

### Position Validation
- Quantity must be positive
- Entry price must be positive
- Valid position side (long/short)

### Signal Validation
- Confidence must be in [0, 1]
- Valid direction (long/short/neutral)
- Valid strength level
- Non-empty symbol

### Portfolio Validation
- Initial capital must be positive
- Position quantities must sum correctly
- No duplicate position IDs

## Best Practices

1. **Always Use Value Objects**: Wrap primitives in value objects for type safety
2. **Keep Logic in Domain**: Business rules belong in entities, not services
3. **Immutability**: Use frozen dataclasses for value objects
4. **Use Decimal for Money**: Never use float for prices or quantities
5. **Validate Early**: Enforce invariants in constructors
6. **Emit Events**: Publish domain events for all state changes
7. **Test Domain Logic**: Unit test entities independent of infrastructure

## Testing

```bash
# Run domain tests
pytest tests/unit/domain -v

# Test with coverage
pytest tests/unit/domain --cov=domain --cov-report=html

# Test value objects
pytest tests/unit/domain/test_value_objects.py -v

# Test entities
pytest tests/unit/domain/test_entities.py -v
```

## Architecture Principles

### Domain-Driven Design (DDD)

```
┌────────────────────────────────────────────────────┐
│              Application Layer                     │
│  (Use Cases, Application Services)                 │
├────────────────────────────────────────────────────┤
│              Domain Layer                          │
│  ├─ Entities  ├─ Value Objects  ├─ Services       │
│  ├─ Repositories (Interfaces)                      │
│  └─ Domain Events                                  │
├────────────────────────────────────────────────────┤
│              Infrastructure Layer                  │
│  (Database, External APIs, Frameworks)             │
└────────────────────────────────────────────────────┘
```

### Key Principles

- **Ubiquitous Language**: Domain terms used consistently across code and docs
- **Bounded Contexts**: Clear boundaries between domain concepts
- **Aggregates**: Order, Position, Signal are aggregate roots
- **Value Objects**: Immutable types for domain concepts
- **Domain Events**: Communicate state changes
- **Rich Domain Models**: Logic in entities, not anemic data structures

## Type Safety

All domain models use:
- Type hints on all methods and attributes
- Runtime validation with Pydantic
- Immutable value objects (frozen dataclasses)
- Decimal for financial values

```python
# Example: Fully typed order creation
def create_order(
    symbol: str,
    side: OrderSide,
    quantity: Decimal,
    order_type: OrderType
) -> Order:
    return Order(
        order_id=generate_order_id(),
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        timestamp=now()
    )
```

## Related Modules

- [`execution`](../execution/README.md): Uses domain entities for order management
- [`core`](../core/README.md): Strategies generate domain signals
- [`analytics`](../analytics/README.md): Analyzes domain entities (positions, orders)
- [`backtest`](../backtest/README.md): Simulates domain entities

## Documentation

- [API Reference](https://docs.tradepulse.io/api/domain)
- [Domain Models Guide](https://docs.tradepulse.io/guides/domain-models)
- [DDD Principles](https://docs.tradepulse.io/architecture/ddd)

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines.

## License

See [LICENSE](../LICENSE) for licensing information.

## Support

- [GitHub Issues](https://github.com/neuron7x/TradePulse/issues)
- [Documentation](https://docs.tradepulse.io)
- [Community](https://github.com/neuron7x/TradePulse/discussions)
