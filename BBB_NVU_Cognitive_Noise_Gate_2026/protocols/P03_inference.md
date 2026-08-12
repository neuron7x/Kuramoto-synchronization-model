# P03 — Deterministic Inference Protocol

Steps: load canonical input, validate schema, load pinned rules, normalize features, compute domain indices, apply safety overrides, compute confidence, generate explanation, and write provenance plus `run_hash`.

Prohibited: automatic imputation of critical missing fields, unversioned weight updates, hidden LLM calls in the production path, and clinical diagnosis without validated clinical mode.
