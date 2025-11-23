# Core Module

## Overview

The `core` module provides the fundamental building blocks and infrastructure for the TradePulse algorithmic trading platform. It contains essential components for data processing, event handling, indicator calculation, strategy execution, and system orchestration.

## Purpose

This module serves as the backbone of TradePulse, offering:

- **Trading Infrastructure**: Core engine components for order execution and portfolio management
- **Market Indicators**: Advanced geometric and technical indicators (Kuramoto oscillators, Ricci Flow, etc.)
- **Data Pipeline**: Data ingestion, validation, and quality control mechanisms
- **Event System**: Event sourcing and domain event infrastructure for reactive architecture
- **Neural Components**: Machine learning infrastructure for predictive models
- **Strategy Framework**: Base contracts and implementations for trading strategies

## Key Features

- ✨ **Geometric Market Indicators**: Unique indicators based on differential geometry and physics
- 🔄 **Event-Driven Architecture**: Robust event sourcing with domain events
- 📊 **Data Quality Controls**: Comprehensive validation and sanitization pipelines
- 🧠 **Neural Network Integration**: Built-in ML components with training infrastructure
- ⚡ **High-Performance Processing**: Optimized data transformations using NumPy and Numba
- 🎯 **Strategy Abstractions**: Clean interfaces for implementing custom trading strategies
- 📈 **Phase Detection**: Advanced market regime and phase identification
- 🔧 **Configuration Management**: Flexible configuration using Hydra and OmegaConf

## Module Structure

```
core/
├── __init__.py                 # Module initialization and public API
├── accelerators/               # Performance acceleration utilities
├── agent/                      # Trading agent implementations
├── altdata/                    # Alternative data sources integration
├── architecture_integrator/    # System architecture coordination
├── compliance/                 # Compliance and regulatory checks
├── config/                     # Configuration schemas and loaders
├── data/                       # Data ingestion and processing
├── energy.py                   # Thermodynamic energy calculations
├── engine/                     # Core trading engine
├── events/                     # Event sourcing infrastructure
├── experiments/                # Experimentation framework
├── features/                   # Feature engineering tools
├── idempotency/               # Idempotency guarantees for operations
├── indicators/                 # Market indicators library
├── maintenance/                # System maintenance utilities
├── messaging/                  # Message queue and bus abstractions
├── metrics/                    # Metrics collection and reporting
├── ml/                        # Machine learning components
├── neuro/                     # Neural network infrastructure
├── orchestrator/              # System orchestration layer
├── phase/                     # Market phase detection
├── pipelines/                 # Data processing pipelines
├── reporting/                 # Report generation
├── security/                  # Security and authentication
├── strategies/                # Base strategy implementations
├── tracing/                   # Distributed tracing support
└── utils/                     # Common utilities and helpers
```

## Technology Stack

- **Python**: 3.11+ (type hints throughout)
- **NumPy**: Numerical computing and array operations
- **Pandas**: Time series data manipulation
- **Numba**: JIT compilation for performance-critical code
- **SciPy**: Scientific computing and optimization
- **NetworkX**: Graph-based algorithms
- **Hydra**: Configuration management
- **SQLAlchemy**: Database ORM
- **OpenTelemetry**: Observability and tracing

## Installation

The core module is included as part of the main TradePulse installation:

```bash
# Install base TradePulse with core dependencies
pip install -e .

# Install with development tools
pip install -e ".[dev]"

# Install with neural network enhancements
pip install -e ".[neuro_advanced]"
```

## Usage Examples

### Using Core Indicators

```python
from core.indicators import KuramotoIndicator, RicciFlowIndicator

# Initialize Kuramoto oscillator for market synchronization
kuramoto = KuramotoIndicator(n_oscillators=10, coupling_strength=0.5)
sync_score = kuramoto.compute(price_data)

# Apply Ricci Flow for geometric market curvature
ricci = RicciFlowIndicator(time_steps=100)
curvature = ricci.compute(market_graph)
```

