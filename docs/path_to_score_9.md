# Path to score 9.0 (from current ~7.0)

## Target
Raise project from strong pre-production R&D to near-production excellence by closing evidence, governance, and live-ops gaps.

## 10 concrete actions

1. **Live canary pipeline (mandatory)**
   Run continuous replay/live shadow with strict SLOs (latency, lock-rate, divergence-rate).

2. **Independent replication harness**
   Second implementation (reference solver) must match outputs within tolerance on fixed datasets.

3. **External benchmark pack**
   Evaluate on out-of-sample market/IoT regimes with public metrics and fixed seeds.

4. **Formal incident drill**
   Simulate outage/jitter/fork conditions weekly; record MTTR and rollback time.

5. **Governance gate in CI**
   Block merge if invariant regression > threshold (potential monotonicity, lock correctness, determinism).

6. **Contract versioning + migration tests**
   Version every API/report schema; add backward-compat tests.

7. **Prediction-layer calibration**
   Add calibration curves (Brier/ECE), not only label accuracy.

8. **Operator runbook + on-call playbooks**
   Explicit actions for lock storms, divergence spikes, stale-feed cases.

9. **Data provenance + audit trail**
   Immutable event log with UTC timestamps, config hash, code commit hash.

10. **Quarterly red-team falsification**
    Independent team tries to break assumptions; publish negative results.

## Numeric promotion rule
Move to **9.0** only if all are true for >= 90 days:
- SLO pass-rate >= 99.5%
- No unresolved critical incident
- External benchmark parity within agreed tolerance
- All governance gates green in CI/CD

## Current priority order (next 30 days)
1) Live canary + SLO dashboard
2) CI governance gates
3) Independent replication harness
4) Incident drills + rollback proof
