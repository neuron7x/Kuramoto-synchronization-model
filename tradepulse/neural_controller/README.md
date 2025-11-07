# NeuralMarketController (EMH Neuro-Adaptation Layer)

EMH-SSM → EKF (clean) → Belief → Homeostasis → BasalGanglia (Go/No-Go) → CVaR → TACL/Kuramoto Bridge.

**Quickstart**
```python
from tradepulse.neural_controller import *
ctrl = NeuralMarketController.from_yaml("tradepulse/neural_controller/config/neural_params.yaml")
obs = {"dd":0.2,"liq":0.3,"reg":0.4,"vol":0.5,"reward":0.01,"var_breach":False,"m_proxy":0.6}
decision = ctrl.decide(obs)               # pure neural decide
# bridge usage (pass real TACL/Kuramoto from TradePulse)
bridge = NeuralTACLBridge(ctrl, tacl_system, kuramoto_sync, sync_threshold=0.30, generations=10)
out = bridge.step(obs)                    # adds optimization + desync throttle
```

**Invariants**

* States clamped to [0,1]
* `mode=RED` ⇒ `increase_risk` forbidden
* CVaR gate ensures `ES ≤ cvar_limit` after scaling
* One state update per tick; EKF is side-effect-free
