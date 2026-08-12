# Metrics and Incident Workflow

The observability layer converts deterministic inference outputs into canonical counters and incident records. It does not change inference decisions; it only makes operational state measurable and actionable.

## Metrics snapshot

`build_metrics_snapshot(outputs, created_at=...)` returns deterministic counters for:

- total runs;
- risk-state distribution;
- degradation counts;
- action-class counts;
- human-review-required runs;
- autonomous-execution-prohibited runs;
- low-confidence runs;
- incident candidates.

The snapshot ID is derived from the canonical metric body, so the same batch and timestamp produce the same metrics hash. The runtime shape is mirrored by `schemas/metrics_snapshot.schema.json`.

## Incident register

`incident_from_output(output)` opens incidents for non-green states only:

| Risk state | Severity | Response posture |
| --- | --- | --- |
| `YELLOW_WATCH` | `WARN` | collect/repeat data |
| `ORANGE_RISK` | `ERROR` | open human review and mitigation tracking |
| `RED_CRITICAL` | `CRITICAL` | block autonomous execution and urgent human review |
| `BLACK_INVALID` | `CRITICAL` | block autonomous execution and quarantine/repair path |

`build_incident_register(outputs)` returns a deterministic list sorted by incident ID. `write_incidents(path, incidents)` writes JSONL incident records for append-only operational logs. The runtime shape is mirrored by `schemas/incident_record.schema.json`.

## Contract

```text
inference outputs -> metrics snapshot + incident register
GREEN_STABLE -> no incident
YELLOW/ORANGE/RED/BLACK -> OPEN incident with deterministic severity and response steps
```
