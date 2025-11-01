# Thermodynamic Autonomic Control Layer (TACL)

The Thermodynamic Autonomic Control Layer is responsible for validating that the
TradePulse execution graph operates inside the safe energy envelope before a
rollout progresses beyond the laboratory environment.  The validator ingests a
compact set of telemetry collected from the link activator and control plane and
computes the Helmholtz free energy

\[
F = U - T S
\]

where:

- **U** is the internal energy composed of weighted penalties derived from the
  latency, coherency, and resource metrics.
- **T** is the control temperature (fixed to 0.60 for TradePulse) representing
  how aggressively we discount available slack.
- **S** is the stability term, proportional to the headroom each metric keeps
  relative to its threshold.  Higher stability increases entropy and therefore
  reduces the free energy.

## Metrics and Thresholds

| Metric            | Description                              | Threshold | Weight |
| ----------------- | ---------------------------------------- | --------- | ------ |
| `latency_p95`     | 95th percentile end-to-end latency (ms)  | 85.0      | 1.6    |
| `latency_p99`     | 99th percentile end-to-end latency (ms)  | 120.0     | 1.9    |
| `coherency_drift` | Fractional drift of shared state         | 0.08      | 1.2    |
| `cpu_burn`        | CPU utilisation ratio (0–1)              | 0.75      | 0.9    |
| `mem_cost`        | Memory footprint per node (GiB)          | 6.5       | 0.8    |
| `queue_depth`     | Queue length at the activator ingress    | 32.0      | 0.7    |
| `packet_loss`     | Control-plane packet loss ratio (0–1)    | 0.005     | 1.4    |

The validator normalises penalties by the sum of weights before combining them
with the base internal energy.  This behaviour fixes the regression that caused
`validate-energy` to fail after merge: previously the penalties were summed
without normalisation which doubled the influence of latency and packet loss
metrics.

## Acceptable Energy Range

The CI pipeline declares success when the computed free energy does not exceed
**1.35**.  This boundary was derived from the post-incident review and gives a
12% safety margin relative to the highest energy observed during the hot path
load tests.

- Free energy ≤ 1.35: rollout proceeds to release gates.
- Free energy > 1.35: automated rollback is triggered.

## Authorisations for Energy Exceptions

Temporary exceptions to the energy budget require dual approval:

1. **Thermodynamic Duty Officer** (rotating weekly).
2. **Platform Staff Engineer** responsible for the affected cluster.

Both approvals must be recorded in the release ticket together with the
telemetry snapshots exported by `.ci_artifacts/energy_validation.json`.
