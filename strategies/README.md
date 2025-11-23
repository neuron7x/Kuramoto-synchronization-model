# Strategies Module

## Overview

The `strategies` module contains implementations of various trading strategies, from classic momentum and mean-reversion to advanced neural network-based approaches. It provides a unified interface for strategy development and deployment.

## Purpose

This module offers:

- **Pre-built Strategies**: Production-ready implementations of common strategies
- **Strategy Framework**: Base classes and interfaces for custom strategy development
- **Neural Strategies**: ML-powered strategies using geometric indicators
- **Quantum Neural**: Cutting-edge quantum-inspired neural network strategies
- **Strategy Registry**: Centralized registration and discovery of strategies

## Key Features

- 🎯 **Multiple Strategy Types**: Momentum, mean-reversion, trend-following, arbitrage
- 🧠 **Neural Network Integration**: Deep learning strategies with geometric features
- ⚡ **Production-Ready**: Battle-tested implementations with risk controls
- 🔧 **Configurable**: Extensive parameter customization via YAML
- 📊 **Backtestable**: Fully compatible with backtest module
- 🔄 **Event-Driven**: Reactive to market data and order events
- 🎛️ **Strategy Composition**: Combine multiple strategies into ensembles

## Module Structure

```
strategies/
├── __init__.py                  # Public API exports
├── neuro_trade_pulse.py        # Neuroeconomic trading strategy
├── quantum_neural.py           # Quantum-inspired neural strategy
└── registry.py                 # Strategy registration system
```

## Technology Stack

- **Python**: 3.11+ with type annotations
- **NumPy/Pandas**: Data manipulation and numerical computing
- **Scikit-learn**: Machine learning utilities
- **Core Indicators**: Geometric and technical indicators from core module

## Installation

```bash
# Base installation
pip install -e .

# With neural network support
pip install -e ".[neuro_advanced]"
```

## Usage Examples

### Using NeuroTradePulse Strategy

```python
from strategies import NeuroTradePulseStrategy

# Initialize neuroeconomic strategy
strategy = NeuroTradePulseStrategy(
    lookback_period=50,
    risk_aversion=0.5,
    use_geometric_indicators=True,
    indicators=["kuramoto", "ricci_flow", "vpin"]
)

# Generate signals
signals = strategy.generate_signals(market_data)

# Execute trades
for signal in signals:
    if signal.strength > 0.7:  # High confidence signals only
        order = strategy.create_order(signal)
        await execution_engine.submit_order(order)
```

### Using Quantum Neural Strategy

```python
from strategies import QuantumNeuralStrategy

# Initialize quantum-inspired strategy
strategy = QuantumNeuralStrategy(
    n_qubits=8,
    entanglement_layers=3,
    learning_rate=0.001,
    ensemble_size=5
)

# Train on historical data
strategy.train(
    training_data=historical_data,
    validation_split=0.2,
    epochs=100
)

# Generate predictions
predictions = strategy.predict(current_market_data)

# Create trading signals
signals = strategy.signals_from_predictions(predictions)
```

### Creating Custom Strategies

```python
from strategies.base import BaseStrategy, Signal

class MyCustomStrategy(BaseStrategy):
    """Custom momentum strategy with volatility filter"""
    
    def __init__(self, momentum_period: int = 20, volatility_threshold: float = 0.02):
        super().__init__(name="custom_momentum")
        self.momentum_period = momentum_period
        self.volatility_threshold = volatility_threshold
    
    def generate_signals(self, data: pd.DataFrame) -> list[Signal]:
        """Generate trading signals based on momentum and volatility"""
        # Calculate momentum
        momentum = data["close"].pct_change(self.momentum_period)
        
        # Calculate volatility
        volatility = data["close"].pct_change().rolling(20).std()
        
        # Generate signals
        signals = []
        for idx, row in data.iterrows():
            if volatility.loc[idx] < self.volatility_threshold:
                if momentum.loc[idx] > 0:
                    signals.append(Signal(
                        symbol=row["symbol"],
                        side="buy",
                        strength=abs(momentum.loc[idx]),
                        timestamp=idx
                    ))
                elif momentum.loc[idx] < 0:
                    signals.append(Signal(
                        symbol=row["symbol"],
                        side="sell",
                        strength=abs(momentum.loc[idx]),
                        timestamp=idx
                    ))
        
        return signals
    
    def on_market_data(self, event):
        """React to market data updates"""
        signals = self.generate_signals(event.data)
        for signal in signals:
            self.emit_signal(signal)

# Register custom strategy
from strategies import register_strategy
register_strategy("custom_momentum", MyCustomStrategy)
```

### Strategy Registry

```python
from strategies import get_strategy, list_strategies

# List all available strategies
available = list_strategies()
print(f"Available strategies: {available}")

# Get strategy by name
strategy_class = get_strategy("neuro_trade_pulse")
strategy = strategy_class(lookback_period=50)

# Or use registry decorator
@register_strategy("my_new_strategy")
class MyNewStrategy(BaseStrategy):
    pass
```

### Strategy Ensembles

```python
from strategies import StrategyEnsemble, VotingMethod

# Create ensemble of multiple strategies
ensemble = StrategyEnsemble(
    strategies=[
        ("momentum", MomentumStrategy(lookback=20)),
        ("mean_reversion", MeanReversionStrategy(lookback=30)),
        ("neural", NeuroTradePulseStrategy())
    ],
    voting_method=VotingMethod.WEIGHTED,
    weights=[0.3, 0.3, 0.4]  # Higher weight on neural
)

# Generate ensemble signals
signals = ensemble.generate_signals(market_data)

# Signals are combined based on voting method
for signal in signals:
    print(f"Ensemble Signal: {signal.side} strength={signal.strength:.2f}")
```

