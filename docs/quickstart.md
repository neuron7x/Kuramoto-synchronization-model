# Quick Start Guide

Get up and running with TradePulse in 5 minutes.

---

## Prerequisites

- **Python 3.11 or higher**
- **pip** (Python package manager)
- **git** (version control)
- Basic understanding of Python and trading concepts

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/neuron7x/TradePulse.git
cd TradePulse
```

---

## Step 2: Create Virtual Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate it
# On Linux/macOS:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

---

## Step 3: Install Dependencies

```bash
# Install runtime packages (locked)
pip install -r requirements.lock

# Install development tools (optional, extends runtime lock)
pip install -r requirements-dev.lock

# Extras: install only what you need
# pip install ".[connectors]"  # market & broker integrations
# pip install ".[gpu]"         # GPU acceleration backends
# pip install ".[docs]"        # documentation toolchain
```

Prefer a single command that provisions everything? Use the bundled bootstrapper
from the repository root:

```bash
python -m scripts bootstrap --include-dev --verify --smoke-test
```

This creates `.venv`, installs the locked dependencies, runs `pip check`, and
executes a tiny sample analysis to confirm the stack is healthy.

---

## Step 4: Verify Installation

```bash
# Test that imports work
python -c "from core.indicators.kuramoto import compute_phase; print('OK')"

# Run tests
pytest tests/ -v
```

---

## Step 5: Analyze Market Data

### Using Sample Data

```bash
# Analyze the included sample.csv
python -m interfaces.cli analyze --csv sample.csv --window 200
```

Expected output:
```json
{
  "R": 0.85,
  "H": 2.34,
  "delta_H": 0.12,
  "kappa_mean": 0.45,
  "Hurst": 0.58,
  "phase": "trending"
}
```

### Using Your Own Data

Create a CSV file with this format:
```csv
timestamp,close,volume
2024-01-01 00:00:00,50000,100
2024-01-01 00:01:00,50100,150
2024-01-01 00:02:00,49950,120
```

Then analyze:
```bash
python -m interfaces.cli analyze --csv your_data.csv
```

---

## Step 6: Run a Backtest

```bash
# Simple backtest
python -m interfaces.cli backtest \
    --csv sample.csv \
    --train-window 500 \
    --test-window 100 \
    --initial-capital 10000
```

Output shows:
- Total return
- Sharpe ratio
- Max drawdown
- Win rate
- Number of trades

---

## Step 7: Explore Indicators

### Python Script

Create a file `my_analysis.py`:

```python
import numpy as np
import pandas as pd
from core.indicators.kuramoto import compute_phase, kuramoto_order
from core.indicators.entropy import entropy
from core.indicators.ricci import build_price_graph, mean_ricci

# Load data
df = pd.read_csv('sample.csv')
prices = df['close'].to_numpy()

# Compute indicators
phases = compute_phase(prices)
R = kuramoto_order(phases[-200:])
H = entropy(prices[-200:])
G = build_price_graph(prices[-200:], delta=0.005)
kappa = mean_ricci(G)

print(f"Kuramoto Order: {R:.3f}")
print(f"Entropy: {H:.3f}")
print(f"Mean Ricci Curvature: {kappa:.3f}")
```

Run it:
```bash
python my_analysis.py
```

---

## Step 8: Create a Custom Strategy

Create `my_strategy.py`:

```python
import numpy as np
from backtest.engine import walk_forward

