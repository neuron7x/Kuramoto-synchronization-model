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
- **Dynamic temperature floor synthesis** that linearly expands the dopamine
  temperature floor bounds as serotonin inhibition grows, keeping exploration
  temperatures above configurable minima during stress periods.

## Public API

The public interface is intentionally small and stable:

| Method | Contract |
|--------|----------|
| `step(stress, drawdown, novelty, **kwargs)` | **Primary API**: Consolidated control step returning `(hold, veto, cooldown_s, level)`. Accepts high-level inputs (stress, drawdown, novelty) and optional overrides for market_vol, free_energy, cum_losses, rho_loss. Emits TACL telemetry. Thread-safe. |
| `estimate_aversive_state(market_vol, free_energy, cum_losses, rho_loss, override_weights=None)` | Returns a non-negative float release signal. Inputs must be ≥0 except `rho_loss`, which is clamped to [-1, 1]. |
| `compute_serotonin_signal(aversive_state)` | Updates the internal tonic/phasic state and returns the serotonin level in [0, 1]. Input must be ≥0. Thread-safe. |
| `modulate_action_prob(original_prob, serotonin_signal=None, za_bias=None)` | Applies inhibition and bias, returning a probability in [0, 1]. Raises `ValueError` when `original_prob` is outside [0, 1]. |
| `check_cooldown(serotonin_signal=None)` | Returns `True` when any veto channel (tonic, phasic, gate) exceeds configured thresholds. Consults the optional TACL guard before final approval. |
| `apply_internal_shift(exploitation_gradient, serotonin_signal=None, beta_temper=None)` | Returns a tempered gradient. Raises `ValueError` for negative gradients. |
| `meta_adapt(performance_metrics)` | Mutates release weights according to drawdown/Sharpe metrics, guarded by TACL. Persists the config atomically and writes an audit snapshot. |
| `to_dict()` | Serialises the controller state for auditing, including hold_state and cooldown_s. |
| `set_tacl_guard(guard_fn)` | Registers a callable `(event_name, payload) -> bool` invoked for cooldown and meta-adapt actions. |
| **`save_state(path)`** | **NEW**: Saves controller state to JSON for recovery or analysis. Includes metadata (timestamp, step count, veto metrics). |
| **`load_state(path)`** | **NEW**: Loads controller state from JSON file. Validates and restores core state and performance metrics. |
| **`reset()`** | **NEW**: Resets controller to initial state while preserving configuration. Useful for testing or recovery. |
| **`health_check()`** | **NEW**: Returns diagnostic dict with health status, issues, warnings, and current state. Detects stuck HOLD, low sensitivity, invalid config. |
| **`get_performance_metrics()`** | **NEW**: Returns performance statistics: step_count, veto_count, veto_rate, cooldown durations. |
| **`diagnose()`** | **NEW**: Generates formatted diagnostic report for troubleshooting. Includes state, thresholds, metrics, and health status. |

Internally-scoped helpers are prefixed with `_` and are not part of the compatibility surface.

## Configuration

Default parameters live in `configs/serotonin.yaml`. The controller first
attempts to load the given path, then `GEOSYNC_CONFIG_DIR/serotonin.yaml`, and
finally the deprecated `config/serotonin.yaml`, emitting a warning when
falling back. Configuration is validated through `SerotoninConfig`
(`pydantic`), which also exposes a JSON Schema and Markdown table for
documentation. Generate artefacts via:

```bash
python -m core.neuro.serotonin.serotonin_controller > /tmp/serotonin_schema.json
python - <<'PY'
from core.neuro.serotonin import SerotoninConfig, _generate_config_table
print(_generate_config_table(SerotoninConfig.model_json_schema()))
PY
```

