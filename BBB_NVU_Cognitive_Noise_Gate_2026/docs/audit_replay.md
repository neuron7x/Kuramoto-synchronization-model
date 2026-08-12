# Audit and Replay Bundle

The audit layer converts inference outputs into structured JSONL events and replay bundles. This addresses the operational blocker where provenance existed in the run output but was not yet exportable as a compact audit stream or replayable bundle.

## Audit event

`AuditEvent.from_output(output)` extracts:

- UTC `created_at`.
- `run_id`, `run_hash`, `input_hash`, `rules_hash`, and `engine_hash`.
- `risk_state`, `confidence`, and explicit degradations.
- action IDs plus human-review/autonomous-execution flags.

`AuditEvent.to_jsonl()` returns one deterministic JSON line for append-only logs.

## Replay bundle

`build_replay_bundle(output, input_doc, rules)` stores the input, pinned rules, source ID, timestamp, expected hashes, and expected state. `verify_replay_bundle(bundle)` replays the bundle with `DeterministicInferenceEngine.from_rules(...)` and returns `true` only when the run hash, input hash, rules hash, engine hash, and risk state match.

## Contract

```text
input_doc + rules + created_at + source_id + engine_hash -> replayed run_hash == expected run_hash
```

Tampering with the input or rules breaks replay verification.
