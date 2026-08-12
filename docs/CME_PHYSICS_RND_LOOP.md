<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# CME Physics-Grade R&D Loop

Operational contract for running GeoSync through a constraint-first, verifier-first, benchmark-first R&D loop without inflating research claims.

This document does not promote GeoSync to measured, predictive, AGI, cognitive, therapeutic, or physics-proven status. It defines a disciplined loop for improving the repository as research software.

## Boundary

CME means **Claim-governed Mechanism Engineering** inside this repository.

Allowed scope:

```text
contracts
schemas
tests
benchmarks
CLI/API smoke paths
evidence bundles
source ledgers
release verdicts
negative-result preservation
```

Forbidden scope:

```text
claim promotion by prose
physics metaphor without validation
LLM judge as final truth
proxy metric presented as physical measurement
agent count presented as cognition
release claim without persisted evidence
```

## Status Tags

```text
S0_REPO_FACT      present in repository files
S1_TESTED         verified by command, test, CLI, API, benchmark, or schema gate
S2_LITERATURE     supported by canonical literature or official technical source
S5_PROXY          implemented as operational heuristic or proxy
S6_SPECULATIVE    research hypothesis only
X_FORBIDDEN       blocked by claim governance
```

## First Missing Condition

The current repository has strong claim-boundary documents, but it needs a single machine-readable CME iteration contract that tells agents exactly what to improve, which files to touch, what commands prove it, and when the iteration fails.

Until that contract exists and validates, any grand multi-agent loop is only a persuasive checklist. Humanity invented checklists and then immediately started worshipping them. This repository should not.

## Agent Orchestration

| Agent | Role | Output | Gate |
| --- | --- | --- | --- |
| Principal Architect | Map subsystem boundary and contracts | architecture delta | every module has purpose and file path |
| Physics Anchor | Convert physics/SciML practice into software gates | source ledger and limitations | no fake physics claim |
| Reverse Planner | Derive first missing condition | iteration contract | exactly one first action |
| Implementation | Patch code/docs/tests minimally | files and tests | no untested behavior |
| Verifier | Execute gates and record evidence | validation report | every PASS has command evidence |
| Red Team | Break claims, schemas, docs, CLI, benchmark | falsification report | at least one meaningful weakness |
| Benchmark | Compare baseline and ablations | benchmark result | no fake human evaluation |
| Productization | Make run path usable | quickstart/usage | one-command demo/test path |
| Release Manager | Package honest release surface | verdict and changelog | no unsupported claim |

## Iteration Rule

Every iteration must collapse to:

```text
intent
final_state
first_missing_condition
agent_plan
files_to_create_modify
implementation_tasks
validation_commands
benchmark_ablation
failure_modes
verdict_criteria
next_cycle
```

If this shape fails validation, the iteration fails before any claim or roadmap can pretend to be operational.

## Physics-to-Engineering Translation

The physics/SciML import is methodological, not metaphysical.

| Anchor | Engineering translation | GeoSync/CME gate |
| --- | --- | --- |
| Constraint-informed modeling | declare invariants before generation | invariant and forbidden-claim checks |
| Mechanism plus residual | deterministic core first, learned/proxy residual second | explicit module role and status tag |
| Neural/operator thinking | state transformation over families, not one-off examples | input/output contract and replay path |
| Differentiable/runtime thinking | expose trajectory, logs, gradients where valid | evidence bundle with commands and artifacts |
| Scientific backend discipline | typed contracts and scalable validation | pytest, mypy, ruff, schema validation, benchmark |

## Trajectory Trace Contract

Role 2 adds a persisted trace contract for one CME state transformation:

```text
state_t
operation_t
candidate_t
score_t
decision_t
artifact_delta_t
rollback_condition_t
state_t_plus_1
```

Repository locations:

```text
schemas/cme_trajectory_trace.schema.json
data/cme_trajectory_trace_example.json
tools/research/record_cme_trajectory_trace.py
tests/test_cme_trajectory_trace_schema.py
```

The trace contract prevents a final artifact from pretending to explain the process that created it. A CME iteration is only trajectory-aware when the transformation path is persisted and validated.

Trajectory records remain `S5_PROXY` until validation commands are executed and their outputs are preserved as evidence.

## Validation Surface

The loop is admissible only if the machine-readable iteration contract validates with:

```bash
python tools/research/validate_cme_iteration_contract.py docs/CME_ITERATION_0001.json
```

The Role 2 trajectory trace contract validates with:

```bash
python tools/research/record_cme_trajectory_trace.py data/cme_trajectory_trace_example.json
python -m pytest tests/test_cme_trajectory_trace_schema.py -q
```

Recommended full local gate:

```bash
python -m pytest -q
mypy --strict
ruff check .
python tools/research/validate_cme_iteration_contract.py docs/CME_ITERATION_0001.json
python tools/research/record_cme_trajectory_trace.py data/cme_trajectory_trace_example.json
```

## Release Honesty

A CME iteration may report `PASS` only when the validation command exits zero and the evidence path is recorded.

If validation cannot be run in the current environment, the status is:

```text
S0_REPO_FACT + S5_PROXY
```

not:

```text
S1_TESTED
```

A good repository can survive this honesty. A fragile one needs marketing, which is how software gets haunted.