| Key | Type | Constraints | Description |
| --- | --- | --- | --- |
| alpha | number | minimum=0.0; required | Weight for market volatility |
| beta | number | minimum=0.0; required | Weight for free energy term |
| gamma | number | minimum=0.0; required | Weight for cumulative losses |
| delta_rho | number | minimum=0.0; maximum=5.0; required | Weight for rho-loss complement |
| k | number | exclusiveMinimum=0.0; required | Logistic steepness parameter |
| theta | number | minimum=-5.0; maximum=5.0; required | Logistic mid-point for tonic level |
| delta | number | minimum=0.0; maximum=5.0; required | Inhibition multiplier |
| za_bias | number | minimum=-1.0; maximum=1.0; required | Zero-action bias applied post inhibition |
| decay_rate | float | — | Tonic decay rate per decision step |
| cooldown_threshold | number | minimum=0.0; maximum=1.0; required | Serotonin signal threshold for veto |
| desens_threshold_ticks | integer | minimum=0; required | Ticks above threshold before desensitisation |
| desens_rate | number | minimum=0.0; maximum=1.0; required | Recovery rate when below threshold |
| target_dd | number | required | Target drawdown for meta-adapt |
| target_sharpe | number | exclusiveMinimum=0.0; required | Target Sharpe for meta-adapt |
| beta_temper | number | minimum=0.0; maximum=1.0; required | Gradient tempering coefficient |
| phase_threshold | number | minimum=0.0; required | Threshold for triggering phasic bursts |
| phase_kappa | number | exclusiveMinimum=0.0; required | Smoothing factor for phasic gate sigmoid |
| burst_factor | number | minimum=0.0; required | Scaling factor for phasic component |
| mod_t_max | number | exclusiveMinimum=0.0; required | Time constant for modulation saturation |
| mod_t_half | number | exclusiveMinimum=0.0; required | Half-life for modulation decay |
| mod_k | number | minimum=-5.0; maximum=5.0; required | Modulation gain |
| max_desens_counter | integer | minimum=1; required | Maximum desensitisation counter |
| desens_gain | number | exclusiveMinimum=0.0; required | Gain applied during desensitisation |
| gate_veto | number | minimum=0.0; maximum=1.0 | Gate level above which cooldown veto triggers |
| phasic_veto | number | minimum=0.0 | Phasic level above which cooldown veto triggers |
| temperature_floor_min | number | minimum=0.0; maximum=1.0 | Lower bound for the serotonin-governed temperature floor |
| temperature_floor_max | number | minimum=0.0; maximum=1.0 | Upper bound for the serotonin-governed temperature floor |
| tau_5ht_ms | float | — | Tonic decay time constant in milliseconds |
| step_ms | float | — | Decision step duration in milliseconds |
| tick_hours | number | exclusiveMinimum=0.0 | Wall-clock hours represented by a controller tick |

All time-based parameters are interpreted as: `tau_5ht_ms`/`step_ms` in
milliseconds, `tick_hours` in hours. When both `tau_5ht_ms` and `step_ms` are
provided, `decay_rate` is derived as `1 - exp(-step_ms/tau_5ht_ms)` and logged
for traceability.

## Usage

### Primary API: step() method
```python
import logging
from core.neuro.serotonin import SerotoninController

logger = logging.getLogger("geosync.serotonin")

def tacl_guard(name: str, payload: dict[str, float]) -> bool:
    """Return ``True`` to accept serotonin proposals (stub for demo)."""
    return payload.get("drawdown", 0.0) <= 0.0

controller = SerotoninController("configs/serotonin.yaml", logger.info)
controller.set_tacl_guard(tacl_guard)

# Primary API: single step() call handles everything
hold, veto, cooldown_s, level = controller.step(
    stress=1.2,      # Current market stress
    drawdown=-0.03,  # 3% drawdown
    novelty=0.8      # Uncertainty measure
)

if hold:
    print(f"HOLD triggered: level={level:.3f}, cooldown={cooldown_s:.1f}s")
    # Risk manager vetoes new positions
else:
    print(f"Trading allowed: level={level:.3f}")

# Update telemetry periodically
controller.update_metrics()

# Meta-adaptation based on performance
controller.meta_adapt({"drawdown": -0.06, "sharpe": 1.2})
```

### Advanced Usage: granular control
```python
# For fine-grained control, use individual methods
release = controller.estimate_aversive_state(1.0, 0.5, 0.2, -0.90)
serotonin_signal = controller.compute_serotonin_signal(release)
modulated_prob = controller.modulate_action_prob(0.85, serotonin_signal)
if controller.check_cooldown(serotonin_signal):
    # Trigger HOLD veto in the risk manager
    ...

shifted_gradient = controller.apply_internal_shift(2.0, serotonin_signal)
state_snapshot = controller.to_dict()
```

### Production Usage Patterns

**State Persistence and Recovery**
```python
# Save state periodically for recovery
controller.save_state("checkpoints/serotonin_state.json")

# Recover from crash or restart
try:
    controller.load_state("checkpoints/serotonin_state.json")
    logger.info("Restored from checkpoint")
except FileNotFoundError:
    logger.info("Starting fresh")
```

**Health Monitoring**
```python
# Regular health checks
health = controller.health_check()
if not health["healthy"]:
    logger.error(f"Controller issues: {health['issues']}")
    # Alert ops team or trigger recovery
    controller.reset()

# Log warnings
for warning in health["warnings"]:
    logger.warning(f"Serotonin: {warning}")
```

**Performance Monitoring**
```python
# Track performance metrics
metrics = controller.get_performance_metrics()
logger.info(f"Veto rate: {metrics['veto_rate']:.2%}")
logger.info(f"Avg cooldown: {metrics['average_cooldown_duration']:.1f}s")

# Alert on high veto rate
if metrics["veto_rate"] > 0.5 and metrics["step_count"] > 100:
    logger.warning("High veto rate detected")
```

**Diagnostic Troubleshooting**
```python
# Generate diagnostic report
if trading_errors_detected:
    report = controller.diagnose()
    logger.info(report)
    # Save to incident logs
    with open(f"incidents/{timestamp}_serotonin.txt", "w") as f:
        f.write(report)
```

