---
owner: integrations@geosync
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# GeoSync Interfaces

This directory contains the interface layer for GeoSync, providing entry points for users and systems to interact with the trading framework.

> 📚 **For comprehensive documentation with detailed examples, see the [User Interaction Guide](../docs/USER_INTERACTION_GUIDE.md).**

---

## Quick Start

```bash
# CLI Analysis
python -m interfaces.cli analyze --csv sample.csv --window 200

# CLI Backtest
python -m interfaces.cli backtest --csv sample.csv --fee 0.001

# Streamlit Dashboard
streamlit run interfaces/dashboard_streamlit.py

# Python API
python -c "from interfaces.cli import signal_from_indicators; import numpy as np; print(signal_from_indicators(np.random.randn(300) + 100)[-10:])"
```

---

## Overview

The interfaces module provides multiple ways to interact with GeoSync:

1. **Command-Line Interface (CLI)** - For scripting and automation
2. **Streamlit Dashboard** - For interactive analysis and visualization
3. **Web Application** - For production-grade UI (Next.js app in `/apps/web`)
4. **Programmatic API** - For direct Python integration

## Components

### 1. CLI (`cli.py`)

Command-line interface for running analyses, backtests, and live trading.

#### Commands

##### `geosync analyze`

Compute geometric and technical indicators from price data.

**Usage:**
```bash
geosync analyze --csv data.csv [OPTIONS]
```

**Options:**
- `--csv`: Path to CSV file (required)
- `--price-col`: Price column name (default: "price")
- `--window`: Analysis window size (default: 200)
- `--bins`: Entropy calculation bins (default: 30)
- `--delta`: Ricci curvature step size (default: 0.005)
- `--gpu`: Enable GPU acceleration
- `--config`: YAML configuration file path

**Output:**
JSON object with indicators:
```json
{
  "R": 0.85,
  "H": 3.2,
  "delta_H": -0.05,
  "kappa_mean": 0.34,
  "Hurst": 0.62,
  "phase": "trending",
  "metadata": {
    "window_size": 200,
    "data_points": 1000,
    "bins": 30,
    "delta": 0.005
  }
}
```

**Example:**
```bash
# Analyze price data with 100-period window
geosync analyze --csv prices.csv --window 100

# Use GPU acceleration
geosync analyze --csv prices.csv --gpu

# Specify custom price column
geosync analyze --csv data.csv --price-col close_price
```

##### `geosync backtest`

Run walk-forward backtesting with indicator-based signals.

**Usage:**
```bash
geosync backtest --csv data.csv [OPTIONS]
```

**Options:**
- `--csv`: Path to CSV file (required)
- `--price-col`: Price column name (default: "price")
- `--window`: Indicator lookback window (default: 200)
- `--fee`: Transaction fee fraction (default: 0.0005)
- `--gpu`: Enable GPU acceleration
- `--config`: YAML configuration file path

**Output:**
```json
{
  "pnl": 5234.56,
  "max_dd": -1234.50,
  "trades": 42,
  "sharpe_ratio": 1.85,
  "metadata": {
    "window_size": 200,
    "fee": 0.0005,
    "data_points": 1000
  }
}
```

**Example:**
```bash
# Backtest with 0.1% fees
geosync backtest --csv historical_data.csv --fee 0.001

# Backtest with custom window
geosync backtest --csv data.csv --window 150
```

##### `geosync live`

Launch live trading with risk management.

**Usage:**
```bash
geosync live [OPTIONS]
```

**Options:**
- `--config`: TOML configuration file (default: configs/live/default.toml)
- `--venue`: Specific venue(s) to trade on (can specify multiple)
- `--state-dir`: Override state directory for OMS
- `--cold-start`: Skip position reconciliation
- `--metrics-port`: Port for Prometheus metrics

**Example:**
```bash
# Launch with default config
geosync live

# Trade on specific venues
geosync live --venue binance --venue coinbase

# Enable metrics export
geosync live --metrics-port 8000
```

#### Error Handling

All CLI commands return:
- **Exit code 0**: Success
- **Exit code 1**: Error (with JSON error message to stderr)
- **Exit code 130**: Keyboard interrupt (Ctrl+C)

Error messages follow this format:
```json
{
  "error": "ValueError",
  "message": "Detailed error description",
  "suggestion": "How to fix the issue"
}
```

### 2. Streamlit Dashboard (`dashboard_streamlit.py`)

Interactive web-based dashboard for market analysis.

#### Features

- **Data Upload & Validation**: CSV upload with comprehensive validation
- **Multi-Indicator Analysis**: Kuramoto, Entropy, Hurst, Ricci
- **Interactive Visualizations**: Price charts, volume analysis
- **Export Functionality**: JSON and CSV export formats
- **Analysis History**: Track and compare multiple analyses
- **Historical Trends**: Visualize indicator evolution over time

#### Running the Dashboard

```bash
streamlit run interfaces/dashboard_streamlit.py
```

Or using the module:
```bash
python -m streamlit run interfaces/dashboard_streamlit.py
```

#### Configuration

Set environment variables for authentication:
```bash
export DASHBOARD_ADMIN_USERNAME=admin
export DASHBOARD_ADMIN_PASSWORD_HASH=<bcrypt_hash>
export DASHBOARD_COOKIE_KEY=<secret_key>
```

#### Features by Tab

**📈 Data Upload Tab:**
- CSV file upload
- Data preview (first 10 rows)
- Comprehensive validation
- Quality checks (missing values, variance, etc.)
- Interactive data cleaning

