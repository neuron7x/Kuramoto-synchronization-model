# P04 — Control Action Protocol

Action classes: `DATA_CONTROL`, `OPERATIONAL_CONTROL`, `RESEARCH_CONTROL`, and `CLINICAL_ESCALATION`.

Safety constraints:

- The system does not prescribe treatment.
- `RED_CRITICAL` requires human review.
- Every action includes reason, rule ID, risk state, and provenance context.
