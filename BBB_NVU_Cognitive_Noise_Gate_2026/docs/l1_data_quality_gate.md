# L1 Data Quality Gate

The L1 gate is the runtime compiler for incoming data. It replaces prose-only data dictionary validation with strict Pydantic v2 contracts inside `src/deterministic_engine.py`.

## Runtime contracts

- `StrictProvenance`: provenance fields required before data can be trusted.
- `StrictObservation`: atomic numeric observation contract; `value` is finite numeric only.
- `StrictInferenceInput`: normalized inference input contract; confidence must be finite 0-1 and domain indices must be finite 0-100 values for known domains only.

## Fail-closed behavior

If L1 validation fails in the inference path, the engine emits:

```yaml
risk_state: BLACK_INVALID
confidence: 0.0
degradations:
  - SCHEMA_INVALID
actions:
  - prohibited_autonomous_execution: true
```

The production inference path does not coerce string numbers, extra fields, unknown domains, `NaN`, `Inf`, or out-of-range values into usable signals.

## Verified tests

- `tests/test_l1_data_quality_gate.py`
- `tests/test_invariants.py`
- `tests/test_adversarial_auditor.py`
- `tests/test_traceability.py`
