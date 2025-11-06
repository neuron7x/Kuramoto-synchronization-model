# Serotonin Stabilizer Module v2.3.1

## Overview

SerotoninController v2.3.1 realises a serotonin-inspired inhibitory loop that
translates aversive market cues into deterministic action modulation. The
implementation follows 2025 prospective value and aversive learning findings,
providing:

- **Prospective value coding** that aggregates volatility, free energy and loss
  statistics into a release signal.
- **τ-calibrated tonic filtering** that derives the decay rate from
  physiological time constants and decision step durations.
- **Smooth phasic gating** that blends tonic and burst modes without threshold
  discontinuities while exposing HOLD veto triggers across tonic, gate, and
  phasic channels.
- **Exponential desensitisation** with configurable gain and capped counters to
  avoid chronic inhibition while ensuring a hard lower bound at sensitivity
  0.1.
- **Meta-adaptation with TACL guardrails** that nudges release weights based on
  drawdown and Sharpe ratios while enforcing monotonic free-energy descent.
- **Expanded telemetry** for tonic, phasic, gate, sensitivity, and drift
  metrics.
- **Action modulation hooks** for the Fractal Motivation Engine and risk
  manager, delivering noise reduction, HOLD veto enforcement and exploitation
  tempering.

## Configuration
Default parameters live in `configs/serotonin.yaml` and can be tuned at runtime.
Key fields include:

| Parameter | Description |
|-----------|-------------|
| `alpha`, `beta`, `gamma`, `delta_rho` | Linear weights for the aversive release estimator. |
| `decay_rate` | Exponential filter rate for the tonic level (derived from `tau_5ht_ms` and `step_ms` when provided). |
| `k`, `theta` | Logistic transform controls for tonic to serotonin conversion. |
| `delta`, `za_bias` | Action inhibition gain and aversive bias. |
| `cooldown_threshold` | HOLD veto activation threshold. |
| `phase_threshold`, `phase_kappa`, `burst_factor` | Smooth phase gate and burst scaling controls. |
| `desens_rate`, `desens_threshold_ticks`, `max_desens_counter`, `desens_gain` | Desensitisation cadence, onset tick, counter cap, and exponential gain. |
| `beta_temper` | Gradient tempering coefficient. |
| `target_dd`, `target_sharpe` | Objectives for the meta-adaptation routine. |
| `mod_t_half`, `mod_t_max`, `mod_k`, `tick_hours` | Time-scaled modulation parameters for meta-adaptation. |
| `tau_5ht_ms`, `step_ms` | Optional physiological constants to derive the tonic decay rate. |

## Usage
```python
import logging
from core.neuro.serotonin import SerotoninController

logger = logging.getLogger("tradepulse.serotonin")

def tacl_guard(name: str, payload: dict[str, float]) -> bool:
    """Return ``True`` to accept serotonin proposals (stub for demo)."""

    return payload.get("drawdown", 0.0) <= 0.0


controller = SerotoninController("configs/serotonin.yaml", logger.info)
controller.set_tacl_guard(tacl_guard)

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
