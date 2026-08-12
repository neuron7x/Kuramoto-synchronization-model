# Neurodecision Stack

## Architecture Overview

```
 market state ─┐
               │   ┌─────────────────────┐
 reward stream ├──►│ Dopamine Controller │──┐
 novelty feed  ┘   └─────────────────────┘  │
                                             ▼
                                   ┌────────────────┐
 stress / drawdown ───────────────►│ Serotonin 5-HT │─┐
 impulses (trade cadence) ────────►│    Veto Gate   │─┼─► ActionGate ─► Basal Ganglia decision
 volatility ──────────────────────►│ GABA Inhibitor │─┤
 novelty ─────────────────────────►│  NA/ACh Tone   │─┘
```

1. **Dopamine** computes TD(0) reward prediction error (RPE), tonic/phasic decomposition, and policy temperature control. Release gates prevent spurious Go bursts under high RPE variance.
2. **Serotonin (5-HT)** accumulates stress, drawdown, and novelty into a hysteretic hold signal with chronic stress desensitisation. When active it enforces HOLD decisions and floors the exploration temperature.
3. **GABA** tracks impulsive trading sequences, applying a bounded inhibition coefficient and optional STDP-like plasticity tied to RPE.
4. **NA/ACh** derive arousal from volatility and attention from novelty, scaling both risk budget and the weight of fresh signals.
5. **ActionGate** fuses the neuromodulators into a stable `GO|NO_GO|HOLD` output, respecting vetoes and inhibitory pressure before surfacing the decision via the basal ganglia policy API.

## Mathematical Summary

- **RPE**: \( \delta_t = r_t + \gamma V_{t+1} - V_t \), with \(\lambda = 0\).
- **Tonic DA**: \( T_t = (1-\beta) T_{t-1} + \beta (A_t + P_t) \) where \(A_t\) is appetitive drive and \(P_t\) is the positive phasic burst.
- **Phasic DA**: \( P_t = \max(0, \delta_t) \cdot \text{burst\_factor} \).
- **Policy temperature**: \( \tau_t = \max(\tau_{\min}, \tau_{base} e^{-k_T D_t}) \) adjusted by DDM scaling and NA/ACh temperature factors.
- **Serotonin hold**: triggered when \(S_t \geq \theta_{hold}\) with release at \(\theta_{release}\); chronic exposure increases desensitisation \(d_t\) reducing effective level \(S_t (1-d_t)\).
- **GABA inhibition**: \( G_t = \text{clip}( (I_t - I_{th})^+ g_s (1 + g_{stress} \cdot stress), 0, g_{max} ) \) with STDP update \( w_{t+1} = \text{clip}(w_t + \eta (\delta_t - \bar{\delta}) (I_t - I_{th})^+, w_{min}, w_{max}) \).
- **NA/ACh scaling**: risk multiplier \( \rho_t = \text{clip}(1 + (a_t - a_0), \rho_{min}, \rho_{max}) \); attention \( \alpha_t = \text{clip}(a_{base} + g_a (novelty - a_{base}), a_{min}, a_{max}) \).

## Configuration Summary

| Module | Key Parameters | Description |
| --- | --- | --- |
| Dopamine | `discount_gamma`, `burst_factor`, `base_temperature`, `rpe_var_release_threshold` | TD learning, phasic scaling, exploration temperature, and release gate tuning. |
| Serotonin | `stress_threshold`, `release_threshold`, `cooldown_ticks`, `max_desensitization` | HOLD hysteresis, cooldown window, and chronic stress adaptation. |
| GABA | `impulse_decay`, `impulse_threshold`, `inhibition_gain`, `stdp_lr` | Impulse averaging, inhibition gain, and STDP learning rate bounds. |
| NA/ACh | `arousal_gain`, `risk_min`/`risk_max`, `attention_gain`, `temp_gain` | Volatility → arousal mapping and novelty-driven attention scaling. |

Configuration files live under `configs/` and are validated on load. Missing or out-of-range values raise explicit errors.

## Example Usage

```python
from geosync.policy.basal_ganglia import select_action

q_values = {"long": 0.8, "flat": 0.4, "short": 0.2}
constraints = {
    "reward": 0.05,
    "value": 0.7,
    "next_value": 0.75,
    "novelty": 0.3,
    "stress": 0.4,
    "drawdown": 0.1,
    "impulse": 0.2,
    "volatility": 0.5,
}

result = select_action(q_values, constraints)
print(result["decision"], result["score"])
```

The returned payload follows the canonical schema:

```json
{
  "decision": "GO|NO_GO|HOLD",
  "score": 0.0,
  "extras": {
    "dopamine": {"dopamine_level": 0.72, ...},
    "serotonin": {"hold": 0.0, "temperature_floor": 0.2},
    "gaba": {"inhibition": 0.18},
    "na_ach": {"arousal": 0.66, "risk_multiplier": 1.1},
    "temperature": 0.74
  }
}
```

Telemetry channels exposed during decision making:

- `tacl.dopa.rpe`, `tacl.dopa.temp`, `tacl.dopa.ddm.bound`
- `tacl.5ht.level`, `tacl.5ht.hold`, `tacl.5ht.cooldown`
- `tacl.gaba.inhib`, `tacl.gaba.stdp_dw`
- `tacl.na.arousal`, `tacl.ach.attn`
- `tacl.bg.route`, `tacl.bg.score`, `tacl.ag.decision`

These metrics enable downstream observability pipelines to track neuromodulator balance and routing decisions in production.
