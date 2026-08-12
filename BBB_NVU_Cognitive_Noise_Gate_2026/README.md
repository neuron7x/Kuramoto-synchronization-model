# BBB–NVU Cognitive Noise Gate 2026

```yaml
artifact_id: BBB-NVU-CNG-2026
version: 1.0.0
status: repo-seed / research-grade operational artifact
language: uk-UA
domain: CNS risk monitoring / BBB-NVU proxy inference / cognitive noise control
date: 2026-06-03
mode: deterministic / fail-closed / provenance-first / degradation-aware
clinical_status: not_a_medical_device_without_validation
```

## Contract

**BBB–NVU Cognitive Noise Gate 2026** is a deterministic vertical inference artifact for research-grade CNS risk signal monitoring using BBB/NVU, neuroinflammation, vascular-metabolic, glymphatic-sleep, and cognitive-noise proxies.

It is **not a medical device**, does not diagnose disease, does not prescribe treatment, and does not permit autonomous clinical action without independent validation, governance, and human review.

## One-command example

```bash
python BBB_NVU_Cognitive_Noise_Gate_2026/src/deterministic_engine.py \
  BBB_NVU_Cognitive_Noise_Gate_2026/examples/sample_run_input.json \
  BBB_NVU_Cognitive_Noise_Gate_2026/config/risk_rules.yaml
```

Expected class for the bundled sample is `YELLOW_WATCH` because VML is in risk range, BSI/GRS/CNI are warning-range signals, and the sample carries an explicit sleep-proxy degradation.

## Invariant

The production inference path is deterministic and fail-closed:

```text
same canonical input + same pinned rules + same engine source = same run_hash
critical_data_invalid=true => BLACK_INVALID + human review + no autonomous execution
missing/noisy/conflicting data => explicit degradation, never hidden optimism
```

## Vertical loop

```text
Threat / Noise → Detect → Gate → Export → Immune Modulate → Clear → Restore
```

Technical layers:

```text
L0 Raw Events → L1 Data Quality Gate → L2 Feature / Proxy Builder
→ L3 Deterministic Risk Inference → L4 Control Policy Engine
→ L5 Provenance / Audit Ledger → L6 Validation / Governance
```

## Risk indices

| Index | Meaning | Direction |
| --- | --- | --- |
| `BSI` | Barrier Stress Index | higher is worse |
| `NRI` | Neuroinflammation Risk Index | higher is worse |
| `VML` | Vascular-Metabolic Load | higher is worse |
| `GRS` | Glymphatic Recovery Score | lower is worse |
| `CNI` | Cognitive Noise Index | higher is worse |

## Risk states

| State | Meaning | Control posture |
| --- | --- | --- |
| `GREEN_STABLE` | signals within baseline | continue monitoring |
| `YELLOW_WATCH` | uncertainty or weak risk | collect/repeat data |
| `ORANGE_RISK` | convergent risk in at least two domains | human review + mitigation |
| `RED_CRITICAL` | critical or multi-domain risk pattern | urgent human review; autonomous action prohibited |
| `BLACK_INVALID` | data are not fit for inference | no inference; quarantine/fix input |

## Allowed and restricted use

Allowed use: research mode, operational wellness mode, data-quality control, risk-signal monitoring, reproducible inference, and evidence audit.

Restricted use: autonomous clinical diagnosis, autonomous treatment decisions, emergency medical triage without human review, hidden model/rule updates, and silent imputation of critical data.

## Repository map

```text
BBB_NVU_Cognitive_Noise_Gate_2026/
  README.md
  docs/
  protocols/
  schemas/
  config/
  src/deterministic_engine.py
  examples/
  tests/
```

## Validation status

Current maturity: **Level 1 — Repo Seed**. Target next level: **Level 2 — Verified Prototype** with schema validation, unit tests, frozen test vectors, CI, changelog, and data license model.

## L1 Data Quality Gate

Runtime input compilation is implemented with strict Pydantic v2 contracts in `src/deterministic_engine.py`. The gate validates `StrictObservation`, `StrictProvenance`, and `StrictInferenceInput` before inference; invalid payloads fail closed as `BLACK_INVALID` with `confidence=0.0`. Details are documented in `docs/l1_data_quality_gate.md`.

