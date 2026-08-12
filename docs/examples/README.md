---
owner: dx@geosync
review_cadence: quarterly
last_reviewed: 2026-01-01
---

# Usage Examples

This directory contains practical examples for using GeoSync.

---

## Key Use-Case Quickstarts (requirements.lock compatible)

The quickstarts below are validated against `requirements.lock`, so each listed
dependency is pinned there and compatible with the current lockfile.

| Use-case | Quickstart | Dependencies (version lock) |
| --- | --- | --- |
| Market regime snapshot (core indicators) | `python examples/quick_start.py --seed 7 --num-points 400` | `numpy==2.3.3`, `pandas==2.3.3` |
| Strategy backtest (GeoSync HPC) | `python examples/neuro_geosync_backtest.py` | `numpy==2.3.3`, `pandas==2.3.3` |
| Real-time style snapshot (signal generation) | `python examples/neuro_geosync_snapshot.py` | `numpy==2.3.3`, `pandas==2.3.3` |
| Integrated risk management pipeline | `python examples/integrated_risk_management_example.py` | `numpy==2.3.3` |

These same quickstarts are used for CI smoke tests so compatibility with
`requirements.lock` stays enforced.

---

## Example Catalog (Seeds + Dependencies)

All example scripts are indexed in [`docs/examples/examples_manifest.yaml`](examples_manifest.yaml).
The manifest lists deterministic seeds and the pinned dependencies (from
`requirements.lock`) required by each example.

---

## API & Integration Examples

| Example | Description |
| --- | --- |
| [`quickstart_signal_fetch.md`](quickstart_signal_fetch.md) | Fetch market signals with signed requests. |
| [`prediction_submission.md`](prediction_submission.md) | Submit async predictions with idempotency. |
| [`webhook_consumer.md`](webhook_consumer.md) | Consume `signal.published` and `prediction.completed` webhooks. |
| [`sdk_integration.md`](sdk_integration.md) | SDK wrapper patterns for GeoSync API. |

---

## Quick Examples

### 1. Basic Analysis

```python
import numpy as np
import pandas as pd
from core.indicators.kuramoto import compute_phase, kuramoto_order
from core.indicators.entropy import entropy
from core.indicators.ricci import build_price_graph, mean_ricci

# Load data
df = pd.read_csv('sample.csv')
prices = df['close'].to_numpy()

# Compute Kuramoto order
phases = compute_phase(prices)
R = kuramoto_order(phases[-200:])
print(f"Kuramoto Order: {R:.3f}")

# Compute entropy
H = entropy(prices[-200:])
print(f"Entropy: {H:.3f}")

# Compute Ricci curvature
G = build_price_graph(prices[-200:], delta=0.005)
kappa = mean_ricci(G)
print(f"Mean Ricci Curvature: {kappa:.3f}")
```

### 2. Simple Backtest

```python
from backtest.engine import walk_forward
import pandas as pd
import numpy as np

# Load data
df = pd.read_csv('sample.csv')
prices = df['close'].to_numpy()

# Define signal function
def moving_average_crossover(prices: np.ndarray, window: int = 50) -> np.ndarray:
    """Generate signals based on MA crossover."""
    signals = np.zeros(len(prices))
    
    fast = pd.Series(prices).rolling(window).mean()
    slow = pd.Series(prices).rolling(window*2).mean()
    
    signals[fast > slow] = 1  # Buy
    signals[fast < slow] = -1  # Sell
    
    return signals

# Run backtest
results = walk_forward(
    prices=prices,
    signal_func=moving_average_crossover,
    train_window=500,
    test_window=100,
    initial_capital=10000.0
)

print(f"Total Return: {results['total_return']:.2%}")
print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
print(f"Max Drawdown: {results['max_drawdown']:.2%}")
print(f"Number of Trades: {results['num_trades']}")
```

### 3. Live Data Stream

```python
from core.data.ingestion import DataIngestor, Ticker
from core.indicators.kuramoto import compute_phase, kuramoto_order
import numpy as np

# Collect ticks
ticks = []

def on_tick(tick: Ticker):
    ticks.append(tick.price)
    
    # Compute indicator every 100 ticks
    if len(ticks) >= 200:
        prices = np.array(ticks[-200:])
        phases = compute_phase(prices)
        R = kuramoto_order(phases)
        print(f"{tick.symbol} @ {tick.ts}: R = {R:.3f}")

# Ingest from CSV (demo)
ingestor = DataIngestor()
ingestor.historical_csv('sample.csv', on_tick)
```

