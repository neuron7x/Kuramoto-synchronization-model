<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# Operator: Validate

## Definition

**Validate** means to check whether an artifact, state transition, output, schema, claim, or runtime result matches explicit expectations before it can be promoted.

Ukrainian operational definition:

```text
Валідувати — перевірити відповідність результатів очікуванням через явні критерії, схему, команду, тест, поріг або verdict, не через довіру до формулювання.
```

## Operator Form

```text
candidate_result + expected_contract + validation_method
→ validation_operation
→ pass_fail_decision + evidence_record + next_action
```

## Purpose

Validation is the uncertainty-collapse operator of the CME loop. It prevents candidate outputs, generated patches, benchmark numbers, or claim text from becoming accepted project state without an observable check.

## Required Inputs

```text
candidate_result
expected_contract
acceptance_criteria
validation_method
failure_policy
evidence_destination
```

## Required Outputs

```text
validation_report
pass_fail_decision
error_list
evidence_record
promotion_or_rejection
next_action
```

## Acceptance Gates

```text
No validation without explicit expectations.
No PASS without a command, schema, threshold, or reviewed verdict.
No schema validation without reporting failed fields.
No benchmark validation without baseline or threshold.
No claim validation without status tag.
No S1_TESTED status without persisted evidence.
```

## Failure Modes

```text
expectations are implicit
validator only checks file existence
LLM judgement is treated as final truth
proxy score is promoted as physical measurement
failed validation produces no next action
PASS is written without evidence
```

## Status Discipline

```text
S0_REPO_FACT   operator spec exists in repo
S1_TESTED      validation commands executed and evidence persisted
S5_PROXY       quality is estimated through operational proxy metrics
```

Until commands execute and evidence is persisted, this operator remains `S0_REPO_FACT + S5_PROXY`, not `S1_TESTED`.

## Minimal Validation

```bash
python tools/research/validate_operator_contract.py docs/operators/validate_operator.json
python -m pytest tests/research/test_validate_normalize_operator_contracts.py -q
```

## Next Validation Target

Bind this operator to the CME trajectory trace:

```text
trajectory_trace_json → schema + semantic validator → validation_report → evidence_bundle → VERDICT
```

A result that cannot be validated is not a result. It is just a confident noise object wearing a lab coat.
