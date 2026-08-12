# P02 — Quality Control Protocol

QC gates: schema, time, unit, range, missingness, duplication, provenance, and biological plausibility.

Severity levels:

- `INFO`: does not affect inference.
- `WARN`: lowers confidence.
- `ERROR`: blocks partial inference.
- `CRITICAL`: fail-closed.

Required outputs: `qc_status`, `qc_findings`, `quality_score`, and `allowed_for_inference`.
