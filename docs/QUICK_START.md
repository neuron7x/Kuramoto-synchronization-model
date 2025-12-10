# Quick Start — Golden Path (Research Beta)

**Status: ✅ Guaranteed to work as of 2025-01-01**

This guide provides the fastest path from a fresh repository clone to a working backtest result. Follow these steps exactly for guaranteed reproducibility.

---

## Prerequisites

- **Python 3.11 or 3.12** ([Download](https://www.python.org/downloads/))
- **Git** 2.30+ for version control
- **4 GB RAM** minimum (8 GB recommended)

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
# Upgrade pip first
pip install --upgrade pip

# Install with security constraints (recommended)
pip install -c constraints/security.txt -r requirements.txt

# Optional: Install matplotlib for plot generation
pip install matplotlib
```

Alternatively, use the Makefile:

```bash
make install
```

---

## Step 4: Run the Golden Path Backtest

This is the **guaranteed reproducible** demo:

```bash
make golden-path
```

Or directly:

```bash
PYTHONPATH=. python scripts/golden_path_backtest.py
```

---

## Expected Output

```
============================================================
🌟 TradePulse Golden Path Backtest
============================================================

Status: Research Beta
This is the guaranteed reproducible demo scenario.

📥 Step 1: Generating synthetic market data...
   Generated 1000 price bars
   Price range: $92.13 - $109.16

⚙️  Step 2: Running backtest...
   Backtest completed successfully

📊 Step 3: Results
----------------------------------------
   PnL:           $70.40
   Max Drawdown:  -1.06%
   Total Trades:  123
   Sharpe Ratio:  4.445

💾 Step 4: Saving outputs...
📊 Metrics saved: reports/golden_path/metrics.json
📈 PnL data saved: reports/golden_path/pnl.csv
📉 Plot saved: reports/golden_path/plot.png

============================================================
✅ Golden Path backtest completed successfully!
============================================================
```

---

## Output Files

After running the Golden Path, check `reports/golden_path/`:

| File | Description |
|------|-------------|
| `metrics.json` | Performance metrics (PnL, Sharpe, max drawdown) |
| `pnl.csv` | Equity curve data (step, equity) |
| `plot.png` | Visual equity curve (requires matplotlib) |

### Sample `metrics.json`

```json
{
  "timestamp": "2025-01-01T12:00:00.000000",
  "pnl": 70.40,
  "max_drawdown": -0.0106,
  "trades": 123,
  "sharpe_ratio": 4.445,
  "n_bars": 1000,
  "initial_capital": 100000.0,
  "status": "success"
}
```

---

## What This Proves

When the Golden Path completes successfully, you know:

✅ **Python environment** is correctly configured  
✅ **Core dependencies** are installed  
✅ **Backtest engine** works correctly  
✅ **Data generation** produces valid inputs  
✅ **Output pipeline** saves results properly  

---

## Next Steps

### 1. Explore the Strategy

Open `scripts/golden_path_backtest.py` and study:
- `generate_synthetic_data()` — How data is created
- `simple_momentum_signal()` — The trading strategy
- `save_results()` — How outputs are saved

### 2. Modify the Strategy

Try changing parameters in `simple_momentum_signal()`:
```python
# Current: 20-period lookback
def simple_momentum_signal(prices: np.ndarray, window: int = 20):

# Try: 50-period lookback
def simple_momentum_signal(prices: np.ndarray, window: int = 50):
```

### 3. Use Real Data

Replace synthetic data with your own CSV:
```python
import pandas as pd

# Load your data
df = pd.read_csv('your_data.csv')
prices = df['close'].values
bars = df[['close', 'volume']]
```

### 4. Explore Advanced Features

Once comfortable with the Golden Path, explore:
- [Indicators Guide](indicators.md) — Available technical indicators
- [Backtesting Guide](backtest.md) — Advanced backtest features
- [CLI Reference](tradepulse_cli_reference.md) — Command-line interface

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'numpy'"

Dependencies not installed. Run:
```bash
pip install -c constraints/security.txt -r requirements.txt
```

### "PYTHONPATH issue"

Ensure you're running from the repository root:
```bash
cd /path/to/TradePulse
PYTHONPATH=. python scripts/golden_path_backtest.py
```

### "matplotlib not available"

The plot is optional. Install matplotlib for visualization:
```bash
pip install matplotlib
```

### Need More Help?

- Check [FAQ](faq.md)
- Check [Troubleshooting Guide](troubleshooting.md)
- Open an issue on GitHub

---

## Experimental / Lab Features

The following features are **NOT part of the Golden Path** and may require additional setup:

| Feature | Status | Notes |
|---------|--------|-------|
| Live Trading | 🔬 Lab | Requires exchange API keys |
| GPU Acceleration | 🔬 Lab | Requires CUDA setup |
| HydroBrain v2 | 🔬 Lab | Advanced neural components |
| Reinforcement Learning | 🔬 Lab | Requires additional dependencies |
| TACL (Thermodynamic Control) | 🔬 Lab | Research prototype |
| Kubernetes Deployment | 🔬 Lab | Production infrastructure |

These features are documented separately but are **not guaranteed to work without additional configuration**.

---

## Summary

| Step | Command | Time |
|------|---------|------|
| 1. Clone | `git clone ...` | 30s |
| 2. Venv | `python -m venv .venv && source .venv/bin/activate` | 10s |
| 3. Install | `pip install -c constraints/security.txt -r requirements.txt` | 2-5m |
| 4. Run | `make golden-path` | 10s |

**Total time to first result: ~5 minutes**

---

**Last Updated:** 2025-01-01  
**Status:** Research Beta  
**Guaranteed:** Yes ✅