## Runtime Boundary

Integration callers should use `RuntimeBoundary` from `src/runtime_boundary.py` or `DeterministicInferenceEngine.from_rules(...)` instead of coupling to the CLI. The boundary requires an explicit `created_at` timestamp, supports `full` / `risk` / `actions` output profiles, and keeps rule-file I/O outside the core engine path. Details are documented in `docs/runtime_boundary.md`.

## Audit and Replay

Operational audit export is available through `src/audit.py`. `AuditEvent.from_output(...)` emits deterministic JSONL-safe events with `run_hash`, `input_hash`, `rules_hash`, `engine_hash`, risk state, confidence, degradations, and action IDs. `build_replay_bundle(...)` and `verify_replay_bundle(...)` verify that a saved input/rules/timestamp/source bundle reconstructs the same run hash. Details are documented in `docs/audit_replay.md`.

## Metrics and Incident Workflow

Operational observability is implemented in `src/observability.py`. `build_metrics_snapshot(...)` produces deterministic counters for state distribution, degradations, action classes, human-review load, autonomous-execution blocks, low-confidence runs, and incident candidates. `incident_from_output(...)` and `build_incident_register(...)` convert non-green outputs into deterministic `OPEN` incidents with severity and response steps. Details are documented in `docs/observability_incidents.md`.

## Operational Kernel

Integration-grade execution is available through `src/operational_kernel.py`. `OperationalKernel.execute(...)` composes runtime evaluation, audit events, replay bundles, metrics, incidents, and an artifact manifest into one deterministic envelope with `envelope_hash`; `verify_operational_envelope(...)` recomputes internal hashes and replay checks for tamper detection. Details are documented in `docs/operational_kernel.md`.

## Tier-1 calibration harness

The artifact now uses a local sandbox-first validation sequence before any service-level adversarial auditor is introduced. The canonical one-command verifier is:

```bash
python BBB_NVU_Cognitive_Noise_Gate_2026/tools/verify_artifact.py
```

The underlying focused pytest suite is:

```bash
pytest -q -W ignore::DeprecationWarning \
  BBB_NVU_Cognitive_Noise_Gate_2026/tests/test_deterministic_engine.py \
  BBB_NVU_Cognitive_Noise_Gate_2026/tests/test_invariants.py \
  BBB_NVU_Cognitive_Noise_Gate_2026/tests/test_adversarial_auditor.py \
  BBB_NVU_Cognitive_Noise_Gate_2026/tests/test_traceability.py \
  BBB_NVU_Cognitive_Noise_Gate_2026/tests/test_l1_data_quality_gate.py \
  BBB_NVU_Cognitive_Noise_Gate_2026/tests/test_runtime_boundary.py \
  BBB_NVU_Cognitive_Noise_Gate_2026/tests/test_audit_replay.py \
  BBB_NVU_Cognitive_Noise_Gate_2026/tests/test_observability_incidents.py \
  BBB_NVU_Cognitive_Noise_Gate_2026/tests/test_operational_kernel.py
```

Traceability is generated from `@requirement("Rxxx")` decorators, and invariants carry requirement/test bindings plus semantic statement hashes so they are executable test targets rather than orphaned prose.

## Integration readiness roadmap

The seven fundamental tasks required to raise this PR from repo seed to integration-ready engineering quality are documented in `docs/integration_readiness_tasks.md`. The roadmap prioritizes contract hardening, runtime API boundaries, executable invariants, calibrated adversarial/property/mutation tests, observability, governance, and release packaging.

A dated verification/status snapshot is available in `docs/integration_status_2026-06-03.md`; it records the current roadmap state, strict-schema alignment, changelog status, verification contour, and remaining integration blockers.

A relative maturity assessment against OpenAI/DeepMind-grade engineering expectations is documented in `docs/relative_maturity_assessment.md`; it provides metric scores, inference-specific confidence, extrapolated maturity, and final conclusions.
