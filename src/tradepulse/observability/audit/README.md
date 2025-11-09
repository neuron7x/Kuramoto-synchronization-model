# Execution Audit Trail

Runtime compliance and risk decisions are appended to `execution.jsonl` in
this directory. The file is intentionally excluded from version control via
`.gitignore` because it is generated at runtime.

## Additional audit trails

| File                     | Purpose                                                                 |
|--------------------------|-------------------------------------------------------------------------|
| `access.jsonl`           | Structured HTTP access logs capturing actor, path, status, and latency. |
| `execution.jsonl`        | Decision log for the execution layer and risk engine.                   |
| `system.jsonl`           | Administrative and orchestration events emitted by `SystemAccess`.      |

Each file stores one JSON document per line with timestamps normalised to UTC
for ingestion into SIEM tooling and long-term MiFID II retention.
