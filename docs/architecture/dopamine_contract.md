# Dopamine Component Contract v1

GeoSync dopamine is a structural reward-error control component.

Bound semantics:

1. `RAW_TD_RPE` — canonical temporal-difference reward prediction error.
2. `BOUNDED_EXECUTION_RPE` — bounded execution feedback normalization.
3. `DISTRIBUTIONAL_RPE_SURFACE` — P2 research-only extension.
4. `BACKTEST_DOPAMINE_SIGNAL` — offline evaluation harness.

No claim may be promoted without replayable artifacts, SHA-256 manifests, and a release verdict.

Required chain:

```text
CLAIM -> CONTRACT -> INVARIANT -> IMPLEMENTATION -> TEST -> ARTIFACT -> SHA256 -> VERDICT
```

Machine contract: `contracts/dopamine_contract.v1.json`.
Checker: `scripts/check_dopamine_contract.py`.
