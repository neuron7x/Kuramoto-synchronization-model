# Extrapolation Act & Target Meta-Tasks (2026-05-26)

## Mandate
Immediate deployment of CI guardians, numeric drift erasure, and hard fail-closed protocols.

## Activated controls
1. `check_epistemic_drift.py` as numerical truth guard (`Δ=0` required).
2. `fail_closed_guardians.yml` CI sentry (PR + push main).
3. `zero_latency_interrupter.py` hard gate for local/runtime preflight.
4. Adversarial invariant fail-closed battery for all 97 ids.
5. Runtime-cost telemetry (`variance_pct`, `peak_memory_kib`, overhead).

## Target meta-tasks (execution plan)
- Dynamic metastability verifier (`γ≈1.0`) to be integrated as nightly gate.
- Distributed claim-to-code DAG runtime auditor with orphan-node detection.
- Generative mutation anomaly injector for continuous stress verification.
- Hardware fail-closed interrupt path bound to `Δ > 0` signal.
- CPU overhead stabilization objective: <3% at peak sessions.


## RIEE v1.0 Integration
- Runtime invariant enforcement kernel added at `runtime/riee/engine.py`.
- Chaos engine added at `scripts/riee/chaos_engine.py` (10000-iteration mode supported).
- ED25519 sign/verify path added for claims/config trust chain.
- Kernel panic now quarantines to `artifacts/quarantine/`.