**Context Manager for Resource Management**
```python
# Use as context manager for automatic cleanup
with SerotoninController("configs/serotonin.yaml") as controller:
    for tick in trading_session:
        hold, veto, cooldown_s, level = controller.step(
            stress=tick.volatility,
            drawdown=tick.drawdown,
            novelty=tick.regime_uncertainty
        )
        if hold:
            skip_trading_tick()
```

### Integration Notes

- **FME (probabilistic policy):** call `modulate_action_prob` on Thompson
  samples. The inhibition stage reduces variance while the `za_bias` introduces
  an aversive bias.
- **Risk manager:** issue a HOLD veto when `check_cooldown()` returns `True`.
- **DDM / basal ganglia emulator:** consume `serotonin_level` as a z-bias offset
  and `gate_level` for veto escalation when solving the drift-diffusion model in
  aversive contexts.
- **Exploitation gradient consumers:** temper gradients via
  `apply_internal_shift` to avoid over-aggressive updates during aversive
  regimes.
- **Telemetry:** all metrics are emitted with the Prometheus-compatible tag
  `controller_version="v2.3.1"`, including the adaptive `serotonin_temperature_floor`.
  Use the optional
  `SerotoninController.prometheus_logger` helper to forward to your collector.


## Behavioral Profiling

The serotonin controller includes a comprehensive behavioral profiler for characterizing
tonic/phasic dynamics and veto/cooldown patterns under various stress scenarios.

### Profiler Features

- **Complete Behavioral Characterization**: Tonic/phasic dynamics, veto/cooldown patterns
- **Multiple Profiling Modes**: Stress response, ramping stress, stress pulses
- **Performance Analytics**: Rise/decay times, burst frequencies, hysteresis analysis
- **Visualization**: Automated plotting of behavioral profiles
- **Export/Import**: JSON serialization for profile comparison

### Usage Example

```python
from core.neuro.serotonin import SerotoninController
from core.neuro.serotonin.profiler import SerotoninProfiler

# Create controller and profiler
controller = SerotoninController("configs/serotonin.yaml")
profiler = SerotoninProfiler(controller)

# Profile stress response
profile = profiler.profile_stress_ramp(
    stress_min=0.0,
    stress_max=3.0,
    total_steps=500
)

# Analyze characteristics
print(f"Tonic baseline: {profile.tonic_phasic.tonic_baseline:.3f}")
print(f"Veto threshold: {profile.veto_cooldown.veto_threshold:.3f}")
print(f"Veto rate: {profile.statistics.veto_rate:.2%}")

# Generate report
print(profile.generate_report())

# Save profile
profile.save("profiles/serotonin_profile.json")

# Generate plots
profiler.plot_profile(profile, output_path="profiles/serotonin_plot.png")
```

### CLI Tool

```bash
# Profile with ramping stress
python -m core.neuro.serotonin.profiler.cli \
    --config configs/serotonin.yaml \
    --mode ramp \
    --steps 500 \
    --output profile.json \
    --plot \
    --report

# Profile stress pulses
python -m core.neuro.serotonin.profiler.cli \
    --config configs/serotonin.yaml \
    --mode pulse \
    --plot

# Profile discrete stress levels
python -m core.neuro.serotonin.profiler.cli \
    --config configs/serotonin.yaml \
    --mode response \
    --stress-levels 0.5,1.0,1.5,2.0,2.5 \
    --report
```

### Profile Characteristics

**Tonic/Phasic Metrics:**
- Tonic baseline, peak, rise/decay times
- Phasic activation threshold, peak amplitude, burst frequency
- Sensitivity floor, recovery rate, desensitization onset

**Veto/Cooldown Metrics:**
- Veto threshold, activation/deactivation latency
- Cooldown mean/max duration, frequency
- Hysteresis width, recovery threshold
- Veto contribution breakdown (gate/phasic/tonic)

**Statistical Summary:**
- Total steps, veto count, veto rate
- Stress/serotonin mean, std, max
- Component level averages

## Migration Notes (v2.3.1)

- `gate_veto` and `phasic_veto` replace hard-coded thresholds for HOLD vetoes.
- The configuration loader now supports `GEOSYNC_CONFIG_DIR`; the legacy
  `config/` path remains functional but is deprecated.
- Config persistence is atomic and mirrored into `configs/audit/` for TACL’s
  seven-year retention requirement.
- Desensitisation is governed by a configurable exponential gain and respects
  the hard floor of `0.1`.
- Telemetry names follow the `serotonin_*{controller_version="v2.3.1"}` format.

## Testing
Unit tests covering release estimation, tonic dynamics, desensitisation,
validation paths, logging hooks and persistence live in
`core/neuro/tests/test_serotonin_controller.py`. Execute them with:

```bash
pytest core/neuro/tests/test_serotonin_controller.py
```
