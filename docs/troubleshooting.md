# Troubleshooting Guide

Common issues and their solutions when working with TradePulse.

---

## Table of Contents

- [Installation Issues](#installation-issues)
- [Import Errors](#import-errors)
- [Data Issues](#data-issues)
- [Indicator Errors](#indicator-errors)
- [Backtesting Problems](#backtesting-problems)
- [Execution Issues](#execution-issues)
- [Performance Problems](#performance-problems)
- [Testing Issues](#testing-issues)
- [Docker Issues](#docker-issues)

---

## Installation Issues

### pip install fails with "No matching distribution"

**Problem:**
```
ERROR: Could not find a version that satisfies the requirement package_name
```

**Solutions:**

1. Update pip:
```bash
pip install --upgrade pip
```

2. Check Python version:
```bash
python --version  # Should be 3.11+
```

3. Try installing packages individually:
```bash
pip install numpy scipy pandas networkx
```

### Cannot install scipy on macOS

**Problem:**
```
error: command 'clang' failed
```

**Solution:**

Install Xcode command line tools:
```bash
xcode-select --install
```

Or use conda:
```bash
conda install scipy
```

### ImportError: No module named 'ruff'

**Problem:**
Development dependencies not installed.

**Solution:**
```bash
pip install -r requirements-dev.lock
```

---

## Import Errors

### ModuleNotFoundError: No module named 'core'

**Problem:**
Python can't find the TradePulse modules.

**Solutions:**

1. Add project to PYTHONPATH:
```bash
export PYTHONPATH=/path/to/TradePulse:$PYTHONPATH
```

2. Install in development mode:
```bash
cd /path/to/TradePulse
pip install -e .
```

3. Run from project root:
```bash
cd /path/to/TradePulse
python -m interfaces.cli analyze --csv sample.csv
```

### ImportError: cannot import name 'compute_phase_gpu'

**Problem:**
GPU acceleration not available (CuPy not installed).

**Solution:**

Either install CuPy:
```bash
pip install cupy-cuda11x  # Replace with your CUDA version
```

Or use CPU version:
```python
from core.indicators.kuramoto import compute_phase  # No GPU
phases = compute_phase(prices)
```

---

## Data Issues

### CSV file cannot be read

**Problem:**
```
FileNotFoundError: [Errno 2] No such file or directory: 'data.csv'
```

**Solutions:**

1. Use absolute path:
```bash
python -m interfaces.cli analyze --csv /full/path/to/data.csv
```

2. Check file exists:
```bash
ls -la data.csv
```

3. Check file permissions:
```bash
chmod 644 data.csv
```

### ValueError: could not convert string to float

**Problem:**
Invalid data in CSV file.

**Solutions:**

1. Check CSV format:
```csv
timestamp,close,volume
2024-01-01 00:00:00,50000,100
2024-01-01 00:01:00,50100,150
```

2. Remove invalid rows:
```python
import pandas as pd
df = pd.read_csv('data.csv')
df = df[pd.to_numeric(df['close'], errors='coerce').notna()]
df.to_csv('cleaned_data.csv', index=False)
```

3. Specify column types:
```python
df = pd.read_csv('data.csv', dtype={'close': float, 'volume': float})
```

### Data gaps causing errors

**Problem:**
Missing data points break indicator calculations.

**Solutions:**

1. Fill gaps with forward fill:
```python
df = df.fillna(method='ffill')
```

2. Interpolate missing values:
```python
df = df.interpolate(method='linear')
```

3. Remove rows with missing data:
```python
df = df.dropna()
```

---

## Indicator Errors

### ValueError: Need at least X data points

**Problem:**
Insufficient historical data for indicator calculation.

**Solutions:**

1. Increase data size:
```python
# Need more historical data
prices = prices[-window*2:]  # Use more data
```

2. Reduce window size:
```python
indicator = RSI(period=7)  # Instead of 14
```

3. Check minimum requirements:
```python
min_required = indicator.min_required_samples()
if len(prices) < min_required:
    raise ValueError(f"Need {min_required} samples, got {len(prices)}")
```

### RuntimeWarning: divide by zero

**Problem:**
Zero or near-zero values in calculation.

**Solutions:**

1. Add epsilon for numerical stability:
```python
result = numerator / (denominator + 1e-10)
```

2. Check for zero before division:
```python
if denominator == 0:
    return 0.0
return numerator / denominator
```

3. Use numpy's safe division:
```python
result = np.divide(
    numerator,
    denominator,
    out=np.zeros_like(numerator),
    where=denominator != 0,
)
```

### Indicator returns NaN or inf

**Problem:**
Invalid mathematical operations.

**Solutions:**

1. Validate input data:
```python
assert np.all(np.isfinite(prices)), "Prices contain NaN or inf"
assert np.all(prices > 0), "Prices must be positive"
```

2. Replace invalid values:
```python
prices = np.nan_to_num(prices, nan=0.0, posinf=0.0, neginf=0.0)
```

3. Check calculation logic:
```python
# Debug step by step
print(f"Input: {prices}")
print(f"Intermediate: {intermediate_value}")
print(f"Result: {result}")
```

---

## Backtesting Problems

### Backtest runs very slowly

**Problem:**
Large datasets or complex indicators.

**Solutions:**

1. Reduce data size:
```python
# Test on smaller subset first
prices = prices[-10000:]  # Last 10k points
```

2. Increase walk-forward window:
```python
# Larger windows = fewer iterations
backtest(train_window=1000, test_window=500)  # Instead of 500/100
```

3. Use multiprocessing:
```python
from multiprocessing import Pool

with Pool(processes=4) as pool:
    results = pool.map(backtest_symbol, symbols)
```

4. Profile to find bottlenecks:
```bash
python -m cProfile -o profile.stats backtest.py
python -m pstats profile.stats
# Then type: sort cumulative, stats 20
```

### Unrealistic backtest results

**Problem:**
Overfitting or look-ahead bias.

**Solutions:**

1. Use walk-forward validation:
```python
# Train on past, test on future
backtest(train_window=500, test_window=100)
```

2. Add realistic costs:
```python
backtest(
    commission=0.001,  # 0.1% commission
    slippage=0.0005,   # 0.05% slippage
)
```

3. Test on out-of-sample data:
```python
# Split data: 70% in-sample, 30% out-of-sample
split = int(len(prices) * 0.7)
in_sample = prices[:split]
out_sample = prices[split:]
```

4. Check for look-ahead bias:
```python
# Make sure you're not using future information
assert all(t1 < t2 for t1, t2 in zip(train_dates, test_dates))
```

### Orders not filling correctly

**Problem:**
Order execution logic issues.

**Solutions:**

1. Check order logic:
```python
# Verify order parameters
print(f"Order: {order.side} {order.quantity} @ {order.price}")
```

2. Ensure sufficient balance:
```python
required = order.quantity * order.price
if balance < required:
    raise ValueError(f"Insufficient balance: {balance} < {required}")
```

3. Check market availability:
```python
if current_price is None:
    logger.warning("No market price available")
    return
```

---

## Execution Issues

### ConnectionError: Failed to connect to exchange

**Problem:**
Cannot connect to exchange API.

**Solutions:**

1. Check internet connection:
```bash
ping api.binance.com
```

2. Verify API credentials:
```python
# Check credentials are set
assert os.getenv("API_KEY"), "API_KEY not set"
assert os.getenv("API_SECRET"), "API_SECRET not set"
```

3. Check API endpoint:
```python
# Ensure using correct endpoint
if testnet:
    url = "https://testnet.binance.vision"
else:
    url = "https://api.binance.com"
```

4. Check rate limits:
```python
# Implement rate limiting
@sleep_and_retry
@limits(calls=10, period=60)
def api_call():
    pass
```

### OrderError: Insufficient balance

**Problem:**
Not enough funds for order.

**Solutions:**

1. Check account balance:
```python
balance = adapter.get_balance()
print(f"Available: {balance}")
```

2. Reduce position size:
```python
# Use smaller fraction of balance
size = balance * 0.01  # 1% of balance
```

3. Check reserved balance:
```python
# Account for open orders
available = total_balance - reserved_for_orders
```

### Order rejected by exchange

**Problem:**
Exchange rejects order.

**Solutions:**

1. Check order parameters:
```python
# Verify all required fields
assert order.symbol, "Symbol required"
assert order.quantity > 0, "Quantity must be positive"
assert order.price > 0, "Price must be positive"
```

2. Check minimum order size:
```python
# Most exchanges have minimums
min_notional = 10  # $10 minimum
if order.quantity * order.price < min_notional:
    raise ValueError(f"Order below minimum: {min_notional}")
```

3. Check price precision:
```python
# Round to exchange precision
price = round(price, exchange.price_precision)
quantity = round(quantity, exchange.quantity_precision)
```

---

## Performance Problems

### High memory usage

**Problem:**
Process uses too much memory.

**Solutions:**

1. **Use float32 precision** (NEW - 50% memory reduction):
```python
from core.indicators.entropy import EntropyFeature
from core.indicators.hurst import HurstFeature

# Memory-efficient features
entropy_feat = EntropyFeature(bins=30, use_float32=True)
hurst_feat = HurstFeature(use_float32=True)

# Or for preprocessing
from core.data.preprocess import scale_series, normalize_df, normalize_numeric_columns
scaled = scale_series(data, use_float32=True)
df_opt = normalize_df(df, use_float32=True)
scaled_frame = normalize_numeric_columns(df, exclude=["ts"], use_float32=True)
```

2. **Process data in chunks** (NEW):
```python
# Process large arrays in chunks
from core.indicators.entropy import entropy
from core.indicators.ricci import mean_ricci, build_price_graph

# Entropy with chunking (for 10M+ points)
H = entropy(large_data, bins=50, chunk_size=100_000, use_float32=True)

# Ricci with chunking (for large graphs)
G = build_price_graph(prices)
ricci = mean_ricci(G, chunk_size=1000, use_float32=True)
```

3. Delete intermediate results:
```python
result = compute_expensive_indicator(prices)
use_result(result)
del result  # Free memory
gc.collect()  # Force garbage collection
```

4. Profile memory usage:
```bash
python -m memory_profiler backtest.py
```

**See also:** [Performance Optimization Guide](performance.md#memory-optimization)

### CPU usage too high

**Problem:**
Process uses 100% CPU continuously.

**Solutions:**

1. **Enable structured logging to find bottlenecks** (NEW):
```python
from core.utils.logging import configure_logging

# Enable JSON logging
configure_logging(level="INFO", use_json=True)

# All optimized functions automatically log execution time
result = entropy(data, bins=30)
# Check logs for duration_seconds
```

2. Add sleep to loops:
```python
while True:
    process_tick()
    time.sleep(0.001)  # Yield CPU
```

3. Optimize hot paths:
```python
# Use numpy instead of loops
# Bad:
result = [expensive_calc(x) for x in prices]

# Good:
result = np.array([expensive_calc(x) for x in prices])
```

4. Use profiling to find bottlenecks:
```bash
python -m cProfile -s cumulative backtest.py | head -20
```

### Indicator calculation too slow

**Problem:**
Complex indicators take too long.

**Solutions:**

1. **Use GPU acceleration** (NEW - requires CuPy):
```python
from core.indicators.kuramoto import compute_phase_gpu

# Automatically uses GPU if available, falls back to CPU
phases = compute_phase_gpu(large_data)

# Install CuPy for GPU support:
# pip install cupy-cuda11x  # For CUDA 11.x
# pip install cupy-cuda12x  # For CUDA 12.x
```

2. **Enable Prometheus metrics** (NEW - for production monitoring):
```python
from core.utils.metrics import get_metrics_collector, start_metrics_server

# Start metrics server
start_metrics_server(port=8000)

# Metrics automatically collected for all features
entropy_feat = EntropyFeature(bins=30)
result = entropy_feat.transform(data)

# View metrics at http://localhost:8000/metrics
```

3. Vectorize calculations:
```python
# Use numpy operations instead of loops
result = np.mean(prices[-window:])  # Fast
# Instead of: sum(prices[-window:]) / window  # Slow
```

2. Cache results:
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def expensive_indicator(prices_tuple):
    # Convert tuple back to array for caching
    prices = np.array(prices_tuple)
    return compute_indicator(prices)
```

3. Use compiled extensions:
```python
# Consider Cython or Numba for hot paths
from numba import jit

@jit(nopython=True)
def fast_indicator(prices):
    # Compiled to machine code
    pass
```

---

## Testing Issues

### Tests fail with import errors

**Problem:**
```
ModuleNotFoundError in tests
```

**Solutions:**

1. Install in editable mode:
```bash
pip install -e .
```

2. Run from project root:
```bash
cd /path/to/TradePulse
pytest tests/
```

3. Set PYTHONPATH:
```bash
export PYTHONPATH=.
pytest tests/
```

### Hypothesis tests fail randomly

**Problem:**
Non-deterministic test failures.

**Solutions:**

1. Fix random seed:
```python
import random
import numpy as np

random.seed(42)
np.random.seed(42)
```

2. Increase deadline:
```python
from hypothesis import settings

@settings(deadline=None)
@given(...)
def test_something():
    pass
```

3. Suppress health checks:
```python
from hypothesis import settings, HealthCheck

@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(...)
def test_with_fixture(data, tmp_path):
    pass
```

### Tests timeout

**Problem:**
Tests take too long and timeout.

**Solutions:**

1. Mark slow tests:
```python
import pytest

@pytest.mark.slow
def test_large_dataset():
    pass
```

2. Skip during development:
```bash
pytest tests/ -m "not slow"
```

3. Increase timeout:
```python
@pytest.mark.timeout(60)  # 60 seconds
def test_long_running():
    pass
```

---

## Docker Issues

### docker compose fails to start

**Problem:**
Services won't start.

**Solutions:**

1. Check logs:
```bash
docker compose logs -f
```

2. Check ports not already in use:
```bash
lsof -i :8000  # Check if port is in use
```

3. Rebuild containers:
```bash
docker compose down
docker compose build --no-cache
docker compose up
```

4. Check Docker daemon:
```bash
docker ps  # Should list running containers
sudo systemctl status docker  # On Linux
```

### Permission denied in Docker

**Problem:**
```
PermissionError: [Errno 13] Permission denied
```

**Solutions:**

1. Fix file ownership:
```bash
sudo chown -R $USER:$USER .
```

2. Run with user:
```yaml
# docker-compose.yml
services:
  tradepulse:
    user: "${UID}:${GID}"
```

3. Fix permissions:
```bash
chmod -R 755 scripts/
```

### Docker container exits immediately

**Problem:**
Container starts and immediately stops.

**Solutions:**

1. Check logs:
```bash
docker compose logs tradepulse
```

2. Run interactively:
```bash
docker compose run --rm tradepulse /bin/bash
```

3. Check command:
```yaml
# docker-compose.yml
services:
  tradepulse:
    command: ["python", "-m", "interfaces.cli", "--help"]
```

---

## General Debugging Tips

### Enable debug logging

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Use interactive debugger

```python
# Add breakpoint
import pdb; pdb.set_trace()

# Or use ipdb for better interface
import ipdb; ipdb.set_trace()
```

### Print stack traces

```python
import traceback

try:
    risky_operation()
except Exception as e:
    traceback.print_exc()
    logger.error(f"Operation failed: {e}")
```

### Check versions

```bash
python --version
pip list | grep -E "(numpy|scipy|pandas)"
```

---

## Still Having Issues?

1. Check [FAQ](faq.md)
2. Search [GitHub Issues](https://github.com/neuron7x/TradePulse/issues)
3. Enable debug logging
4. Create minimal reproducible example
5. Open a new issue with:
   - Clear description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details
   - Logs and error messages

---

## Useful Commands

```bash
# Check Python version
python --version

# List installed packages
pip list

# Show package details
pip show package_name

# Verify imports work
python -c "import core; print(core.__file__)"

# Run with verbose output
python -v script.py

# Check file encoding
file -i data.csv

# Monitor resource usage
top
htop

# Check disk space
df -h

# Check memory usage
free -h
```

---

**Last Updated**: 2025-01-01
