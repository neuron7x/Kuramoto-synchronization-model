# API Examples

Practical code examples for common TradePulse use cases.

## Table of Contents

- [Indicators](#indicators)
- [Backtesting](#backtesting)
- [Risk Management](#risk-management)
- [Data Management](#data-management)
- [Live Trading](#live-trading)
- [Custom Strategies](#custom-strategies)

## Indicators

### Basic Indicator Usage

```python
import numpy as np
from core.indicators.kuramoto import compute_phase, kuramoto_order
from core.indicators.entropy import entropy, delta_entropy
from core.indicators.hurst import hurst_exponent

# Sample price data
prices = np.array([100, 101, 102, 101, 103, 105, 104, 106, 107, 105])

# Kuramoto synchronization
phases = compute_phase(prices)
R = kuramoto_order(phases)
print(f"Kuramoto Order: {R:.4f}")

# Entropy analysis
H = entropy(prices)
dH = delta_entropy(prices, window=5)
print(f"Entropy: {H:.4f}, ΔH: {dH:.4f}")

# Hurst exponent
H_exp = hurst_exponent(prices)
print(f"Hurst: {H_exp:.4f} ({'trending' if H_exp > 0.5 else 'mean-reverting'})")
```

### Multi-Asset Analysis

```python
from core.indicators.kuramoto import MultiAssetKuramotoFeature
import pandas as pd

# Multiple asset prices
data = pd.DataFrame({
    'BTC': [50000, 51000, 50500, 52000],
    'ETH': [3000, 3100, 3050, 3200],
    'SOL': [100, 102, 101, 105]
})

# Compute cross-asset synchronization
feature = MultiAssetKuramotoFeature(window=3)
result = feature.transform(data)

print(f"Cross-asset sync: {result.value:.4f}")
print(f"Metadata: {result.metadata}")
```

### Composite Indicators

```python
from core.indicators.kuramoto_ricci_composite import TradePulseCompositeEngine
import pandas as pd

# Prepare data
bars = pd.DataFrame({
    'close': prices,
    'volume': [1000] * len(prices)  # Placeholder volumes
}, index=pd.date_range('2024-01-01', periods=len(prices), freq='1H'))

# Analyze market regime
engine = TradePulseCompositeEngine()
snapshot = engine.analyze_market(bars)

print(f"Phase: {snapshot.phase.value}")
print(f"Confidence: {snapshot.confidence:.3f}")
print(f"Entry Signal: {snapshot.entry_signal:.3f}")
print(f"Risk Level: {snapshot.risk_level}")
```

### Custom Feature Pipeline

```python
from core.indicators.base import FeatureBlock, FunctionalFeature
from core.indicators.kuramoto import KuramotoOrderFeature
from core.indicators.entropy import EntropyFeature

# Define custom transformation
def custom_momentum(data, period=14):
    """Simple momentum indicator"""
    return (data[-1] - data[-period]) / data[-period] * 100

# Create feature pipeline
pipeline = FeatureBlock(
    name="regime_detector",
    features=[
        KuramotoOrderFeature(window=50, name="sync"),
        EntropyFeature(bins=20, name="uncertainty"),
        FunctionalFeature(
            func=custom_momentum,
            name="momentum",
            params={'period': 14}
        )
    ]
)

# Run pipeline
results = pipeline.transform(prices)
print(f"Sync: {results['sync'].value:.4f}")
print(f"Uncertainty: {results['uncertainty'].value:.4f}")
print(f"Momentum: {results['momentum'].value:.2f}%")
```

## Backtesting

### Simple Moving Average Strategy

```python
import numpy as np
from backtest.event_driven import EventDrivenBacktestEngine

def sma_crossover(prices: np.ndarray, fast: int = 20, slow: int = 50) -> np.ndarray:
    """Generate signals based on SMA crossover"""
    signals = np.zeros(len(prices))
    
    for i in range(slow, len(prices)):
        fast_ma = prices[i-fast:i].mean()
        slow_ma = prices[i-slow:i].mean()
        
        if fast_ma > slow_ma:
            signals[i] = 1.0  # Long
        elif fast_ma < slow_ma:
            signals[i] = -1.0  # Short
            
    return signals

# Run backtest
engine = EventDrivenBacktestEngine()
result = engine.run(
    prices=price_data,
    signal_func=sma_crossover,
    initial_capital=100_000,
    commission=0.001,  # 0.1%
    strategy_name="sma_crossover"
)

print(f"Final PnL: ${result.pnl:,.2f}")
print(f"Sharpe Ratio: {result.performance.as_dict()['sharpe_ratio']:.2f}")
```

### Mean Reversion Strategy

```python
def mean_reversion(prices: np.ndarray, window: int = 20, threshold: float = 2.0) -> np.ndarray:
    """Trade when price deviates significantly from mean"""
    signals = np.zeros(len(prices))
    
    for i in range(window, len(prices)):
        window_data = prices[i-window:i]
        mean = window_data.mean()
        std = window_data.std()
        
        z_score = (prices[i] - mean) / std if std > 0 else 0
        
        if z_score < -threshold:
            signals[i] = 1.0  # Oversold, go long
        elif z_score > threshold:
            signals[i] = -1.0  # Overbought, go short
        else:
            signals[i] = 0.0  # Neutral
            
    return signals

result = engine.run(
    prices=price_data,
    signal_func=mean_reversion,
    initial_capital=100_000,
    strategy_name="mean_reversion"
)
```

### Walk-Forward Optimization

```python
from backtest.time_splits import WalkForwardSplitter

# Define parameter space
param_grid = {
    'window': [10, 20, 30],
    'threshold': [1.5, 2.0, 2.5]
}

# Create walk-forward splitter
splitter = WalkForwardSplitter(
    train_size=252,  # 1 year
    test_size=63,    # 1 quarter
    step=21          # Monthly reoptimization
)

# Optimize and test
for train_idx, test_idx in splitter.split(price_data):
    train_prices = price_data[train_idx]
    test_prices = price_data[test_idx]
    
    # Optimize on training data
    best_params = optimize_parameters(train_prices, param_grid)
    
    # Test on out-of-sample data
    test_result = engine.run(
        prices=test_prices,
        signal_func=lambda p: mean_reversion(p, **best_params),
        initial_capital=100_000
    )
    
    print(f"Test Period Return: {test_result.pnl / 100_000 * 100:.2f}%")
```

## Risk Management

### Position Sizing with Kelly Criterion

```python
from execution.risk import RiskManager, RiskLimits

# Calculate Kelly fraction
def kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """Calculate optimal position size using Kelly criterion"""
    if avg_loss == 0:
        return 0
    odds = avg_win / avg_loss
    return (win_rate * odds - (1 - win_rate)) / odds

# Example usage
win_rate = 0.55  # 55% win rate
avg_win = 2.0    # Average win 2%
avg_loss = 1.0   # Average loss 1%

kelly_fraction = kelly_criterion(win_rate, avg_win, avg_loss)
position_size = 100_000 * kelly_fraction

print(f"Kelly Fraction: {kelly_fraction:.2%}")
print(f"Position Size: ${position_size:,.2f}")
```

### Dynamic Risk Limits

```python
from execution.risk import RiskManager, RiskLimits
from domain import Order, OrderSide, OrderType

# Create risk manager with limits
risk_manager = RiskManager(
    limits=RiskLimits(
        max_notional=500_000,      # Max $500k exposure
        max_position=10.0,         # Max 10 contracts per symbol
        max_leverage=3.0,          # Max 3x leverage
        max_drawdown_pct=0.10,     # Stop at 10% drawdown
    )
)

# Check order before submission
order = Order(
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    quantity=5.0,
    price=50_000,
    order_type=OrderType.LIMIT
)

# Pre-trade risk check
is_allowed, reason = risk_manager.check_order(order)
if is_allowed:
    print("Order approved")
else:
    print(f"Order rejected: {reason}")
```

### Circuit Breakers

```python
from execution.circuit_breaker import CircuitBreaker

# Create circuit breaker
breaker = CircuitBreaker(
    failure_threshold=5,     # Trip after 5 failures
    recovery_time=300,       # 5-minute cooldown
    half_open_max_calls=3    # Allow 3 test calls in half-open state
)

# Protect critical operations
@breaker.protected
def risky_exchange_call():
    # This call will be blocked if circuit is open
    return exchange_connector.place_order(order)

try:
    result = risky_exchange_call()
except Exception as e:
    if breaker.is_open:
        print("Circuit breaker is OPEN - trading halted")
    else:
        print(f"Order failed: {e}")
```

## Data Management

### Versioned Data Storage

```python
from core.data.warehouses.versioned import VersionedWarehouse
import pandas as pd

# Initialize warehouse
warehouse = VersionedWarehouse(base_path="./data/versioned")

# Store data with version
data = pd.DataFrame({'price': prices, 'volume': volumes})
version = warehouse.store(
    dataset_name="BTCUSDT_1H",
    data=data,
    metadata={'source': 'binance', 'timeframe': '1H'}
)

print(f"Stored version: {version}")

# Retrieve specific version
loaded_data = warehouse.retrieve("BTCUSDT_1H", version=version)

# Get latest version
latest_data = warehouse.retrieve("BTCUSDT_1H")

# List all versions
versions = warehouse.list_versions("BTCUSDT_1H")
print(f"Available versions: {versions}")
```

### Data Quality Validation

```python
from core.data.quality_control import DataQualityGate, QualityCheck
import pandas as pd

# Define quality checks
quality_gate = DataQualityGate(
    checks=[
        QualityCheck('no_nulls', lambda df: df.isnull().sum().sum() == 0),
        QualityCheck('positive_prices', lambda df: (df['price'] > 0).all()),
        QualityCheck('monotonic_time', lambda df: df.index.is_monotonic_increasing),
    ]
)

# Validate data
data = pd.DataFrame({
    'price': [100, 101, 102],
    'volume': [1000, 1100, 1200]
}, index=pd.date_range('2024-01-01', periods=3, freq='1H'))

is_valid, failures = quality_gate.validate(data)

if is_valid:
    print("Data passed all quality checks")
else:
    print(f"Quality check failures: {failures}")
```

### Resampling and Aggregation

```python
from backtest.resampling import resample_ohlcv
import pandas as pd

# Original 1-minute data
minute_data = pd.DataFrame({
    'open': [100, 101, 102, 103],
    'high': [101, 102, 103, 104],
    'low': [99, 100, 101, 102],
    'close': [101, 102, 103, 104],
    'volume': [1000, 1100, 1200, 1300]
}, index=pd.date_range('2024-01-01', periods=4, freq='1min'))

# Resample to hourly
hourly_data = resample_ohlcv(minute_data, '1H')

print(hourly_data)
```

## Live Trading

### Paper Trading Setup

```python
from execution.live_loop import LiveExecutionLoop, LiveLoopConfig
from execution.connectors import BinanceConnector
from execution.risk import RiskManager, RiskLimits
from pathlib import Path

# Configure live loop
config = LiveLoopConfig(
    state_dir=Path("./state"),
    submission_interval=1.0,
    fill_poll_interval=2.0,
    heartbeat_interval=30.0,
)

# Create connector in sandbox mode
connector = BinanceConnector(sandbox=True)

# Create risk manager
risk_manager = RiskManager(
    limits=RiskLimits(max_notional=10_000)
)

# Initialize live loop
live_loop = LiveExecutionLoop(
    connectors={"binance": connector},
    risk_manager=risk_manager,
    config=config
)

# Start trading
live_loop.start(cold_start=True)

# Submit order
from domain import Order, OrderSide, OrderType

order = Order(
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    quantity=0.01,
    price=50_000,
    order_type=OrderType.LIMIT
)

live_loop.submit_order("binance", order)

# Monitor status
# ... wait for fills ...

# Shutdown gracefully
live_loop.shutdown()
```

### Order Recovery and Reconnection

```python
from execution.order_lifecycle import OMSState

# Load persisted OMS state
oms_state = OMSState.load(state_dir="./state")

# Check outstanding orders
outstanding = oms_state.outstanding("binance")
print(f"Found {len(outstanding)} outstanding orders")

# Reconcile with exchange
for order in outstanding:
    exchange_status = connector.get_order_status(order.order_id)
    if exchange_status.is_filled:
        oms_state.mark_filled(order.order_id)
```

## Custom Strategies

### Regime-Switching Strategy

```python
import numpy as np
from core.indicators.kuramoto import kuramoto_order, compute_phase
from core.indicators.hurst import hurst_exponent

def regime_switching_strategy(prices: np.ndarray) -> np.ndarray:
    """
    Different strategies for different market regimes:
    - Trending: Momentum
    - Mean-reverting: Contrarian
    - Random: Flat
    """
    signals = np.zeros(len(prices))
    window = 100
    
    for i in range(window, len(prices)):
        window_prices = prices[i-window:i]
        
        # Detect regime
        phases = compute_phase(window_prices)
        R = kuramoto_order(phases)
        H = hurst_exponent(window_prices)
        
        if R > 0.7 and H > 0.6:  # Strong trending regime
            # Momentum strategy
            if prices[i] > prices[i-20]:
                signals[i] = 1.0
            else:
                signals[i] = -1.0
                
        elif R < 0.3 and H < 0.4:  # Mean-reverting regime
            # Contrarian strategy
            mean = window_prices.mean()
            if prices[i] < mean * 0.98:
                signals[i] = 1.0  # Buy dip
            elif prices[i] > mean * 1.02:
                signals[i] = -1.0  # Sell rally
        else:
            # Uncertain regime - stay flat
            signals[i] = 0.0
            
    return signals
```

### Multi-Timeframe Strategy

```python
def multi_timeframe_strategy(
    prices_daily: np.ndarray,
    prices_hourly: np.ndarray,
    prices_minute: np.ndarray
) -> np.ndarray:
    """Combine signals from multiple timeframes"""
    
    # Helper function to calculate RSI
    def calculate_rsi(prices, period=14):
        """Calculate Relative Strength Index"""
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    # Daily: Trend direction
    daily_ma = prices_daily[-50:].mean()
    trend = 1 if prices_daily[-1] > daily_ma else -1
    
    # Hourly: Entry timing
    hourly_ma_fast = prices_hourly[-12:].mean()
    hourly_ma_slow = prices_hourly[-26:].mean()
    entry = hourly_ma_fast > hourly_ma_slow
    
    # Minute: Fine-tune entry
    minute_rsi = calculate_rsi(prices_minute, period=14)
    oversold = minute_rsi < 30
    overbought = minute_rsi > 70
    
    # Combine signals
    if trend == 1 and entry and oversold:
        return 1.0  # Strong buy
    elif trend == -1 and not entry and overbought:
        return -1.0  # Strong sell
    else:
        return 0.0  # No trade
```

### Machine Learning Integration

```python
from sklearn.ensemble import RandomForestClassifier
import numpy as np

def ml_enhanced_strategy(prices: np.ndarray, train_size: int = 1000) -> np.ndarray:
    """Use ML to predict price direction"""
    
    # Feature engineering
    def extract_features(window_prices):
        return {
            'ma_20': window_prices[-20:].mean(),
            'ma_50': window_prices[-50:].mean(),
            'volatility': window_prices[-20:].std(),
            'momentum': (window_prices[-1] - window_prices[-20]) / window_prices[-20],
        }
    
    # Prepare training data
    X_train, y_train = [], []
    for i in range(100, train_size):
        features = extract_features(prices[:i])
        X_train.append(list(features.values()))
        # Label: 1 if price goes up next period, 0 otherwise
        y_train.append(1 if prices[i+1] > prices[i] else 0)
    
    # Train model
    model = RandomForestClassifier(n_estimators=100)
    model.fit(X_train, y_train)
    
    # Generate signals
    signals = np.zeros(len(prices))
    for i in range(train_size, len(prices) - 1):
        features = extract_features(prices[:i])
        prediction = model.predict([list(features.values())])[0]
        signals[i] = 1.0 if prediction == 1 else -1.0
    
    return signals
```

## Best Practices

### Error Handling

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
def fetch_market_data(symbol: str):
    """Fetch data with automatic retry"""
    try:
        data = connector.get_historical_data(symbol)
        if data is None or len(data) == 0:
            raise ValueError("Empty data returned")
        return data
    except Exception as e:
        logger.error(f"Failed to fetch {symbol}: {e}")
        raise
```

### Logging

```python
import logging
from core.utils.logging import StructuredLogger

logger = StructuredLogger(__name__)

def execute_strategy():
    logger.info(
        "Starting strategy execution",
        strategy="momentum",
        capital=100_000
    )
    
    try:
        result = run_backtest()
        logger.info(
            "Strategy completed",
            pnl=result.pnl,
            trades=result.trades,
            sharpe=result.performance.sharpe_ratio
        )
    except Exception as e:
        logger.error(
            "Strategy failed",
            error=str(e),
            exc_info=True
        )
        raise
```

### Configuration Management

```python
from hydra import compose, initialize
from omegaconf import OmegaConf

# Load configuration
with initialize(version_base=None, config_path="../conf"):
    cfg = compose(config_name="config")
    
    # Access nested config
    capital = cfg.strategy.capital
    max_drawdown = cfg.risk.max_drawdown_pct
    
    # Override from code
    cfg.strategy.name = "custom_strategy"
    
    # Convert to dict
    config_dict = OmegaConf.to_container(cfg, resolve=True)
```

## See Also

- [Indicator Guide](./indicators.md) - Detailed indicator documentation
- [Architecture](./ARCHITECTURE.md) - System design overview
- [Risk Management](./risk_management.md) - Risk control mechanisms
- [Backtesting](./backtest.md) - Backtesting framework guide
