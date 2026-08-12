# RIEE v1.0 Operational Readiness (2026-05-26)

## Product structure
RIEE is delivered in three operational modes:

1. **Cloud Native**: CI/guard orchestration and sidecar-style control contracts.
2. **Local Edge**: local fail-closed command path for runtime interception.
3. **Application SDK**: in-process decorator gate enabled by environment variable.

## SDK contract
- Module: `runtime/riee/sdk.py`
- Entry: `riee_guard(claims_path='CLAIMS.md', threshold=1e-6)`
- Switch: `RIEE_ENABLE=1`
- Behavior: fail-closed by raising `KernelPanic` when runtime invariant check fails.

## Runtime acceptance criteria
- `Δ = |gamma_fact - gamma_claim|`
- Panic threshold: `Δ > 1e-6`
- Panic path must create quarantine snapshot under `artifacts/quarantine/`.

## Operational commands
```bash
python scripts/check_epistemic_drift.py
python scripts/guards/zero_latency_interrupter.py
python scripts/riee/chaos_engine.py
```
