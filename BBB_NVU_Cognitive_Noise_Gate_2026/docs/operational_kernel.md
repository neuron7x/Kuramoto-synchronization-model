# Operational Kernel

The operational kernel is the integration-grade execution boundary that composes the existing deterministic mechanisms into one canonical envelope. It does not change risk inference; it orchestrates the runtime boundary, audit/replay, metrics, incidents, and manifest creation in one deterministic transaction.

## Envelope contents

`OperationalKernel.execute(requests, created_at=...)` returns:

- full inference outputs;
- audit events;
- replay bundles;
- metrics snapshot;
- incident register;
- manifest with output hashes, audit-event hashes, replay-bundle hashes, metrics snapshot ID, incident IDs, and replay verification booleans;
- envelope hash.

## Contract

```text
requests + rules + created_at + engine_hash
  -> outputs + audit_events + replay_bundles + metrics + incidents + manifest + envelope_hash
```

The same inputs, rules, timestamp, and engine hash produce the same envelope hash. Boundary request validation remains strict: extra request fields fail before execution.

## Operational posture

- `GREEN_STABLE` runs contribute metrics and audit events but do not open incidents.
- Non-green runs open deterministic incidents through `src/observability.py`.
- Every replay bundle in the manifest must verify true for the envelope to be operationally acceptable. `verify_operational_envelope(...)` recomputes envelope hash, output hashes, audit-event hashes, replay-bundle hashes, replay verification, metrics snapshot ID, incident IDs, and request cardinalities.
