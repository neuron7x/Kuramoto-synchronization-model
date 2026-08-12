# Extending GeoSync

This guide explains how to extend GeoSync with custom indicators, strategies, data sources, and execution adapters.

---

## Table of Contents

- [Overview](#overview)
- [Adding Custom Indicators](#adding-custom-indicators)
- [Creating Custom Strategies](#creating-custom-strategies)
- [Implementing Data Sources](#implementing-data-sources)
- [Building Execution Adapters](#building-execution-adapters)
- [Adding Metrics](#adding-metrics)
- [Testing Extensions](#testing-extensions)

---

## Overview

GeoSync is designed to be extensible. The framework provides base classes and interfaces that you can extend to add custom functionality.

### Extension Points

- **Indicators**: Custom technical or mathematical indicators
- **Strategies**: Trading logic and signal generation
- **Data Sources**: Market data providers and formats
- **Execution Adapters**: Exchange connectors and order routing
- **Metrics**: Custom performance and risk metrics

### Design Principles

1. **Interface Compliance**: Extend base classes and implement required methods
2. **Separation of Concerns**: Keep business logic separate from infrastructure
3. **Testability**: Write unit tests for all extensions
4. **Documentation**: Add comprehensive docstrings

---

## Adding Custom Indicators

### Step 1: Understand the BaseFeature Interface

All indicators inherit from `BaseFeature`:

```python
# core/indicators/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict
import numpy as np

@dataclass
class FeatureResult:
    """Result from a feature transformation."""
    value: float
    metadata: Dict[str, Any]
    name: str

class BaseFeature(ABC):
    """Base class for all features/indicators."""
    
    def __init__(self, name: str, **params):
        self.name = name
        self.params = params
    
    @abstractmethod
    def transform(self, data: np.ndarray) -> FeatureResult:
        """Transform input data into feature value.
        
        Args:
            data: Input array (usually prices)
            
        Returns:
            FeatureResult with value and metadata
        """
        pass
    
    def validate_input(self, data: np.ndarray) -> None:
        """Validate input data."""
        if not isinstance(data, np.ndarray):
            raise TypeError("Input must be numpy array")
        if data.ndim != 1:
            raise ValueError("Input must be 1-dimensional")
        if len(data) == 0:
            raise ValueError("Input cannot be empty")
```

### Step 2: Create Your Indicator

```python
# core/indicators/rsi.py
"""Relative Strength Index (RSI) indicator."""

import numpy as np
from .base import BaseFeature, FeatureResult

class RSI(BaseFeature):
    """Relative Strength Index indicator.
    
    Measures the magnitude of recent price changes to evaluate
    overbought or oversold conditions.
    
    Args:
        name: Indicator name
        period: Lookback period (default: 14)
        
    Example:
        >>> rsi = RSI("rsi_14", period=14)
        >>> prices = np.array([100, 102, 101, 103, 105, 104, 106])
        >>> result = rsi.transform(prices)
        >>> print(f"RSI: {result.value:.2f}")
    """
    
    def __init__(self, name: str = "rsi", period: int = 14):
        super().__init__(name, period=period)
        self.period = period
    
    def transform(self, data: np.ndarray) -> FeatureResult:
        """Compute RSI from price data.
        
        Args:
            data: 1D array of prices
            
        Returns:
            FeatureResult with RSI value and metadata
            
        Raises:
            ValueError: If insufficient data for calculation
        """
        self.validate_input(data)
        
        if len(data) < self.period + 1:
            raise ValueError(
                f"Need at least {self.period + 1} data points, "
                f"got {len(data)}"
            )
        
        # Calculate price changes
        deltas = np.diff(data)
        
        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        # Calculate average gains and losses
        avg_gain = np.mean(gains[-self.period:])
        avg_loss = np.mean(losses[-self.period:])
        
        # Calculate RS and RSI
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        metadata = {
            "period": self.period,
            "avg_gain": float(avg_gain),
            "avg_loss": float(avg_loss),
            "n_samples": len(data)
        }
        
        return FeatureResult(
            value=float(rsi),
            metadata=metadata,
            name=self.name
        )
```

### Step 3: Register Your Indicator

```python
# core/indicators/__init__.py
from .rsi import RSI
from .kuramoto import KuramotoOrder
from .entropy import Entropy
# ... other indicators

__all__ = [
    "RSI",
    "KuramotoOrder",
    "Entropy",
    # ...
]
```

### Step 4: Test Your Indicator

```python
# tests/unit/test_rsi.py
import numpy as np
import pytest
from core.indicators.rsi import RSI

def test_rsi_basic_calculation():
    """Test RSI calculation with known values."""
    rsi = RSI(period=14)
    
    # Create test data with clear trend
    prices = np.array([
        44, 44.34, 44.09, 43.61, 44.33, 44.83,
        45.10, 45.42, 45.84, 46.08, 45.89, 46.03,
        45.61, 46.28, 46.28, 46.00, 46.03
    ])
    
    result = rsi.transform(prices)
    
    # RSI should be between 0 and 100
    assert 0 <= result.value <= 100
    assert result.name == "rsi"
    assert result.metadata["period"] == 14

def test_rsi_overbought():
    """Test RSI indicates overbought on strong uptrend."""
    rsi = RSI(period=5)
    
    # Strong uptrend
    prices = np.array([100, 105, 110, 115, 120, 125])
    result = rsi.transform(prices)
    
    # Should indicate overbought (> 70)
    assert result.value > 70

def test_rsi_oversold():
    """Test RSI indicates oversold on strong downtrend."""
    rsi = RSI(period=5)
    
    # Strong downtrend
    prices = np.array([125, 120, 115, 110, 105, 100])
    result = rsi.transform(prices)
    
    # Should indicate oversold (< 30)
    assert result.value < 30

def test_rsi_insufficient_data():
    """Test RSI raises error with insufficient data."""
    rsi = RSI(period=14)
    prices = np.array([100, 101, 102])  # Only 3 points
    
    with pytest.raises(ValueError, match="Need at least"):
        rsi.transform(prices)

def test_rsi_invalid_input():
    """Test RSI validates input data."""
    rsi = RSI()
    
    with pytest.raises(TypeError):
        rsi.transform([100, 101, 102])  # List instead of array
    
    with pytest.raises(ValueError):
        rsi.transform(np.array([]))  # Empty array
```

---

## Creating Custom Strategies

### Step 1: Understand the Strategy Interface

```python
# core/agent/strategy.py
from dataclasses import dataclass
from typing import Dict, Any, List
import numpy as np

@dataclass
class Signal:
    """Trading signal."""
    action: str  # 'buy', 'sell', 'hold'
    confidence: float  # 0.0 to 1.0
    metadata: Dict[str, Any]

class BaseStrategy(ABC):
    """Base class for trading strategies."""
    
    def __init__(self, name: str, parameters: Dict[str, Any]):
        self.name = name
        self.parameters = parameters
    
    @abstractmethod
    def generate_signal(
        self,
        prices: np.ndarray,
        indicators: Dict[str, float]
    ) -> Signal:
        """Generate trading signal.
        
        Args:
            prices: Historical price data
            indicators: Dictionary of indicator values
            
        Returns:
            Signal with action and confidence
        """
        pass
```

### Step 2: Implement Your Strategy

```python
# core/strategies/mean_reversion.py
"""Mean reversion strategy using RSI and Bollinger Bands."""

import numpy as np
from core.agent.strategy import BaseStrategy, Signal
from core.indicators.rsi import RSI
from typing import Dict, Any

class MeanReversionStrategy(BaseStrategy):
    """Mean reversion strategy.
    
    Buys when price is oversold and sells when overbought.
    Uses RSI and Bollinger Bands to identify extremes.
    
    Parameters:
        rsi_period: RSI calculation period (default: 14)
        rsi_oversold: RSI oversold threshold (default: 30)
        rsi_overbought: RSI overbought threshold (default: 70)
        bb_period: Bollinger Bands period (default: 20)
        bb_std: Bollinger Bands standard deviations (default: 2)
    
    Example:
        >>> strategy = MeanReversionStrategy(
        ...     "mean_reversion",
        ...     {"rsi_oversold": 30, "rsi_overbought": 70}
        ... )
        >>> signal = strategy.generate_signal(prices, indicators)
    """
    
    def __init__(self, name: str = "mean_reversion", parameters: Dict[str, Any] = None):
        default_params = {
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "bb_period": 20,
            "bb_std": 2.0
        }
        if parameters:
            default_params.update(parameters)
        super().__init__(name, default_params)
        
        self.rsi = RSI(period=self.parameters["rsi_period"])
    
    def generate_signal(
        self,
        prices: np.ndarray,
        indicators: Dict[str, float]
    ) -> Signal:
        """Generate mean reversion signal.
        
        Args:
            prices: Price history
            indicators: Pre-computed indicators (optional)
            
        Returns:
            Trading signal with action and confidence
        """
        if len(prices) < max(
            self.parameters["rsi_period"],
            self.parameters["bb_period"],
        ) + 1:
            return Signal(action="hold", confidence=0.0, metadata={})
        
        # Compute RSI
        rsi_result = self.rsi.transform(prices)
        rsi_value = rsi_result.value
        
        # Compute Bollinger Bands
        bb_period = self.parameters["bb_period"]
        bb_std = self.parameters["bb_std"]
        
        sma = np.mean(prices[-bb_period:])
        std = np.std(prices[-bb_period:])
        upper_band = sma + (bb_std * std)
        lower_band = sma - (bb_std * std)
        current_price = prices[-1]
        
        # Generate signal
        action = "hold"
        confidence = 0.0
        
        # Oversold condition
        if (
            rsi_value < self.parameters["rsi_oversold"]
            and current_price < lower_band
        ):
            action = "buy"
            # Confidence increases as RSI gets lower
            confidence = 1.0 - (rsi_value / self.parameters["rsi_oversold"])
        
        # Overbought condition
        elif (
            rsi_value > self.parameters["rsi_overbought"]
            and current_price > upper_band
        ):
            action = "sell"
            # Confidence increases as RSI gets higher
            confidence = (rsi_value - self.parameters["rsi_overbought"]) / \
                        (100 - self.parameters["rsi_overbought"])
        
        metadata = {
            "rsi": rsi_value,
            "price": float(current_price),
            "sma": float(sma),
            "upper_band": float(upper_band),
            "lower_band": float(lower_band),
            "distance_from_sma": float(current_price - sma)
        }
        
        return Signal(action=action, confidence=confidence, metadata=metadata)
```

### Step 3: Test Your Strategy

```python
# tests/unit/test_mean_reversion.py
import numpy as np
import pytest
from core.strategies.mean_reversion import MeanReversionStrategy

def test_mean_reversion_buy_signal():
    """Test strategy generates buy signal when oversold."""
    strategy = MeanReversionStrategy()
    
    # Create oversold condition: downtrend
    prices = np.linspace(100, 80, 50)
    
    signal = strategy.generate_signal(prices, {})
    
    assert signal.action in ["buy", "hold"]
    assert 0.0 <= signal.confidence <= 1.0

def test_mean_reversion_sell_signal():
    """Test strategy generates sell signal when overbought."""
    strategy = MeanReversionStrategy()
    
    # Create overbought condition: uptrend
    prices = np.linspace(80, 100, 50)
    
    signal = strategy.generate_signal(prices, {})
    
    assert signal.action in ["sell", "hold"]
    assert 0.0 <= signal.confidence <= 1.0

def test_mean_reversion_insufficient_data():
    """Test strategy handles insufficient data gracefully."""
    strategy = MeanReversionStrategy()
    prices = np.array([100, 101, 102])
    
    signal = strategy.generate_signal(prices, {})
    
    assert signal.action == "hold"
    assert signal.confidence == 0.0
```

---

## Implementing Data Sources

### Step 1: Understand the Data Source Interface

```python
# core/data/ingestion.py
from typing import Callable, Optional
from datetime import datetime, timezone

from core.data.models import Ticker

class DataSource(ABC):
    """Base class for data sources."""

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to data source."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to data source."""
        pass

    @abstractmethod
    def subscribe(
        self,
        symbol: str,
        callback: Callable[[Ticker], None]
    ) -> None:
        """Subscribe to symbol updates."""
        pass
```

> **Note**: `Ticker` is an immutable Pydantic model.  Any callback you register
> receives a fully validated payload with UTC timestamps and Decimal-backed
> prices/volumes, so downstream code can rely on strict typing.

### Step 2: Implement Your Data Source

```python
# core/data/binance_source.py
"""Binance WebSocket data source."""

import json
import websocket
from typing import Callable
from datetime import datetime
from core.data.ingestion import DataSource, Ticker

class BinanceDataSource(DataSource):
    """Binance WebSocket data source.
    
    Connects to Binance WebSocket API for real-time market data.
    
    Args:
        testnet: Use testnet instead of production (default: True)
        
    Example:
        >>> source = BinanceDataSource(testnet=True)
        >>> source.connect()
        >>> source.subscribe("BTCUSDT", lambda tick: print(tick))
    """
    
    def __init__(self, testnet: bool = True):
        self.testnet = testnet
        self.ws = None
        self.callbacks = {}
    
    def connect(self) -> None:
        """Connect to Binance WebSocket."""
        if self.testnet:
            url = "wss://testnet.binance.vision/ws"
        else:
            url = "wss://stream.binance.com:9443/ws"
        
        self.ws = websocket.WebSocketApp(
            url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
    
    def disconnect(self) -> None:
        """Close WebSocket connection."""
        if self.ws:
            self.ws.close()
    
    def subscribe(
        self,
        symbol: str,
        callback: Callable[[Ticker], None]
    ) -> None:
        """Subscribe to symbol updates.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            callback: Function to call on each tick
        """
        self.callbacks[symbol.lower()] = callback
        
        # Send subscription message
        sub_message = {
            "method": "SUBSCRIBE",
            "params": [f"{symbol.lower()}@trade"],
            "id": 1
        }
        self.ws.send(json.dumps(sub_message))
    
    def _on_message(self, ws, message):
        """Handle incoming WebSocket message."""
        data = json.loads(message)
        
        if "e" in data and data["e"] == "trade":
            symbol = data["s"]

            tick = Ticker.create(
                symbol=symbol,
                venue="BINANCE",
                price=float(data["p"]),
                volume=float(data["q"]),
                timestamp=datetime.fromtimestamp(data["T"] / 1000, tz=timezone.utc),
            )
            
            if symbol.lower() in self.callbacks:
                self.callbacks[symbol.lower()](tick)
    
    def _on_error(self, ws, error):
        """Handle WebSocket error."""
        print(f"WebSocket error: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close."""
        print("WebSocket connection closed")
```

---

## Building Execution Adapters

See [Integration API](integration-api.md) for detailed information on building execution adapters for different exchanges.

---

## Adding Metrics

```python
# core/metrics/sharpe.py
"""Sharpe ratio calculation."""

import numpy as np
from typing import Optional

def sharpe_ratio(
    returns: np.ndarray,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252
) -> float:
    """Calculate annualized Sharpe ratio.
    
    Args:
        returns: Array of period returns
        risk_free_rate: Risk-free rate (annualized)
        periods_per_year: Trading periods per year
        
    Returns:
        Annualized Sharpe ratio
        
    Example:
        >>> returns = np.array([0.01, -0.02, 0.03, 0.01])
        >>> sharpe = sharpe_ratio(returns)
    """
    if len(returns) == 0:
        return 0.0
    
    mean_return = np.mean(returns)
    std_return = np.std(returns, ddof=1)
    
    if std_return == 0:
        return 0.0
    
    # Annualize
    annual_return = mean_return * periods_per_year
    annual_std = std_return * np.sqrt(periods_per_year)
    
    return (annual_return - risk_free_rate) / annual_std
```

---

## Testing Extensions

### Unit Tests

Test your extension in isolation:

```python
def test_my_indicator():
    indicator = MyIndicator()
    result = indicator.transform(test_data)
    assert isinstance(result, FeatureResult)
```

### Integration Tests

Test your extension in the full system:

```python
def test_strategy_with_custom_indicator():
    strategy = MyStrategy()
    prices = load_test_data()
    signal = strategy.generate_signal(prices, {})
    assert signal.action in ["buy", "sell", "hold"]
```

### Property-Based Tests

Use Hypothesis to test invariants:

```python
from hypothesis import given, strategies as st

@given(prices=st.lists(st.floats(min_value=1.0, max_value=1000.0), min_size=20))
def test_indicator_output_range(prices):
    indicator = MyIndicator()
    result = indicator.transform(np.array(prices))
    assert 0 <= result.value <= 100
```

---

## Best Practices

1. **Follow Existing Patterns**: Look at existing indicators/strategies for examples
2. **Comprehensive Documentation**: Add docstrings with examples
3. **Input Validation**: Validate all inputs
4. **Error Handling**: Handle edge cases gracefully
5. **Test Coverage**: Aim for >90% test coverage
6. **Performance**: Profile and optimize hot paths
7. **Logging**: Add appropriate logging statements
8. **Metrics**: Expose relevant metrics

---

## Examples Repository

See the [examples/](../examples/) directory for complete examples of:
- Custom indicators
- Trading strategies
- Data source connectors
- Execution adapters
- Metrics and analytics

---

## Getting Help

- Review existing code in the repository
- Check [GitHub Issues](https://github.com/neuron7xLab/GeoSync/issues)
- Read [CONTRIBUTING.md](../CONTRIBUTING.md)
- Ask in GitHub Discussions

---

**Last Updated**: 2025-01-01
