# Thermodynamics Metrics Formalization (Metaphorical)

This document summarizes how the thermodynamic heuristic is computed in code. The formulation is an engineering shortcut for combining stability and resource metrics; it is **not** a physical thermodynamics model and carries no formal guarantees.

## Heuristic

```
F = U - T · S
```

- **U (Internal Energy)**: Weighted penalty of resource/latency metrics.
- **T (Control Temperature)**: Scalar to modulate sensitivity to slack.
- **S (Entropy / Stability)**: Headroom-based stability term.

The concrete weights and temperature live in `config/thermo_config.yaml` and are surfaced through `runtime/thermo_config.py`.

## Inputs

The validator expects normalized metrics. Common inputs include:

- `latency_p95`, `latency_p99`
- `coherency_drift`
- `cpu_burn`, `mem_cost`
- `queue_depth`
- `packet_loss`

Missing or noisy metrics reduce the usefulness of the score; callers are responsible for supplying reliable values.

## Outputs

- **`free_energy`**: Scalar score returned by `EnergyValidator`.
- **`passed` / `status`**: Boolean flag indicating whether the score is within configured bounds.
- **Telemetry**: Controller surfaces history and current `F` via `runtime/thermo_api.py`.

## Interpretation

- Lower `F` indicates more headroom; higher `F` indicates pressure on the system.
- Thresholds are configuration-driven and should be tuned to the environment being tested.
- Use the score as guidance for human review or guarded automation, not as an absolute safety guarantee.

## Limitations

- No formal proofs or external audits exist for this heuristic.
- Thresholds and weights are environment-specific; defaults are illustrative only.
- The formulation assumes reasonably scaled metrics; extreme or unscaled values can distort results.
