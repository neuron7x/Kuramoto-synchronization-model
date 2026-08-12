# Company Value Functions

Status: normative engineering governance.
Scope: repository-wide engineering, security, evidence, CI, release, and claim decisions.

This repository is not affiliated with OpenAI. OpenAI is used only as a public benchmark for company-grade safety-oriented rigor: mission-first benefit, safety before deployment, technical leadership, cooperative auditability, and continuous evaluation.

## First principle

A value is not a slogan. A value is an optimization target with a falsifier.

In this repository every company-level value must compile into:

```text
value -> measurable invariant -> evidence surface -> automated verdict -> regression test -> self-test
```

If any link is missing, the value is decorative and must not be counted as quality.

## Decision rule

The machine-readable source of truth is:

```text
data/governance/company_value_functions.json
```

A change is acceptable only when:

1. hard constraints are evaluated before aggregate score;
2. missing evidence fails closed;
3. unmeasured success claims are forbidden;
4. green-by-vacuum is forbidden;
5. total value-function score is at least 0.92;
6. each individual value score is at least 0.80;
7. every value has at least three measurable invariants, evidence surfaces, score inputs, and failure modes;
8. every evidence surface exists in the repository;
9. every hard constraint has an executable evidence surface and a CI workflow surface;
10. the validator proves its own falsifiers through `--self-test`.

## Value functions

| ID | Function | Operational meaning |
|---|---|---|
| VF-01 | Safety before capability | Security, dependency, misuse, and fail-closed gates dominate speed or capability claims. |
| VF-02 | Truthfulness over presentation | Green checks are valid only when they measure the relevant risk surface. |
| VF-03 | User and operator value | Every change must reduce uncertainty, recovery cost, or decision error. |
| VF-04 | Reproducibility and provenance | Results must be reconstructable from declared inputs, locks, and hashes. |
| VF-05 | Technical leadership through falsification | Leadership means stronger falsifiers, not faster claim expansion. |
| VF-06 | Cooperative auditability | An external reviewer can reconstruct what changed, why, and how failure is detected. |
| VF-07 | Minimal power concentration in automation | Automation emits verdicts; the human falsifier keeps override authority. |

## Enforcement

Validator:

```text
tools/governance/check_company_value_functions.py --self-test
```

Regression tests:

```text
tests/governance/test_company_value_functions.py
```

CI workflow:

```text
.github/workflows/company-value-functions.yml
```

## Non-negotiable failure classes

The value-function gate must reject:

- weight drift away from a normalized value function;
- disabling fail-closed policy;
- value functions without executable evidence;
- hard constraints without CI evidence;
- references to missing evidence surfaces;
- value functions without failure modes;
- validators that cannot prove their own negative controls;
- soft policy hidden as prose;
- green-by-vacuum;
- claims without measurable evidence;
- automation that cannot be reviewed by a competent external human.

## Practical interpretation

This layer does not make the repository look more serious. It makes future changes less able to fake seriousness.

A company-grade system is not one with more badges. It is one where the path from mission to CI failure is short, deterministic, and hard to bypass.
