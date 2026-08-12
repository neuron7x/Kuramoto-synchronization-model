# NEXT_ITERATION_PLAN.md

## Single best next patch

Implement event-triggered sparse update scheduling controlled by prediction error, E/I balance, and reality-weighted variable impact.

## Why

The largest failure surface is not raw accuracy. It is uncontrolled update cost plus unstable adaptation under noise, delay, and regime shift. Dense updates spend compute on low-value variables and can amplify instability.

## Verification

Run:

```bash
python scripts/cognitive_dynamics_lab/simulation_runner.py --out artifacts/cognitive_dynamics_lab
```

Acceptance:

- energy_efficiency improves versus dense baseline
- realism_gap does not increase by more than 10 percent
- mean E/I remains in the configured target range
- recovery after regime shift stays bounded
- confidence remains no higher than 0.75 unless repeated perturbation runs pass
