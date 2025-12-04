# TradePulse API Reference

Comprehensive reference for TradePulse public APIs: Python library, CLI, and HTTP endpoints.

---

## Table of Contents

- [Python API](#python-api)
  - [TradePulseCompositeEngine](#tradepulsecompositeengine)
  - [Kuramoto Indicators](#kuramoto-indicators)
  - [Ricci Flow Indicators](#ricci-flow-indicators)
  - [Entropy Indicators](#entropy-indicators)
  - [Backtest Engine](#backtest-engine)
- [CLI Reference](#cli-reference)
  - [analyze](#analyze)
  - [backtest](#backtest)
  - [live](#live)
- [HTTP API](#http-api)
  - [Overview](#overview)
  - [Endpoints](#endpoints)

---

## Python API

### Quickstart

```python
import numpy as np
import pandas as pd
from core.indicators.kuramoto_ricci_composite import TradePulseCompositeEngine

# Create market data with DatetimeIndex
index = pd.date_range("2024-01-01", periods=720, freq="5min")
prices = 100 + np.cumsum(np.random.normal(0, 0.6, 720))
volume = np.random.lognormal(9.5, 0.35, 720)
bars = pd.DataFrame({"close": prices, "volume": volume}, index=index)

# Analyze market regime
engine = TradePulseCompositeEngine()
signal = engine.analyze_market(bars)

print(f"Phase: {signal.phase.value}")
print(f"Confidence: {signal.confidence:.3f}")
print(f"Entry Signal: {signal.entry_signal:.3f}")
```

---

### TradePulseCompositeEngine

The main entry point for market regime analysis combining Kuramoto synchronization with Ricci flow curvature.

**Module:** `core.indicators.kuramoto_ricci_composite`

#### Constructor

```python
TradePulseCompositeEngine(
    kuramoto_config: Optional[Dict] = None,
    ricci_config: Optional[Dict] = None,
    composite_config: Optional[Dict] = None
)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `kuramoto_config` | `Dict` | `None` | Configuration for MultiScaleKuramoto analyzer |
| `ricci_config` | `Dict` | `None` | Configuration for TemporalRicciAnalyzer |
| `composite_config` | `Dict` | `None` | Thresholds for phase classification |

**Composite Config Options:**

```python
composite_config = {
    "R_strong_emergent": 0.8,       # Kuramoto R threshold for strong emergence
    "R_proto_emergent": 0.4,        # Kuramoto R threshold for proto-emergence
    "coherence_threshold": 0.6,     # Cross-scale coherence threshold
    "ricci_negative_threshold": -0.3,  # Static Ricci for regime detection
    "temporal_ricci_threshold": -0.2,  # Temporal Ricci curvature threshold
    "transition_threshold": 0.7,    # Topological transition score threshold
    "min_confidence": 0.5           # Minimum confidence for signal generation
}
```

**Full Configuration Example:**

```python
from core.indicators.kuramoto_ricci_composite import TradePulseCompositeEngine

# Custom configuration for all components
engine = TradePulseCompositeEngine(
    kuramoto_config={
        "scales": [60, 300, 900],    # 1m, 5m, 15m timeframes in seconds
        "coupling": 0.8,              # Oscillator coupling strength
    },
    ricci_config={
        "window_size": 50,            # Graph construction window
        "delta": 0.01,                # Edge weight threshold
    },
    composite_config={
        "R_strong_emergent": 0.85,    # Higher threshold for strong signals
        "min_confidence": 0.6,        # Require higher confidence
    }
)
```

#### Methods

##### analyze_market

```python
analyze_market(
    df: pd.DataFrame,
    price_col: str = "close",
    volume_col: str = "volume"
) -> CompositeSignal
```

Analyze market regime and generate trading signals.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `df` | `pd.DataFrame` | required | Market data with DatetimeIndex |
| `price_col` | `str` | `"close"` | Column name for price data |
| `volume_col` | `str` | `"volume"` | Column name for volume data |

**Returns:** `CompositeSignal` dataclass with:

| Field | Type | Description |
|-------|------|-------------|
| `phase` | `MarketPhase` | Current market regime |
| `confidence` | `float` | Signal confidence (0-1) |
| `entry_signal` | `float` | Entry signal strength (-1 to 1) |
| `exit_signal` | `float` | Exit signal strength (0 to 1) |
| `risk_multiplier` | `float` | Position sizing multiplier |
| `kuramoto_R` | `float` | Kuramoto order parameter |
| `temporal_ricci` | `float` | Temporal Ricci curvature |
| `timestamp` | `pd.Timestamp` | Signal timestamp |

**Example:**

```python
from core.indicators.kuramoto_ricci_composite import (
    TradePulseCompositeEngine, MarketPhase
)

engine = TradePulseCompositeEngine()
signal = engine.analyze_market(market_data)

if signal.phase == MarketPhase.STRONG_EMERGENT and signal.confidence > 0.7:
    print(f"Strong buy signal: {signal.entry_signal:.2f}")
```

##### get_signal_dataframe

```python
get_signal_dataframe() -> pd.DataFrame
```

Returns historical signals as a DataFrame for analysis.

##### signal_history

```python
@property
signal_history: list[CompositeSignal]
```

Access raw signal history for custom processing.

---

### MarketPhase Enum

Available market phases classified by the composite engine:

| Phase | Value | Description |
|-------|-------|-------------|
| `CHAOTIC` | `"chaotic"` | Low synchronization, unpredictable dynamics |
| `PROTO_EMERGENT` | `"proto_emergent"` | Early synchronization signals appearing |
| `STRONG_EMERGENT` | `"strong_emergent"` | High synchronization with favorable geometry |
| `TRANSITION` | `"transition"` | Phase shift in progress |
| `POST_EMERGENT` | `"post_emergent"` | Synchronization breaking down |

---

### Kuramoto Indicators

**Module:** `core.indicators.kuramoto`

#### compute_phase

```python
compute_phase(prices: np.ndarray) -> np.ndarray
```

Compute instantaneous phases using Hilbert transform.

**Parameters:**
- `prices` — 1D price array

**Returns:** Array of phase angles in radians

#### kuramoto_order

```python
kuramoto_order(phases: np.ndarray) -> float
```

Compute Kuramoto order parameter (synchronization measure).

**Parameters:**
- `phases` — Array of phase angles

**Returns:** Order parameter R ∈ [0, 1], where 1 = perfect synchronization

**Example:**

```python
from core.indicators.kuramoto import compute_phase, kuramoto_order

phases = compute_phase(prices)
R = kuramoto_order(phases[-200:])
print(f"Kuramoto R: {R:.3f}")
```

---

### Ricci Flow Indicators

**Module:** `core.indicators.ricci`

#### build_price_graph

```python
build_price_graph(prices: np.ndarray, delta: float = 0.005) -> nx.Graph
```

Build a graph representation of price data for Ricci curvature analysis.

**Parameters:**
- `prices` — 1D price array
- `delta` — Step size for edge construction

**Returns:** NetworkX graph

#### mean_ricci

```python
mean_ricci(graph: nx.Graph) -> float
```

Compute mean Ollivier-Ricci curvature of the graph.

**Returns:** Average curvature (negative = divergent geometry, positive = convergent)

---

### Entropy Indicators

**Module:** `core.indicators.entropy`

#### entropy

```python
entropy(data: np.ndarray, bins: int = 30) -> float
```

Compute Shannon entropy of price distribution.

#### delta_entropy

```python
delta_entropy(
    data: np.ndarray,
    window: int = 200,
    bins_range: tuple[int, int] = (10, 50)
) -> float
```

Compute entropy change rate over a rolling window.

---

### Backtest Engine

**Module:** `backtest.event_driven`

#### EventDrivenBacktestEngine

```python
from backtest.event_driven import EventDrivenBacktestEngine

engine = EventDrivenBacktestEngine()
result = engine.run(
    prices,
    signal_function,
    initial_capital=100_000,
    strategy_name="my_strategy"
)
```

**Run Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prices` | `np.ndarray` | required | Price series to backtest |
| `signal_function` | `Callable` | required | Signal generator function |
| `initial_capital` | `float` | `100000` | Starting capital |
| `strategy_name` | `str` | `None` | Strategy identifier |

**Result Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `pnl` | `float` | Total profit/loss |
| `max_dd` | `float` | Maximum drawdown (fraction) |
| `trades` | `int` | Number of trades executed |
| `equity_curve` | `np.ndarray` | Equity over time |
| `performance` | `PerformanceMetrics` | Detailed metrics |

**Example:**

```python
from backtest.event_driven import EventDrivenBacktestEngine
from core.indicators import KuramotoIndicator

indicator = KuramotoIndicator(window=80, coupling=0.9)

def my_signal(series):
    order = indicator.compute(series)
    return np.where(order > 0.75, 1.0, np.where(order < 0.25, -1.0, 0.0))

engine = EventDrivenBacktestEngine()
result = engine.run(prices, my_signal, initial_capital=100_000)

print(f"PnL: ${result.pnl:,.2f}")
print(f"Max Drawdown: {result.max_dd:.2%}")
print(f"Sharpe Ratio: {result.performance.sharpe_ratio:.2f}")
```

---

## CLI Reference

The TradePulse CLI provides operational commands for analysis, backtesting, and live trading.

```bash
python -m interfaces.cli <command> [options]
```

### analyze

Compute geometric and technical indicators from price data.

```bash
python -m interfaces.cli analyze \
    --csv data.csv \
    --price-col close \
    --window 200 \
    --bins 30 \
    --delta 0.005
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--csv` | required | Path to CSV file with price data |
| `--price-col` | `price` | Column name for prices |
| `--window` | `200` | Analysis window size |
| `--bins` | `30` | Entropy histogram bins |
| `--delta` | `0.005` | Ricci curvature step size |
| `--gpu` | `false` | Enable GPU acceleration |
| `--config` | `None` | YAML configuration file |

**Output (JSON):**

```json
{
  "R": 0.85,
  "H": 2.34,
  "delta_H": 0.12,
  "kappa_mean": 0.45,
  "Hurst": 0.58,
  "phase": "trending",
  "metadata": {
    "window_size": 200,
    "data_points": 1000,
    "bins": 30,
    "delta": 0.005,
    "gpu_enabled": false
  }
}
```

---

### backtest

Run walk-forward backtesting with indicator-based signals.

```bash
python -m interfaces.cli backtest \
    --csv data.csv \
    --price-col close \
    --window 200 \
    --fee 0.0005
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--csv` | required | Path to CSV with historical prices |
| `--price-col` | `price` | Column name for prices |
| `--window` | `200` | Indicator lookback window |
| `--fee` | `0.0005` | Transaction fee (fraction) |
| `--gpu` | `false` | Enable GPU acceleration |
| `--config` | `None` | YAML configuration file |

**Output (JSON):**

```json
{
  "pnl": 12500.50,
  "max_dd": 0.082,
  "trades": 47,
  "metadata": {
    "window_size": 200,
    "fee": 0.0005,
    "data_points": 5000
  }
}
```

---

### live

Launch live trading with risk management and monitoring.

```bash
python -m interfaces.cli live \
    --config configs/live/default.toml \
    --venue binance \
    --metrics-port 9090
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--config` | `configs/live/default.toml` | TOML config with venues and risk limits |
| `--venue` | all | Restrict to specific venue(s) |
| `--state-dir` | `None` | Override state persistence directory |
| `--cold-start` | `false` | Skip position reconciliation |
| `--metrics-port` | `None` | Prometheus metrics port |

---

## HTTP API

### Overview

TradePulse exposes a FastAPI-based REST API for programmatic access.

**Base URL:** `http://localhost:8000/api/v1`

**Authentication:** Bearer token via `Authorization` header

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/health
```

### Endpoints

#### Health Check

```http
GET /health
```

**Response:**

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

#### Analyze Market Data

```http
POST /analyze
Content-Type: application/json

{
  "prices": [100.0, 101.2, 99.8, ...],
  "window": 200,
  "bins": 30
}
```

**Response:**

```json
{
  "R": 0.85,
  "H": 2.34,
  "delta_H": 0.12,
  "kappa_mean": 0.45,
  "phase": "strong_emergent"
}
```

#### Get Signal

```http
POST /signal
Content-Type: application/json

{
  "symbol": "BTC/USDT",
  "timeframe": "5m",
  "lookback": 200
}
```

**Response:**

```json
{
  "phase": "strong_emergent",
  "confidence": 0.87,
  "entry_signal": 0.72,
  "exit_signal": 0.15,
  "risk_multiplier": 1.35,
  "timestamp": "2024-01-01T12:00:00Z"
}
```

#### TACL Thermodynamic API

```http
GET /thermo/status
```

Returns current thermodynamic control layer status.

```http
GET /thermo/history
```

Returns free energy history for monitoring.

```http
GET /thermo/crisis
```

Returns current crisis mode and adaptive parameters.

---

## Error Handling

All API endpoints return structured error responses:

```json
{
  "error": "ValueError",
  "message": "Insufficient data: 50 rows < window size 200",
  "suggestion": "Provide a dataset with at least 200 rows or reduce the --window parameter."
}
```

**Common Error Codes:**

| Code | Description |
|------|-------------|
| `400` | Invalid request parameters |
| `401` | Authentication required |
| `404` | Resource not found |
| `422` | Validation error |
| `500` | Internal server error |

---

## Rate Limits

| Tier | Requests/min | Burst |
|------|--------------|-------|
| Free | 60 | 10 |
| Pro | 600 | 100 |
| Enterprise | Unlimited | — |

---

## SDK Examples

### Python SDK

```python
from tradepulse import TradePulseClient

client = TradePulseClient(api_key="your-key")

# Analyze market
result = client.analyze(symbol="BTC/USDT", window=200)
print(f"Phase: {result.phase}")

# Get signal
signal = client.get_signal(symbol="BTC/USDT")
if signal.entry_signal > 0.5:
    print("Consider long position")
```

### Streaming Data

```python
async def on_signal(signal):
    print(f"New signal: {signal.phase}")

await client.subscribe_signals(
    symbols=["BTC/USDT", "ETH/USDT"],
    callback=on_signal
)
```

---

## Further Reading

- [Quickstart Guide](quickstart.md) — Step-by-step tutorial
- [Indicator Library](indicators.md) — All available indicators
- [Architecture](ARCHITECTURE.md) — System design
- [Examples](examples/) — Working code samples