def my_signal_function(prices: np.ndarray, window: int = 50) -> np.ndarray:
    """Simple moving average crossover strategy."""
    signals = np.zeros(len(prices))
    
    fast_ma = np.convolve(prices, np.ones(window)//window, mode='valid')
    slow_ma = np.convolve(prices, np.ones(window*2)//(window*2), mode='valid')
    
    # Align arrays
    min_len = min(len(fast_ma), len(slow_ma))
    fast_ma = fast_ma[-min_len:]
    slow_ma = slow_ma[-min_len:]
    
    # Generate signals
    for i in range(1, len(fast_ma)):
        if fast_ma[i] > slow_ma[i] and fast_ma[i-1] <= slow_ma[i-1]:
            signals[-(min_len-i)] = 1  # Buy signal
        elif fast_ma[i] < slow_ma[i] and fast_ma[i-1] >= slow_ma[i-1]:
            signals[-(min_len-i)] = -1  # Sell signal
    
    return signals

# Load data
import pandas as pd
df = pd.read_csv('sample.csv')
prices = df['close'].to_numpy()

# Backtest
results = walk_forward(
    prices=prices,
    signal_func=my_signal_function,
    train_window=500,
    test_window=100,
    initial_capital=10000.0
)

print(f"Total Return: {results['total_return']:.2%}")
print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {results['max_drawdown']:.2%}")
```

Run:
```bash
python my_strategy.py
```

---

## Step 9: Set Up Monitoring (Optional)

If you want to use monitoring features:

```bash
# Start Prometheus and Grafana
docker compose up -d prometheus grafana

# Access Grafana at http://localhost:3000
# Default credentials: admin/admin
```

---

## Step 10: Optimize Performance (Optional)

For large datasets or production deployments, use performance optimizations:

```python
import numpy as np
from core.indicators.entropy import EntropyFeature
from core.indicators.hurst import HurstFeature
from core.data.preprocess import scale_series

# Load large dataset
large_data = np.random.randn(1_000_000)

# Memory-efficient processing with float32
entropy_feat = EntropyFeature(
    bins=50,
    use_float32=True,        # 50% memory reduction
    chunk_size=100_000       # Process in chunks
)

hurst_feat = HurstFeature(
    use_float32=True
)

# Scale data efficiently
scaled = scale_series(large_data, use_float32=True)

# Compute indicators with monitoring
result = entropy_feat.transform(scaled)
print(f"Entropy: {result.value:.4f}")

# Enable structured logging
from core.utils.logging import configure_logging
configure_logging(level="INFO", use_json=True)

# Start Prometheus metrics server
from core.utils.metrics import start_metrics_server
start_metrics_server(port=8000)  # Metrics at http://localhost:8000/metrics
```

See the **[Performance Optimization Guide](performance.md)** for details.

---

## Step 11: Explore Documentation

Now that you're up and running, explore:

- **[Performance Guide](performance.md)** - Memory optimization and execution profiling
- **[Indicators Guide](indicators.md)** - Learn about available indicators
- **[Backtesting Guide](backtest.md)** - Advanced backtesting features
- **[Execution Guide](execution.md)** - Live trading setup
- **[Extending TradePulse](extending.md)** - Add custom indicators and strategies
- **[Integration API](integration-api.md)** - Connect to exchanges

---

## Next Steps

### For Development

1. Read [CONTRIBUTING.md](../CONTRIBUTING.md)
2. Set up your IDE
3. Run the full test suite:
   ```bash
   pytest tests/ \
     --cov=core --cov=backtest --cov=execution \
     --cov-config=configs/quality/critical_surface.coveragerc \
     --cov-report=term-missing --cov-report=xml

   python -m tools.coverage.guardrail \
     --config configs/quality/critical_surface.toml \
     --coverage coverage.xml
   ```
4. Explore the codebase

### For Trading

1. Get API keys from your exchange
2. Set up paper trading first
3. Test strategies thoroughly
4. Start with small position sizes
5. Monitor closely

### For Learning

1. Read the [Architecture Documentation](ARCHITECTURE.md)
2. Study the included examples
3. Experiment with different indicators
4. Join the community discussions

---

## Quick Reference

### Common Commands

```bash
# Analyze data
python -m interfaces.cli analyze --csv data.csv

# Run backtest
python -m interfaces.cli backtest --csv data.csv --train-window 500

# Run tests
pytest tests/

# Run linter
ruff check .

# Format code
black .

# Type checking
mypy core/
```

### Project Structure

```
TradePulse/
├── core/               # Core trading logic
│   ├── indicators/     # Technical indicators
│   ├── agent/          # Strategy optimization
│   ├── data/           # Data handling
│   └── phase/          # Regime detection
├── backtest/           # Backtesting engine
├── execution/          # Order execution
├── interfaces/         # CLI and APIs
├── tests/              # Test suite
└── docs/               # Documentation
```

---

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError`:
```bash
# Ensure you're in the project directory
cd /path/to/TradePulse

# Install in editable mode
pip install -e .
```

### Missing Dependencies

If a package is missing:
```bash
# Reinstall all dependencies (dev extras include runtime stack)
pip install -r requirements-dev.lock
```

### Permission Errors

On Linux/macOS:
```bash
# Inspect available helper commands
python -m scripts --help
```

### Need More Help?

- Check [Troubleshooting Guide](troubleshooting.md)
- Read [FAQ](faq.md)
- Open an issue on GitHub

---

## Summary

You've successfully:
- ✅ Installed TradePulse
- ✅ Verified the installation
- ✅ Analyzed market data
- ✅ Run a backtest
- ✅ Explored indicators
- ✅ Created a custom strategy

**Ready to dive deeper?** Check out the [full documentation](index.md).

---

**Time to complete:** ~5-10 minutes  
**Difficulty:** Beginner  
**Last Updated:** 2025-01-01
