# Unified System Integration

## Overview

The Unified System Integrator provides a cohesive way to integrate all TradePulse components (modules, microservices, and core components) into a single, well-orchestrated system. It uses the `ArchitectureIntegrator` pattern to manage dependencies, lifecycle, and health monitoring across all components.

## Architecture

### Components Integrated

1. **Microservices**
   - Market Data Service - Data ingestion and management
   - Backtesting Service - Strategy simulation and testing
   - Execution Service - Order execution and management

2. **Modules**
   - Adaptive Risk Manager - Dynamic risk management with TACL integration
   - Market Regime Analyzer - Market condition detection and classification
   - Dynamic Position Sizer - Position sizing with Kelly criterion
   - Agent Coordinator - Multi-agent task coordination

3. **Core Components**
   - Neuro Controllers (optional) - Neural network-based control systems
   - Indicators - Geometric and technical market indicators
   - Strategies - Trading strategy implementations

## Key Features

- **Automatic Dependency Resolution**: Components are initialized in the correct order based on their dependencies
- **Lifecycle Management**: Unified initialization, startup, and shutdown across all components
- **Health Monitoring**: Real-time health checks for all system components
- **Architecture Validation**: Validates that all dependencies are satisfied and the system is correctly configured
- **Selective Component Enablement**: Enable only the components you need
- **Configuration Management**: Flexible configuration for all components

## Usage

### Basic Usage

```python
from application.unified_integrator import build_unified_system

# Build and start the unified system with default configuration
integrator = build_unified_system()
integrator.initialize()
integrator.start()

# Check system health
is_healthy = integrator.is_system_healthy()
print(f"System healthy: {is_healthy}")

# Get detailed health information
health_map = integrator.get_system_health()
for name, health in health_map.items():
    print(f"{name}: {health.message}")

# Stop the system
integrator.stop()
```

### Custom Configuration

```python
from application.unified_integrator import (
    UnifiedIntegratorConfig,
    build_unified_system,
)

# Configure which components to enable
config = UnifiedIntegratorConfig(
    enable_risk_manager=True,
    enable_regime_analyzer=True,
    enable_position_sizer=True,
    enable_agent_coordinator=False,  # Disable agent coordinator
    risk_manager_config={
        "max_portfolio_risk": 0.05,
        "default_stop_loss": 0.02,
    },
    regime_analyzer_config={
        "lookback_periods": [20, 50, 200],
        "volatility_window": 20,
    },
)

integrator = build_unified_system(integrator_config=config)
integrator.initialize()
integrator.start()
```

### Accessing Components

```python
# Access specific components
risk_manager = integrator.get_component("adaptive_risk_manager")
regime_analyzer = integrator.get_component("market_regime_analyzer")

# Access microservices
service_registry = integrator.service_registry
market_data = service_registry.market_data
backtesting = service_registry.backtesting
execution = service_registry.execution
```

### Dependency Graph

```python
# View component dependencies
graph = integrator.get_dependency_graph()
for component, deps in graph.items():
    if deps:
        print(f"{component} → {', '.join(deps)}")
    else:
        print(f"{component} (no dependencies)")
```

### Architecture Validation

```python
# Validate that all dependencies are satisfied
is_valid = integrator.validate_architecture()
if not is_valid:
    print("Architecture validation failed!")
```

## Configuration Options

### UnifiedIntegratorConfig

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable_risk_manager` | `bool` | `True` | Enable adaptive risk manager |
| `enable_regime_analyzer` | `bool` | `True` | Enable market regime analyzer |
| `enable_position_sizer` | `bool` | `True` | Enable dynamic position sizer |
| `enable_agent_coordinator` | `bool` | `True` | Enable agent coordinator |
| `enable_fractal_regulator` | `bool` | `False` | Enable fractal regulator |
| `risk_manager_config` | `dict` | `None` | Configuration for risk manager |
| `regime_analyzer_config` | `dict` | `None` | Configuration for regime analyzer |
| `position_sizer_config` | `dict` | `None` | Configuration for position sizer |
| `agent_coordinator_config` | `dict` | `None` | Configuration for agent coordinator |
| `fractal_regulator_config` | `dict` | `None` | Configuration for fractal regulator |

## Component Dependencies

The system automatically manages these dependencies:

```
market_data_service (no dependencies)
  ↓
  ├─→ adaptive_risk_manager
  ├─→ market_regime_analyzer
  └─→ execution_service

