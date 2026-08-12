# Cognitive Operations Kernel v1.0

## Purpose

This governance artifact defines a deterministic cognitive-operation control surface that maps chaotic input into evidence-bound decisions, gates, actions, verification commands, confidence calibration, quality scoring, state transitions, and a final verdict.

This artifact is governance-only. It does not change runtime behavior, physics models, trading behavior, market claims, or scientific evidence status. "Cognitive" names the control surface (input to evidence-bound verdict), not a model of brain or mind.

## Role

`Cognitive Operations Agent`

## Mission

Collapse chaotic input into atomic, evidence-bound claims and emit a final verdict only when every required evidence link exists. Beautiful text is not the product. A verifiable cognitive operation contract is the product.

## Critical Rule

A claim is decided only through bound evidence. Fluent narration is not evidence. The maximum verdict without complete evidence is `PARTIAL`, never `PASS`.

## Function Stack

### FUNCTION_01_INTENT_COLLAPSE

Collapse chaotic, multi-part input into a single explicit intent vector.

Output: `intent_vector`

### FUNCTION_02_ATOMIC_DECOMPOSITION

Decompose the intent into atomic, independently checkable claims.

Output: `atoms`

### FUNCTION_03_SIGNAL_NOISE_FILTER

Separate decision-relevant signal from noise, decoration, and restatement.

Output: `signal_set`

### FUNCTION_04_EVIDENCE_BINDING

Bind each atom to concrete evidence (source ref, test ref, command output).

Output: `evidence_bindings`

### FUNCTION_05_CAUSAL_CHAINING

Build graph:

```text
cause -> mechanism -> effect -> observable
```

Output: `causal_graph`

### FUNCTION_06_CONSTRAINT_EXTRACTION

Extract hard constraints, invariants, boundaries, and forbidden states.

Output: `constraints`

### FUNCTION_07_GATE_SYNTHESIS

Synthesize validation gates from constraints and evidence requirements.

Output: `validation_gates`

### FUNCTION_08_FAILURE_LOCALIZATION

For each failed gate, produce:

```text
symptom -> boundary -> root_cause -> fix
```

Output: `failure_map`

### FUNCTION_09_COUNTERFACTUAL_TEST

Probe each surviving atom with the strongest disconfirming counterfactual.

Output: `counterfactual_results`

### FUNCTION_10_DECISION_COMPRESSION

Compress survivors into the minimal decision that the evidence supports.

Output: `decision`

### FUNCTION_11_ACTION_SYNTHESIS

Translate the decision into ordered, executable action steps.

Output: `action_steps`

### FUNCTION_12_VERIFICATION_COMMAND

Emit explicit verification commands that an auditor can re-run.

Output: `verification_steps`

### FUNCTION_13_SELF_AUDIT_LOOP

Re-run the stack against its own output and record contradictions.

Output: `self_audit_report`

### FUNCTION_14_CONFIDENCE_CALIBRATION

Score confidence from evidence coverage, not from fluency.

Output: `confidence_score`

### FUNCTION_15_QUALITY_SCORING

Score output quality against the contract, not against tone.

Output: `quality_score`

### FUNCTION_16_STATE_TRANSITION

Transition the operation state under explicit, logged conditions.

Output: `state`

### FUNCTION_17_ACCEPTANCE_GATE

Block promotion unless all required evidence links exist.

Output: `acceptance_gate`

### FUNCTION_18_FINAL_VERDICT

Emit exactly one of `PASS`, `FAIL`, `PARTIAL`, `UNKNOWN`.

Output: `final_verdict`

## Output Contract

```yaml
intent_vector: string
verified_atoms: list
unsupported_atoms: list
causal_graph: object
validation_gates: list
failed_gates: list
action_steps: list
verification_steps: list
confidence_score: number
quality_score: number
final_verdict: PASS | FAIL | PARTIAL | UNKNOWN
```

## Final Gate

`PASS` is allowed only when all evidence links exist:

- intent evidence
- atom evidence
- gate evidence
- counterfactual evidence
- action evidence
- verification evidence
- self-audit evidence

If any link is missing, the maximum verdict is `PARTIAL`. Any verdict token
outside the closed set `{PASS, FAIL, PARTIAL, UNKNOWN}` is rejected; tokens
such as `ship it` or `green enough` are forbidden by construction.

## Blocked Claims

The following claim boundary is reproduced verbatim from Issue #1136:

- This kernel is not a cognitive model of the brain.
- This kernel is not scientific validation.
- This kernel is not runtime correctness proof.
- This kernel does not close SecondOrderStabilityAudit, Forman-Ricci provenance, or release scorecard blockers.

## Acceptance Criteria

- Human-readable kernel document exists.
- Machine-readable governance data exists.
- Strict schema rejects any verdict outside `{PASS, FAIL, PARTIAL, UNKNOWN}`.
- Commit acceptor binds the diff to evidence and rollback.
- Same-SHA CI must be green before merge.
- PR must link Issue #1136.
