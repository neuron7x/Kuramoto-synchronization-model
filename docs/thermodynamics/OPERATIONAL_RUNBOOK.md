# TACL Operational Runbook (Sandbox)

This runbook describes how to operate the Thermodynamic Autonomic Control Layer (TACL) in research and staging environments. The control model is metaphorical thermodynamics and should be supervised by humans.

## Scope

- Monitor and record thermodynamic heuristic scores for latency/coherency/cost metrics.
- Gate topology or runtime changes in sandboxes.
- Provide human-in-the-loop decision points rather than unattended production automation.

## Setup

1. Review and tune `config/thermo_config.yaml` to match the environment being observed.
2. Ensure the metrics you supply (`latency_p95`, `latency_p99`, `coherency_drift`, `cpu_burn`, `mem_cost`, `queue_depth`, `packet_loss`) are populated and scaled to the same units as `thermo_config.yaml` (latency in ms, resource ratios between 0 and 1). See [METRICS_FORMALIZATION.md](./METRICS_FORMALIZATION.md) for expected shapes.
3. Start the controller/API if needed:
   ```bash
   uvicorn runtime.thermo_api:app --reload --port 8080
   ```

## Observability

- Current status: `curl http://localhost:8080/thermo/status`
- Recent history: `curl http://localhost:8080/thermo/history?limit=50`
- Crisis summary (if enabled): `curl http://localhost:8080/thermo/crisis`

> These endpoints are intended for local/staging inspection. Secure them appropriately if exposed.

## Responding to elevated scores

1. Confirm metrics are accurate (drop outliers, fix missing values).
2. Re-run `EnergyValidator` with corrected metrics to confirm the signal.
3. If the score remains high, pause automated actuations and review pending topology/runtime changes.
4. Adjust thresholds or weights in `thermo_config.yaml` if the environment has shifted.

## Maintenance

- Periodically trim or rotate telemetry archives if stored on disk.
- Rebaseline thresholds when workload characteristics or hardware change.
- Keep experimental actuators (`runtime/link_activator.py`, `runtime/recovery_agent.py`, `evolution/crisis_ga.py`) behind feature flags until manually reviewed.

## Limitations

- No external audits or guarantees; outputs are advisory.
- Behavior is only as good as the metrics supplied.
- Not intended for unattended production control loops.