**📊 Indicators Tab:**
- Real-time indicator computation
- Core metrics display (R, H, ΔH, Hurst)
- Geometric indicators (Ricci curvature)
- Regime classification
- Interactive charts
- Detailed analysis summary

**📋 Export & History Tab:**
- Export current analysis (JSON/CSV)
- Export enhanced dataset with indicators
- Analysis history (last 10 analyses)
- Historical trend visualization
- Clear history functionality

**ℹ️ Info Tab:**
- Comprehensive indicator documentation
- Best practices guide
- CSV format requirements
- Troubleshooting tips
- System information

### 3. Data Ingestion (`ingestion.py`)

Defines interfaces for market data loading components.

**Key Classes:**
- Synchronous and asynchronous data ingestion interfaces
- Standardized data validation
- Multi-source data handling

### 4. Backtest Interface (`backtest.py`)

Generic interface for backtesting engines.

**Purpose:**
- Standardized backtest execution contract
- Consistent performance reporting
- Engine interoperability

### 5. Execution Interfaces (`execution/`)

Contracts for position sizing, risk control, and portfolio analysis.

**Components:**
- `base.py`: Base execution interface
- `binance.py`: Binance-specific implementation
- `coinbase.py`: Coinbase-specific implementation
- `common.py`: Shared execution utilities

### 6. Live Trading Runner (`live_runner.py`)

Production live trading orchestrator with comprehensive risk controls.

**Features:**
- Position limits and exposure caps
- Circuit breakers and kill switches
- State reconciliation and recovery
- Real-time monitoring and alerting

### 7. Secrets Management (`secrets/`)

Secure credential and configuration management.

**Components:**
- `manager.py`: Secret management interface
- `backends.py`: Various backend implementations (Vault, env vars, etc.)

## CSV Data Format

All interfaces expect CSV files with the following structure:

**Required Columns:**
- `price`: Numeric price values (close, last, mid, etc.)

**Optional Columns:**
- `volume`: Trading volume
- `ts`, `timestamp`, `date`: Time information
- Any other columns are preserved but not used

**Example CSV:**
```csv
timestamp,price,volume
2024-01-01 09:00,100.5,1000000
2024-01-01 10:00,101.2,1200000
2024-01-01 11:00,100.8,900000
```

## Integration Examples

### Python Integration

```python
from interfaces.cli import signal_from_indicators
import numpy as np

# Generate signals from price data
prices = np.array([100, 101, 99, 102, 104])
signals = signal_from_indicators(prices, window=3)
```

### Scripting Integration

```bash
#!/bin/bash
# Analyze multiple datasets

for file in data/*.csv; do
    echo "Analyzing $file..."
    geosync analyze --csv "$file" > "results/$(basename $file .csv).json"
done
```

### Pipeline Integration

```python
import subprocess
import json

# Run analysis via CLI
result = subprocess.run(
    ['geosync', 'analyze', '--csv', 'data.csv'],
    capture_output=True,
    text=True
)

if result.returncode == 0:
    analysis = json.loads(result.stdout)
    print(f"Kuramoto Order: {analysis['R']}")
else:
    error = json.loads(result.stderr)
    print(f"Error: {error['message']}")
```

## Testing

Run interface tests:
```bash
pytest tests/unit/test_interfaces_cli.py -v
pytest tests/interfaces/ -v
```

## Error Handling Best Practices

1. **Always check exit codes** when using CLI in scripts
2. **Parse JSON errors** from stderr for programmatic error handling
3. **Validate data** before passing to interfaces
4. **Use appropriate window sizes** (recommended: 100-300 periods)
5. **Handle missing values** in your data preprocessing

## Performance Considerations

- **GPU Acceleration**: Use `--gpu` flag when available (requires CUDA)
- **Window Size**: Larger windows are more accurate but slower
- **Data Size**: Minimum recommended: 2x window size for backtesting
- **Parallelization**: CLI commands are single-threaded; use shell parallelization for multiple files

## Security

- **Secrets**: Use environment variables or HashiCorp Vault
- **Authentication**: Dashboard requires valid credentials
- **API Keys**: Never commit API keys; use secure secret management
- **State Files**: Protect OMS state files with appropriate permissions

## Monitoring & Observability

All interfaces support distributed tracing via W3C traceparent:

```bash
# Pass traceparent for distributed tracing
export TRACEPARENT="00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
geosync analyze --csv data.csv
```

## Support & Documentation

- **Full Documentation**: [https://github.com/neuron7xLab/GeoSync](https://github.com/neuron7xLab/GeoSync)
- **User Interaction Guide**: [docs/USER_INTERACTION_GUIDE.md](../docs/USER_INTERACTION_GUIDE.md) — Comprehensive examples for all interfaces
- **API Reference**: [https://docs.geosync.io/api](https://docs.geosync.io/api)
- **Examples**: See `examples/` directory in repository
- **Issues**: [GitHub Issues](https://github.com/neuron7xLab/GeoSync/issues)

## Version History

- **v2.1.0**: Added comprehensive User Interaction Guide with examples
- **v2.0.0**: Enhanced dashboard with export, history, and advanced indicators
- **v2.0.0**: Comprehensive CLI error handling and validation
- **v1.0.0**: Initial interface implementations

---

**Note**: This is the interface layer for GeoSync. Implementations must follow the contracts defined by the respective ABC classes to ensure boundary transparency and facilitate testing.
