# TradePulse Main Package

## Overview

The `tradepulse` package is the main entry point for the TradePulse platform. It provides high-level interfaces and integrations of all core modules.

## Purpose

- **Unified API**: Single import point for all TradePulse functionality
- **Configuration**: Centralized configuration management
- **Initialization**: Platform startup and dependency injection
- **Public Interfaces**: Clean, user-friendly API surface

## Usage

```python
import tradepulse

# Initialize platform
platform = tradepulse.init(config_path="config/production.yaml")

# Access modules
strategy = platform.get_strategy("neuro_trade_pulse")
backtest_engine = platform.get_backtest_engine()
execution_engine = platform.get_execution_engine()

# Run operations
results = await backtest_engine.run(strategy, data)
```

## Configuration

Configuration is managed through YAML files and environment variables.

```yaml
# config/tradepulse.yaml
tradepulse:
  environment: production
  log_level: INFO
  
  modules:
    core: enabled
    execution: enabled
    analytics: enabled
```

## Related Modules

- [`core`](../core/README.md): Core infrastructure
- [`execution`](../execution/README.md): Order execution
- [`backtest`](../backtest/README.md): Backtesting
- [`strategies`](../strategies/README.md): Trading strategies

## Documentation

- [Getting Started](https://docs.tradepulse.io/getting-started)
- [API Reference](https://docs.tradepulse.io/api)

## License

See [LICENSE](../LICENSE) for licensing information.
