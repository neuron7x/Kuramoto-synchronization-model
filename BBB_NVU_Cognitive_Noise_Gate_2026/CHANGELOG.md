# Changelog

## 1.0.0 — 2026-06-03

- Seeded research-grade BBB–NVU Cognitive Noise Gate artifact.
- Added deterministic demo engine, pinned risk rules, evidence grades, schemas, examples, protocols, documentation, and test vectors.
- Added unit tests for golden states, fail-closed invalid input, explicit missing-domain degradation, human review flags, and stable run hashes.

## 1.0.1 — 2026-06-03

- Replaced polymorphic observation values with a strict numeric metric contract and added a strict inference input schema.
- Added fail-closed math gates for `NaN`, `Inf`, non-numeric, out-of-range domain values, and out-of-range confidence.
- Added executable invariant bindings, dynamic traceability generation from `@requirement` decorators, property-based invariant tests, and a deterministic local adversarial sandbox with golden vectors.

## 1.0.2 — 2026-06-03

- Added an integration-readiness roadmap with seven fundamental engineering tasks required before product-grade integration.
- Aligned the data dictionary with the strict numeric observation schema.

## 1.0.3 — 2026-06-03

- Added a dated integration-status snapshot that records the roadmap state, data-contract stabilization, verification contour, and remaining integration blockers.

## 1.0.4 — 2026-06-03

- Added a relative maturity assessment against OpenAI/DeepMind-grade engineering expectations with metric scores, inference-specific confidence, extrapolated maturity, and final conclusions.

## 1.0.5 — 2026-06-03

- Added a strict Pydantic v2 L1 Data Quality Gate for provenance, numeric observations, and normalized inference inputs.
- Integrated L1 validation into the deterministic engine so schema/coercion failures return `BLACK_INVALID` with zero confidence instead of entering inference.
- Added L1 gate tests for ISO datetimes, numeric metric rejection, extra fields, string coercion, unknown domains, and fail-closed engine behavior.

## 1.0.6 — 2026-06-03

- Added an integration-facing runtime boundary with explicit timestamps, output profiles, batch evaluation, and request validation.
- Added `DeterministicInferenceEngine.from_rules(...)` so loaded rules can be injected without rule-file I/O in the core engine path.
- Added runtime boundary tests and documentation.

## 1.0.7 — 2026-06-03

- Added structured audit JSONL events and deterministic replay bundles with `input_hash`, `rules_hash`, `engine_hash`, and `run_hash` verification.
- Added audit/replay tests for event serialization, replay reconstruction, and tamper detection.
- Added `rules_hash` and `engine_hash` to inference outputs and the inference-run schema.

## 1.0.8 — 2026-06-03

- Added deterministic metrics snapshots for risk-state distribution, degradations, action classes, human-review load, autonomous-execution blocks, low-confidence runs, and incident candidates.
- Added incident records, severity mapping, response steps, JSONL incident writing, schemas, and observability tests for green/no-incident, warning, critical, and invalid states.
- Documented the metrics and incident workflow and removed metrics/incident workflow from the remaining blocker list.

## 1.0.9 — 2026-06-03

- Added an operational kernel that composes runtime inference, audit events, replay bundles, metrics snapshots, incidents, and a manifest into one deterministic envelope.
- Added an operational envelope schema and tests for envelope determinism, replay verification, fail-closed invalid handling, and request-boundary rejection.
- Documented the operational kernel and narrowed the remaining release blocker to checklist/distribution packaging after adding artifact hash manifest behavior.

## 1.0.10 — 2026-06-03

- Added operational envelope verification that recomputes envelope hashes, manifest hashes, replay-bundle hashes, replay verification, metrics snapshot IDs, incident IDs, and request cardinalities.
- Added tamper-detection tests for output mutation and manifest replay-verification mutation while preserving deterministic acceptance for fresh envelopes.

## 1.0.11 — 2026-06-03

- Added a one-command verification harness that regenerates traceability, runs the focused pytest suite, compiles critical Python modules, parses JSON artifacts, executes an operational-kernel smoke check, and runs `git diff --check` for the artifact.
- Documented the canonical verification command in the README.