### 4. Custom Indicator

```python
from core.indicators.base import BaseFeature, FeatureResult
import numpy as np

class SimpleMovingAverage(BaseFeature):
    """Simple moving average indicator."""
    
    def __init__(self, name: str = "sma", period: int = 20):
        super().__init__(name, period=period)
        self.period = period
    
    def transform(self, data: np.ndarray) -> FeatureResult:
        """Compute SMA."""
        self.validate_input(data)
        
        if len(data) < self.period:
            raise ValueError(f"Need at least {self.period} data points")
        
        sma = np.mean(data[-self.period:])
        
        return FeatureResult(
            value=float(sma),
            metadata={"period": self.period, "n_samples": len(data)},
            name=self.name
        )

# Use it
import pandas as pd
df = pd.read_csv('sample.csv')
prices = df['close'].to_numpy()

sma = SimpleMovingAverage(period=50)
result = sma.transform(prices)
print(f"SMA(50): {result.value:.2f}")
```

### 5. Risk Management

Use ``execution.order.position_sizing(balance, risk, price, max_leverage=5.0)``
to convert account risk into base units. The helper enforces leverage caps while
keeping your per-trade loss aligned with ``balance * risk``.

```python
from execution.order import position_sizing

# Account settings
balance = 10000.0
risk_per_trade = 0.01  # 1% risk

# Current trade
entry_price = 50000.0
stop_loss_pct = 0.02  # 2% stop loss

# Calculate position size
size = position_sizing(
    balance=balance,
    risk=risk_per_trade,
    price=entry_price,
)

# Manually derive the stop loss price for a long position.
# When risking ``stop_loss_pct`` of the entry price, the protective order
# sits ``stop_loss_pct`` below ``entry_price``. For short trades the sign flips.
stop_loss_price = entry_price * (1 - stop_loss_pct)

print(f"Position Size: {size:.6f}")
print(f"Stop Loss: ${stop_loss_price:.2f}")
print(f"Risk Amount: ${balance * risk_per_trade:.2f}")
```

The same approach works for short positions by adding the percentage to the
entry price instead of subtracting it: ``entry_price * (1 + stop_loss_pct)``.
If your broker specifies stop losses in ticks or currency instead of
percentages, convert the value to a price offset before applying the formula.

### 6. Strategy Optimization

```python
from core.agent.strategy import Strategy
from core.agent.bandits import GeneticOptimizer
import numpy as np

# Define parameter space
param_space = {
    'window': (10, 100),
    'threshold': (0.5, 0.9),
    'risk': (0.01, 0.05)
}

# Optimize
optimizer = GeneticOptimizer(
    population_size=50,
    generations=20,
    mutation_rate=0.1
)

best_params = optimizer.optimize(
    prices=prices,
    param_space=param_space,
    fitness_func=lambda p, params: backtest_strategy(p, params)
)

print(f"Best Parameters: {best_params}")
```

### 7. Metrics Calculation

Combine lightweight objective helpers with the comprehensive backtest
performance report to inspect only the metrics that are actually exposed by
the library (`backtest.performance.PerformanceReport`).

```python
import numpy as np
from core.strategies.objectives import sharpe_ratio
from backtest.performance import compute_performance_metrics

# Sample returns for a strategy (daily percentage changes)
returns = np.array([0.02, -0.01, 0.03, -0.02, 0.04, 0.01, -0.01])
initial_capital = 10_000.0

# Build an equity curve and simple PnL series for the performance report
equity_curve = initial_capital * np.cumprod(1 + returns)
pnl = initial_capital * returns

# Objective helpers live under core.strategies.objectives
basic_sharpe = sharpe_ratio(returns, risk_free=0.02)

# Full performance analytics are exposed by backtest.performance
report = compute_performance_metrics(
    equity_curve=equity_curve,
    pnl=pnl,
    initial_capital=initial_capital,
    risk_free_rate=0.02,
)
metrics = report.as_dict()

def display(name: str, value: float | None, scale: float = 1.0, suffix: str = "") -> None:
    if value is None:
        print(f"{name}: n/a")
    else:
        print(f"{name}: {scale * value:.2f}{suffix}")

print(f"Objective Sharpe Ratio: {basic_sharpe:.2f}")
display("Sharpe Ratio", metrics["sharpe_ratio"])
display("Sortino Ratio", metrics["sortino_ratio"])
display("Probabilistic Sharpe", metrics["probabilistic_sharpe_ratio"])
display("Max Drawdown", metrics["max_drawdown"], scale=100 / initial_capital, suffix="%")
display("Hit Ratio", metrics["hit_ratio"], scale=100, suffix="%")
```

