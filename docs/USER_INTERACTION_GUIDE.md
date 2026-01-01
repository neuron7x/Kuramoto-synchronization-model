---
owner: dx@tradepulse
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# TradePulse User Interaction Guide

> **Comprehensive documentation for all TradePulse interaction methods**

This guide provides detailed documentation and practical examples for interacting with TradePulse through various interfaces: Command-Line Interface (CLI), Streamlit Dashboard, Web Application, and Programmatic API.

---

## Table of Contents

- [Overview](#overview)
- [Quick Start Summary](#quick-start-summary)
- [Command-Line Interface (CLI)](#command-line-interface-cli)
  - [Installation & Setup](#cli-installation--setup)
  - [Available Commands](#available-commands)
  - [Practical Examples](#cli-practical-examples)
  - [Configuration Options](#cli-configuration-options)
  - [Error Handling](#cli-error-handling)
- [Streamlit Dashboard](#streamlit-dashboard)
  - [Launching the Dashboard](#launching-the-dashboard)
  - [Dashboard Features](#dashboard-features)
  - [Usage Examples](#dashboard-usage-examples)
- [Web Application (Next.js)](#web-application-nextjs)
  - [Running the Web App](#running-the-web-app)
  - [Features](#web-app-features)
- [Programmatic API](#programmatic-api)
  - [Python SDK](#python-sdk)
  - [HTTP REST API](#http-rest-api)
  - [Integration Examples](#api-integration-examples)
- [Choosing the Right Interface](#choosing-the-right-interface)
- [Troubleshooting](#troubleshooting)

---

## Overview

TradePulse provides multiple interaction methods to suit different use cases:

| Interface | Best For | Location |
|-----------|----------|----------|
| **CLI** | Automation, scripting, batch processing | `cli/`, `interfaces/cli.py` |
| **Streamlit Dashboard** | Interactive analysis, visualization | `interfaces/dashboard_streamlit.py` |
| **Web Application** | Production UI, team collaboration | `apps/web/` |
| **Programmatic API** | Custom integrations, live trading | `application/api/`, `tradepulse/sdk/` |

---

## Quick Start Summary

```bash
# CLI - Analyze market data
python -m interfaces.cli analyze --csv data.csv --window 200

# CLI - Run backtest
python -m interfaces.cli backtest --csv data.csv --fee 0.001

# Streamlit Dashboard
streamlit run interfaces/dashboard_streamlit.py

# Web Application
cd apps/web && npm install && npm run dev

# Python API - Verify installation
python -c "from core.indicators.kuramoto import compute_phase; import numpy as np; phases = compute_phase(np.array([100,101,102])); print('API ready, phases:', phases)"
```

---

## Command-Line Interface (CLI)

The TradePulse CLI provides two main entry points:

1. **Research CLI** (`interfaces/cli.py`) - For analysis and backtesting
2. **Orchestration CLI** (`cli/tradepulse_cli.py`) - For production workflows

### CLI Installation & Setup

```bash
# Clone and install TradePulse
git clone https://github.com/neuron7x/TradePulse.git
cd TradePulse

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.lock

# Verify installation
python -m interfaces.cli --help
```

### Available Commands

#### Research CLI (`interfaces/cli.py`)

| Command | Description |
|---------|-------------|
| `analyze` | Compute geometric indicators from price data |
| `backtest` | Run walk-forward backtesting with indicator signals |
| `live` | Launch live trading with risk management |

#### Orchestration CLI (`cli/tradepulse_cli.py`)

| Command | Description |
|---------|-------------|
| `ingest` | Run data ingestion and register artifacts |
| `backtest` | Execute vectorized backtest |
| `optimize` / `train` | Perform parameter grid search |
| `exec` / `serve` | Evaluate and persist trading signals |
| `report` | Generate markdown reports |
| `deploy` | Apply Kubernetes manifests |
| `parity` | Reconcile offline/online feature stores |
| `fete-backtest` | Run FETE engine backtest |
| `causal-pipeline` | Execute causal early-warning pipeline |

### CLI Practical Examples

#### Example 1: Basic Market Analysis

```bash
# Analyze a CSV file with default settings
python -m interfaces.cli analyze --csv sample.csv

# Output:
# {
#   "R": 0.85,
#   "H": 3.24,
#   "delta_H": -0.05,
#   "kappa_mean": 0.34,
#   "Hurst": 0.62,
#   "phase": "trending"
# }
```

#### Example 2: Custom Analysis Parameters

```bash
# Analyze with custom window size and column name
python -m interfaces.cli analyze \
    --csv market_data.csv \
    --price-col close \
    --window 150 \
    --bins 40 \
    --delta 0.01

# With GPU acceleration (requires CUDA)
python -m interfaces.cli analyze --csv data.csv --gpu
```

#### Example 3: Running a Backtest

```bash
# Simple backtest
python -m interfaces.cli backtest \
    --csv historical_prices.csv \
    --price-col close \
    --window 200 \
    --fee 0.001

# Output:
# {
#   "pnl": 12543.78,
#   "max_dd": -2341.50,
#   "trades": 87,
#   "metadata": {
#     "window_size": 200,
#     "fee": 0.001,
#     "data_points": 5000
#   }
# }
```

#### Example 4: Orchestration CLI Workflows

```bash
# Generate configuration template
python cli/tradepulse_cli.py backtest \
    --generate-config \
    --template-output configs/my_backtest.yaml

# Run backtest with configuration
python cli/tradepulse_cli.py backtest \
    --config configs/my_backtest.yaml \
    --output jsonl

# Run parameter optimization
python cli/tradepulse_cli.py optimize \
    --config configs/optimize.yaml \
    --output table

# Execute FETE backtest
python cli/tradepulse_cli.py fete-backtest \
    --csv prices.csv \
    --price-col close \
    --out equity_curve.csv
```

#### Example 5: Batch Processing Script

```bash
#!/bin/bash
# Analyze multiple datasets

OUTPUT_DIR="results"
mkdir -p "$OUTPUT_DIR"

for file in data/*.csv; do
    filename=$(basename "$file" .csv)
    echo "Processing $filename..."
    
    python -m interfaces.cli analyze \
        --csv "$file" \
        --price-col close \
        --window 200 \
        > "$OUTPUT_DIR/${filename}_analysis.json"
done

echo "Batch analysis complete!"
```

#### Example 6: Pipeline Integration

```python
#!/usr/bin/env python3
"""Integration example: Run CLI analysis from Python."""
import subprocess
import json
import sys
from pathlib import Path

def analyze_market_data(csv_path: str, window: int = 200) -> dict:
    """Run TradePulse analysis and return results.
    
    Args:
        csv_path: Path to CSV file (validated for safety)
        window: Analysis window size
        
    Returns:
        Analysis results as dictionary
        
    Raises:
        ValueError: If csv_path is invalid
        RuntimeError: If analysis fails
    """
    # Validate and sanitize the file path
    safe_path = Path(csv_path).resolve()
    if not safe_path.exists():
        raise ValueError(f"CSV file not found: {safe_path}")
    if not safe_path.suffix.lower() == '.csv':
        raise ValueError(f"Expected CSV file, got: {safe_path.suffix}")
    
    result = subprocess.run(
        [
            sys.executable, "-m", "interfaces.cli", "analyze",
            "--csv", str(safe_path),
            "--window", str(window),
        ],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        error = json.loads(result.stderr)
        raise RuntimeError(f"Analysis failed: {error['message']}")
    
    return json.loads(result.stdout)

# Usage
if __name__ == "__main__":
    analysis = analyze_market_data("sample.csv", window=150)
    print(f"Kuramoto Order: {analysis['R']:.4f}")
    print(f"Market Phase: {analysis['phase']}")
```

### CLI Configuration Options

You can provide configuration via YAML files:

```yaml
# config/analysis.yaml
indicators:
  window: 200
  bins: 30
  delta: 0.005

data:
  path: data/market_prices.csv
```

Use with:

```bash
python -m interfaces.cli analyze --config config/analysis.yaml
```

### CLI Error Handling

The CLI provides structured JSON error messages:

| Exit Code | Meaning |
|-----------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 3 | Artifact/file error |
| 4 | Computation error |
| 130 | Keyboard interrupt |

Example error handling in scripts:

```bash
if ! python -m interfaces.cli analyze --csv data.csv; then
    case $? in
        1) echo "General error - check logs" ;;
        2) echo "Configuration error - check parameters" ;;
        3) echo "File not found - verify path" ;;
        4) echo "Computation error - check data quality" ;;
        *) echo "Unknown error" ;;
    esac
    exit 1
fi
```

---

## Streamlit Dashboard

The Streamlit dashboard provides an interactive web interface for market analysis.

### Launching the Dashboard

```bash
# Basic launch
streamlit run interfaces/dashboard_streamlit.py

# Custom port
streamlit run interfaces/dashboard_streamlit.py --server.port 8080

# With authentication (set environment variables first)
export DASHBOARD_ADMIN_USERNAME=analyst
export DASHBOARD_ADMIN_PASSWORD_HASH='$2b$12$...'  # bcrypt hash
export DASHBOARD_COOKIE_KEY='your-secret-key'
streamlit run interfaces/dashboard_streamlit.py
```

### Dashboard Features

The dashboard is organized into four tabs:

#### 📈 Data Upload Tab

- Upload CSV files with price data
- Automatic data validation
- Data quality checks (missing values, variance)
- Interactive data cleaning options

#### 📊 Indicators Tab

- **Core Indicators:**
  - Kuramoto Order Parameter (R) - Phase synchronization
  - Shannon Entropy (H) - Information content
  - Delta Entropy (ΔH) - Entropy change
  - Hurst Exponent - Long-term memory

- **Geometric Indicators:**
  - Mean Ricci Curvature (κ) - Market manifold geometry
  - Regime Classification - Automated market state

- **Visualizations:**
  - Price charts with moving averages
  - Volume analysis
  - Regime indicators

#### 📋 Export & History Tab

- Export analysis results as JSON or CSV
- Download enhanced datasets with computed indicators
- Track analysis history (last 10 analyses)
- Historical trend visualization
- Bulk history export

#### ℹ️ Info Tab

- Indicator documentation and interpretation
- Best practices guide
- CSV format requirements
- Troubleshooting tips

### Dashboard Usage Examples

#### Example 1: Basic Analysis Workflow

1. **Open the dashboard:**
   ```bash
   streamlit run interfaces/dashboard_streamlit.py
   ```

2. **Upload your data:**
   - Navigate to "📈 Data Upload" tab
   - Click "Browse files" and select your CSV
   - Review the validation results

3. **Configure analysis:**
   - Use the sidebar to set "Analysis Window" (default: 200)
   - Adjust "Ricci Delta" and "Entropy Bins" in Advanced Settings

4. **View results:**
   - Switch to "📊 Indicators" tab
   - Review computed metrics
   - Examine the regime classification

5. **Export results:**
   - Go to "📋 Export & History" tab
   - Download analysis as JSON or CSV

#### Example 2: Preparing CSV Data

Your CSV should have at least a `price` column:

```csv
timestamp,price,volume
2024-01-01 09:00,50000.50,1200000
2024-01-01 10:00,50125.75,1350000
2024-01-01 11:00,49980.25,1100000
2024-01-01 12:00,50250.00,1450000
```

#### Example 3: Environment Configuration

```bash
# .env file for dashboard configuration
DASHBOARD_ADMIN_USERNAME=admin
DASHBOARD_ADMIN_PASSWORD_HASH=$2b$12$EixZaYVK1fsbw1ZfbX3OXe.RKjKWbFUZYWbAKpKnvGmcPNW3OL2K6
DASHBOARD_COOKIE_NAME=tradepulse_auth
DASHBOARD_COOKIE_KEY=your-secure-random-key-here
DASHBOARD_COOKIE_EXPIRY_DAYS=30
```

---

## Web Application (Next.js)

The production-grade web application is built with Next.js and provides a full-featured trading interface.

### Running the Web App

```bash
# Navigate to web app directory
cd apps/web

# Install dependencies
npm install

# Development mode
npm run dev

# Production build
npm run build
npm start
```

Access at: http://localhost:3000

### Web App Features

The Next.js web application includes:

- **Real-time Dashboard** - Live market data and indicators
- **Strategy Management** - Configure and monitor trading strategies
- **Portfolio Analytics** - Performance tracking and reporting
- **Risk Monitoring** - Real-time risk metrics and alerts
- **Admin Controls** - User management and system configuration

### Running Tests

```bash
cd apps/web

# Unit tests
npm test

# End-to-end tests
npm run test:e2e

# Type checking
npm run type-check
```

---

## Programmatic API

For custom integrations and advanced use cases, TradePulse provides a comprehensive Python SDK and REST API.

### Python SDK

#### Basic Indicator Computation

```python
import numpy as np
import pandas as pd
from core.indicators.kuramoto import compute_phase, kuramoto_order
from core.indicators.entropy import entropy, delta_entropy
from core.indicators.ricci import build_price_graph, mean_ricci
from core.indicators.hurst import hurst_exponent

# Load your data
df = pd.read_csv('prices.csv')
prices = df['close'].to_numpy()

# Compute Kuramoto order parameter
phases = compute_phase(prices)
R = kuramoto_order(phases[-200:])
print(f"Kuramoto Order: {R:.4f}")

# Compute entropy measures
H = entropy(prices[-200:], bins=30)
dH = delta_entropy(prices, window=200)
print(f"Entropy: {H:.4f}, ΔH: {dH:.4f}")

# Compute Ricci curvature
G = build_price_graph(prices[-200:], delta=0.005)
kappa = mean_ricci(G)
print(f"Mean Ricci Curvature: {kappa:.6f}")

# Compute Hurst exponent
Hs = hurst_exponent(prices[-200:])
print(f"Hurst Exponent: {Hs:.4f}")
```

#### Using the Composite Engine

```python
import pandas as pd
from core.indicators.kuramoto_ricci_composite import TradePulseCompositeEngine

# Prepare data with DatetimeIndex
df = pd.read_csv('prices.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])
df = df.set_index('timestamp')

# Initialize engine
engine = TradePulseCompositeEngine()

# Analyze market
snapshot = engine.analyze_market(df)

print(f"Market Phase: {snapshot.phase.value}")
print(f"Confidence: {snapshot.confidence:.3f}")
print(f"Entry Signal: {snapshot.entry_signal:.3f}")
print(f"Risk Level: {snapshot.risk_level}")
```

#### Backtesting with Custom Strategy

```python
import numpy as np
from backtest.event_driven import EventDrivenBacktestEngine

def my_strategy(prices: np.ndarray) -> np.ndarray:
    """Custom momentum strategy."""
    signals = np.zeros(len(prices))
    window = 20
    
    for i in range(window, len(prices)):
        # Simple momentum: buy if price above MA, sell if below
        ma = prices[i-window:i].mean()
        if prices[i] > ma * 1.02:
            signals[i] = 1.0  # Long
        elif prices[i] < ma * 0.98:
            signals[i] = -1.0  # Short
        else:
            signals[i] = 0.0  # Flat
    
    return signals

# Load data
prices = np.loadtxt('prices.csv', delimiter=',', skiprows=1, usecols=1)

# Run backtest
engine = EventDrivenBacktestEngine()
result = engine.run(
    prices=prices,
    signal_func=my_strategy,
    initial_capital=100_000,
    commission=0.001,
    strategy_name="momentum_strategy"
)

print(f"PnL: ${result.pnl:,.2f}")
print(f"Max Drawdown: {result.max_dd:.2%}")
print(f"Trades: {result.trades}")
```

#### Trading SDK Usage

```python
from tradepulse.sdk import TradePulseSDK, MarketState, SDKConfig
from application.system import TradePulseSystem
from hydra import compose, initialize

# Load configuration using Hydra
# Configuration files are typically in configs/ directory
with initialize(version_base=None, config_path="../configs"):
    config = compose(config_name="config")

# Initialize system with configuration
system = TradePulseSystem(config)

# Configure SDK
sdk_config = SDKConfig(
    default_venue="binance",
    signal_strategy=my_strategy,
    position_sizer=lambda s: 0.1,  # 10% position size
)

# Create SDK instance
sdk = TradePulseSDK(system, sdk_config)

# Generate trading signal
state = MarketState(
    symbol="BTCUSDT",
    venue="BINANCE",
    market_frame=df
)
signal = sdk.get_signal(state)

# Propose and execute trade
if signal.action not in ["HOLD", "EXIT"]:
    proposal = sdk.propose_trade(signal)
    risk_result = sdk.risk_check(proposal.order)
    
    if risk_result.approved:
        result = sdk.execute(proposal.order)
        print(f"Order submitted: {result.correlation_id}")
    else:
        print(f"Order rejected: {risk_result.reason}")
```

### HTTP REST API

TradePulse exposes a FastAPI-based REST API for HTTP integrations.

#### Starting the API Server

```bash
# Development
uvicorn application.api:app --reload --port 8000

# Production
uvicorn application.api:app --host 0.0.0.0 --port 8000 --workers 4
```

#### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/signals` | POST | Generate trading signals |
| `/api/v1/orders` | POST | Submit orders |
| `/api/v1/orders/{id}` | GET | Get order status |
| `/api/v1/indicators` | POST | Compute indicators |
| `/api/v1/backtest` | POST | Run backtest |

#### Example: Using the API with Python

```python
import httpx

API_BASE = "http://localhost:8000/api/v1"

# Compute indicators
response = httpx.post(
    f"{API_BASE}/indicators",
    json={
        "prices": [100, 101, 102, 101, 103, 105, 104],
        "window": 5,
        "indicators": ["kuramoto", "entropy", "hurst"]
    }
)
result = response.json()
print(f"Kuramoto Order: {result['kuramoto']}")

# Generate signal
response = httpx.post(
    f"{API_BASE}/signals",
    json={
        "symbol": "BTCUSDT",
        "prices": prices,
        "strategy": "momentum"
    }
)
signal = response.json()
print(f"Signal: {signal['action']}, Confidence: {signal['confidence']}")
```

#### Example: Using the API with curl

```bash
# Compute indicators
curl -X POST http://localhost:8000/api/v1/indicators \
    -H "Content-Type: application/json" \
    -d '{
        "prices": [100, 101, 102, 101, 103],
        "window": 3,
        "indicators": ["kuramoto", "entropy"]
    }'

# Get signal
curl -X POST http://localhost:8000/api/v1/signals \
    -H "Content-Type: application/json" \
    -d '{
        "symbol": "BTCUSDT",
        "prices": [100, 101, 102, 101, 103, 105],
        "strategy": "composite"
    }'
```

### API Integration Examples

#### Example 1: Jupyter Notebook Integration

```python
# In a Jupyter notebook cell
import pandas as pd
import numpy as np
from core.indicators.kuramoto_ricci_composite import TradePulseCompositeEngine
import matplotlib.pyplot as plt

# Load and prepare data
df = pd.read_csv('btc_hourly.csv', parse_dates=['timestamp'], index_col='timestamp')

# Initialize engine
engine = TradePulseCompositeEngine()

# Analyze multiple timepoints
results = []
for i in range(200, len(df), 50):
    window_df = df.iloc[i-200:i]
    snapshot = engine.analyze_market(window_df)
    results.append({
        'timestamp': df.index[i],
        'phase': snapshot.phase.value,
        'confidence': snapshot.confidence,
        'entry_signal': snapshot.entry_signal
    })

results_df = pd.DataFrame(results)

# Visualize
fig, axes = plt.subplots(2, 1, figsize=(12, 8))

# Price with entry signals
axes[0].plot(df.index, df['close'], label='Price')
axes[0].set_title('BTC Price with Entry Signals')

# Confidence over time
axes[1].plot(results_df['timestamp'], results_df['confidence'])
axes[1].set_title('Analysis Confidence Over Time')

plt.tight_layout()
plt.show()
```

#### Example 2: Scheduled Analysis Job

```python
#!/usr/bin/env python3
"""Scheduled market analysis job.

Requires: pip install schedule
"""
import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# pip install schedule
try:
    import schedule
except ImportError:
    raise ImportError("This example requires 'schedule'. Install with: pip install schedule")

from core.indicators.kuramoto_ricci_composite import TradePulseCompositeEngine


def load_latest_market_data() -> pd.DataFrame:
    """Load latest market data from your data source.
    
    Replace this with your actual data loading logic:
    - Read from database
    - Fetch from exchange API
    - Load from file system
    """
    # Example: Generate sample data for demonstration
    # In production, replace with actual data source
    index = pd.date_range(end=datetime.now(), periods=500, freq='5min')
    prices = 100 + np.cumsum(np.random.normal(0, 0.5, 500))
    volume = np.random.lognormal(10, 0.3, 500)
    return pd.DataFrame({'close': prices, 'volume': volume}, index=index)


def send_alert(result: dict) -> None:
    """Send alert notification.
    
    Replace with your alerting implementation:
    - Email via SMTP
    - Slack webhook
    - SMS via Twilio
    - Push notification
    """
    print(f"🚨 ALERT: High-confidence signal detected!")
    print(f"   Phase: {result['phase']}")
    print(f"   Confidence: {result['confidence']:.3f}")
    print(f"   Entry Signal: {result['entry_signal']:.3f}")


def run_analysis():
    """Run periodic market analysis."""
    df = load_latest_market_data()
    
    engine = TradePulseCompositeEngine()
    snapshot = engine.analyze_market(df)
    
    result = {
        'timestamp': datetime.utcnow().isoformat(),
        'phase': snapshot.phase.value,
        'confidence': snapshot.confidence,
        'entry_signal': snapshot.entry_signal,
        'risk_level': snapshot.risk_level
    }
    
    # Save result
    output_path = Path(f"results/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2))
    
    print(f"[{result['timestamp']}] Phase: {result['phase']}, Signal: {result['entry_signal']:.3f}")
    
    # Alert on high-confidence signals
    if result['confidence'] > 0.8 and abs(result['entry_signal']) > 0.5:
        send_alert(result)

# Schedule every 15 minutes
schedule.every(15).minutes.do(run_analysis)

if __name__ == "__main__":
    print("Starting scheduled analysis...")
    run_analysis()  # Run immediately
    while True:
        schedule.run_pending()
        time.sleep(60)
```

---

## Choosing the Right Interface

| Use Case | Recommended Interface |
|----------|----------------------|
| Quick analysis, one-off tasks | CLI |
| Interactive exploration | Streamlit Dashboard |
| Production trading system | Web Application + API |
| Automated pipelines | CLI or Python SDK |
| Custom integrations | Python SDK or REST API |
| Team collaboration | Web Application |
| Jupyter research | Python SDK |
| Mobile access | REST API + custom frontend |

### Decision Flowchart

```
Need to analyze data?
├── One-time or scripted → CLI
├── Interactive exploration → Streamlit Dashboard
└── Custom visualization → Python SDK + matplotlib

Building a trading system?
├── Prototype → Python SDK
├── Production → REST API + Web App
└── High-frequency → Direct SDK integration

Team needs access?
├── Analysts → Streamlit Dashboard
├── Developers → CLI + Python SDK
└── Traders → Web Application
```

---

## Troubleshooting

### Common CLI Issues

**Issue: `ModuleNotFoundError: No module named 'core'`**
```bash
# Solution: Install in editable mode
pip install -e .
```

**Issue: `FileNotFoundError: CSV file not found`**
```bash
# Solution: Use absolute path or verify working directory
python -m interfaces.cli analyze --csv /full/path/to/data.csv
```

**Issue: `ValueError: Insufficient data`**
```bash
# Solution: Reduce window size or provide more data
python -m interfaces.cli analyze --csv data.csv --window 50
```

### Common Dashboard Issues

**Issue: Authentication fails**
```bash
# Solution: Check environment variables
export DASHBOARD_ADMIN_PASSWORD_HASH=$(python -c "import bcrypt; print(bcrypt.hashpw(b'your_password', bcrypt.gensalt()).decode())")
```

**Issue: Dashboard won't start**
```bash
# Solution: Check port availability
lsof -i :8501
streamlit run interfaces/dashboard_streamlit.py --server.port 8502
```

### Common API Issues

**Issue: Connection refused**
```bash
# Solution: Ensure API server is running
uvicorn application.api:app --reload --port 8000
```

**Issue: CORS errors in browser**
```python
# Solution: Configure CORS in FastAPI with specific allowed origins
# Note: Never use "*" in production - specify allowed domains explicitly
import os
from fastapi.middleware.cors import CORSMiddleware

# Use environment variable for allowed origins in production
allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Specify allowed origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

---

## Additional Resources

- **Full Documentation**: [docs/index.md](index.md)
- **API Reference**: [docs/api/API_REFERENCE.md](api/API_REFERENCE.md)
- **Examples Directory**: [examples/](../examples/)
- **CLI Reference**: [docs/tradepulse_cli_reference.md](tradepulse_cli_reference.md)
- **Quickstart Guide**: [docs/quickstart.md](quickstart.md)
- **Architecture Overview**: [docs/ARCHITECTURE.md](ARCHITECTURE.md)

---

## Version History

- **v1.0.0**: Comprehensive user interaction guide with CLI, Dashboard, and API examples
- **Initial**: Interface implementations and basic documentation

---

**Questions?** Open an issue on [GitHub](https://github.com/neuron7x/TradePulse/issues) or join our [Discord community](https://discord.gg/tradepulse).
