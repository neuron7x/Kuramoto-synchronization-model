# Developer Scenarios

Common development tasks and workflows for TradePulse contributors.

---

## Table of Contents

- [Scenario Templates](#scenario-templates)
- [Setting Up Development Environment](#setting-up-development-environment)
- [Adding a New Indicator](#adding-a-new-indicator)
- [Creating a Trading Strategy](#creating-a-trading-strategy)
- [Implementing a Data Source](#implementing-a-data-source)
- [Adding Exchange Support](#adding-exchange-support)
- [Writing Tests](#writing-tests)
- [Debugging Issues](#debugging-issues)
- [Performance Optimization](#performance-optimization)
- [Documentation](#documentation)
- [Release Process](#release-process)

---

## Scenario Templates

Use the [Scenario Template](scenario_template.md) alongside the web-based **Scenario Studio** (`apps/web`) when drafting new workflows. The UI now offers:

- **Input sanity checkers** – invalid balances, risk allocations, or timeframe formats are flagged before you export JSON.
- **Auto-generated JSON snippets** – copy the preview directly into documentation or configuration files once all warnings clear.
- **Template presets** – choose from breakout, mean-reversion, or volatility archetypes as a starting point.

> 🛡️ Pair these guardrails with the CLI sanity checks (`cli/amm_cli.py`) so malformed CSV feeds or unsafe metrics never reach production pipelines.

---

## Setting Up Development Environment

### Initial Setup

```bash
# Clone repository
git clone https://github.com/neuron7x/TradePulse.git
cd TradePulse

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies (dev extras include runtime stack)
pip install -r requirements-dev.lock

# Install pre-commit hooks
pre-commit install

# Verify setup
pytest tests/ -v
```

### IDE Configuration

**VS Code (.vscode/settings.json):**
```json
{
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "black",
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests"],
  "editor.formatOnSave": true
}
```

**PyCharm:**
- Set Python interpreter to `.venv/bin/python`
- Enable pytest as test runner
- Configure ruff as external tool
- Set line length to 100

---

## Adding a New Indicator

### Scenario: Add RSI Indicator

**1. Create indicator file:**

```bash
touch core/indicators/rsi.py
```

**2. Implement indicator:**

```python
# core/indicators/rsi.py
"""Relative Strength Index indicator."""

import numpy as np
from .base import BaseFeature, FeatureResult

class RSI(BaseFeature):
    """RSI indicator implementation."""
    
    def __init__(self, name: str = "rsi", period: int = 14):
        super().__init__(name, period=period)
        self.period = period
    
    def transform(self, data: np.ndarray) -> FeatureResult:
        """Compute RSI."""
        self.validate_input(data)
        
        if len(data) < self.period + 1:
            raise ValueError(f"Need {self.period + 1} samples")
        
        deltas = np.diff(data)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-self.period:])
        avg_loss = np.mean(losses[-self.period:])
        
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        return FeatureResult(
            value=float(rsi),
            metadata={"period": self.period},
            name=self.name
        )
```

**3. Add to __init__.py:**

```python
# core/indicators/__init__.py
from .rsi import RSI

__all__ = [..., "RSI"]
```

**4. Write tests:**

```python
# tests/unit/test_rsi.py
import numpy as np
import pytest
from core.indicators.rsi import RSI

def test_rsi_basic():
    rsi = RSI(period=14)
    prices = np.linspace(100, 110, 20)
    result = rsi.transform(prices)
    assert 0 <= result.value <= 100

def test_rsi_overbought():
    rsi = RSI(period=5)
    prices = np.array([100, 105, 110, 115, 120, 125])
    result = rsi.transform(prices)
    assert result.value > 70
```

**5. Run tests:**

```bash
pytest tests/unit/test_rsi.py -v
```

**6. Add documentation:**

```python
# Update docs/indicators.md with RSI description
```

**7. Commit:**

```bash
git add core/indicators/rsi.py tests/unit/test_rsi.py
git commit -m "feat(indicators): add RSI indicator"
```

---

## Creating a Trading Strategy

### Scenario: Implement Mean Reversion Strategy

**1. Create strategy file:**

```bash
touch core/strategies/mean_reversion.py
```

**2. Implement strategy:**

```python
# core/strategies/mean_reversion.py
from core.agent.strategy import BaseStrategy, Signal
from core.indicators.rsi import RSI
import numpy as np

class MeanReversionStrategy(BaseStrategy):
    """Buy oversold, sell overbought."""
    
    def __init__(self, name: str = "mean_reversion", parameters: dict = None):
        default_params = {
            "rsi_period": 14,
            "oversold": 30,
            "overbought": 70
        }
        if parameters:
            default_params.update(parameters)
        super().__init__(name, default_params)
        self.rsi = RSI(period=self.parameters["rsi_period"])
    
    def generate_signal(self, prices: np.ndarray, indicators: dict) -> Signal:
        """Generate trading signal."""
        result = self.rsi.transform(prices)
        rsi_value = result.value
        
        if rsi_value < self.parameters["oversold"]:
            return Signal(
                action="buy",
                confidence=(self.parameters["oversold"] - rsi_value) / self.parameters["oversold"],
                metadata={"rsi": rsi_value}
            )
        elif rsi_value > self.parameters["overbought"]:
            return Signal(
                action="sell",
                confidence=(rsi_value - self.parameters["overbought"]) / (100 - self.parameters["overbought"]),
                metadata={"rsi": rsi_value}
            )
        else:
            return Signal(action="hold", confidence=0.0, metadata={"rsi": rsi_value})
```

**3. Backtest strategy:**

```python
# backtest_mean_reversion.py
from core.strategies.mean_reversion import MeanReversionStrategy
from backtest.engine import walk_forward
import pandas as pd

df = pd.read_csv('sample.csv')
prices = df['close'].to_numpy()

strategy = MeanReversionStrategy()

def signal_func(prices, window):
    signal = strategy.generate_signal(prices, {})
    if signal.action == "buy":
        return 1
    elif signal.action == "sell":
        return -1
    return 0

results = walk_forward(prices, signal_func, 500, 100, 10000.0)
print(f"Sharpe: {results['sharpe_ratio']:.2f}")
print(f"Return: {results['total_return']:.2%}")
```

**4. Optimize parameters:**

```python
# Use genetic algorithm
from core.agent.strategy import optimize_strategy

best_params = optimize_strategy(
    strategy_class=MeanReversionStrategy,
    prices=prices,
    param_ranges={
        "rsi_period": (7, 21),
        "oversold": (20, 40),
        "overbought": (60, 80)
    }
)
```

---

## Implementing a Data Source

### Scenario: Add Binance WebSocket Source

**1. Create source file:**

```python
# core/data/binance_source.py
import websocket
import json
from datetime import datetime, timezone
from core.data.ingestion import DataSource, Ticker

class BinanceWebSocketSource(DataSource):
    """Binance WebSocket data source."""
    
    def __init__(self, testnet: bool = True):
        self.testnet = testnet
        self.ws = None
        self.callbacks = {}
    
    def connect(self) -> None:
        url = "wss://testnet.binance.vision/ws" if self.testnet else "wss://stream.binance.com:9443/ws"
        self.ws = websocket.WebSocketApp(
            url,
            on_message=self._on_message,
            on_error=self._on_error
        )
    
    def subscribe(self, symbol: str, callback):
        self.callbacks[symbol.lower()] = callback
        sub_msg = {
            "method": "SUBSCRIBE",
            "params": [f"{symbol.lower()}@trade"],
            "id": 1
        }
        self.ws.send(json.dumps(sub_msg))
    
    def _on_message(self, ws, message):
        data = json.loads(message)
        if "e" in data and data["e"] == "trade":
            tick = Ticker.create(
                symbol=data["s"],
                venue="BINANCE",
                price=float(data["p"]),
                volume=float(data["q"]),
                timestamp=datetime.fromtimestamp(data["T"] / 1000, tz=timezone.utc),
            )
            if data["s"].lower() in self.callbacks:
                self.callbacks[data["s"].lower()](tick)
```

**2. Test data source:**

```python
# Test connection
source = BinanceWebSocketSource(testnet=True)
source.connect()

def on_tick(tick):
    print(f"{tick.symbol}: {tick.price}")

source.subscribe("BTCUSDT", on_tick)
```

---

## Adding Exchange Support

### Scenario: Add Coinbase Pro Support

**1. Create adapter:**

```python
# execution/adapters/coinbase.py
from execution.order import ExecutionAdapter, Order
import cbpro

class CoinbaseAdapter(ExecutionAdapter):
    """Coinbase Pro execution adapter."""
    
    def connect(self, credentials: dict):
        self.client = cbpro.AuthenticatedClient(
            credentials["api_key"],
            credentials["api_secret"],
            credentials["passphrase"]
        )
    
    def place_order(self, order: Order) -> Order:
        result = self.client.place_market_order(
            product_id=order.symbol,
            side=order.side.value,
            size=order.quantity
        )
        order.order_id = result["id"]
        return order
```

**2. Add tests:**

```python
# tests/unit/test_coinbase_adapter.py
def test_coinbase_connect():
    adapter = CoinbaseAdapter()
    adapter.connect({
        "api_key": "test_key",
        "api_secret": "test_secret",
        "passphrase": "test_pass"
    })
    assert adapter.client is not None
```

---

## Writing Tests

### Unit Test Pattern

```python
# tests/unit/test_feature.py
import pytest
from core.feature import MyFeature

def test_feature_basic():
    """Test basic functionality."""
    feature = MyFeature()
    result = feature.process(input_data)
    assert result == expected

def test_feature_edge_case():
    """Test edge case."""
    feature = MyFeature()
    with pytest.raises(ValueError):
        feature.process(invalid_input)

@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
])
def test_feature_multiple_inputs(input, expected):
    """Test multiple inputs."""
    feature = MyFeature()
    assert feature.process(input) == expected
```

### Property-Based Test

```python
from hypothesis import given, strategies as st

@given(
    prices=st.lists(st.floats(min_value=1.0, max_value=1000.0), min_size=20)
)
def test_indicator_properties(prices):
    """Test indicator properties."""
    indicator = MyIndicator()
    result = indicator.transform(np.array(prices))
    assert 0 <= result.value <= 100
```

### Integration Test

```python
def test_full_pipeline(tmp_path):
    """Test complete workflow."""
    # Create test data
    data_file = tmp_path / "test.csv"
    data_file.write_text("timestamp,close\n2024-01-01,100\n")
    
    # Run analysis
    result = analyze_file(str(data_file))
    
    # Verify results
    assert "indicators" in result
    assert result["status"] == "success"
```

---

## Debugging Issues

### Enable Debug Logging

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.debug("Debug information here")
```

### Use Debugger

```python
# Add breakpoint
import pdb; pdb.set_trace()

# Or use ipdb
import ipdb; ipdb.set_trace()
```

### Profile Performance

```bash
# Profile execution
python -m cProfile -o profile.stats script.py

# Analyze results
python -m pstats profile.stats
>>> sort cumulative
>>> stats 20
```

---

## Performance Optimization

### Vectorize Operations

```python
# Bad: Loop
result = []
for price in prices:
    result.append(price * 2)

# Good: Vectorized
result = prices * 2
```

### Use Caching

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def expensive_calculation(data_tuple):
    return compute(np.array(data_tuple))
```

### Profile Memory

```bash
python -m memory_profiler script.py
```

---

## Documentation

### Docstring Format

```python
def function(arg1: int, arg2: str) -> bool:
    """Short description.
    
    Longer explanation of what the function does.
    
    Args:
        arg1: Description of arg1
        arg2: Description of arg2
    
    Returns:
        Description of return value
    
    Raises:
        ValueError: When and why
    
    Example:
        >>> result = function(1, "test")
        >>> print(result)
        True
    """
```

### Update Documentation

```bash
# Add/update docs
vim docs/my-feature.md

# Build docs locally
mkdocs serve

# View at http://localhost:8000
```

---

## Release Process

### 1. Update Version

```python
# VERSION file
1.0.0
```

### 2. Update CHANGELOG

```markdown
## [1.0.0] - 2024-01-15

### Added
- New feature X
- New indicator Y

### Fixed
- Bug in calculation Z

### Changed
- Improved performance of A
```

### 3. Run Full Test Suite

```bash
pytest tests/ \
  --cov=core --cov=backtest --cov=execution \
  --cov-config=configs/quality/critical_surface.coveragerc \
  --cov-report=term-missing --cov-report=xml

python -m tools.coverage.guardrail \
  --config configs/quality/critical_surface.toml \
  --coverage coverage.xml
```

### 4. Create Release

```bash
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0
```

### 5. Build and Publish

```bash
# Build Docker image
docker build -t tradepulse:1.0.0 .
docker push tradepulse:1.0.0
```

---

## Common Workflows

### Fix a Bug

```bash
# Create branch
git checkout -b fix/issue-123-calculation-error

# Fix issue
vim core/indicators/indicator.py

# Add test
vim tests/unit/test_indicator.py

# Verify fix
pytest tests/unit/test_indicator.py

# Commit
git commit -m "fix(indicators): correct calculation in edge case

Fixes #123"

# Push and create PR
git push origin fix/issue-123-calculation-error
```

### Add Feature

```bash
# Create branch
git checkout -b feat/add-new-indicator

# Implement feature
# ... (see Adding a New Indicator)

# Test thoroughly
pytest tests/

# Update docs
vim docs/indicators.md

# Commit
git commit -m "feat(indicators): add new indicator

Implements #456"

# Push and create PR
```

---

## Best Practices

1. **Test First**: Write tests before implementation
2. **Small Commits**: Commit frequently with clear messages
3. **Code Review**: Request reviews for all changes
4. **Documentation**: Update docs with code changes
5. **Performance**: Profile before optimizing
6. **Security**: Never commit secrets
7. **Backwards Compatibility**: Don't break existing APIs

---

## Resources

- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [TESTING.md](../TESTING.md)
- [Code Review Guidelines](https://github.com/neuron7x/TradePulse/wiki/Code-Review)

---

**Last Updated**: 2025-01-01