### Event System

```python
from core.events import EventBus, OrderFilledEvent

# Set up event bus
bus = EventBus()

# Subscribe to events
@bus.subscribe(OrderFilledEvent)
def handle_order_filled(event: OrderFilledEvent):
    print(f"Order {event.order_id} filled at {event.price}")

# Publish events
bus.publish(OrderFilledEvent(order_id="123", price=100.50, quantity=10))
```

### Data Pipeline

```python
from core.data import DataValidator, DataQualityControl

# Validate incoming market data
validator = DataValidator()
clean_data = validator.validate_and_sanitize(raw_market_data)

# Apply quality controls
qc = DataQualityControl(
    max_price_deviation=0.05,
    min_volume_threshold=1000
)
quality_data = qc.filter(clean_data)
```

## Running Tests

```bash
# Run all core module tests
pytest tests/unit/core -v

# Run with coverage
pytest tests/unit/core --cov=core --cov-report=html

# Run specific indicator tests
pytest tests/unit/core/test_indicators.py -v
```

## Configuration

Core components can be configured via YAML files or environment variables:

```yaml
# config/core.yaml
core:
  engine:
    max_orders_per_second: 100
    order_timeout: 30
  
  indicators:
    kuramoto:
      coupling_strength: 0.5
      n_oscillators: 10
    
  data:
    validation:
      strict_mode: true
      max_nan_ratio: 0.01
```

Override with environment variables:
```bash
export CORE__ENGINE__MAX_ORDERS_PER_SECOND=200
export CORE__INDICATORS__KURAMOTO__COUPLING_STRENGTH=0.75
```

## Architecture

The core module follows a layered architecture:

1. **Infrastructure Layer**: Low-level utilities, messaging, and storage
2. **Domain Layer**: Business logic, indicators, and strategies
3. **Application Layer**: Orchestration, pipelines, and workflows
4. **API Layer**: Public interfaces and entry points

### Key Design Patterns

- **Event Sourcing**: All state changes captured as immutable events
- **Repository Pattern**: Clean separation of data access logic
- **Strategy Pattern**: Pluggable trading strategy implementations
- **Observer Pattern**: Event-driven reactive components
- **Factory Pattern**: Dynamic object creation for indicators and strategies

## Performance Considerations

- **Vectorization**: NumPy operations for batch processing
- **JIT Compilation**: Numba decorators on hot paths
- **Caching**: LRU caching for expensive computations
- **Lazy Loading**: Deferred initialization of heavy components
- **Connection Pooling**: Efficient database connection management

## Security

- Input validation on all external data
- Sanitization of user-provided parameters
- Rate limiting on API endpoints
- Authentication via JWT tokens
- Audit logging of sensitive operations

## Related Modules

- [`analytics`](../analytics/README.md): Analytics and portfolio attribution
- [`execution`](../execution/README.md): Order execution and management
- [`backtest`](../backtest/README.md): Backtesting framework
- [`strategies`](../strategies/README.md): Trading strategy implementations
- [`observability`](../observability/README.md): Metrics and monitoring

## Documentation

- [API Reference](https://docs.tradepulse.io/api/core)
- [Indicator Guide](https://docs.tradepulse.io/guides/indicators)
- [Event System Guide](https://docs.tradepulse.io/guides/events)
- [Configuration Reference](https://docs.tradepulse.io/config/core)

## Contributing

See the main [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines on:
- Code style and formatting
- Testing requirements
- Documentation standards
- Pull request process

## License

See [LICENSE](../LICENSE) for details. This module is part of the TradePulse proprietary codebase.

## Support

- GitHub Issues: [Report bugs or request features](https://github.com/neuron7x/TradePulse/issues)
- Documentation: [Full documentation](https://docs.tradepulse.io)
- Community: [Join discussions](https://github.com/neuron7x/TradePulse/discussions)