backtesting_service
  ← market_data_service

adaptive_risk_manager + market_regime_analyzer
  ↓
  └─→ dynamic_position_sizer

adaptive_risk_manager + market_regime_analyzer + dynamic_position_sizer
  ↓
  └─→ agent_coordinator
```

## Health Monitoring

The system provides comprehensive health monitoring:

```python
# Check overall system health
is_healthy = integrator.is_system_healthy()

# Get detailed health for each component
health_map = integrator.get_system_health()
for name, health in health_map.items():
    print(f"Component: {name}")
    print(f"  Status: {health.status.value}")
    print(f"  Healthy: {health.healthy}")
    print(f"  Message: {health.message}")
    if health.metrics:
        print(f"  Metrics: {health.metrics}")
```

### Health Status Values

- `UNINITIALIZED` - Component not yet initialized
- `INITIALIZED` - Component initialized but not started
- `RUNNING` - Component is running normally
- `STOPPED` - Component has been stopped
- `FAILED` - Component has failed
- `DEGRADED` - Component is running but with reduced functionality

## Examples

### Example 1: Minimal System

```python
# Only core services, no modules
config = UnifiedIntegratorConfig(
    enable_risk_manager=False,
    enable_regime_analyzer=False,
    enable_position_sizer=False,
    enable_agent_coordinator=False,
)
integrator = build_unified_system(integrator_config=config)
integrator.initialize()
integrator.start()
```

### Example 2: Risk Management Only

```python
# Core services + risk management
config = UnifiedIntegratorConfig(
    enable_risk_manager=True,
    enable_regime_analyzer=False,
    enable_position_sizer=False,
    enable_agent_coordinator=False,
    risk_manager_config={
        "max_portfolio_risk": 0.03,
        "max_position_risk": 0.01,
    },
)
integrator = build_unified_system(integrator_config=config)
integrator.initialize()
integrator.start()
```

### Example 3: Full Integration

```python
# All components enabled
integrator = build_unified_system()
integrator.initialize()
integrator.start()

# Simulate trading workflow
risk_manager = integrator.get_component("adaptive_risk_manager")
regime_analyzer = integrator.get_component("market_regime_analyzer")
position_sizer = integrator.get_component("dynamic_position_sizer")

# Components work together seamlessly
# - Regime analyzer detects market conditions
# - Risk manager adjusts limits based on conditions
# - Position sizer calculates optimal position sizes

integrator.stop()
```

## Testing

Run the integration tests:

```bash
pytest tests/application/test_unified_integrator.py -v
```

Run the demonstration:

```bash
python examples/module_integration_demo.py
```

## Best Practices

1. **Always validate architecture** before starting the system:
   ```python
   if not integrator.validate_architecture():
       raise RuntimeError("Architecture validation failed")
   ```

2. **Monitor system health** during operation:
   ```python
   while running:
       if not integrator.is_system_healthy():
           logger.error("System unhealthy, taking corrective action")
   ```

3. **Graceful shutdown**:
   ```python
   try:
       integrator.start()
       # ... run system ...
   finally:
       integrator.stop()
   ```

4. **Use selective component enablement** for testing and development:
   ```python
   # Enable only what you need for testing
   config = UnifiedIntegratorConfig(
       enable_risk_manager=True,
       enable_regime_analyzer=False,  # Skip for unit tests
       enable_position_sizer=False,
       enable_agent_coordinator=False,
   )
   ```

## Troubleshooting

### Component Not Starting

If a component fails to start, check its dependencies:
```python
graph = integrator.get_dependency_graph()
print(f"Dependencies for failing_component: {graph['failing_component']}")
```

### Health Check Failing

Get detailed health information:
```python
health = integrator.get_system_health()
for name, h in health.items():
    if not h.healthy:
        print(f"{name}: {h.message}")
        print(f"  Status: {h.status}")
```

### Architecture Validation Errors

Run validation and review issues:
```python
validation = integrator.integrator.validate_architecture()
if not validation.passed:
    for issue in validation.issues:
        print(f"[{issue.severity.value}] {issue.message}")
```

## See Also

- [Architecture Integrator Documentation](../architecture/architecture_integrator.md)
- [Module Documentation](../../modules/README.md)
- [Microservices Documentation](../microservices/README.md)
- [Examples](../../examples/)
