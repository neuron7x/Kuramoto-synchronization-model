# Integration Patch Outline

1. Instantiate components:

```python
from tradepulse.neural_controller import (
    MarketDataAdapter,
    NeuralMarketController,
    NeuralTACLBridge,
    KuramotoSync,
    TACLSystem,
)

adapter = MarketDataAdapter()
neural = NeuralMarketController.from_yaml("tradepulse/neural_controller/config/neural_params.yaml")
tacl = TACLSystem()  # wraps runtime ThermoController when available
kuramoto = KuramotoSync()
bridge = NeuralTACLBridge(neural, tacl, kuramoto)
```

2. Wrap strategy output before risk manager:

```python
def process_signal(strategy, candles, portfolio):
    base_signal = strategy.compute(candles, portfolio)
    obs = adapter.transform(candles, portfolio)
    out = bridge.step(obs)

    action = out["action"]
    allocs = out["allocs"]

    risk_manager.apply_neural_directive(
        action=action,
        alloc_main=allocs["main"],
        alloc_alt=allocs["alt"],
        alloc_scale=out["alloc_scale"],
    )

    metrics.emit(
        emh_mode=out["mode"],
        emh_D=out["D"],
        emh_H=out["H"],
        emh_M=out["M"],
        emh_E=out["E"],
        emh_S=out["S"],
        emh_RPE=out["RPE"],
        emh_belief=out["belief"],
        emh_alloc_scale=out["alloc_scale"],
        emh_tail_ES95=out["tail_ES95"],
        emh_prop_RED=out["prop_RED"],
        emh_prop_increase_risk_in_RED=out["prop_increase_risk_in_RED"],
        emh_rpe_mean=out["rpe_mean"],
        sync_order=out["sync_order"],
        tacl_temp=out["temperature"],
        tacl_coupling=out["coupling"],
    )
```

3. Grafana dashboards: `emh_mode`, `alloc_scale`, `tail_ES95`, `gate_blocks` (Go/No-Go veto counts), `sync_order`, `tacl_coupling`.