### 8. Multi-Indicator Analysis

```python
from core.indicators.kuramoto import KuramotoOrder
from core.indicators.entropy import Entropy
from core.indicators.ricci import RicciCurvature
from core.indicators.hurst import HurstExponent
from core.indicators.base import FeatureBlock

# Create indicator block
block = FeatureBlock("market_regime")
block.add_feature(KuramotoOrder(window=200))
block.add_feature(Entropy(bins=50))
block.add_feature(RicciCurvature(delta=0.005))
block.add_feature(HurstExponent())

# Process data
import pandas as pd
df = pd.read_csv('sample.csv')
prices = df['close'].to_numpy()

results = block.transform_all(prices)

for name, result in results.items():
    print(f"{name}: {result.value:.3f}")
```

### 9. Phase Detection

```python
from core.phase.detector import phase_flags, composite_transition
from core.indicators.kuramoto import compute_phase, kuramoto_order
from core.indicators.entropy import entropy, delta_entropy
from core.indicators.ricci import build_price_graph, mean_ricci
import numpy as np
import pandas as pd

# Load data
df = pd.read_csv('sample.csv')
prices = df['close'].to_numpy()

# Compute indicators
phases = compute_phase(prices)
R = kuramoto_order(phases[-200:])
H = entropy(prices[-200:])
dH = delta_entropy(prices, window=200)
G = build_price_graph(prices[-200:], delta=0.005)
kappa = mean_ricci(G)

# Detect phase
phase = phase_flags(R, dH, kappa, H)
transition = composite_transition(R, dH, kappa)

print(f"Market Phase: {phase}")
print(f"Transition Signal: {transition}")
```

### 10. Complete Trading System

```python
# complete_system.py
import pandas as pd
import numpy as np
from core.indicators.kuramoto import compute_phase, kuramoto_order
from core.indicators.entropy import entropy
from backtest.engine import walk_forward
from execution.risk import position_sizing

class TradingSystem:
    """Complete trading system."""
    
    def __init__(self, balance: float = 10000.0):
        self.balance = balance
        self.positions = []
    
    def analyze(self, prices: np.ndarray) -> dict:
        """Analyze market conditions."""
        phases = compute_phase(prices)
        R = kuramoto_order(phases[-200:])
        H = entropy(prices[-200:])
        
        return {"R": R, "H": H}
    
    def generate_signal(self, analysis: dict) -> str:
        """Generate trading signal."""
        if analysis["R"] > 0.7 and analysis["H"] < 2.0:
            return "buy"
        elif analysis["R"] < 0.3 or analysis["H"] > 3.0:
            return "sell"
        return "hold"
    
    def execute_trade(self, signal: str, price: float):
        """Execute trade with risk management."""
        if signal == "buy":
            size = position_sizing(
                self.balance,
                risk=0.01,
                price=price,
                stop_loss_pct=0.02
            )
            self.positions.append({"side": "long", "size": size, "price": price})
        elif signal == "sell" and self.positions:
            # Close positions
            self.positions = []
    
    def run(self, data_file: str):
        """Run complete system."""
        df = pd.read_csv(data_file)
        prices = df['close'].to_numpy()
        
        for i in range(200, len(prices)):
            window = prices[i-200:i]
            analysis = self.analyze(window)
            signal = self.generate_signal(analysis)
            self.execute_trade(signal, prices[i])

# Run system
system = TradingSystem(balance=10000.0)
system.run('sample.csv')
```

---

## More Examples

For more detailed examples, see:
- [Extending GeoSync](../extending.md)
- [Integration API](../integration-api.md)
- [Developer Scenarios](../scenarios.md)

---

## Running Examples

```bash
# Save example to file
cat > example.py << 'EOF'
# ... example code ...
EOF

# Run example
python example.py
```

---

**Last Updated**: 2025-12-28
