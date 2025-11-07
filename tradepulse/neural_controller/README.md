# Neural Controller for TradePulse

The neural controller is the **governing brain** that sits between strategy output
and the Thermodynamic Autonomic Control Layer (TACL). It enforces Monotonic Free
Energy Descent (MFED), harmonises allocations with the CVaR gate, and exports
observability data for the governance dashboards. The stack includes:

- EMH-inspired bounded state-space model `(H, M, E, S)` with dopamine-style RPE trigger.
- Extended Kalman Filter free of hidden side-effects.
- Volatility belief filter (high/low regime persistence).
- Basal-ganglia softmax policy with Go/No-Go gating logic.
- CVaR/expected-shortfall allocation gate.
- Homeostatic pressure module to reinforce stability.
- TACL bridge with configurable generations plus Kuramoto-based synchrony throttle.
- Structured JSON logging and rolling metrics exporter (tail ES95, RED ratios, etc.).

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
tacl = TACLSystem()  # auto-resolves runtime ThermoController when available
kuramoto = KuramotoSync()
bridge = NeuralTACLBridge(neural, tacl, kuramoto)

adapter = MarketDataAdapter()
obs = adapter.transform(candles, portfolio)
decision = bridge.step(obs)
```

## Integration Path

1. Build observations from strategy context with `MarketDataAdapter` (handles missing keys safely).
2. Pass them to `bridge.step(obs)` to receive the action, MFED-compliant allocations, and TACL knobs.
3. Apply `alloc_scale`, `alloc_main`, and `alloc_alt` through the risk manager (see integration patch).
4. Forward `{allocs, temperature, coupling, sync_order}` to the TACL optimiser; respect desync throttles.
5. Use `MetricsEmitter` or Prometheus exporter to publish `tail_ES95`, `prop_RED`, `alloc_scale`, and sync metrics.

## Guarantees

- All state variables are clamped to `[0, 1]`.
- RED mode forbids `increase_risk`; AMBER requires both `E > tau_E_amber` and positive `RPE`.
- CVaR gate ensures ES(α) does not exceed the configured limit after scaling and exports the realised ES95.
- EKF operates independently from the generative model (no hidden mutations).
- JSON decision logs contain `{mode, belief, RPE, allocs, MFED compliance flags}` for audit.

## Observability

- `telemetry.metrics.DecisionMetricsExporter` maintains rolling statistics (`tail_ES95`, `prop_RED`, `prop_increase_risk_in_RED`, `avg_alloc_scale`, `rpe_mean`).
- `telemetry.metrics.MetricsEmitter` emits structured JSON logs consumable by the existing ingestion pipeline.
- Grafana dashboards should include panels for `emh_mode`, `alloc_scale`, `tail_ES95`, `gate_blocks`, and `sync_order`.

## Testing

Unit and property tests live in `tradepulse/neural_controller/tests/`. Run with:

```bash
pytest tradepulse/neural_controller/tests
```

The suite covers EKF invariants, Go/No-Go gating, CVaR monotonicity, YAML loading, bridge throttling, toy-stream bounds, and performance checks (`≤3ms/tick`).
