# Serotonin Stabilizer Module v2.2

## Overview
SerotoninController v2.2 realises a serotonin-inspired inhibitory loop that
translates aversive market cues into deterministic action modulation. The
implementation follows 2025 prospective value and aversive learning findings,
providing:

- **Prospective value coding** that aggregates volatility, free energy and loss
  statistics into a release signal.
- **Exponential tonic filtering** with a decay constant of 0.05 (≈20 tick time
  constant) to maintain contextual awareness.
- **Adaptive desensitisation** with capped counters to avoid chronic
  inhibition while ensuring a hard lower bound at sensitivity 0.1.
- **Meta-adaptation** that nudges release weights based on drawdown and Sharpe
  ratios, aligning with target risk appetites.
- **Action modulation hooks** for the Fractal Motivation Engine and risk
  manager, delivering noise reduction, HOLD veto enforcement and exploitation
  tempering.

## Configuration
Default parameters live in `configs/serotonin.yaml` and can be tuned at runtime.
Key fields include:

| Parameter | Description |
|-----------|-------------|
| `alpha`, `beta`, `gamma`, `delta_rho` | Linear weights for the aversive release estimator. |
| `decay_rate` | Exponential filter rate for the tonic level. |
| `k`, `theta` | Logistic transform controls for tonic to serotonin conversion. |
| `delta`, `za_bias` | Action inhibition gain and aversive bias. |
| `cooldown_threshold` | HOLD veto activation threshold. |
| `desens_rate`, `desens_threshold_ticks`, `max_desens_counter` | Desensitisation cadence, onset tick, and counter cap. |
| `beta_temper` | Gradient tempering coefficient. |
| `target_dd`, `target_sharpe` | Objectives for the meta-adaptation routine. |

## Usage
```python
import logging
from core.neuro.serotonin import SerotoninController

logger = logging.getLogger("tradepulse.serotonin")
controller = SerotoninController("configs/serotonin.yaml", logger.info)

release = controller.estimate_aversive_state(1.0, 0.5, 0.2, -0.90)
serotonin_signal = controller.compute_serotonin_signal(release)
modulated_prob = controller.modulate_action_prob(0.85, serotonin_signal)
if controller.check_cooldown(serotonin_signal):
    # Trigger HOLD veto in the risk manager
    ...

shifted_gradient = controller.apply_internal_shift(2.0, serotonin_signal)
controller.update_metrics()
controller.meta_adapt({"drawdown": -0.06, "sharpe": 1.2})
state_snapshot = controller.to_dict()
```

## Testing
Unit tests covering release estimation, tonic dynamics, desensitisation,
validation paths, logging hooks and persistence live in
`core/neuro/tests/test_serotonin_controller.py`. Execute them with:

```bash
pytest core/neuro/tests/test_serotonin_controller.py
```
