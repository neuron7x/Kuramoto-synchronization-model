# Markets Module

## Overview

The `markets` module provides comprehensive market microstructure tools including order book management, market regime detection, and volume-synchronized probability of informed trading (VPIN) analysis. It enables deep market analysis and real-time order flow monitoring.

## Purpose

This module delivers professional market microstructure capabilities:

- **Order Book Management**: High-performance limit order book (LOB) implementation
- **Real-Time Ingestion**: Stream and process order book updates from multiple exchanges
- **Market Regime Detection**: Identify trending, mean-reverting, and volatile market conditions
- **VPIN Analysis**: Measure probability of informed trading for adverse selection risk
- **Liquidity Metrics**: Calculate spread, depth, and order imbalance indicators
- **Market Microstructure**: Tools for analyzing price formation and order flow

## Key Features

- 📚 **Limit Order Book**: Fast, memory-efficient order book with price-time priority
- 🌊 **Multi-Exchange Streaming**: Real-time data from Binance, OKX, Coinbase, and more
- 📊 **Regime Detection**: HMM and statistical models for regime classification
- 🎯 **VPIN Metric**: Volume-synchronized informed trading probability
- 💧 **Liquidity Analysis**: Measure market depth and resilience
- ⚡ **High Performance**: Optimized for low-latency processing
- 🔍 **Order Flow Toxicity**: Detect potentially toxic order flow

## Module Structure

```
markets/
├── __init__.py                        # Public API exports
├── orderbook/                         # Order book implementation
│   ├── src/
│   │   ├── core/
│   │   │   └── lob.py                # Limit order book engine
│   │   ├── ingest/
│   │   │   ├── ingester.py           # Data ingestion coordinator
│   │   │   ├── consistency.py        # Data consistency checks
│   │   │   ├── metrics.py            # Ingestion metrics
│   │   │   ├── state.py              # State management
│   │   │   ├── models.py             # Data models
│   │   │   └── exchanges/            # Exchange-specific adapters
│   │   │       ├── binance.py
│   │   │       ├── okx.py
│   │   │       └── ...
│   │   ├── ports/
│   │   │   └── ports.py              # Interface definitions
│   │   └── adapters/
│   │       └── local.py              # Local storage adapter
│   └── tests/                        # Comprehensive test suite
├── regime/                           # Market regime detection
└── vpin/                             # VPIN calculation and analysis
```

## Technology Stack

- **Python**: 3.11+ with full type annotations
- **NumPy**: Efficient numerical operations for order book arrays
- **WebSockets**: Real-time exchange connectivity
- **Redis**: High-speed caching and pub/sub for order updates
- **CCXT**: Unified exchange API interface
- **SciPy**: Statistical methods for regime detection
- **Statsmodels**: Hidden Markov Models and time series analysis

## Installation

```bash
# Base installation
pip install -e .

# With exchange connectors
pip install -e ".[connectors]"

# Development mode
pip install -e ".[dev]"
```

## Usage Examples

### Order Book Management

```python
from markets.orderbook import LimitOrderBook, Order

# Initialize order book
lob = LimitOrderBook(symbol="BTC/USDT", tick_size=0.01)

# Add orders
lob.add_order(Order(
    order_id="1",
    side="buy",
    price=50000.00,
    quantity=0.5,
    timestamp=1234567890
))

lob.add_order(Order(
    order_id="2",
    side="sell",
    price=50001.00,
    quantity=0.3,
    timestamp=1234567891
))

# Query order book state
best_bid = lob.get_best_bid()
best_ask = lob.get_best_ask()
spread = lob.get_spread()
mid_price = lob.get_mid_price()

print(f"Best Bid: {best_bid.price} x {best_bid.quantity}")
print(f"Best Ask: {best_ask.price} x {best_ask.quantity}")
print(f"Spread: {spread:.2f}")
print(f"Mid Price: {mid_price:.2f}")

# Get order book snapshot
snapshot = lob.get_snapshot(depth=10)
print(f"Top 10 levels:")
for level in snapshot.bids[:10]:
    print(f"  Bid: {level.price} x {level.quantity}")
```

### Real-Time Order Book Streaming

