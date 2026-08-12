# SIMULATION_PROTOCOL.md

## Loop

1. Define environment case.
2. Generate deterministic target trajectory.
3. Predict next state from internal state.
4. Compute prediction error.
5. Compute excitation and inhibition proxies.
6. Update internal state through gated error correction.
7. Measure convergence, divergence, E/I balance, realism gap, and energy.
8. Detect failure holes H1 through H10.
9. Emit weight patches.
10. Calibrate confidence by evidence level.

## Environment cases

- baseline
- high_noise
- delayed_feedback
- scarce_data
- rapid_regime_shift
- adversarial_perturbation
- resource_constrained

## Pass criteria

- mean E/I balance must stay within the configured target range
- outside-balance fraction must not exceed 0.25
- realism_gap must not exceed 0.45
- mae must not exceed 0.35
- energy_efficiency must be positive
- divergence must remain bounded
- confidence must not exceed evidence level

## Replay command

```bash
python scripts/cognitive_dynamics_lab/simulation_runner.py --out artifacts/cognitive_dynamics_lab
```
