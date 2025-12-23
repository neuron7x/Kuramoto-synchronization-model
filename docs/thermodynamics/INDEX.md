# Thermodynamics (TACL) Index

## Purpose

TACL materials describe the experimental free-energy heuristic used to score system stability in sandboxes. All terminology is metaphorical thermodynamics; no formal guarantees or biological/physical claims are made.

## Documents

- [README.md](./README.md) — overview of the heuristic and its scope.
- [METRICS_FORMALIZATION.md](./METRICS_FORMALIZATION.md) — inputs, weights, and outputs for the `F = U - T·S` score.
- [OPERATIONAL_RUNBOOK.md](./OPERATIONAL_RUNBOOK.md) — sandbox operations and monitoring steps.
- [OPTIMIZATION_GUIDE.md](./OPTIMIZATION_GUIDE.md) — tuning considerations for experiments.

## Code Modules

- `runtime/energy_validator.py` — metric ingestion and scoring.
- `runtime/thermo_controller.py` — control loop using the score to gate actions.
- `runtime/thermo_api.py` — telemetry surface for status/history.
- `runtime/thermo_config.py` — default weights and thresholds.
- `runtime/link_activator.py`, `runtime/recovery_agent.py`, `evolution/crisis_ga.py` — experimental actuators that should be supervised.

## Notes

- Defaults in `config/thermo_config.yaml` are illustrative and should be tuned per environment.
- Metrics quality directly affects usefulness; missing or noisy inputs will degrade the signal.
- Keep automated changes behind feature flags; this layer is intended for research and stress-testing, not unattended production rollout.
