# P05 — Degradation Management Protocol

Degradation types: `DATA_MISSING`, `DATA_NOISY`, `UNIT_MISMATCH`, `SOURCE_CONFLICT`, `CLOCK_SKEW`, `RULE_VERSION_MISMATCH`, `MODEL_DRIFT`, `UNKNOWN_PROVENANCE`, and `OUT_OF_DISTRIBUTION`.

Response ladder: flag, penalize confidence, quarantine feature, block inference, escalate human review, freeze deployment, and perform post-incident review.

Principle: degradation is a control signal, not a hidden error.
