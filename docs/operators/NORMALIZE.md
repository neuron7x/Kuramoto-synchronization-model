<!-- Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab) -->
<!-- SPDX-License-Identifier: MIT -->

# Operator: Normalize

## Definition

**Normalize** means to transform heterogeneous data, scores, units, labels, or state fields into a shared scale or canonical representation while preserving provenance and reversibility constraints.

Ukrainian operational definition:

```text
Нормалізувати — привести дані до єдиного масштабу або канонічної форми так, щоб порівняння стало валідним, а походження, межі та втрати інформації залишились явними.
```

## Operator Form

```text
raw_values + scale_contract + provenance_record
→ normalization_operation
→ normalized_values + normalization_metadata + loss_report
```

## Purpose

Normalization is the scale-alignment operator of the CME loop. It makes comparison possible without pretending that different units, score ranges, schemas, or evidence qualities are naturally equivalent.

## Required Inputs

```text
raw_values
source_units_or_domains
scale_contract
allowed_range
missing_value_policy
provenance_record
reversibility_or_loss_policy
```

## Required Outputs

```text
normalized_values
normalization_metadata
range_report
loss_report
provenance_link
validation_ready_state
```

## Acceptance Gates

```text
No normalization without declaring the target scale.
No cross-source comparison without provenance.
No silent clipping.
No missing-value coercion without policy.
No irreversible transform without loss report.
No normalized metric promoted as physical measurement unless independently validated.
```

## Failure Modes

```text
different units are mixed as if equivalent
scores are scaled without preserving source meaning
outliers are clipped silently
missing values become false zeros
normalization hides uncertainty
normalized proxy is treated as ground truth
```

## Status Discipline

```text
S0_REPO_FACT   operator spec exists in repo
S1_TESTED      normalization commands executed and evidence persisted
S5_PROXY       normalized scores are operational comparison aids
```

Until commands execute and evidence is persisted, this operator remains `S0_REPO_FACT + S5_PROXY`, not `S1_TESTED`.

## Minimal Validation

```bash
python tools/research/validate_operator_contract.py docs/operators/normalize_operator.json
python -m pytest tests/research/test_validate_normalize_operator_contracts.py -q
```

## Next Normalization Target

Bind this operator to CME quality scores:

```text
raw_gate_scores → shared 0..1 scale + provenance + loss report → benchmark-ready metric set
```

Normalization is not cleaning. It is scale discipline. Cleaning without scale discipline is just data laundering with better posture.
