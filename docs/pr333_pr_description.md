# PR #333 — RebusGate Finalization

## Short description
RebusGate is finalized as a fail-closed Layer 2–3 exploration primitive with deterministic activation/terminal contracts, reduced canonical invariants, mandatory indicator integration witnesses, and reproducible validation artifacts.

## Detailed description

### Scope
- Runtime primitive: `runtime/rebus_gate.py`
- Protocol wrapper/export surface: `tacl/rebus_protocol.py`, `tacl/__init__.py`
- Canonical invariants: `.claude/physics/INVARIANTS.yaml`, `runtime/INVARIANTS.yaml`
- Tests and validation: `tests/unit/runtime/test_rebus_gate.py`, `bench/rebus_perf.py`, `docs/rebus_ci_validation.md`
- Architecture/docs: `README.md`, `CLAUDE.md`, `docs/NEURO-TO-DIGITAL-ONTOLOGY.md`

### What was completed
1. REBUS naming and runtime/protocol surface alignment completed.
2. Canonical invariant set reduced to six enforceable invariants:
   - `INV-REBUS-1`, `INV-REBUS-3`, `INV-REBUS-4`, `INV-REBUS-5`, `INV-REBUS-6`, `INV-REBUS-7`.
3. Supporting proof surface (non-canonical invariants) is explicitly separated:
   - contract-safety tests (non-canonical)
   - integration witnesses (Kuramoto/entropy)
   - benchmark/validation artifacts
4. Integration witnesses are mandatory in CI-capable environments and remain supporting evidence, not canonical laws:
   - Kuramoto order parameter integration witness.
   - Entropy integration witness as free-energy descent proxy behavior.
5. Physics kernel gate execution is recorded with a real run:
   - `python .claude/physics/validate_tests.py --self-check`.
6. Performance artifact provided:
   - 10k-cycle benchmark script with avg step latency, memory peak, deepcopy count.

### Contract assurances
- Activation is fail-closed and coherence/priors are strictly validated.
- Reintegration and emergency paths remain restore-confirmed before reset.
- Safety preemption remains deterministic (`kill_switch_active`, `stressed_state`).
- Required six canonical invariants each map to direct canonical witness tests.
- Additional tests/artifacts are labeled and treated as supporting evidence.
