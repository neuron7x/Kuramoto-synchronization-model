# CLI Module

## Overview

The `cli` module provides command-line interfaces for interacting with TradePulse. It offers commands for running backtests, managing data, executing trades, and monitoring system health.

## Purpose

This module delivers:

- **Trading Operations**: Execute and monitor live trades
- **Backtesting**: Run strategy backtests from command line
- **Data Management**: Import, export, and manage market data
- **System Administration**: Health checks, migrations, and maintenance
- **Development**: Tools for development and debugging

## Key Features

- 🖥️ **Interactive Commands**: Rich CLI with autocomplete and validation
- 📊 **Progress Tracking**: Real-time progress bars and status updates
- 🎨 **Formatted Output**: Colored, tabular output for readability
- 🔧 **Scriptable**: Suitable for automation and CI/CD
- 📝 **Comprehensive Help**: Detailed help for all commands

## Technology Stack

- **Click**: Command-line interface framework
- **Rich**: Beautiful terminal formatting
- **Typer**: Type-hint based CLI (alternative)

## Installation

```bash
# CLI is included in base installation
pip install -e .
```

## Usage Examples

### Backtesting

```bash
# Run backtest for a strategy
tradepulse backtest \
    --strategy momentum \
    --start-date 2023-01-01 \
    --end-date 2023-12-31 \
    --initial-capital 100000

# Run with custom config
tradepulse backtest \
    --config configs/backtest/momentum.yaml \
    --output reports/backtest_results.json
```

### Data Management

```bash
# Sync market data
tradepulse-sync \
    --symbols BTC/USDT ETH/USDT \
    --exchange binance \
    --start-date 2023-01-01

# Export data to CSV
tradepulse data export \
    --symbol BTC/USDT \
    --timeframe 1h \
    --output data/btc_usdt_1h.csv
```

### Database Operations

```bash
# Run database migrations
tradepulse-db upgrade

# Create new migration
tradepulse-db revision --message "Add new table"

# Rollback migration
tradepulse-db downgrade -1
```

### Live Trading

```bash
# Start live trading
tradepulse trade start \
    --strategy neuro_trade_pulse \
    --exchange binance \
    --mode live

# Paper trading mode
tradepulse trade start \
    --strategy momentum \
    --mode paper \
    --initial-capital 100000
```

### System Health

```bash
# Check system health
tradepulse health check

# View system metrics
tradepulse metrics show

# Test connectivity
tradepulse connectivity test
```

## Available Commands

### Main Commands

- `tradepulse backtest`: Run strategy backtests
- `tradepulse trade`: Live and paper trading operations
- `tradepulse data`: Data management commands
- `tradepulse health`: System health checks
- `tradepulse metrics`: View system metrics
- `tradepulse-sync`: Sync market data from exchanges
- `tradepulse-db`: Database migration operations

### Options

Common options across commands:
- `--config PATH`: Path to configuration file
- `--verbose`: Enable verbose output
- `--quiet`: Suppress non-essential output
- `--output PATH`: Output file path
- `--format [json|csv|yaml]`: Output format

## Configuration

CLI commands can be configured via:

1. **Command-line arguments** (highest priority)
2. **Environment variables**
3. **Configuration files** (lowest priority)

Example configuration file:

```yaml
# config/cli.yaml
cli:
  default_exchange: binance
  default_timeframe: 1h
  output_format: json
  verbose: false
```

## Related Modules

- [`scripts`](../scripts/README.md): Automation scripts
- [`core`](../core/README.md): Core functionality
- [`execution`](../execution/README.md): Trade execution
- [`backtest`](../backtest/README.md): Backtesting engine

## Documentation

- [CLI Reference](https://docs.tradepulse.io/cli)
- [Configuration Guide](https://docs.tradepulse.io/configuration)

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines.

## License

See [LICENSE](../LICENSE) for licensing information.
