# Integration Patch Outline

1. Instantiate components:

```python
from tradepulse.neural_controller import MarketDataAdapter, NeuralMarketController, NeuralTACLBridge
from tradepulse.neural_controller import KuramotoSync, TACLSystem

adapter = MarketDataAdapter()
neural = NeuralMarketController.from_yaml("tradepulse/neural_controller/config/neural_params.yaml")
tacl = TACLSystem()        # replace with production implementation
kuramoto = KuramotoSync()  # replace with production implementation
bridge = NeuralTACLBridge(neural, tacl, kuramoto, sync_threshold=0.30)
```

2. Wrap strategy output before risk manager:

```python
def process_signal(strategy, candles, portfolio):
    base_signal = strategy.compute(candles, portfolio)
    obs = adapter.transform(candles, portfolio)
    out = bridge.step(obs)

    action = out["action"]
    allocs = out["allocs"]
    if action == "increase_risk":
        risk_manager.scale_up(allocs["main"])
    elif action == "decrease_risk":
        risk_manager.scale_down(allocs["main"])
    elif action in ("switch_to_alt", "hedge"):
        risk_manager.route_alt(allocs["alt"])
    else:
        risk_manager.hold()

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
        emh_action=out["action"],
        sync_order=out["sync_order"],
        tacl_temp=out["temperature"],
    )
```

3. Instrument dashboards to monitor `emh_mode`, `emh_alloc_scale`, `sync_order`, and CVaR statistics.
