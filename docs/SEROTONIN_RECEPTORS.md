# Serotonin Receptor Modulators (Engineering Safety Layer)

This optional layer adds bounded, receptor-inspired parameter modulation to the canonical `SerotoninController`. It is **disabled by default** and keeps existing behaviour unchanged when off.

## Enabling

```yaml
# configs/serotonin.yaml
serotonin_v24:
  ...
  receptors:
    enabled: true
    enabled_list: ["5ht3", "5ht1b", "5ht2c", "5ht1a", "5ht7", "5ht2a"]  # pick a subset as needed
```

## What Changes When Enabled

Receptors modulate explicit controller parameters only (all activations are clamped to `[0, 1]`):

- `cooldown_s` (increase)
- `temperature_floor` (bounded by config min/max)
- `pos_mult_cap` (decrease-only risk cap)
- `hold` hysteresis margins (widening only)
- `phasic_weight` (downscale)
- `tonic_weight` (upscale)
- `5-HT3` may assert a fail-closed veto in its own lane

Explainability is attached to diagnostics traces when receptors are enabled (activation map + delta map).

## Receptors

- **5-HT3**: fast alarm, hysteresis latch; increases cooldown, widens hysteresis, may veto.
- **5-HT1B**: impulse throttle; adds cooldown and down-weights phasic component.
- **5-HT2C**: risk clamp; reduces position/risk cap and biases veto upward under drawdown/novelty.
- **5-HT1A**: tonic damping; widens hysteresis and boosts tonic weight for stability.
- **5-HT7**: scheduler; small temperature/hysteresis adjustments when a circadian phase is supplied.
- **5-HT2A**: guarded exploration; slight temperature lift when conditions are stable, without increasing cap.

## Guarantees (Tested)

- **OFF mode:** behaviour matches the baseline controller (snapshot test).
- **ON mode:** activations bounded; risk cap never increases; fast alarm can force veto; hysteresis widening reduces chatter.
- **Deterministic:** identical inputs produce identical outputs (seedless) when receptors are enabled.