```python
from markets.orderbook import OrderBookIngester
from markets.orderbook.ingest.exchanges import BinanceAdapter

# Configure ingester
ingester = OrderBookIngester(
    exchange_adapter=BinanceAdapter(),
    symbols=["BTC/USDT", "ETH/USDT"],
    consistency_checks=True,
    metrics_enabled=True
)

# Start streaming
async for update in ingester.stream():
    print(f"Update for {update.symbol}:")
    print(f"  Best Bid: {update.best_bid_price} x {update.best_bid_size}")
    print(f"  Best Ask: {update.best_ask_price} x {update.best_ask_size}")
    print(f"  Mid Price: {update.mid_price}")
    print(f"  Spread: {update.spread}")
    
    # Process update
    lob = order_books[update.symbol]
    lob.apply_update(update)
```

### Market Regime Detection

```python
from markets.regime import RegimeDetector, RegimeConfig

# Configure regime detector
detector = RegimeDetector(
    config=RegimeConfig(
        n_states=3,  # trending, mean-reverting, volatile
        detection_method="hmm",  # Hidden Markov Model
        lookback_period=100,
        features=["returns", "volatility", "autocorrelation"]
    )
)

# Fit detector on historical data
detector.fit(historical_price_data)

# Detect current regime
regime = detector.detect_current_regime(recent_data)
print(f"Current Regime: {regime.label}")
print(f"Confidence: {regime.confidence:.2%}")
print(f"Duration: {regime.duration_bars} bars")

# Get regime probabilities
probabilities = detector.get_regime_probabilities(recent_data)
print(f"Trending: {probabilities['trending']:.2%}")
print(f"Mean-Reverting: {probabilities['mean_reverting']:.2%}")
print(f"Volatile: {probabilities['volatile']:.2%}")

# Track regime transitions
transitions = detector.get_transition_matrix()
print("Regime Transition Matrix:")
print(transitions)
```

### VPIN Analysis

```python
from markets.vpin import VPINCalculator, VPINConfig

# Configure VPIN calculator
vpin = VPINCalculator(
    config=VPINConfig(
        bucket_size=50,  # Volume bucket size
        lookback_buckets=50,
        classification_method="bulk_volume"
    )
)

# Calculate VPIN from trade data
vpin_values = vpin.calculate(
    trades=trade_data,
    time_bars=True  # Use time-based bucketing
)

# Analyze VPIN signal
current_vpin = vpin_values.iloc[-1]
if current_vpin > 0.7:
    print("⚠️ High VPIN: Informed trading likely, expect adverse selection")
elif current_vpin < 0.3:
    print("✅ Low VPIN: Uninformed flow, good conditions for market making")
else:
    print("➖ Moderate VPIN: Mixed flow")

# Get VPIN statistics
stats = vpin.get_statistics(vpin_values)
print(f"Mean VPIN: {stats.mean:.3f}")
print(f"Std VPIN: {stats.std:.3f}")
print(f"95th Percentile: {stats.percentile_95:.3f}")
```

### Liquidity Metrics

```python
from markets.orderbook import LiquidityMetrics

# Calculate liquidity metrics
metrics = LiquidityMetrics(order_book=lob)

# Spread metrics
spread_bps = metrics.get_spread_bps()
effective_spread = metrics.get_effective_spread(trade_size=1.0)
realized_spread = metrics.get_realized_spread(trades=recent_trades)

print(f"Quoted Spread: {spread_bps:.2f} bps")
print(f"Effective Spread: {effective_spread:.2f} bps")
print(f"Realized Spread: {realized_spread:.2f} bps")

# Depth metrics
depth_10bps = metrics.get_depth_at_bps(10)  # Liquidity within 10 bps
depth_usd = metrics.get_depth_usd(bps_range=20)

print(f"Depth at 10 bps: {depth_10bps:.4f} BTC")
print(f"USD Depth at 20 bps: ${depth_usd:,.2f}")

# Order imbalance
imbalance = metrics.get_order_imbalance(depth_levels=5)
print(f"Order Imbalance (top 5): {imbalance:.3f}")

# Resilience
resilience = metrics.estimate_price_impact(order_size=10.0)
print(f"Estimated Price Impact for 10 BTC: {resilience:.2%}")
```

### Order Flow Toxicity

```python
from markets import OrderFlowToxicity

# Analyze order flow toxicity
toxicity = OrderFlowToxicity(
    window_size=100,
    vpin_threshold=0.7,
    spread_threshold=20  # basis points
)

# Calculate toxicity score
score = toxicity.calculate(
    trades=recent_trades,
    order_book=lob,
    vpin=current_vpin
)

if score.is_toxic:
    print(f"⚠️ Toxic Order Flow Detected!")
    print(f"  Toxicity Score: {score.value:.2f}")
    print(f"  VPIN: {score.vpin:.3f}")
    print(f"  Adverse Selection Risk: High")
    print(f"  Recommendation: Widen spreads or reduce inventory")
else:
    print(f"✅ Healthy Order Flow")
    print(f"  Toxicity Score: {score.value:.2f}")
```

