# Validation Plan

## Verification: system built correctly

- JSON schema validation.
- YAML syntax validation.
- Unit consistency.
- Rule-version immutability.
- Golden test vectors.
- Boundary tests.
- Missingness tests.
- Deterministic rerun tests.
- Critical invalid input fail-closed tests.

## Validation: system solves the right task

- Analytical comparison of sensor values against reference methods.
- Error, bias, and limits-of-agreement assessment.
- Calibration curves.
- Biological validation against independent expected states.
- Evidence-grade preservation per feature.
- Clinical validation only after appropriate ethics, lifecycle, cybersecurity, privacy, and regulatory controls.

## Acceptance criteria

| Area | Criterion |
| --- | --- |
| Determinism | 100% identical `run_hash` on rerun with same input/rules/engine |
| Traceability | 100% runs include provenance |
| Fail-closed | 100% critical invalid inputs return `BLACK_INVALID` |
| Explainability | At least 95% decisions linked to rule IDs |
| Safety | No autonomous high-risk clinical action |

## Calibration order

The CI/CD path starts with a **local sandbox adversarial auditor**, not a networked microservice. This keeps the reverse loop hermetic, deterministic, and reproducible while the attack vocabulary is calibrated. Promotion to a service-level auditor is allowed only after the local sandbox, property-based invariant tests, and dynamic traceability checks are stable.

Recommended order:

1. Static gate-based validation: strict numeric schemas and deterministic JSON hashing.
2. Property-based invariant testing: bounded Hypothesis campaigns for corrupted math (`NaN`, `Inf`, out-of-range values) and hash canonicalization.
3. Local adversarial sandbox: deterministic Creator/Verifier campaign with committed golden vectors.
4. Mutation testing and external adversarial orchestration after the above are stable.
