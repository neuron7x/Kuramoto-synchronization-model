# Remediation-ledger dependency finding — a real cycle (2026-07-21)

While closing the safety cluster we found the ledger's `dependencies` field contains a
**circular dependency**:

```
ARC-016 (OMS idempotency)  --depends-->  TST-015 (fault-injection suite)
TST-015 (fault-injection)  --depends-->  ARC-016 (OMS idempotency)  [+ SEC-010]
OPS-003 (kill-switch)      --depends-->  ARC-016, TST-015
```

ARC-016 ↔ TST-015 are **mutually dependent**. A strict "close all dependencies before an item
may close" ordering is therefore **provably unsatisfiable** for this cluster — no topological
order exists through a cycle.

## Consequence for closure policy
`check_remediation_ledger` does **not** enforce dependency-order (it enforces
closed ⟹ PASS-signoff ∧ evidence-paths-exist). Given the cycle, the honest reading of
`dependencies` is **related-work cross-references, not a strict DAG gate**. Closure policy is
therefore: an item closes when (a) its OWN acceptance is genuinely met, and (b) a SEPARATE
adversarial reviewer signs PASS — not when an unsatisfiable dependency order is achieved.

This is stricter than dependency-order on the thing that matters (real evidence + independent
sign-off) and does not pretend a cycle can be linearised.

## The safety cluster closes together
All three items in the cycle now carry independently-verified evidence:
- **TST-015** — `tests/reliability/test_fault_injection_suite.py` (5 fault-injection tests:
  breaker trips OPEN + denies; half-open probe budget + refund; success closes; multi
  protective-callback aggregation surfaces, fail-closed).
- **ARC-016** — OMS `_in_flight` + `threading.Condition`; two same-cid concurrent submits →
  exactly one queued order; INV-OMS1 E_kinetic≥0 witnessed.
- **OPS-003** — kill-switch `_notify_callbacks` aggregate+raise; `_load_state` HALTED on corrupt
  latch; verified fail-closed.

Follow-up (not blocking, honest residual): the ledger's `dependencies` values should be
re-typed as `related` vs `blocks` so a future gate can distinguish cross-refs from true
ordering. Filed as a ledger-hygiene note, not faked as done.