## Running Tests

```bash
# Run all markets module tests
pytest markets/orderbook/tests -v
pytest markets/regime/tests -v
pytest markets/vpin/tests -v

# Run with coverage
pytest markets/ --cov=markets --cov-report=html

# Test order book performance
pytest markets/orderbook/tests/test_core.py -v --benchmark

# Test ingestion streams (requires exchange connectivity)
pytest markets/orderbook/tests/test_ingest_streams.py -v
```

## Configuration

Configure markets module via YAML:

```yaml
# config/markets.yaml
markets:
  orderbook:
    default_depth: 20
    tick_size: 0.01
    enable_metrics: true
    snapshot_interval_ms: 100
    
  ingestion:
    buffer_size: 1000
    consistency_checks: true
    retry_policy:
      max_retries: 3
      backoff_multiplier: 2
    exchanges:
      binance:
        enabled: true
        websocket_url: wss://stream.binance.com:9443
      okx:
        enabled: true
        websocket_url: wss://ws.okx.com:8443
        
  regime:
    n_states: 3
    detection_method: hmm
    lookback_period: 100
    update_frequency: 1m
    
  vpin:
    bucket_size: 50
    lookback_buckets: 50
    classification_method: bulk_volume
    alert_threshold: 0.7
```

## Performance Optimization

- **Efficient Data Structures**: Red-black tree for price levels, hash maps for orders
- **Batch Processing**: Process multiple updates in batches
- **Memory Pooling**: Reuse order objects to reduce allocations
- **Lazy Evaluation**: Compute metrics only when requested
- **Caching**: Cache frequently accessed calculations (mid-price, spread)

## Best Practices

1. **Always Validate Updates**: Use consistency checks for exchange data
2. **Monitor Latency**: Track ingestion and processing delays
3. **Handle Reconnections**: Implement robust reconnection logic
4. **Snapshot Regularly**: Persist order book snapshots for recovery
5. **Use VPIN Wisely**: Combine with other signals, not standalone
6. **Regime Awareness**: Adjust strategies based on detected regimes
7. **Measure Everything**: Track liquidity metrics continuously

## Common Use Cases

### Market Making
- Monitor order book depth and spread
- Detect toxic order flow via VPIN
- Adjust quotes based on regime

### Algorithmic Trading
- Assess market impact before large orders
- Route orders to most liquid venues
- Time execution during low-toxicity periods

### Risk Management
- Monitor liquidity for position exits
- Detect regime changes early
- Track adverse selection costs

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                  Markets Module API                    │
├────────────────────────────────────────────────────────┤
│  OrderBook  │  Regime Detector  │  VPIN Calculator    │
├────────────────────────────────────────────────────────┤
│  Ingestion Layer                                       │
│  ├─ Exchange Adapters  ├─ Consistency Checks          │
│  ├─ State Management   ├─ Metrics Collection          │
├────────────────────────────────────────────────────────┤
│  Core Data Structures                                  │
│  ├─ Limit Order Book   ├─ Order Objects               │
│  ├─ Price Levels       ├─ Snapshots                   │
└────────────────────────────────────────────────────────┘
```

## Integration Points

### With Execution Module
- Provides real-time order book data for order routing
- Supplies liquidity metrics for smart order sizing

### With Analytics Module
- Exports VPIN and liquidity metrics for analysis
- Provides regime labels for performance attribution

### With Strategies Module
- Regime signals inform strategy selection
- VPIN thresholds trigger risk adjustments

## Related Modules

- [`execution`](../execution/README.md): Order execution and routing
- [`analytics`](../analytics/README.md): Market microstructure analytics
- [`core`](../core/README.md): Core indicators and infrastructure
- [`strategies`](../strategies/README.md): Trading strategies

## Documentation

- [API Reference](https://docs.tradepulse.io/api/markets)
- [Order Book Guide](https://docs.tradepulse.io/guides/orderbook)
- [VPIN Guide](https://docs.tradepulse.io/guides/vpin)
- [Regime Detection](https://docs.tradepulse.io/guides/regime-detection)

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines.

## License

See [LICENSE](../LICENSE) for licensing information.

## Support

- [GitHub Issues](https://github.com/neuron7x/TradePulse/issues)
- [Documentation](https://docs.tradepulse.io)
- [Community](https://github.com/neuron7x/TradePulse/discussions)
