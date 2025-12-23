# Thermodynamics (TACL) Documentation

This directory captures the current state of the Thermodynamic Autonomic Control Layer (TACL) as implemented in code. TACL is an experimental control-systems layer that scores system health using a free-energy-style heuristic. The thermodynamics framing is metaphorical and intended for research sandboxes, not as a physics-derived guarantee.

## Scope

- Monitor latency, coherency, and resource metrics and score them with a Helmholtz-inspired heuristic.
- Gate topology/runtime changes in sandboxes before they are allowed to proceed.
- Expose telemetry for manual review rather than autonomous production decision-making.

## Implemented Components

- `runtime/energy_validator.py` — computes the `F = U - T · S` score from provided metrics.
- `runtime/thermo_controller.py` — consumes the score to gate actions and emit telemetry.
- `runtime/thermo_config.py` — houses tunable weights and thresholds.
- `runtime/thermo_api.py` — FastAPI endpoints for status and history.
- `runtime/link_activator.py`, `runtime/recovery_agent.py`, `evolution/crisis_ga.py` — experimental actuators intended for supervised use.

## How the heuristic works (metaphorical thermodynamics)

- Free energy is treated as a weighted penalty across metrics defined in [`config/thermo_config.yaml`](../../config/thermo_config.yaml) (latency, coherency, and resource ratios).
- Default weights and temperature values live in `config/thermo_config.yaml` and can be overridden per environment.
- The output `F` value is used as guidance; it does not carry formal guarantees of safety or stability.

## Usage guidance

- Start with sandbox or test telemetry and run it through `EnergyValidator`.
- Adjust weights to match the environment you are observing; defaults are illustrative.
- Keep automatic actuations behind feature flags and pair changes with human review.

## Known limitations

- No external audits or formal proofs; behavior depends entirely on the quality of supplied metrics.
- Thresholds and crisis modes are heuristics and may not generalize across deployments.
- Not internally tested for unattended production usage; intended for research and stress-testing.

## Related documents

- [METRICS_FORMALIZATION.md](./METRICS_FORMALIZATION.md) — details of the heuristic inputs and outputs.
- [OPERATIONAL_RUNBOOK.md](./OPERATIONAL_RUNBOOK.md) — sandbox operations guidance.
- [OPTIMIZATION_GUIDE.md](./OPTIMIZATION_GUIDE.md) — tuning notes for experiments.
