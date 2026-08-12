# GeoSync Physics Validation Verdict

Status: GENERATED_BY_tools/physics_score.py
Score type: `evidence_oracle_with_partial_ci_not_release_proof`
S_total: `81.5`
Target interval: `88.0-92.0`
Verdict: `FAIL_BELOW_TARGET_BLOCKED_FOR_VALIDATION`

## Evidence added in this iteration

```text
CI evidence validator: tools/physics_ci_evidence.py
CI evidence artifact: artifacts/physics_validation/ci_evidence_summary.json
CI evidence tests: tests/test_physics_ci_evidence.py
Physics-specific workflow evidence: Physics Invariants, Physics Kernel Gate, Physics Reliability Gate, Commit Acceptor Gate, Repo Integrity Gate
Score delta: 77.82 -> 81.5
```

## Remaining gates

- Repository-level PR Gate is not fully green for the recorded physics lane.
- Full Ricci graph provenance audit is still required before Ricci can leave experimental status.
- Immutable BN-Syn and MFN+ source references are still required before those systems can be scored here.

## Metric table

| metric | weight | score | weighted | status |
|---|---:|---:|---:|---|
| `S_math_object` | 0.12 | 75.0 | 9.0 | PARTIAL_PASS_TRACEABLE |
| `S_dimensional_consistency` | 0.1 | 70.0 | 7.0 | PARTIAL_PASS_NO_TYPED_UNITS |
| `S_numerical_stability` | 0.12 | 86.0 | 10.32 | RUNTIME_PARTIAL_PASS_PR_GATE_REQUIRED |
| `S_invariant_preservation` | 0.12 | 88.0 | 10.56 | RUNTIME_PARTIAL_PASS_PR_GATE_REQUIRED |
| `S_falsifiability` | 0.14 | 86.0 | 12.04 | RUNTIME_PARTIAL_PASS_PR_GATE_REQUIRED |
| `S_baseline_models` | 0.1 | 85.0 | 8.5 | RUNTIME_PARTIAL_PASS_PR_GATE_REQUIRED |
| `S_UQ` | 0.08 | 74.0 | 5.92 | RUNTIME_PARTIAL_PASS_PR_GATE_REQUIRED |
| `S_reproducibility` | 0.08 | 83.0 | 6.64 | RUNTIME_PARTIAL_PASS_PR_GATE_REQUIRED |
| `S_interface_contracts` | 0.08 | 78.0 | 6.24 | RUNTIME_PARTIAL_PASS_PR_GATE_REQUIRED |
| `S_traceability` | 0.06 | 88.0 | 5.28 | PARTIAL_PASS_WITH_CI_EVIDENCE |

## Final decision

```text
CONTROL_PLANE: BUILT
UQ_SMOKE: ADDED
INDEPENDENT_REPLICATION: ADDED
RICCI_BRIDGE_SMOKE: ADDED
CI_EVIDENCE_LEDGER: ADDED
S_TOTAL: 81.5/100
TARGET: 88-92
FINAL_PHYSICS_VALIDATION: NO
MERGE_READY: NO
```
