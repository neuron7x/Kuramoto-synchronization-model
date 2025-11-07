# Neural Controller for TradePulse

This module supplies a neuro-inspired risk controller that augments TradePulse with:

- EMH-inspired bounded state-space model `(H, M, E, S)` with dopamine-style RPE trigger.
- Extended Kalman Filter free of hidden side-effects.
- Volatility belief filter (high/low regime persistence).
- Basal-ganglia softmax policy with Go/No-Go gating logic.
- CVaR/expected-shortfall allocation gate.
- Homeostatic pressure module to reinforce stability.
- TACL bridge with Kuramoto sync throttle.
- Metrics/logging helpers and validation utilities.

## Installation

Copy the `tradepulse/neural_controller/` directory into your project or install as a package. Dependencies: `numpy`, `pyyaml`. Python 3.11+.

## Quickstart

```python
from tradepulse.neural_controller import (
    MarketDataAdapter,
    NeuralMarketController,
    NeuralTACLBridge,
    KuramotoSync,
    TACLSystem,
)

neural = NeuralMarketController.from_yaml("tradepulse/neural_controller/config/neural_params.yaml")
tacl = TACLSystem()        # replace with production implementation
kuramoto = KuramotoSync()  # replace with production implementation
bridge = NeuralTACLBridge(neural, tacl, kuramoto, sync_threshold=0.30)

adapter = MarketDataAdapter()
obs = adapter.transform(candles, portfolio)
result = bridge.step(obs)
```

## Integration Path

1. Build observations from strategy context with `MarketDataAdapter`.
2. Pass them to `bridge.step(obs)` and receive risk actions and allocations.
3. Map `action` to TradePulse risk manager (scale up/down, hedge, switch to alt, hold).
4. Forward `allocs`, `temperature`, `coupling`, `sync_order` to TACL.
5. Emit metrics via `telemetry.metrics.MetricsEmitter` if needed.

## Guarantees

- All state variables are clamped to `[0, 1]`.
- RED mode forbids `increase_risk`; AMBER requires both `E > tau_E_amber` and positive `RPE`.
- CVaR gate ensures ES(α) does not exceed the configured limit after scaling.
- EKF operates independently from the generative model (no hidden mutations).

## Testing

Unit tests live in `tests/test_integration.py`. Run with:

```bash
pytest tradepulse/neural_controller/tests/test_integration.py
```

They cover state bounds, EKF stability, Go/No-Go, CVaR gate, integration bridge, toy stream generator, and ES calculation.
