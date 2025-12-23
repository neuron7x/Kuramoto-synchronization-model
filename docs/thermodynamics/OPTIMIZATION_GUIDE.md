# Thermodynamics Optimization Guide (Research)

This guide provides practical tuning tips for the thermodynamic heuristic in research and staging environments. All recommendations are advisory; results depend on workload, hardware, and metric quality.

## Goals

- Keep the `F` score stable for known-good workloads.
- Detect meaningful degradations without excessive noise.
- Maintain lightweight overhead in sandbox deployments.

## Tuning levers

- **Weights and temperature**: Adjust `runtime/thermo_config.py` or `config/thermo_config.yaml` to emphasize the metrics that best reflect your environment.
- **Metric normalization**: Ensure inputs are scaled similarly; large magnitude differences can dominate the score.
- **Sampling cadence**: Reduce noise by smoothing inputs or using rolling windows before feeding them to `EnergyValidator`.
- **Caching**: If you repeatedly score similar topologies, use the caching utilities in `runtime/thermo_cache.py` to avoid recomputation overhead.

## Validation approach

- Start with recorded traces from a stable period and confirm the score stays within your expected envelope.
- Introduce controlled perturbations (latency spikes, coherency drift) to ensure the heuristic reacts as intended.
- Document thresholds and decisions alongside the commit or deployment that introduced them.

## Limitations

- Performance claims are environment-dependent; measure locally if you need concrete numbers.
- The heuristic is advisory and metaphorical; keep actuations behind feature flags and human review.