## Pre-built Strategies

### NeuroTradePulse Strategy

An advanced neuroeconomic strategy that combines:
- Geometric market indicators (Kuramoto, Ricci Flow)
- Neural network signal processing
- Risk-aware position sizing
- Adaptive parameter tuning

**Best for**: Medium to long-term trading, trending markets

```python
strategy = NeuroTradePulseStrategy(
    lookback_period=50,
    risk_aversion=0.5,
    use_geometric_indicators=True
)
```

### Quantum Neural Strategy

Quantum-inspired neural network strategy utilizing:
- Quantum circuit layers for feature extraction
- Entanglement for capturing non-linear relationships
- Ensemble of quantum models
- Uncertainty quantification

**Best for**: Complex market regimes, high-frequency signals

```python
strategy = QuantumNeuralStrategy(
    n_qubits=8,
    entanglement_layers=3,
    ensemble_size=5
)
```

## Strategy Parameters

### Common Parameters

All strategies support these base parameters:

- `lookback_period`: Historical data window size
- `risk_aversion`: Risk preference (0=aggressive, 1=conservative)
- `position_sizing_method`: "fixed", "kelly", "volatility_scaled"
- `max_position_size`: Maximum position as fraction of capital
- `stop_loss_pct`: Stop-loss percentage
- `take_profit_pct`: Take-profit percentage

### NeuroTradePulse Parameters

```yaml
neuro_trade_pulse:
  lookback_period: 50
  risk_aversion: 0.5
  use_geometric_indicators: true
  indicators:
    - kuramoto
    - ricci_flow
    - vpin
  neural_network:
    hidden_layers: [64, 32, 16]
    activation: "relu"
    dropout: 0.2
  position_sizing:
    method: "kelly"
    max_leverage: 2.0
```

### Quantum Neural Parameters

```yaml
quantum_neural:
  n_qubits: 8
  entanglement_layers: 3
  learning_rate: 0.001
  ensemble_size: 5
  training:
    epochs: 100
    batch_size: 32
    validation_split: 0.2
```

## Running Tests

```bash
# Run all strategy tests
pytest tests/unit/strategies -v

# Test specific strategy
pytest tests/unit/strategies/test_neuro_trade_pulse.py -v

# Run backtests for all strategies
pytest tests/integration/strategies -v --run-backtests
```

## Configuration

Configure strategies via YAML:

```yaml
# config/strategies.yaml
strategies:
  default_strategy: neuro_trade_pulse
  
  neuro_trade_pulse:
    lookback_period: 50
    risk_aversion: 0.5
    use_geometric_indicators: true
    indicators: [kuramoto, ricci_flow, vpin]
  
  quantum_neural:
    n_qubits: 8
    entanglement_layers: 3
    ensemble_size: 5
  
  ensemble:
    enabled: true
    strategies: [momentum, mean_reversion, neural]
    voting_method: weighted
    weights: [0.3, 0.3, 0.4]
```

## Performance Considerations

- **Vectorization**: Use NumPy operations for indicator calculations
- **Caching**: Cache expensive computations (e.g., neural network predictions)
- **Batch Processing**: Process multiple symbols simultaneously
- **Lazy Evaluation**: Only compute indicators when needed

## Best Practices

1. **Backtest Thoroughly**: Test strategies on multiple time periods and market regimes
2. **Use Walk-Forward**: Validate with out-of-sample testing
3. **Set Conservative Parameters**: Start with low risk and adjust gradually
4. **Monitor Performance**: Track strategy metrics in production
5. **Diversify**: Use multiple strategies to reduce risk
6. **Rebalance Regularly**: Adjust positions based on changing conditions
7. **Document Parameters**: Keep detailed records of parameter choices

## Strategy Development Checklist

- [ ] Implement `generate_signals()` method
- [ ] Add parameter validation in `__init__()`
- [ ] Include risk controls (stop-loss, position limits)
- [ ] Write unit tests for signal generation
- [ ] Backtest on historical data
- [ ] Perform walk-forward analysis
- [ ] Document strategy logic and parameters
- [ ] Register in strategy registry
- [ ] Add example usage to documentation

## Architecture

```
┌──────────────────────────────────────────────────────┐
│              Strategy Interface                      │
├──────────────────────────────────────────────────────┤
│  BaseStrategy                                        │
│  ├─ generate_signals()                               │
│  ├─ on_market_data()                                 │
│  ├─ on_order_filled()                                │
│  └─ update_parameters()                              │
├──────────────────────────────────────────────────────┤
│  Strategy Implementations                            │
│  ├─ NeuroTradePulse  ├─ QuantumNeural               │
├──────────────────────────────────────────────────────┤
│  Support Layer                                       │
│  ├─ Indicators  ├─ Risk Controls  ├─ Position Sizer │
└──────────────────────────────────────────────────────┘
```

## Related Modules

- [`core`](../core/README.md): Core indicators and infrastructure
- [`execution`](../execution/README.md): Order execution
- [`backtest`](../backtest/README.md): Strategy backtesting
- [`analytics`](../analytics/README.md): Performance analysis

## Documentation

- [API Reference](https://docs.tradepulse.io/api/strategies)
- [Strategy Development Guide](https://docs.tradepulse.io/guides/strategy-development)
- [Backtesting Strategies](https://docs.tradepulse.io/guides/backtesting-strategies)

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for:
- Strategy development guidelines
- Testing requirements
- Documentation standards

## License

See [LICENSE](../LICENSE) for licensing details.

## Support

- [GitHub Issues](https://github.com/neuron7x/TradePulse/issues)
- [Documentation](https://docs.tradepulse.io)
- [Community](https://github.com/neuron7x/TradePulse/discussions)
